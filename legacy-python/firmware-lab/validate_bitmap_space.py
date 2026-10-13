"""Offline ARM validation of space reclaimed by lossless background compression.

The combined image exists in process memory ONLY for Unicorn. No installable
firmware is written and no hardware API is used. This is not a full boot test.
"""
import hashlib
import json
import random
import re
import struct
import sys
from pathlib import Path

from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
import emulator_runtime
from unicorn import UC_HOOK_MEM_READ
from unicorn.arm_const import *

from bitmap_pack import pack, unpack
import validate_ram_stream as stream

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'references'))
from audit_pixel_patch import audit, BASE

START=0x0800AF24
END=0x0800D724
HELPER=0x0800519A
DIRECTORY=START+256
BLOB=DIRECTORY+44
FB=0x200017F0
RENDERERS=[0x080034B0,0x080035E4,0x08003710,0x080038BC,0x08003A70,
           0x08003C20,0x08003DC4,0x08003F98,0x08004138,0x080042D4]


def assemble(source,address):
    source='\n'.join(line.split('//',1)[0] for line in source.splitlines())
    return bytes(Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(source,addr=address)[0])


class BitmapMachine(stream.Machine):
    def __init__(self,image,decoder_bytes=0):
        super().__init__(image,b'\0\0')
        self.decoder_bytes=decoder_bytes
        self.asset_reads=[]
        self.uc.hook_add(UC_HOOK_MEM_READ,self.watch_asset,begin=START,end=END-1)

    def watch_asset(self,uc,access,address,size,value,_):
        if START<=address<END:self.asset_reads.append((address,size))

    def code(self,uc,address,size,user):
        if self.decoder_bytes and START<=address<END:
            assert START<=address and address+size<=START+self.decoder_bytes, 'Executed packed data'
        super().code(uc,address,size,user)

    def invoke(self,entry,args=(0,0,0,0),stack_word=0x01010101):
        self.returned=False
        self.uc.mem_write(stream.SP,struct.pack('<I',stack_word)*8)
        self.uc.reg_write(UC_ARM_REG_SP,stream.SP)
        self.uc.reg_write(UC_ARM_REG_LR,stream.STOP|1)
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):
            self.uc.reg_write(reg,value)
        for i,reg in enumerate(stream.SAVED):self.uc.reg_write(reg,0xC0010000+i)
        self.uc.emu_start(entry|1,0xFFFFFFFF,count=300000)
        assert self.returned,'Instruction bound exceeded'
        assert self.uc.reg_read(UC_ARM_REG_SP)==stream.SP,'Stack imbalance'
        for i,reg in enumerate(stream.SAVED):
            assert self.uc.reg_read(reg)==0xC0010000+i,'Callee-saved register changed'
        return self.framebuffer()


