"""Execute patched stock UART parser/dispatcher and session hooks in Unicorn.

All firmware composition is in process memory. Only analysis modules and reports
are written. No device APIs, no full firmware output, no update container.
"""
from collections import deque
import hashlib
import json
from pathlib import Path
import random
import struct

import emulator_runtime
from unicorn.arm_const import *
from unicorn import UC_HOOK_MEM_READ
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
import validate_ram_stream as core
from validate_bitmap_space import (ROOT,BASE,START,END,HELPER,DIRECTORY,BLOB,
                                   assemble,BitmapMachine,static_references)
from audit_pixel_patch import audit
from bitmap_pack import pack
from session_packets import *

LEASE=0x200017C0
RX=0x200022E0
INDEX=0x2000033A
MODE=0x20002A20
TICK=0x20002AD8
MAGIC=0x324C5048


def build():
    image=(ROOT/'firmware-analysis/v137/mcu.bin').read_bytes();audit(image)
    static_references(image)
    blocks=[pack(image[a-BASE:a-BASE+1024]) for a in range(START,END,1024)]
    positions=[BLOB]
    for block in blocks:positions.append(positions[-1]+len(block))
    text=Path(__file__).with_name('bitmap_unpack_thumb.s').read_text()
    for key,value in dict(ASSET_BEGIN=START,DIRECTORY=DIRECTORY,PACKED_BEGIN=BLOB,PACKED_END=positions[-1]).items():
        text=text.replace(key,hex(value))
    decoder=assemble(text,START);assert len(decoder)<=256
    core_address=(positions[-1]+3)&~3
    source=Path(__file__).with_name('ram_stream_thumb.s').read_text()
    # Lease hooks own access; retain the real mode so the stock settings saver
    # cannot persist a temporary streaming mode. Stock protocol remains intact.
    a='    ldrb r6, [r5, #0x1c]\n    cmp r6, #3\n    bne begin_bad\n'
    b='    ldr r3, =0x20002a20\n    ldrb r3, [r3]\n    cmp r3, #3\n    bne data_bad\n'
    assert a in source and b in source
    source=source.replace(a,'').replace(b,'').replace('movs r0, #0x24','movs r0, #0x25')
    receiver=assemble(source,core_address)
    address=(core_address+len(receiver)+3)&~3
    source=Path(__file__).with_name('session_thumb.s').read_text()
    for key,value in dict(LEASE=LEASE,CORE_BEGIN=core_address|1,CORE_DATA=(core_address+4)|1).items():
        source=source.replace(key,hex(value))
    session=assemble(source,address)
    assert address+len(session)<=END
    entries={name:address+4*i for i,name in enumerate(
        ['dispatch','service','timer','initialize','scheduler0','scheduler1','scheduler2',
         'scheduler3','scheduler4','rx_guard','loop_guard','save_guard'])}
    patched=bytearray(image)
    patched[START-BASE:END-BASE]=b'\xff'*(END-START)
    patched[START-BASE:START-BASE+len(decoder)]=decoder
    patched[DIRECTORY-BASE:BLOB-BASE]=struct.pack('<11I',*positions)
    patched[BLOB-BASE:positions[-1]-BASE]=b''.join(blocks)
    patched[core_address-BASE:core_address-BASE+len(receiver)]=receiver
    patched[address-BASE:address-BASE+len(session)]=session
    sites=[(HELPER,START,'b.w',None),
           (0x08006BE6,entries['dispatch'],'bl',0x0800694C),
           (0x08008C7E,entries['service'],'bl',0x08006BDC),
           (0x0800F292,entries['timer'],'bl',0x0800A5E4),
           (0x08008BCE,entries['initialize'],'b.w',None),
           (0x0800886E,entries['rx_guard'],'b.w',None),
           (0x08008BF4,entries['loop_guard'],'b.w',None),
           (0x08008CC2,entries['save_guard'],'bl',0x0800919C)]
    sites.extend((site,entries[f'scheduler{i}'],'bl',original) for i,(site,original) in enumerate(
        [(0x08008C82,0x0800A2DA),(0x08008C86,0x0800A31E),(0x08008C8A,0x0800A35A),
         (0x08008C92,0x0800A3AC),(0x08008C9A,0x0800A3D2)]))
    dis=Cs(CS_ARCH_ARM,CS_MODE_THUMB);hooks=[]
    for site,target,op,original in sites:
        before=image[site-BASE:site-BASE+4]
        if original:
            ins=next(dis.disasm(before,site))
            assert ins.mnemonic=='bl' and int(ins.op_str[1:],16)==original
        branch=assemble(f'{op} {target:#x}',site)
        assert len(branch)==4
        ins=next(dis.disasm(branch,site));assert int(ins.op_str[1:],16)==target
        patched[site-BASE:site-BASE+4]=branch
        hooks.append(dict(address=hex(site),original=before.hex(),replacement=branch.hex(),target=hex(target)))
    assert image[0x8BCE-0x2000:0x8BD2-0x2000].hex()=='2de9fc47'
    assert image[0x886E-0x2000:0x8872-0x2000].hex()=='2c540888'
    assert image[0x8BF4-0x2000:0x8BF8-0x2000].hex()=='3a4d2868'
    assert len(image)==len(patched) and patched[:224]==image[:224]
    assert patched[0x5E34-0x2000:0x6318-0x2000]==image[0x5E34-0x2000:0x6318-0x2000]
    assert all(a==b or START<=BASE+i<END or any(s<=BASE+i<s+4 for s,_,_,_ in sites)
               for i,(a,b) in enumerate(zip(image,patched)))
    return image,bytes(patched),entries,dict(core_address=hex(core_address),core_bytes=len(receiver),
        session_address=hex(address),session_bytes=len(session),decoder_bytes=len(decoder),
        remaining_bytes=END-address-len(session),hooks=hooks),receiver,session


