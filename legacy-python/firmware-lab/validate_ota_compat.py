"""Run exact installed dispatcher AND original OTA writer with Flash mocked.

No HID APIs. Verify every transported byte, buffer boundary and final marker.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import validate_session as session
import validate_codec
from validate_bitmap_space import BASE,ROOT,BitmapMachine,HELPER,RENDERERS
from validate_ram_stream import FB,SP
from unicorn.arm_const import *
sys.path.insert(0,str(ROOT))
from references.ota_chunks import plan


def uart(command,data):
    return b'BLT+OTA+'+command+b'#'+len(data).to_bytes(2,'big')+data+b'\r\n'


class OtaMachine(session.Machine):
    def __init__(self,image,entries):
        super().__init__(image,entries)
        self.spi=bytearray(b'\xff'*0x10000);self.erases=[];self.markers=[];self.writes=[]
        self.data_calls=0

    def write(self,uc,access,address,size,value,user):
        if 0x20001340<=address and address+size<=0x200017f0:return
        super().write(uc,access,address,size,value,user)

    def code(self,uc,address,size,user):
        if address in (0x080060a4,0x08006116):
            assert not self.owned()
            if address==0x08006116:self.data_calls+=1
            self.instructions+=1;self.trace.append(hex(address));return
        if address==0x08008656:
            self.erases.append(tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1)))
            self.result();return
        if address==0x080082ec:
            src,dst,n=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
            assert src==0x20001340 and n==1024 and 0x20000<=dst<=0x2fc00
            data=bytes(uc.mem_read(src,n));self.spi[dst-0x20000:dst-0x20000+n]=data
            self.writes.append((dst,n));self.result();return
        if address==0x08009262:
            self.markers.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
            self.result();return
        if address==0x08008bb4:
            self.result();return
        super().code(uc,address,size,user)


def verify_graphics(original,image):
    themes=0
    for entry in RENDERERS:
        for field in (1,2,6):
            a=BitmapMachine(original);b=BitmapMachine(image)
            word=field*0x01010101
            assert a.invoke(entry,(word,)*4,word)==b.invoke(entry,(word,)*4,word)
            assert a.frames==b.frames and len(b.frames)==1
            themes+=1
    # All 1024 source bytes are restored by the actual copy entry.
    m=BitmapMachine(image)
    assert m.invoke(HELPER,(0x0800eaec,0,0,0))==original[0x0800eaec-BASE:0x0800eeec-BASE]
    # Each byte of the complete 8-entry 6x32 glyph table is drawn through
    # the original rasterizer, including both sides of the transformed span.
    n=0
    for index in range(8):
        source=0x0800f5b4+index*24
        for invert in (0,1):
            old=BitmapMachine(original);new=BitmapMachine(image)
            # Fifth/sixth arguments are stack words at entry SP/SP+4.
            for machine in (old,new):
                machine.uc.mem_write(SP+4,struct.pack('<I',invert))
            # invoke's stack fixture repeats its word. Write the sixth argument
            # through a small subclass so the fixture can set both words.
            def run(machine):
                machine.uc.mem_write(SP,struct.pack('<II',source,invert))
                machine.returned=False
                machine.uc.reg_write(UC_ARM_REG_SP,SP)
                from validate_ram_stream import STOP,SAVED
                machine.uc.reg_write(UC_ARM_REG_LR,STOP|1)
                for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),(2,0,6,32)):
                    machine.uc.reg_write(reg,value)
                for i,reg in enumerate(SAVED):machine.uc.reg_write(reg,0xc0010000+i)
                machine.uc.emu_start(0x080052a5,0xffffffff,count=300000)
                assert machine.returned and machine.uc.reg_read(UC_ARM_REG_SP)==SP
                assert all(machine.uc.reg_read(reg)==0xc0010000+i for i,reg in enumerate(SAVED))
                return machine.framebuffer()
            assert run(old)==run(new)
            n+=1
    # Equivalent weak interrupt loop: both stay at the same entry, no writes.
    states=[]
    for raw in (original,image):
        machine=BitmapMachine(raw)
        regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_APSR)
        before=tuple(machine.uc.reg_read(r) for r in regs)
        machine.uc.emu_start(0x0800fed5,0xffffffff,count=64)
        assert machine.uc.reg_read(UC_ARM_REG_PC)==0x0800fed4
        assert tuple(machine.uc.reg_read(r) for r in regs)==before
        states.append(machine.uc.reg_read(UC_ARM_REG_PC))
    return dict(background_bytes=1024,glyph_cases=n,theme_cases=themes,weak_loop_same_pc=states)


def main():
    original,image,entries,layout=validate_codec.build()
    _,old,old_entries,*_=session.build()
    assert hashlib.sha256(old).hexdigest()=='fe18bc92afd790cd2f2248b98091033f8d8d76cac674b60540cbf5c644f389ae'
    old_results=[];new_results=[]
    for first in range(256):
        for raw,ent,results in ((old,old_entries,old_results),(image,entries,new_results)):
            machine=session.Machine(raw,ent)
            machine.receive(uart(b'DAT',bytes([first])))
            results.append(bool(machine.forwarded))
    assert old_results==[True]*128+[False]*128 and all(new_results)
    chunks=plan(image);m=OtaMachine(old,old_entries)
    m.receive(uart(b'STA',len(image).to_bytes(4,'big')+b'\0'))
    assert m.acks[-1]==b'MCU+OTA+STA\r\n'
    assert not m.markers
    for index,(a,b) in enumerate(chunks):
        before=m.data_calls
        m.receive(uart(b'DAT',image[a:b]))
        assert m.data_calls==before+1,(index,a)
        if index<len(chunks)-1:
            assert not m.markers and m.acks[-1]==b'MCU+OTA+NXT\r\n',(index,a,b,m.acks[-1],m.markers)
    assert m.markers==[(2,len(image))] and m.acks[-1]==b'MCU+OTA+END\r\n'
    assert m.spi[:len(image)]==image
    assert m.spi[len(image):((len(image)+1023)//1024)*1024]==b'\xff'*((-len(image))%1024)
    graphics=verify_graphics(original,image)
    result=dict(candidate_sha256=hashlib.sha256(image).hexdigest(),
        installed_sha256=hashlib.sha256(old).hexdigest(),checks_passed=5,
        old_first_byte_cases=256,new_first_byte_cases=256,packets=len(chunks),bytes=len(image),
        first_byte_filter_reproduced=True,staging_byte_exact=True,marker_after_complete_only=m.markers,
        spi_writes=len(m.writes),erases=m.erases,graphics=graphics,instructions=m.instructions,
        physical_flash_access=False,device_accessed=False,
        bridge_model='USB actual payload length minus two gives UART OTA DATA byte count; static audit at 0603BCFA and 060217AC..060217F2',
        limitations=['Jieli bridge forwarding verified statically, not instruction-emulated',
                    'Absent bootloader install/copy not emulated; physical boot not proven'])
    out=ROOT/'firmware-analysis/codec-lab/ota-compat-validation.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