def static_references(image):
    literals=json.loads((ROOT/'firmware/evidence/literal-references.json').read_text())
    direct=[item for item in literals if int(item['instruction'],16)<START and
            START<=int(item['value'],16)<END]
    raw=[]
    for offset in range(len(image)-3):
        if START<=BASE+offset<END:continue
        value=struct.unpack_from('<I',image,offset)[0]
        if START<=value<END:
            raw.append(dict(location=hex(BASE+offset),value=hex(value),aligned=offset%4==0))
    references={int(item['literal'],16) for item in direct}
    other=[item for item in raw if int(item['location'],16) not in references]
    assert len(direct)==10
    assert {int(item['value'],16) for item in direct}==set(range(START,END,1024))
    # 0x08007BAC..0x08007BBE indexes (ASCII-32)*16 at 0x0800D724.
    # These three odd-address matches lie inside the 16-byte glyphs B/h/r.
    # The font is outside the reclaimed region and remains byte-identical.
    reviewed={0x0800D949:0x0800B8FC,0x0800DBA9:0x0800C0E0,0x0800DC49:0x0800C0E0}
    assert {int(item['location'],16):int(item['value'],16) for item in other}==reviewed
    for item in other:
        offset=int(item['location'],16)-0x0800D724
        item.update(classification='Unaligned pixel bytes in stock ASCII font',
                    glyph=chr(32+offset//16),offset_in_glyph=offset%16)
    return dict(direct_literal_loads=direct,all_byte_alignment_pointer_scan=raw,
                reviewed_font_byte_matches=other,unresolved_raw_pointer_candidates=[],
                caveat='Does not prove absence of computed pointers or unexecuted paths')


def main():
    image=(ROOT/'firmware-analysis/v137/mcu.bin').read_bytes();audit(image)
    refs=static_references(image)
    assets=[image[a-BASE:a-BASE+1024] for a in range(START,END,1024)]
    blocks=[pack(data) for data in assets]
    assert all(unpack(block)==data for block,data in zip(blocks,assets))
    positions=[BLOB]
    for block in blocks:positions.append(positions[-1]+len(block))
    packed_end=positions[-1]
    module_address=(packed_end+3)&~3
    source=Path(__file__).with_name('bitmap_unpack_thumb.s').read_text()
    for key,value in dict(ASSET_BEGIN=START,DIRECTORY=DIRECTORY,PACKED_BEGIN=BLOB,PACKED_END=packed_end).items():
        source=re.sub(r'\b'+key+r'\b',hex(value),source)
    decoder=assemble(source,START)
    assert len(decoder)<=256
    module=assemble(Path(__file__).with_name('ram_stream_thumb.s').read_text(),module_address)
    assert module_address+len(module)<=END
    branch=assemble(f'b.w {START:#x}',HELPER)
    assert len(branch)==4
    # Simulation-only image: no filesystem output of this bytearray.
    patched=bytearray(image)
    patched[START-BASE:END-BASE]=b'\xff'*(END-START)
    patched[START-BASE:START-BASE+len(decoder)]=decoder
    patched[DIRECTORY-BASE:BLOB-BASE]=struct.pack('<11I',*positions)
    patched[BLOB-BASE:packed_end-BASE]=b''.join(blocks)
    patched[module_address-BASE:module_address-BASE+len(module)]=module
    patched[HELPER-BASE:HELPER-BASE+4]=branch
    patched=bytes(patched)
    assert len(patched)==len(image)
    changes=[BASE+i for i,(a,b) in enumerate(zip(image,patched)) if a!=b]
    assert all(START<=a<END or HELPER<=a<HELPER+4 for a in changes)
    assert patched[:224]==image[:224]
    assert patched[0x5E34-0x2000:0x6318-0x2000]==image[0x5E34-0x2000:0x6318-0x2000]
    assert patched[END-BASE:]==image[END-BASE:]

    stats=[]
    for index,asset in enumerate(assets):
        address=START+index*1024
        old=BitmapMachine(image);new=BitmapMachine(patched,len(decoder))
        assert old.invoke(HELPER,(address,0,0,0))==asset
        assert new.invoke(HELPER,(address,0,0,0))==asset
        assert not new.flash_calls
        stats.append(dict(address=hex(address),original_bytes=1024,packed_bytes=len(blocks[index]),
                          original_instructions=old.instructions,decoded_instructions=new.instructions,
                          sha256=hashlib.sha256(asset).hexdigest()))

    # Raw images elsewhere in Flash, plus a RAM source, retain exact copy behavior.
    fallback=[]
    for address in (0x0800E6EC,0x0800EAEC,0x20000000):
        old=BitmapMachine(image);new=BitmapMachine(patched,len(decoder))
        assert old.invoke(HELPER,(address,0,0,0))==new.invoke(HELPER,(address,0,0,0))
        fallback.append(hex(address))

    # Run the real ten theme functions, with their actual glyph compositor and
    # flush wrapper. Only the electrical display bus is mocked by Machine.
    rendered=[]
    for entry in RENDERERS:
        for field in (1,2,6):
            old=BitmapMachine(image);new=BitmapMachine(patched,len(decoder))
            word=field*0x01010101;args=(word,)*4
            a=old.invoke(entry,args,word);b=new.invoke(entry,args,word)
            assert a==b and old.frames==new.frames and len(new.frames)==1
            assert not new.flash_calls
            rendered.append(dict(entry=hex(entry),sample_field=field,
                                 frame_sha256=hashlib.sha256(a).hexdigest(),
                                 byte_exact=True,decoded_instructions=new.instructions))

    # Malformed RLE must never exceed FB or read beyond the declared block.
    malformed=0
    rng=random.Random(0xA106)
    for index in range(36):
        variant=bytearray(patched)
        data=(bytes([127]) if index==0 else bytes([255]) if index==1 else
              bytes([255,0])*9 if index==2 else rng.randbytes(rng.randrange(1,90)))
        variant[BLOB-BASE:BLOB-BASE+len(data)]=data
        struct.pack_into('<I',variant,DIRECTORY-BASE+4,BLOB+len(data))
        machine=BitmapMachine(bytes(variant),len(decoder))
        expected=None
        try:expected=unpack(data)
        except ValueError:pass
        result=machine.invoke(HELPER,(START,0,0,0))
        assert result==(expected if expected is not None else bytes(1024))
        assert all(a>=BLOB and a+s<=BLOB+len(data) or
                   START<=a and a+s<=START+len(decoder) or
                   DIRECTORY<=a and a+s<=DIRECTORY+44 for a,s in machine.asset_reads)
        malformed+=1

    for address in (START+1,START+1023,END-1):
        machine=BitmapMachine(patched,len(decoder))
        assert machine.invoke(HELPER,(address,0,0,0))==bytes(1024)
    for first,last in ((BLOB-1,positions[1]),(BLOB,packed_end+1),
                       (positions[1],BLOB),(BLOB,BLOB)):
        variant=bytearray(patched)
        struct.pack_into('<II',variant,DIRECTORY-BASE,first,last)
        machine=BitmapMachine(bytes(variant),len(decoder))
        assert machine.invoke(HELPER,(START,0,0,0))==bytes(1024)

    previous=(ROOT/'firmware-analysis/v104/mcu.bin').read_bytes()
    assert hashlib.sha256(previous).hexdigest()=='5d32e35f3758385e1e99d08c8ae3960e19f3e3fe32d4916fc9c6ff872c1074b9'
    previous_assets=previous[START-BASE-4:END-BASE-4]

    # Re-run every ARM stream-core check at the reclaimed real-image address.
    old_module,old_entries=stream.MODULE,stream.ENTRIES
    try:
        stream.MODULE=module_address
        stream.ENTRIES={name:module_address+offset for name,offset in
                        [('begin',0),('data',4),('end',8),('gate',12)]}
        stream_result=stream.validate(patched,module)
    finally:stream.MODULE,stream.ENTRIES=old_module,old_entries

    report=dict(status='OFFLINE_SPACE_CANDIDATE_VALIDATED_NOT_INSTALLABLE',
        original_sha256=hashlib.sha256(image).hexdigest(),original_image_bytes=len(image),
        original_resource_range=[hex(START),hex(END)],original_resource_bytes=END-START,
        compressed_bytes=sum(map(len,blocks)),decoder_bytes=len(decoder),decoder_reserved_bytes=256,
        directory_bytes=44,decoder_address=hex(START),copy_helper_hook=hex(HELPER),
        packed_end_exclusive=hex(packed_end),stream_core_address=hex(module_address),
        stream_core_bytes=len(module),remaining_contiguous_bytes=END-module_address-len(module),
        remaining_range=[hex(module_address+len(module)),hex(END)],
        original_diy_and_ota_unchanged=True,vector_table_unchanged=True,
        image_size_unchanged=True,assets=stats,static_references=refs,
        stock_theme_execution=rendered,raw_copy_fallbacks=fallback,
        malformed_cases=malformed,invalid_source_or_directory_cases=7,
        v104_background_bytes_identical=previous_assets==b''.join(assets),
        v104_asset_base=hex(START-4),v104_executable_patch_tested=False,
        stream_core_relocated_validation=stream_result,
        firmware_file_generated=False,device_accessed=False,
        limitations=['No complete firmware boot, interrupt, mode-transition or peripheral timing test',
                     'Static reference scan does not rule out every computed or indirect reference',
                     'Copy helper ARM hook and packed layout exist only in the emulator',
                     'Stream dispatch, lease, capability and recovery integration remain incomplete',
                     'No measured decoder CPU time or power consumption on the actual MCU',
                     'Actual silicon capacity, bootloader behavior and image acceptance still unverified'])
    output=ROOT/'firmware-analysis/bitmap-space-lab';output.mkdir(exist_ok=True)
    (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (output/'bitmap-unpack.thumb').write_bytes(decoder)
    (output/'ram-stream-relocated.thumb').write_bytes(module)
    # Store each compressed asset as an analysis resource, never a combined image.
    (output/'stock-backgrounds.rle').write_bytes(b''.join(blocks))
    print(json.dumps({k:v for k,v in report.items() if k not in
                     ('assets','static_references','stock_theme_execution','stream_core_relocated_validation')},indent=2))
    print(json.dumps(dict(stock_theme_cases=len(rendered),stream_checks=stream_result['checks_passed'],
                          stream_instructions=stream_result['arm_instructions'],
                          forbidden_flash_calls=stream_result['forbidden_flash_calls'])))


if __name__=='__main__':main()