class Machine(BitmapMachine):
    def __init__(self,image,entries):
        super().__init__(image)
        self.entries=entries;self.queue=deque();self.forwarded=[];self.parser_calls=0
        self.uc.mem_write(core.RAM,bytes(0x4000))
        self.uc.mem_write(INDEX,b'\xfd\xff')
        self.uc.mem_write(MODE,b'\x02')
        self.uc.mem_write(core.FB,core.SENTINEL)
        self.uc.mem_write(0x20002ABC,b'\x01')
        self.uc.mem_write(0x20002AEC,struct.pack('<I',1700000000))
        self.uc.mem_write(0x20002AE4,b'\x01'*8)
        self.initialization_stopped=False
        self.cycle_stop=False
        self.continuation_stop=None

    def write(self,uc,access,address,size,value,user):
        allowed=[(core.STATE,core.STATE+24),(LEASE,LEASE+32),(core.FB,core.FB+1024),
                 (core.STAGE,core.STAGE+1024),(RX,RX+400),(INDEX,INDEX+2),
                 (0x20002A04,0x20002B58),(0x20003200,core.SP)]
        assert any(lo<=address and address+size<=hi for lo,hi in allowed),f'Unexpected write {address:#x}+{size}; PC={uc.reg_read(UC_ARM_REG_PC):#x}; SP={uc.reg_read(UC_ARM_REG_SP):#x}; trace={list(self.trace)}'

    def result(self,value=0):
        self.peripheral_return();self.uc.reg_write(UC_ARM_REG_R0,value)

    def invoke(self,*args,**kwargs):
        try:return super().invoke(*args,**kwargs)
        except Exception as error:
            raise RuntimeError(f'PC={self.uc.reg_read(UC_ARM_REG_PC):#x}; SP={self.uc.reg_read(UC_ARM_REG_SP):#x}; trace={list(self.trace)}') from error

    def code(self,uc,address,size,user):
        if address==self.continuation_stop:
            self.returned=True;uc.emu_stop();return
        if self.cycle_stop and address==0x08008BF4:
            self.returned=True;uc.emu_stop();return
        if address==0x08008738:
            self.result(len(self.queue));return
        if address==0x08008756:
            assert self.queue;self.result(self.queue.popleft());return
        if address==0x0800A5B6:
            self.result(1);return
        if address in (0x0800A5E4,0x08009468):
            self.result();return
        if address==0x08008BD2:
            # Stop after the actual replaced init entry and displaced prologue.
            sp=uc.reg_read(UC_ARM_REG_SP)
            words=struct.unpack('<10I',bytes(uc.mem_read(sp,40)))
            uc.reg_write(UC_ARM_REG_SP,sp+40);uc.reg_write(UC_ARM_REG_PC,words[-1])
            self.initialization_stopped=True;return
        # These tests observe forwarding into the stock handler, without doing
        # its Flash I/O or asking real power/reset hardware to change state.
        if address in (0x08005E34,0x08005ED6,0x0800606E,0x080060A4,
                       0x08006116,0x0800626A,0x0800628A,0x08006486,
                       0x0800672C,0x080066BA,0x080066E8):
            self.forwarded.append((address,self.owned()))
            assert not self.owned(),'Stock mutator reached while display owned'
            self.result();return
        core.Machine.code(self,uc,address,size,user)

    def owned(self):
        return bytes(self.uc.mem_read(LEASE,8))==struct.pack('<II',MAGIC,MAGIC^0xffffffff)

    def value(self,offset):return struct.unpack('<I',bytes(self.uc.mem_read(LEASE+offset,4)))[0]
    def time(self,tick):self.uc.mem_write(LEASE+8,struct.pack('<I',tick&0xffffffff))

    def receive(self,data):
        self.queue.extend(data)
        while self.queue:
            before=len(self.queue)
            self.invoke(0x08006BDC)
            self.parser_calls+=1
            if len(self.queue)==before:break

    def send(self,body):self.receive(uart_packet(body))
    def service(self):self.invoke(self.entries['service'])

    def main_cycle(self):
        # Enter immediately after the original startup-overlay section. The
        # next iteration boundary stops us before its (separately tested) hook.
        self.cycle_stop=True;self.returned=False
        self.uc.reg_write(UC_ARM_REG_SP,core.SP-40)
        self.uc.reg_write(UC_ARM_REG_R4,0x20002A04)
        self.uc.emu_start(0x08008C7F,0xffffffff,count=300000)
        self.cycle_stop=False
        assert self.returned and self.uc.reg_read(UC_ARM_REG_SP)==core.SP-40

    def loop_guard(self,target):
        self.continuation_stop=target;self.returned=False
        self.uc.reg_write(UC_ARM_REG_SP,core.SP-40)
        self.uc.reg_write(UC_ARM_REG_R4,0x20002A04)
        self.uc.emu_start(0x08008BF5,0xffffffff,count=300000)
        self.continuation_stop=None
        assert self.returned and self.uc.reg_read(UC_ARM_REG_SP)==core.SP-40


