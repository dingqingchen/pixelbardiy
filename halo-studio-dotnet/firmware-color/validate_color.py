"""Offline only: execute real ARM color/animation/lease code and OTA staging."""
from pathlib import Path
import sys, json, struct, random
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / 'halo-controller/firmware-lab/vendor-arm-tools'), str(HERE.parent / 'firmware-fullscreen'), str(HERE.parent / 'firmware-matrix')]
import validate_fullscreen as full
import validate_matrix as rain
from session_packets import payload, ACQUIRE, RELEASE, HEARTBEAT
from unicorn.arm_const import UC_ARM_REG_R0

SOURCE = HERE / 'codec_color_thumb.s'
BaseMachine = full.codec.Machine
class ColorMachine(BaseMachine):
    def __init__(self, *args):
        self.colors = []
        super().__init__(*args)
    def write(self, uc, access, address, size, value, user):
        if 0x20000057 <= address and address + size <= 0x200001a7: return
        if address == 0x200001bf and size == 1 and value == 0: return
        super().write(uc, access, address, size, value, user)
    def code(self, uc, address, size, user):
        if address == 0x080097de:
            # Execute stock scaling + bit encoding; only physical DMA is mocked.
            grb = bytes(uc.mem_read(0x20002a64, 42))
            pulses = bytes(0x39 if byte & (1 << bit) else 0x1f for byte in grb for bit in range(7, -1, -1))
            assert bytes(uc.mem_read(0x20000057, 336)) == pulses
            self.colors.append(grb)
            self.result(); return
        super().code(uc, address, size, user)

def packets(number, target, basis=None, base_id=0, style=0, rgb=None, interval=16):
    batch = full.frame_packets(number, target, basis, base_id, style, interval)
    if rgb is not None:
        begin = bytearray(batch[0]); begin[12] += 3; begin.extend(rgb); batch[0] = bytes(begin)
    return batch

