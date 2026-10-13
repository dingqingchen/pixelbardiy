"""Build and emulate compression/delta/local-animation extension, offline only.

Keep the reviewed original assets, receiver and hook locations. New code stays
inside reclaimed background space; OTA/vector/font regions stay byte-identical.
"""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

import validate_session as session
from validate_bitmap_space import assemble, BASE, END, START, RENDERERS, HELPER, DIRECTORY, BitmapMachine
from validate_ram_stream import FB, STAGE, RAM
from session_packets import payload, ACQUIRE, HEARTBEAT, RELEASE, BEGIN, DATA

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from halo.ram_codec import encode, packets, pack, crc, Encoded

EX = 0x20001358
OLD = 0x200013B8


def build():
    original, baseline, entries, layout, receiver, _ = session.build()
    source = Path(__file__).with_name('session_thumb.s').read_text()
    def patch(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    # The installed revision shared this branch with OTA DATA. Its prototype
    # START marker test accidentally discarded OTA chunks starting with 80..FF.
    # Apply the marker check only to START, keeping the active-lease gate above.
    patch('    // Block the obsolete prototype\'s marked START even with no lease.\n', '''    adds r0, r4, #4
    bl be32
    ldr r1, =0x2b535441
    cmp r0, r1
    bne forward
    // Block the obsolete prototype's marked START even with no lease.
''')
    patch('    cmp r6, #4\n    beq pixels',
          '    cmp r6, #6\n    beq extended_begin\n    cmp r6, #7\n    beq extended_data\n    cmp r6, #4\n    beq pixels')
    patch('frame_id:\n', '''extended_begin:
    mov r0, r4
    mov r1, r8
    ldr r3, =EXT_BEGIN
    blx r3
    cmp r0, #1
    beq refresh_lease
    b handled
extended_data:
    bl frame_id
    cmp r0, #0
    beq handled
    ldr r1, [r5, #20]
    cmp r0, r1
    bne handled
    mov r0, r4
    mov r1, r8
    ldr r3, =EXT_DATA
    blx r3
    cmp r0, #1
    beq refresh_lease
    b handled
frame_id:
''')
    patch('    str r7, [r5, #16]\n', '    str r7, [r5, #16]\n    ldr r3, =EXT_RESET\n    blx r3\n')
    patch('    str r0, [r5, #20]\n    ldr r0, =core_header',
          '    str r0, [r5, #20]\n    ldr r3, =EXT_RESET\n    blx r3\n    ldr r0, =core_header')
    patch('    str r2, [r1, #12]\n', '    str r2, [r1, #12]\n    ldr r3, =EXT_RESET\n    blx r3\n    movs r0, #0\n')
    patch('service:\n    push {r4, lr}\n    bl poll\n', '''service:
    push {r4, lr}
    bl poll
    bl active
    cmp r0, #0
    beq service_stock
    ldr r3, =EXT_TICK
    blx r3
service_stock:
''')
    address = int(layout['session_address'], 16)
    def compile_session(ext):
        text = source
        values = dict(LEASE=session.LEASE, CORE_BEGIN=int(layout['core_address'],16)|1,
                      CORE_DATA=(int(layout['core_address'],16)+4)|1,
                      EXT_BEGIN=ext|1, EXT_DATA=(ext+4)|1, EXT_TICK=(ext+8)|1, EXT_RESET=(ext+12)|1)
        for key, value in values.items(): text = text.replace(key, hex(value))
        return assemble(text, address)
    module = compile_session(0x0800D000)
    ext = (address+len(module)+3)&~3
    module2 = compile_session(ext)
    assert len(module2) == len(module)
    text = Path(__file__).with_name('codec_thumb.s').read_text()
    for key,value in dict(EX=EX, OLD=OLD, LEASE=session.LEASE).items(): text = text.replace(key, hex(value))
    codec = assemble(text, ext)
    compat_address = (ext+len(codec)+3)&~3
    compat = assemble(Path(__file__).with_name('ota_compat_thumb.s').read_text().replace('DECODER',hex(START|1)),compat_address)
    assert compat_address+len(compat) <= END
    image = bytearray(baseline)
    # Zero only unused reclaimed space, so the OLD installed dispatcher's OTA
    # high-byte bug can be bypassed by lossless, variable-sized packet boundaries.
    image[address-BASE:END-BASE] = bytes(END-address)
    image[address-BASE:address-BASE+len(module2)] = module2
    image[ext-BASE:ext-BASE+len(codec)] = codec
    image[compat_address-BASE:compat_address-BASE+len(compat)] = compat
    # This gap was explicitly reserved but unused by the 200-byte decoder.
    image[START+layout['decoder_bytes']-BASE:DIRECTORY-BASE] = bytes(DIRECTORY-START-layout['decoder_bytes'])
    image[HELPER-BASE:HELPER-BASE+4] = assemble(f'b.w {compat_address:#x}',HELPER)
    assert original[0x52e2-0x2000:0x52e6-0x2000].hex() == '28788046'
    image[0x52e2-0x2000:0x52e6-0x2000] = assemble(f'bl {compat_address+4:#x}',0x080052e2)
    for lo,hi in ((0x0800ebec,0x0800ecec),(0x0800f632,0x0800f674)):
        image[lo-BASE:hi-BASE] = bytes(v^128 for v in original[lo-BASE:hi-BASE])
    # Same infinite-loop handler, same entry address, no register/flag changes:
    # replace a 32-bit branch-to-self by 16-bit branch-to-self + unreachable NOP.
    assert original[0x0800fed4-BASE:0x0800fed8-BASE] == bytes.fromhex('fff7febf')
    image[0x0800fed4-BASE:0x0800fed8-BASE] = bytes.fromhex('fee700bf')
    assert len(image) == len(original) == 57252 and image[:224] == original[:224]
    for lo,hi in ((0x08005E34,0x08006318),(0x08009114,0x08009330)):
        assert image[lo-BASE:hi-BASE] == original[lo-BASE:hi-BASE]
    changes=[(address,END),(START+layout['decoder_bytes'],DIRECTORY),(HELPER,HELPER+4),
             (0x080052e2,0x080052e6),(0x0800ebec,0x0800ecec),(0x0800f632,0x0800f674),(0x0800fed4,0x0800fed8)]
    assert all(a==b or any(lo<=BASE+i<hi for lo,hi in changes) for i,(a,b) in enumerate(zip(image,baseline)))
    layout.update(session_bytes=len(module2), extension_address=hex(ext), extension_bytes=len(codec),
                  remaining_bytes=END-compat_address-len(compat), extension_state=[hex(EX),hex(EX+96)],
                  ota_compat_address=hex(compat_address),ota_compat_bytes=len(compat),
                  change_ranges_vs_installed=[[hex(lo),hex(hi)] for lo,hi in changes],
                  animation_old_frame=[hex(OLD),hex(OLD+1024)])
    return original,bytes(image),entries,layout


class Machine(session.Machine):
    def write(self, uc, access, address, size, value, user):
        if EX <= address and address+size <= OLD+1024: return
        super().write(uc,access,address,size,value,user)


def animated(old, new, step, style):
    if step >= 24: return new
    out = bytearray(new)
    for x in range(38,238):
        a = sum(old[256*p+x] << (p*8) for p in range(4))
        b = sum(new[256*p+x] << (p*8) for p in range(4))
        if style == 1:
            value = (((a>>4 & 0xffffff)>>step) | ((b>>4 & 0xffffff)<<(24-step))) & 0xffffff
            word = (b & 0xf000000f) | (value<<4)
        else: word = b if x < 38+step*8 else (b & 0xf000000f) | (a & 0x0ffffff0)
        for p in range(4): out[256*p+x] = (word>>(p*8)) & 255
    return bytes(out)


def check(image, entries):
    # All original lifecycle/parser tests must pass with the new exact image.
    old_machine = session.Machine
    session.Machine = Machine
    try: baseline = session.check(image, entries)
    finally: session.Machine = old_machine
    machines=[]; checks=[]
    def fresh():
        m=Machine(image,entries); machines.append(m); m.send(payload(ACQUIRE,123)); assert m.owned(); return m
    def send_frame(m, n, target, base=None, base_id=0, animation=0):
        item=encode(target,base,base_id,animation)
        old=m.framebuffer(); batch=packets(123,n,item)
        before=len(m.acks)
        for p in batch[:-1]:
            m.send(p); assert m.framebuffer()==old
        m.send(batch[-1])
        assert len(m.acks)==before+len(batch), (len(m.acks)-before,len(batch))
        assert m.acks[-1]==b'MCU+DAT+END\r\n'
        if not animation: assert m.framebuffer()==target
        return item,batch
    rng=random.Random(20261012)
    samples=[bytes(1024),b'\xff'*1024,bytes(range(256))*4,rng.randbytes(1024),
             b'\x00'*383+rng.randbytes(260)+b'\x00'*381]
    for data in samples:
        m=fresh(); send_frame(m,1,data)
        newest=bytearray(data); newest[145:155]=b'0123456789'
        encoded,_=send_frame(m,2,bytes(newest),data,1)
        assert encoded.codec in (1,2) and len(encoded.data)<60
    checks.append('raw/RLE/XOR-RLE including incompressible pixels, sparse differences and split tokens; CRC atomic commit')
    # Force every possible valid fragment size to split both literal and repeat tokens.
    for chunk in range(1,38):
        m=fresh(); data=samples[-1]; item=encode(data)
        batch=packets(123,1,item); m.send(batch[0])
        parts=[item.data[i:i+chunk] for i in range(0,len(item.data),chunk)]
        if len(parts)>256: continue  # Protocol sequence is one byte, no wrapping.
        for i,part in enumerate(parts):
            p=b'HPL2'+bytes([7])+struct.pack('>IHB',123,1,i)+bytes([len(part)])+part
            m.send(p)
        assert m.framebuffer()==data
    checks.append('RLE streaming decoder handles every permitted fragment split without crossing the output boundary')
    for kind in ('crc','order','truncated','overflow','extra','duplicate','wrong_base','wrong_crc'):
        m=fresh(); base=samples[2]; send_frame(m,1,base); before=len(m.frames)
        newer=bytearray(base); newer[200:550]=rng.randbytes(350); item=encode(bytes(newer),base,1)
        metadata=bytearray(item.metadata); data=item.data
        if kind=='crc': metadata[-1]^=1
        elif kind=='wrong_base': metadata[7]^=7
        elif kind=='wrong_crc': metadata[9]^=1
        elif kind=='truncated': data=b'\xff'; metadata[4:6]=len(data).to_bytes(2,'big')
        elif kind=='overflow': data=b'\xff\x00'*9; metadata[4:6]=len(data).to_bytes(2,'big')
        elif kind=='extra': data+=b'\x80\x00'; metadata[4:6]=len(data).to_bytes(2,'big')
        batch=packets(123,2,Encoded(item.codec,data,bytes(metadata)))
        if kind=='order': batch=batch[:1]+batch[2:]
        if kind=='duplicate': batch.insert(2,batch[1])
        for p in batch:m.send(p)
        assert m.framebuffer()==base and len(m.frames)==before,kind
        # Reconnect protocol baseline after a rejected BEGIN uses same next ID.
        n=m.value(20)+1; send_frame(m,n,samples[3])
    checks.append('bad CRC/order/base/repeated fragment/truncation/overflow/extra data never publish; full frame recovers')
    for style in (1,2):
        m=fresh(); a=samples[3]; b=samples[2]; send_frame(m,1,a)
        send_frame(m,2,b,a,1,style)
        assert m.framebuffer()==animated(a,b,0,style)
        ack_count=len(m.acks)
        for step in range(1,25):
            m.time(step*16); m.service()
            assert m.framebuffer()==animated(a,b,step,style), (style,step)
        assert len(m.acks)==ack_count and len(m.frames)==26
        # The next delta uses the final target, never the intermediate pixels.
        send_frame(m,3,a,b,2)
    checks.append('24 local up/wipe steps preserve decorations and match independent bit model; no USB frames needed')
    m=fresh(); a=samples[3]; b=samples[2]; send_frame(m,1,a); send_frame(m,2,b,a,1,1)
    m.time(64);m.service()
    # A new BEGIN settles the accepted target before verifying the delta base.
    item=encode(a,b,2); batch=packets(123,3,item)
    for p in batch:m.send(p)
    assert m.framebuffer()==a
    checks.append('new content interrupts animation safely; delta applies to accepted target')
    for mode in ('release','timeout','legacy','wrong_owner'):
        m=fresh();a=samples[3];b=samples[2];send_frame(m,1,a);send_frame(m,2,b,a,1,2)
        if mode=='release':m.send(payload(RELEASE,123));assert not m.owned()
        elif mode=='timeout':m.time(2000);m.service();assert not m.owned()
        elif mode=='legacy':
            m.send(payload(BEGIN,123,3)); assert bytes(m.uc.mem_read(EX,4))==bytes(4)
        else:
            for p in packets(124,3,encode(a)):m.send(p)
            assert m.value(20)==2
    checks.append('release/heartbeat timeout cancel native animation; legacy fallback and wrong-SID exclusion preserved')
    # Real PC encoder/queue -> actual patched UART parser and machine code.
    from halo.ram_display import RamDisplay
    from halo.pixels import PixelFrame
    m=fresh()
    class EmulatedLink(RamDisplay):
        def __init__(self):
            super().__init__(Path('unused'))
            self.codec_enabled=self.owned=self.authorized=True
            self.sid=123;self.pixel_color='#FFFFFF';self.response=None
        def _pixel_query(self,command,payload=(),**kwargs):
            assert command==0x17 and payload[:4]==b'\0\x02\xff\xff'
            if self.response is None:
                before=len(m.acks);m.send(payload[4:])
                assert len(m.acks)==before+1
                self.response=b'\0\x05' if m.acks[-1]==b'MCU+DAT+END\r\n' else b'\0\x03\xff\xff'
                return None
            answer,self.response=self.response,None;return answer
    d=EmulatedLink();a=samples[3];b=rng.randbytes(1024);c=bytearray(a);c[42:46]=b'abcd';c=bytes(c)
    d.offer(PixelFrame(a,'A','A'),'#FFFFFF')
    for i in range(32):d.tick(i*.05)
    assert m.framebuffer()==a
    d.offer(PixelFrame(b,'B','B'),'#FFFFFF');d.tick(2);d.tick(2.05)
    d.offer(PixelFrame(c,'C','C'),'#FFFFFF',urgent=True,animation=1)
    for i in range(42,60):d.tick(i*.05)
    m.time(384);m.service()
    assert d.committed[0].pixels==m.framebuffer()==c and d.frames_dropped==1 and d.committed_number==3
    checks.append('real PC latest-target sender -> new MCU code: partial frame cancelled, committed-base delta, native animation')
    # Malformed metadata and packets are consumed, never reach resource Flash.
    for _ in range(64):
        m=fresh();before=m.framebuffer()
        for op in (6,7):
            raw=rng.randbytes(rng.randrange(0,38))
            m.send(b'HPL2'+bytes([op])+struct.pack('>IHB',123,1,0)+bytes([len(raw)])+raw)
        assert m.framebuffer()==before and not m.forwarded
    checks.append('64 randomized malformed extended headers/data remain bounded with no resource handler forwarding')
    assert all(not m.flash_calls for m in machines)
    return dict(legacy=baseline, checks=checks,checks_passed=len(checks),machines=len(machines),
                instructions=sum(m.instructions for m in machines),frames=sum(len(m.frames) for m in machines),
                forbidden_flash_calls=0)


def main():
    original,image,entries,layout=build()
    print(json.dumps(dict(sha256=hashlib.sha256(image).hexdigest(),layout=layout)),flush=True)
    result=check(image,entries)
    result.update(candidate_sha256=hashlib.sha256(image).hexdigest(),layout=layout,
                  device_accessed=False,firmware_written=False)
    out=ROOT/'firmware-analysis/codec-lab';out.mkdir(exist_ok=True)
    (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