def check(image,entries):
    checks=[];machines=[]
    def fresh():
        m=Machine(image,entries);machines.append(m);return m
    def acquire(m,sid=0x12345678):m.send(payload(ACQUIRE,sid));assert m.owned();return sid
    def frame(m,sid,number,pixels):
        m.send(payload(BEGIN,sid,number))
        data=pixels+binascii.crc_hqx(pixels,0).to_bytes(2,'big')
        packets=[payload(DATA,sid,number,i,data[o:o+37]) for i,o in enumerate(range(0,len(data),37))]
        old=m.framebuffer()
        for i,p in enumerate(packets):
            m.send(p)
            if i<len(packets)-1:assert m.framebuffer()==old
        assert m.framebuffer()==pixels
        return packets

    m=fresh()
    # Reproduces the monitored IT-block failure seen with Unicorn 2.1.4.
    m.invoke(0x08008940,(core.FB,128,0,0))
    assert m.framebuffer()==bytes(128)+core.SENTINEL[128:]
    m.uc.mem_write(RX,b'12345678');m.uc.mem_write(RX+16,b'12345678')
    m.invoke(0x0800932C,(RX,RX+16,8,0))
    assert m.uc.reg_read(UC_ARM_REG_R0)==0
    checks.append('pinned emulator executes real monitored memset/memcmp IT blocks with correct bounds and return')

    m=fresh();m.uc.mem_write(LEASE,b'\xa5'*32);m.invoke(0x08008BCE)
    assert m.initialization_stopped and bytes(m.uc.mem_read(LEASE,32))==bytes(32)
    checks.append('actual init hook clears shared lease state before original startup continuation')

    m=fresh();sid=acquire(m);assert bytes(m.uc.mem_read(MODE,1))==b'\x02'
    first=bytes(range(256))*4
    parts=frame(m,sid,1,first);assert len(m.frames)==1
    m.send(parts[-1]);assert len(m.frames)==1
    frame(m,sid,2,bytes(255-x for x in first));assert len(m.frames)==2
    checks.append('real UART parser -> patched dispatcher -> bounded receiver -> stock copy/flush; two atomic frames and final retry')

    # Heartbeats have no image commit or persistent writes. Test timer wrap too.
    m=fresh();sid=acquire(m)
    for tick in range(500,10001,500):
        m.time(tick);m.send(payload(HEARTBEAT,sid));m.service();assert m.owned()
    assert not m.frames and not m.flash_calls
    m.time(0xfffffff0);m.uc.mem_write(LEASE+12,struct.pack('<I',0xfffffff0))
    m.time(20);m.service();assert m.owned()
    checks.append('idle heartbeats hold lease without frames; unsigned monotonic counter wrap')

    m=fresh();sid=acquire(m);m.uc.mem_write(TICK,struct.pack('<I',998))
    for _ in range(3):m.invoke(0x0800F27E)
    assert m.value(8)==3 and struct.unpack('<I',bytes(m.uc.mem_read(TICK,4)))[0]==1
    checks.append('real timer ISR crosses stock 1000-tick reset; separate lease counter continues')

    m=fresh();sid=acquire(m);frame(m,sid,1,first)
    before=m.framebuffer()
    for command in (b'+STR+LRC',b'+STR+MSG',b'+STR+DIY',b'+OED+SET',b'+INT+USB',b'+FFT+EGY'):
        m.receive(b'BLT'+command+b'#\x00\x04test\r\n')
    m.receive(b'BLT+DIY+STA#\x00\x04\x00\x00\x04\x28\r\n')
    m.receive(b'BLT+DIY+DAT#\x00\x05\0\0\0\0a\r\n')
    m.receive(b'BLT+DIY+END#\x00\x00\r\n')
    for i in range(5):m.invoke(entries[f'scheduler{i}'])
    assert m.framebuffer()==before and not m.forwarded
    m.receive(b'BLT+COM+RDY\r\n');assert m.owned()
    checks.append('stock text/mode/upload/draw schedulers excluded; communication-ready still passes')

    m=fresh();acquire(m);before=m.framebuffer()
    m.uc.mem_write(0x20002A08,b'\x01')
    m.uc.mem_write(0x20002A35,b'\xff')
    for _ in range(3):m.main_cycle()
    assert m.owned() and m.framebuffer()==before and not m.flash_calls
    assert bytes(m.uc.mem_read(0x20002A35,1))==b'\xff'
    checks.append('actual main-loop body defers a pending settings save while owned; no persistent writer reached')

    m=fresh();acquire(m);m.uc.mem_write(0x20002AF8,struct.pack('<I',2))
    before=m.framebuffer();m.loop_guard(0x08008C7E)
    assert m.owned() and m.framebuffer()==before and not m.frames
    m.time(2000);m.loop_guard(0x08008BF8)
    assert not m.owned() and m.uc.reg_read(UC_ARM_REG_R5)==0x20002AF8
    assert m.uc.reg_read(UC_ARM_REG_R0)==0
    checks.append('actual loop-entry branch skips pending stock overlay while owned; timeout restores original continuation')

    m=fresh();sid=acquire(m);parts=frame(m,sid,1,first)
    m.send(payload(RELEASE,sid));assert not m.owned()
    assert bytes(m.uc.mem_read(MODE,1))==b'\x02'
    expected=m.framebuffer();assert expected!=first
    m.send(parts[0]);m.send(parts[-1]);m.send(payload(HEARTBEAT,sid))
    m.send(payload(ACQUIRE,sid));assert not m.owned()
    assert m.framebuffer()==expected and not m.forwarded
    acquire(m,sid+1);m.send(parts[0]);assert m.framebuffer()==expected
    checks.append('explicit release calls real built-in clock initializer; old SID/data/heartbeat cannot reclaim it')

    for reason in ('silent_host','unplug','sleep','killed_process'):
        m=fresh();sid=acquire(m);m.send(payload(BEGIN,sid,1))
        m.time(1999);m.service();assert m.owned()
        m.time(2000);m.service();assert not m.owned()
        assert bytes(m.uc.mem_read(MODE,1))==b'\x02'
        assert not m.flash_calls
    checks.append('host silence scenarios release at 2000 ticks through actual service hook; incomplete frame discarded')

    m=fresh();sid=acquire(m)
    for op in (ACQUIRE,HEARTBEAT,BEGIN,RELEASE):m.send(payload(op,sid+1,1))
    assert m.owned() and m.value(16)==sid and m.value(12)==0
    m.time(1500);m.send(payload(HEARTBEAT,sid+1));assert m.value(12)==0
    checks.append('another SID cannot change lease, release it, or renew timeout')

    for defect in ('crc','order','changed_retry'):
        m=fresh();sid=acquire(m);m.send(payload(BEGIN,sid,1));old=m.framebuffer()
        data=first+binascii.crc_hqx(first,0).to_bytes(2,'big')
        parts=[payload(DATA,sid,1,i,data[o:o+37]) for i,o in enumerate(range(0,len(data),37))]
        if defect=='crc':parts[-1]=parts[-1][:-1]+bytes([parts[-1][-1]^1])
        elif defect=='order':parts=parts[1:]
        else:parts.insert(1,parts[0][:-1]+bytes([parts[0][-1]^1]))
        for part in parts:m.send(part)
        assert m.framebuffer()==old and not m.frames
        frame(m,sid,2,first)
    checks.append('integrated CRC/order/changed-retry rejection retains old frame; a fresh frame transaction recovers')

    for command,handler in ((b'+OTA+STA',0x080060A4),(b'+POW+OFF',0x080066BA),(b'+RST+ONN',0x080066E8)):
        m=fresh();acquire(m);m.receive(b'BLT'+command+b'#\x00\x04test\r\n')
        assert not m.owned() and m.forwarded==[(handler,False)]
    checks.append('OTA start/power/reset release before original handler; dangerous handler I/O mocked')

    for mode,upload in ((0x5a,0),(3,1)):
        m=fresh();m.uc.mem_write(MODE,bytes([mode]));m.uc.mem_write(0x20002A5C,bytes([upload]))
        m.send(payload(ACQUIRE,123));assert not m.owned()
    checks.append('cannot acquire during OTA or an existing stock upload')

    # Reserved packets remain intercepted even when another stock mode has
    # overwritten our shared workspace. This is essential to avoid Flash fallthrough.
    m=fresh();m.uc.mem_write(LEASE,b'\xff'*32)
    m.send(payload(DATA,123,1,0,b'abc'));assert not m.forwarded
    m.receive(b'BLT+DIY+STA#\x00\x04\x80\x00\x04\x02\r\n');assert not m.forwarded
    m.receive(b'BLT+DIY+STA#\x00\x04\x00\x00\x04\x28\r\n')
    assert m.forwarded==[(0x08005E34,False)]
    checks.append('reserved data and obsolete START never enter Flash handlers after workspace reuse; fresh normal START still routes')

    m=fresh();sid=123;wire=uart_packet(payload(ACQUIRE,sid))
    for byte in wire:m.receive(bytes([byte]))
    assert m.owned()
    m.send(payload(RELEASE,sid))
    assert not m.owned()
    checks.append('real parser accepts byte-by-byte split header, payload and terminator')

    rng=random.Random(0x2D99)
    for i in range(48):
        m=fresh();acquire(m)
        data=rng.randbytes(rng.randrange(0,90))
        # Reserved sequence distinguishes malformed extension from stock packets.
        raw=b'\0\0\xff\xff'+data
        m.receive(b'BLT+DIY+DAT#'+len(raw).to_bytes(2,'big')+raw+b'\r\n')
        assert not m.forwarded and not m.flash_calls
    m=fresh();sid=acquire(m)
    m.receive(b'BLT+DIY+DAT#\xff\xff'+b'x'*500+b'\r\n')
    m.send(payload(HEARTBEAT,sid));assert m.owned()
    checks.append('48 malformed extension frames and overlong declared length stay in guarded buffers; parser resynchronizes')

    plan=SessionPlan(125);assert plan.start(0)
    assert plan.heartbeat(.499) is None and plan.heartbeat(.5)
    packets=plan.pixels(first);assert len(packets)==29
    assert plan.stop() and plan.stop() is None and plan.heartbeat(2) is None
    checks.append('offline PC planner uses 500ms idle heartbeat, 28 fragments, and idempotent explicit stop')

    m=fresh();sent=[]
    def emit(body):sent.append(body);m.send(body)
    driver=OfflineSessionDriver(9988,emit);driver.start(0)
    driver.tick(0,first);assert m.framebuffer()==first
    sent_after_frame=len(sent)
    for i in range(1,21):
        m.time(i*500);driver.tick(i*.5,first);m.main_cycle();assert m.owned()
    assert len(sent)==sent_after_frame+20 and len(m.frames)==1
    driver.close();assert not m.owned();driver.close()
    try:driver.start(11)
    except RuntimeError:pass
    else:raise AssertionError('Retired SID reused')
    checks.append('PC lifecycle driver -> actual ARM parser: static-frame dedup, 10s heartbeat, explicit close, retired-ID refusal')
    return dict(checks=checks,checks_passed=len(checks),machines=len(machines),
                instructions=sum(m.instructions for m in machines),
                frames=sum(len(m.frames) for m in machines),
                forbidden_flash_calls=sum(len(m.flash_calls) for m in machines))