def model(old, new, step, style):
    if step >= 32: return new
    out = bytearray(1024)
    for y in range(32):
        for x in range(256):
            use_new = 128-step*4 <= x < 128+step*4
            if style == 7:
                a, b = x%8, y%4
                use_new = ((a^(a>>1))*4 + (b^(b>>1))) < step
            p = new if use_new else old
            if p[y//8*256+x] >> (y%8) & 1: out[y//8*256+x] |= 1 << (y%8)
    return bytes(out)

def main():
    full.codec.Machine = ColorMachine
    regression = HERE / 'regression'; regression.mkdir(exist_ok=True)
    original, image, entries, baseline = full.main(SOURCE, regression, 7)
    installed = (HERE.parent/'firmware-matrix/mcu-hpl2-matrix.bin').read_bytes()
    assert full.sha(installed) == 'ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884'
    assert image[0x7804:0x79d6] == original[0x7804:0x79d6]
    rng = random.Random(20261014); old, target = rng.randbytes(1024), rng.randbytes(1024)
    machines, checks = [], []
    def fresh():
        m = ColorMachine(image, entries); machines.append(m)
        m.uc.mem_write(0x20002a15, bytes([50, 255, 255, 144]))
        m.send(payload(ACQUIRE, 123)); return m
    def send(m, batch):
        before = len(m.acks)
        for p in batch: m.send(p)
        assert len(m.acks)-before == len(batch) and m.acks[-1] == b'MCU+DAT+END\r\n'
    expected = lambda rgb: bytes(rgb[i]*50//100 for i in (1,0,2))*14
    for style in (6,7):
        for interval in (8,16,64):
            m=fresh(); send(m,packets(1,old)); send(m,packets(2,target,old,1,style,(96,255,48),interval))
            assert m.colors[-1] == expected((96,255,48))
            for step in range(33):
                m.time(step*interval)
                if step and step%7==0: m.send(payload(HEARTBEAT,123))
                count=len(m.acks); m.service()
                assert m.framebuffer()==model(old,target,step,style),(style,interval,step)
                assert len(m.acks)==count
                count=len(m.frames); m.service(); assert len(m.frames)==count
            send(m,packets(3,old,target,2,0,(255,96,72)))
            assert m.framebuffer()==old and m.colors[-1]==expected((255,96,72))
        checks.append(f'animation {style}: every pixel, all 33 steps, intervals 8/16/64, local-only, exact XOR base')
    # Packet atomicity, no settings changes, no release when RGB changes.
    m=fresh(); config=bytes(m.uc.mem_read(0x20002a15,4)); send(m,packets(1,old,rgb=(96,255,48)))
    count=len(m.colors); batch=packets(2,target,old,1,7,(255,96,72))
    for p in batch[:-1]:
        m.send(p); assert len(m.colors)==count and m.framebuffer()==old and m.owned()
    m.send(batch[-1]); assert len(m.colors)==count+1 and m.owned()
    assert bytes(m.uc.mem_read(0x20002a15,4))==config
    checks.append('RGB commits only after final frame CRC; no clock/release/brightness/config mutation')
    for bad in ('crc','owner','length','animation','interrupted'):
        m=fresh(); send(m,packets(1,old,rgb=(96,255,48))); count=len(m.colors)
        batch=packets(2,target,old,1,7,(255,96,72))
        if bad=='crc':
            b=bytearray(batch[0]); b[24]^=1; batch[0]=bytes(b)
        elif bad=='owner': batch=[p[:5]+struct.pack('>I',124)+p[9:] for p in batch]
        elif bad=='length':
            b=bytearray(batch[0]); b[12]-=1; batch[0]=bytes(b[:-1])
        elif bad=='animation':
            b=bytearray(batch[0]); b[14]=8; batch[0]=bytes(b)
        elif bad=='interrupted': batch=batch[:2]
        for p in batch: m.send(p)
        assert len(m.colors)==count and m.framebuffer()==old and m.owned(),bad
        checks.append('malformed/uncommitted color rejected: '+bad)
    # Duplicate colors must not retransmit the LED driver on every clock tick.
    m=fresh(); send(m,packets(1,old,rgb=(96,255,48))); count=len(m.colors)
    send(m,packets(2,target,old,1,0,(96,255,48))); assert len(m.colors)==count
    checks.append('identical committed RGB suppressed; legacy 12-byte frames compatible')
    # A long-running display wraps its sequence without releasing the lease.
    m.uc.mem_write(full.codec.session.LEASE+20, struct.pack('<I',65535))
    m.uc.mem_write(full.codec.EX+28, struct.pack('<I',65535))
    send(m,packets(1,old,target,65535,6,(255,96,72)))
    assert m.owned() and m.value(20)==1
    checks.append('65535-to-1 frame sequence wrap retains ownership and delta base')
    for style in (5,6,7):
        for action in ('release','timeout','interrupt'):
            m=fresh(); send(m,packets(1,old)); send(m,packets(2,target,old,1,style,(255,96,72)))
            m.time(160); m.service()
            if action=='interrupt':
                send(m,packets(3,old,target,2,0,(96,255,48))); assert m.framebuffer()==old and m.owned()
            else:
                if action=='release': m.send(payload(RELEASE,123))
                else: m.time(2200); m.service()
                assert not m.owned() and m.colors[-1]==expected((255,255,144))
                stable=m.framebuffer(); m.time(6000); m.service(); assert m.framebuffer()==stable
            checks.append(f'animation {style} {action}: color/frame restoration and stable lease lifecycle')
    # Keep the local matrix rain identical to its independent original model.
    m=fresh(); send(m,packets(1,target,style=5,rgb=(96,255,48),interval=32))
    for step in range(161):
        m.time(step*32)
        if step and step%10==0: m.send(payload(HEARTBEAT,123))
        m.service(); assert m.framebuffer()==rain.model(target,step)
    checks.append('all 160 character-rain frames unchanged with atomic RGB')
    assert all(not m.flash_calls for m in machines)
    transfers=dict(upgrade=full.staging(installed,entries,image),rollback=full.staging(image,entries,installed))
    report=dict(candidate_sha256=full.sha(image),installed_sha256=full.sha(installed),image_bytes=len(image),baseline=baseline,
                color_checks=checks,color_checks_passed=len(checks),forbidden_flash_calls=0,additional_ram_bytes=0,ota=transfers,
                layout=baseline['layout'],device_accessed=False,firmware_written=False,device_flash_readback=False,independent_dead_mcu_recovery=False)
    (HERE/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (HERE/'mcu-hpl2-color.bin').write_bytes(image)
    (HERE/'mcu-hpl2-color.bin.sha256').write_text(full.sha(image)+'  mcu-hpl2-color.bin\n')
    print(json.dumps(dict(phase='color-passed',sha256=full.sha(image),checks=len(checks),remaining_bytes=baseline['layout']['remaining_bytes'])),flush=True)
if __name__=='__main__': main()
