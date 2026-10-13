"""Offline ARM execution, exact pixels and OTA/rollback staging verification.

Never opens a device. Imports the audited lab next door; leaves old firmware
sources and exported candidates intact. Emits a new image only after all checks.
"""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / 'halo-controller'
if (HERE.parents[1] / 'legacy-python/firmware-lab').is_dir():
    ROOT = HERE.parents[1] / 'legacy-python'
sys.path[:0] = [str(ROOT / 'firmware-lab'), str(ROOT)]
import validate_codec as codec
import validate_ota_compat as ota
from validate_bitmap_space import BASE, END
from session_packets import payload, ACQUIRE, HEARTBEAT, RELEASE
from halo.ram_codec import FIRMWARE_SHA, encode, packets, Encoded


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def frame_packets(number, data, base=None, base_id=0, style=0, interval=16):
    item = encode(data, base, base_id, 0, interval)
    metadata = bytearray(item.metadata)
    metadata[1] = style
    return packets(123, number, Encoded(item.codec, item.data, bytes(metadata)))


def model(old, new, step, style):
    """Independent pixel-coordinate model; intentionally no packed column math."""
    if step >= 32:
        return new
    out = bytearray(1024)
    for y in range(32):
        for x in range(256):
            if style == 3:
                source, sy = (old, y + step) if y + step < 32 else (new, y + step - 32)
            else:
                source, sy = (new if x < step * 8 else old), y
            if source[sy // 8 * 256 + x] >> (sy % 8) & 1:
                out[y // 8 * 256 + x] |= 1 << (y % 8)
    return bytes(out)


def staging(sender_image, sender_entries, target):
    machine = ota.OtaMachine(sender_image, sender_entries)
    machine.receive(ota.uart(b'STA', len(target).to_bytes(4, 'big') + b'\0'))
    assert machine.acks[-1] == b'MCU+OTA+STA\r\n' and not machine.markers
    chunks = [target[i:i + 55] for i in range(0, len(target), 55)]
    for index, chunk in enumerate(chunks):
        machine.receive(ota.uart(b'DAT', chunk))
        if index != len(chunks) - 1:
            assert not machine.markers and machine.acks[-1] == b'MCU+OTA+NXT\r\n'
    assert machine.markers == [(2, len(target))]
    assert machine.acks[-1] == b'MCU+OTA+END\r\n'
    assert machine.spi[:len(target)] == target
    assert machine.spi[len(target):((len(target) + 1023) // 1024) * 1024] == b'\xff' * ((-len(target)) % 1024)
    return dict(packets=len(chunks), bytes=len(target), exact=True, markers=machine.markers)


def main(source=None, out=None, maximum_animation=4):
    source = source or HERE / 'codec_fullscreen_thumb.s'
    out = out or HERE
    original, installed, entries, installed_layout = codec.build()
    assert sha(installed) == FIRMWARE_SHA
    baseline_file = ROOT / 'firmware-candidates/hpl2-codec/mcu-hpl2-codec.bin'
    if not baseline_file.is_file():
        baseline_file = ROOT / 'firmware/hpl2-codec/mcu-hpl2-codec.bin'
    assert installed == baseline_file.read_bytes()
    _, image, new_entries, layout = codec.build(source)
    assert entries == new_entries and len(image) == len(installed) == 57252
    extension = int(layout['extension_address'], 16)
    # Only two relocation branches and the existing reclaimed extension region.
    spans = [(extension, END), (0x0800519A, 0x0800519E), (0x080052E2, 0x080052E6)]
    assert all(a == b or any(lo <= BASE + i < hi for lo, hi in spans)
               for i, (a, b) in enumerate(zip(installed, image)))
    assert image[:224] == installed[:224]
    print(json.dumps(dict(phase='built', sha256=sha(image), bytes=len(image),
                          remaining_code_bytes=layout['remaining_bytes'])), flush=True)
    baseline = codec.check(image, entries)
    print(json.dumps(dict(phase='existing-regressions', legacy=baseline['legacy']['checks_passed'],
                          codec=baseline['checks_passed'])), flush=True)
    rng = random.Random(20261013)
    old, new = rng.randbytes(1024), rng.randbytes(1024)
    checks, machines = [], []

    def fresh(style, interval=16, begin_time=0):
        m = codec.Machine(image, entries)
        machines.append(m)
        m.send(payload(ACQUIRE, 123))
        # ACQUIRE resets the lease clock to zero. A wrap fixture represents an
        # already-running session immediately before the unsigned clock wraps.
        m.time(begin_time)
        m.uc.mem_write(codec.session.LEASE + 12, struct.pack('<I', begin_time))
        for packet in frame_packets(1, old):
            m.send(packet)
        before = m.framebuffer()
        batch = frame_packets(2, new, old, 1, style, interval)
        for packet in batch[:-1]:
            m.send(packet)
            assert m.framebuffer() == before
        m.send(batch[-1])
        assert m.acks[-1] == b'MCU+DAT+END\r\n'
        return m

    for style in (3, 4):
        for interval in (8, 16, 64):
            m = fresh(style, interval)
            assert m.framebuffer() == old
            for step in range(33):
                m.time(step * interval)
                if step and step % 7 == 0:
                    m.send(payload(HEARTBEAT, 123))
                before = len(m.acks)
                m.service()
                assert m.framebuffer() == model(old, new, step, style), (style, interval, step)
                assert len(m.acks) == before  # Every intermediate frame is entirely local.
                count = len(m.frames)
                m.service()
                assert len(m.frames) == count  # Same tick must not redraw.
            for packet in frame_packets(3, old, new, 2):
                m.send(packet)
            assert m.framebuffer() == old
        checks.append(f'animation {style}: all 8192 pixels at all 33 steps; intervals 8/16/64; no USB redraw; exact delta base')
        m = fresh(style, begin_time=0xFFFFFFF0)
        m.time((0xFFFFFFF0 + 256) & 0xFFFFFFFF)
        m.service()
        assert m.framebuffer() == model(old, new, 16, style)
        checks.append(f'animation {style}: unsigned tick wrap')
        for action in ('release', 'timeout', 'interrupt'):
            m = fresh(style)
            m.time(112)
            m.service()
            if action == 'interrupt':
                for packet in frame_packets(3, old, new, 2):
                    m.send(packet)
                assert m.framebuffer() == old
            else:
                if action == 'release':
                    m.send(payload(RELEASE, 123))
                else:
                    m.time(2000)
                    m.service()
                assert not m.owned() and m.uc.mem_read(codec.EX, 4) == bytes(4)
                stable = m.framebuffer()
                m.time(2400)
                m.service()
                assert m.framebuffer() == stable
            checks.append(f'animation {style}: {action} clears/settles animation safely')
    for invalid in (maximum_animation + 1, 127, 255):
        m = fresh(3)
        before = bytes(m.uc.mem_read(codec.EX, 96))
        m.send(frame_packets(3, old, new, 2, invalid)[0])
        assert bytes(m.uc.mem_read(codec.EX, 96)) == before and not m.forwarded
    checks.append('unknown animation IDs rejected without forwarding or state mutation')
    assert all(not m.flash_calls for m in machines)
    print(json.dumps(dict(phase='full-screen', checks=len(checks), flash_calls=0)), flush=True)
    transfers = dict(upgrade=staging(installed, entries, image), rollback=staging(image, entries, installed))
    graphics = ota.verify_graphics(original, image)
    report = dict(candidate_sha256=sha(image), installed_sha256=sha(installed),
                  image_bytes=len(image), layout=layout, baseline=baseline,
                  fullscreen_checks=checks, fullscreen_checks_passed=len(checks),
                  forbidden_flash_calls=0, ota=transfers, stock_graphics=graphics,
                  changed_bytes=sum(a != b for a, b in zip(installed, image)),
                  allowed_changes=[[hex(a), hex(b)] for a, b in spans],
                  additional_ram_bytes=0, device_accessed=False, firmware_written=False,
                  device_flash_readback=False, independent_dead_mcu_recovery=False,
                  limitations=['Bootloader absent; physical install/boot is not emulated.',
                               'Known-file rollback requires a responsive application.'])
    (out / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out / 'mcu-hpl2-fullscreen.bin').write_bytes(image)
    (out / 'mcu-hpl2-fullscreen.bin.sha256').write_text(sha(image) + '  mcu-hpl2-fullscreen.bin\n')
    print(json.dumps(dict(phase='passed', sha256=sha(image), changed_bytes=report['changed_bytes'],
                          checks=len(checks), ota=transfers, graphics=graphics)), flush=True)
    return original, image, entries, report


if __name__ == '__main__':
    main()