def main():
    original,patched,entries,layout,receiver,session=build()
    result=check(patched,entries)
    result.update(status='OFFLINE_INTEGRATED_HOOKS_NOT_READY_TO_FLASH',layout=layout,
        emulator_version=emulator_runtime.unicorn.__version__,
        original_sha256=hashlib.sha256(original).hexdigest(),image_size=len(patched),
        in_memory_candidate_sha256=hashlib.sha256(patched).hexdigest(),
        source_sha256={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('ram_stream_thumb.s','bitmap_unpack_thumb.s','session_thumb.s','session_packets.py','validate_session.py')},
        lease_ram=[hex(LEASE),hex(LEASE+32)],core_ram_bytes=24,
        nominal_heartbeat_ms=500,lease_timeout_ticks=2000,
        firmware_file_generated=False,hardware_sender_enabled=False,device_accessed=False,
        limitations=['USB main-controller scheduling and end-to-end application ACK are not emulated',
                     'Actual 1ms timer period inferred from stock scheduling, not measured',
                     'Full boot, asynchronous interrupt interleavings, power and thermal behavior unverified',
                     'Legacy parser outside new DIY path/lease retains original bounds behavior',
                     'Retired SID tombstone survives only until stock upload reuses its workspace',
                     'OTA/power/reset forwarding tested only to handler entry; its I/O is mocked',
                     'Independent bootloader recovery and modified image acceptance unresolved'])
    output=ROOT/'firmware-analysis/session-lab';output.mkdir(exist_ok=True)
    (output/'validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (output/'session.thumb').write_bytes(session)
    (output/'receiver-profile.thumb').write_bytes(receiver)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
