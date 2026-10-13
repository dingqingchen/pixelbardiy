"""Offline real ARM character-rain animation, lifecycle, and rollback tests."""
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
FULL = HERE.parent / 'firmware-fullscreen'
sys.path.insert(0, str(FULL))
import validate_fullscreen as full
from session_packets import payload, ACQUIRE, HEARTBEAT, RELEASE

SOURCE = HERE / 'codec_matrix_thumb.s'
FONT = bytes(int(v, 16) for v in re.findall(r'0x([0-9a-f]{2})', SOURCE.read_text().split('rain_font:\n')[1]))
assert len(FONT) == 80


def model(target, step):
    if step >= 160:
        return target
    out = bytearray(1024)
    reveal = max(0, step - 128) * 8
    for x in range(reveal):
        for page in range(4):
            out[page * 256 + x] = target[page * 256 + x]
    for stream in range(32):
        head = (step * (1 + stream % 2) + stream * 13) % 64 - 8
        for tail in range(3):
            glyph = (stream * 7 + step // 8 - tail * 3) % 16
            for gx in range(5):
                x = stream * 8 + gx
                if x < reveal:
                    continue
                for gy in range(7):
                    if not (FONT[glyph * 5 + gx] >> gy & 1):
                        continue
                    if tail and ((x % 2 == 0 and gy % 2 != 0) or (x % 2 == 1 and gy % 2 != 1)):
                        continue
                    y = head - tail * 8 + gy
                    if 0 <= y < 32:
                        out[y // 8 * 256 + x] |= 1 << (y % 8)
    return bytes(out)


def main():
    regression_dir = HERE / 'regression'
    regression_dir.mkdir(exist_ok=True)
    if '--rain-only' in sys.argv:
        original, image, entries, _ = full.codec.build(SOURCE)
        baseline = json.loads((regression_dir / 'validation.json').read_text())
        assert baseline['candidate_sha256'] == full.sha(image)
    else:
        original, image, entries, baseline = full.main(SOURCE, regression_dir, 5)
    installed = (FULL / 'mcu-hpl2-fullscreen.bin').read_bytes()
    assert full.sha(installed) == 'ab4698cf8e826a3c64472ea0af1125653f65f796cd7fcf9013667344e4c0fc50'
    assert full.sha(image) == 'ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884'
    from halo.pixels import Canvas
    c = Canvas()
    c.text('HALO STUDIO', 63, 9, 2)
    c.rect(3, 3, 250, 26)
    target = bytes(c.data)
    checks, machines, preview = [], [], []
    def fresh():
        m = full.codec.Machine(image, entries)
        machines.append(m)
        m.send(payload(ACQUIRE, 123))
        for packet in full.frame_packets(1, target, style=5, interval=32):
            m.send(packet)
        assert m.acks[-1] == b'MCU+DAT+END\r\n'
        return m
    m = fresh()
    largest_step = 0
    for step in range(161):
        m.time(step * 32)
        if step and step % 10 == 0:
            m.send(payload(HEARTBEAT, 123))
        before, ack_count = m.instructions, len(m.acks)
        m.service()
        largest_step = max(largest_step, m.instructions - before)
        assert m.framebuffer() == model(target, step), step
        assert len(m.acks) == ack_count
        preview.append(m.framebuffer())
        count = len(m.frames)
        m.service()
        assert len(m.frames) == count
    checks.append('160 local rain steps plus exact target; every pixel equals independent coordinate model, no USB redraw')
    assert len(m.frames) == 161 and largest_step < 50000
    checks.append('bounded per-step instructions; duplicate tick does not redraw')
    other = bytes(v ^ 255 for v in target)
    for packet in full.frame_packets(2, other, target, 1):
        m.send(packet)
    assert m.framebuffer() == other
    checks.append('post-effect XOR delta uses final target, never rain pixels')
    for action in ('release', 'timeout', 'interrupt', 'wrong-owner'):
        m = fresh()
        m.time(640)
        m.service()
        if action == 'release':
            m.send(payload(RELEASE, 123))
            assert not m.owned()
        elif action == 'timeout':
            m.time(2000)
            m.service()
            assert not m.owned()
        elif action == 'interrupt':
            for packet in full.frame_packets(2, other, target, 1):
                m.send(packet)
            assert m.framebuffer() == other
        else:
            m.send(payload(RELEASE, 124))
            assert m.owned()
            m.time(672)
            m.service()
            assert m.framebuffer() == model(target, 21)
        if action in ('release', 'timeout'):
            assert m.uc.mem_read(full.codec.EX, 4) == bytes(4)
            stable = m.framebuffer()
            m.time(6000)
            m.service()
            assert m.framebuffer() == stable
        checks.append('rain lifecycle: ' + action)
    assert all(not m.flash_calls for m in machines)
    transfers = dict(upgrade=full.staging(installed, entries, image), rollback=full.staging(image, entries, installed))
    report = dict(candidate_sha256=full.sha(image), installed_sha256=full.sha(installed),
                  image_bytes=len(image), baseline=baseline, rain_checks=checks,
                  rain_checks_passed=len(checks), max_instructions_per_step=largest_step,
                  forbidden_flash_calls=0, additional_ram_bytes=0, ota=transfers,
                  changed_bytes=sum(a != b for a, b in zip(installed, image)),
                  layout=baseline['layout'], independent_dead_mcu_recovery=False,
                  device_flash_readback=False, device_accessed=False, firmware_written=False)
    (HERE / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (HERE / 'mcu-hpl2-matrix.bin').write_bytes(image)
    (HERE / 'mcu-hpl2-matrix.bin.sha256').write_text(full.sha(image) + '  mcu-hpl2-matrix.bin\n')
    output = HERE.parent / 'validation/matrix-arm-frames.bin'
    output.write_bytes(b''.join(preview))
    print(json.dumps(dict(phase='matrix-passed', sha256=full.sha(image), checks=len(checks),
                         max_instructions=largest_step, changed_bytes=report['changed_bytes'],
                         remaining_bytes=baseline['layout']['remaining_bytes'], preview=str(output))), flush=True)


if __name__ == '__main__':
    main()
