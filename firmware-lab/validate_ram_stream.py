"""Assemble and execute an OFFLINE-ONLY ARM display-stream experiment.

Loads the exact official MCU 1.3.7 for memcpy, refresh wrapper, and ACK handling.
The experimental module is mapped above the real application ONLY IN UNICORN.
No installable update is generated. The display bus and UART send are mocked;
interrupts, USB bridge pacing, boot/recovery, and real RAM ownership are not proven.
"""
import argparse
import binascii
from collections import deque
import hashlib
import json
import random
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
import emulator_runtime
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import *

from stream_packets import RAM_BEGIN, frame_packets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'references'))
from audit_pixel_patch import audit

MODULE = 0x08010000  # Emulation-only mapping; NOT verified real Flash space.
RAM = 0x20000000
RX = 0x21000000     # Emulation-only input fixture, never a firmware allocation.
STOP = 0x0800FFF0
SP = 0x20003B58
STATE = 0x20001340
FB = 0x200017F0
STAGE = 0x20001BF0
MODE = 0x20002A20
SENTINEL = bytes([0xA5]) * 1024
FORBIDDEN = {0x080082EC, 0x08008424, 0x080084C8, 0x08008656,
             0x08009140, 0x08009114, 0x0800A684, 0x0800A732,
             0x08009262, 0x080092D6, 0x080060A4, 0x08006116}
ENTRIES = dict(begin=MODULE, data=MODULE + 4, end=MODULE + 8, gate=MODULE + 12)
SAVED = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]


class Machine:
    def __init__(self, image, module):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(0x08000000, 0x20000)
        self.uc.mem_write(0x08002000, image)
        self.uc.mem_write(MODULE, module)
        self.uc.mem_map(RAM, 0x4000)
        self.uc.mem_write(RAM, b'\xa5' * 0x4000)
        self.uc.mem_write(MODE, b'\x03')
        self.uc.mem_write(0x20002ABC, b'\x01')  # Original ACK sender enabled.
        self.uc.mem_map(RX, 0x1000)
        self.acks, self.frames, self.flash_calls = [], [], []
        self.instructions = 0
        self.input_span = 0
        self.input_pointer = RX
        self.returned = False
        self.trace = deque(maxlen=12)
        self.uc.hook_add(UC_HOOK_CODE, self.code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.write)
        # Scope the input guard to its actual fixture. Unicorn 2.1.4 can
        # misexecute stock ITTT/memcmp loops with a global MEM_READ hook.
        self.uc.hook_add(UC_HOOK_MEM_READ, self.read, begin=RX, end=RX+0xfff)

    def code(self, uc, address, size, _):
        self.instructions += 1
        self.trace.append(hex(address))
        if address == STOP:
            self.returned = True
            uc.emu_stop()
        elif address in FORBIDDEN:
            self.flash_calls.append(hex(address))
            raise AssertionError(f'Flash/update entry reached: {address:#x}')
        elif address == 0x08005132:
            pointer = uc.reg_read(UC_ARM_REG_R0)
            assert pointer == FB
            self.frames.append(bytes(uc.mem_read(pointer, 1024)))
            self.peripheral_return()
        elif address == 0x08008924:
            pointer, count = uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)
            assert count == 13
            self.acks.append(bytes(uc.mem_read(pointer, count)))
            self.peripheral_return()

    def peripheral_return(self):
        # AAPCS permits external callees to clobber r0-r3/r12.
        for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                    UC_ARM_REG_R3, UC_ARM_REG_R12):
            self.uc.reg_write(reg, 0xDEAD1234)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def write(self, uc, access, address, size, value, _):
        allowed = [(STATE, STATE + 24), (FB, FB + 1024),
                   (STAGE, STAGE + 1024), (0x20002A5C, 0x20002A5D),
                   (0x20003200, SP)]
        if not any(lo <= address and address + size <= hi for lo, hi in allowed):
            raise AssertionError(f'Unexpected CPU write {address:#x}+{size}')

    def read(self, uc, access, address, size, value, _):
        if RX <= address < RX + 0x1000:
            assert self.input_pointer <= address and address + size <= self.input_pointer + self.input_span, 'Read beyond verified input'

    def call(self, entry, packet=b'', now=0, available=None, alignment=0):
        assert 0 <= alignment <= 3 and len(packet) + alignment <= 4096
        self.input_pointer = RX + alignment
        self.uc.mem_write(self.input_pointer, packet)
        self.input_span = len(packet) if available is None else available
        assert 0 <= self.input_span <= len(packet)
        self.returned = False
        self.uc.reg_write(UC_ARM_REG_SP, SP)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.uc.reg_write(UC_ARM_REG_R0, now if entry == 'gate' else self.input_pointer)
        self.uc.reg_write(UC_ARM_REG_R1, now & 0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_R2, self.input_span)
        for index, reg in enumerate(SAVED):
            self.uc.reg_write(reg, 0xC0010000 + index)
        try:
            self.uc.emu_start(ENTRIES[entry] | 1, 0xFFFFFFFF, count=150000)
        except Exception as error:
            pc = self.uc.reg_read(UC_ARM_REG_PC)
            raise RuntimeError(f'{entry}: PC={pc:#010x}, SP='
                               f'{self.uc.reg_read(UC_ARM_REG_SP):#010x}, '
                               f'trace={list(self.trace)}') from error
        assert self.returned, 'Instruction bound exceeded'
        assert self.uc.reg_read(UC_ARM_REG_SP) == SP, 'Stack imbalance'
        for index, reg in enumerate(SAVED):
            assert self.uc.reg_read(reg) == 0xC0010000 + index, 'Callee-saved register changed'
        return self.uc.reg_read(UC_ARM_REG_R0)

    def framebuffer(self):
        return bytes(self.uc.mem_read(FB, 1024))


def validate(image, module):
    checks, machines = [], []
    def fresh():
        m = Machine(image, module)
        machines.append(m)
        return m
    def good_frame(m, pixels, now=100, chunk_size=50):
        previous = m.framebuffer()
        assert m.call('begin', RAM_BEGIN, now) == 1
        assert m.acks[-1] == b'MCU+DAT+STA\r\n'
        packets = frame_packets(pixels, chunk_size=chunk_size)
        for i, packet in enumerate(packets):
            assert m.call('data', packet, now + i) == 1
            if i < len(packets) - 1:
                assert m.framebuffer() == previous, 'Partial frame displayed'
                assert m.acks[-1] == b'MCU+DAT+NXT\r\n'
        assert m.frames[-1] == pixels and m.framebuffer() == pixels
        assert m.acks[-1] == b'MCU+DAT+END\r\n'
        assert m.call('end') == 1
        return packets

    m = fresh()
    before = bytes(m.uc.mem_read(RAM, 0x3000))
    assert m.call('gate', now=1) == 0
    assert m.call('begin', b'\x00\x04\x00\x00\x04\x28') == 0
    assert bytes(m.uc.mem_read(RAM, 0x3000)) == before
    checks.append('default inactive and ordinary START falls back without mutation')

    first = bytes(range(256)) * 4
    second = bytes(255 - x for x in first)
    m = fresh()
    good_frame(m, first)
    good_frame(m, second, 200)
    assert len(m.frames) == 2 and not m.flash_calls
    checks.append('two distinct frames, old frame retained until complete, original ACK/copy/flush wrappers')

    m = fresh()
    m.call('begin', RAM_BEGIN)
    packets = frame_packets(first)
    m.call('data', packets[0], 1)
    snapshot = bytes(m.uc.mem_read(STAGE, 1024))
    assert m.call('data', packets[0], 2) == 1
    assert bytes(m.uc.mem_read(STAGE, 1024)) == snapshot
    for p in packets[1:]:
        assert m.call('data', p, 3) == 1
    count = len(m.frames)
    assert m.call('data', packets[-1], 4) == 1
    assert m.call('end') == 1 and len(m.frames) == count
    checks.append('identical previous fragment and final fragment retries are idempotent')

    for kind in ('crc', 'order', 'length', 'empty', 'oversize', 'duplicate_changed', 'early_end', 'overrun'):
        m = fresh()
        m.call('begin', RAM_BEGIN)
        packets = frame_packets(first)
        if kind == 'crc':
            for p in packets[:-1]: m.call('data', p)
            bad = packets[-1][:-1] + bytes([packets[-1][-1] ^ 1])
        elif kind == 'order': bad = packets[1]
        elif kind == 'length': bad = b'\x00\x35' + packets[0][2:]
        elif kind == 'empty': bad = b'\x00\x04\0\0\0\0'
        elif kind == 'oversize': bad = b'\x00\x37\0\0\0\0' + bytes(51)
        elif kind == 'duplicate_changed':
            m.call('data', packets[0])
            bad = packets[0][:-1] + bytes([packets[0][-1] ^ 1])
        elif kind == 'early_end':
            m.call('data', packets[0])
            assert m.call('end') == 2
            bad = packets[1]
        elif kind == 'overrun':
            for p in packets[:-1]: m.call('data', p)
            bad = (31).to_bytes(2, 'big') + packets[-1][2:] + bytes(1)
            # A valid-sized 27-byte fragment exceeds the 26 remaining bytes.
        assert m.call('data', bad) == 2, kind
        assert m.framebuffer() == SENTINEL and not m.frames, kind
        assert m.call('data', packets[0]) == 2, 'Late data must not fall through'
        assert m.call('gate', now=0) == 0
        checks.append(f'reject {kind}; no partial display, late packets swallowed')

    m = fresh()
    m.uc.mem_write(MODE, b'\0')
    assert m.call('begin', RAM_BEGIN) == 2
    assert not m.acks and not m.frames
    checks.append('stream activation outside resource mode rejected')

    for change_mode in (False, True):
        m = fresh()
        m.call('begin', RAM_BEGIN, 100)
        if change_mode: m.uc.mem_write(MODE, b'\x04')
        assert m.call('gate', now=101 if change_mode else 2101) == 0
        assert m.call('data', frame_packets(first)[0], 2102) == 2
    checks.append('mode change and inactivity release renderer without late-packet fallback')

    m = fresh()
    m.call('begin', RAM_BEGIN, 0xFFFFFFF0)
    assert m.call('gate', now=0x20) == 1
    assert m.call('gate', now=0x1000) == 0
    checks.append('unsigned millisecond wrap handled')

    m = fresh()
    m.call('begin', RAM_BEGIN, 100)
    assert m.call('data', frame_packets(first)[0], 2101) == 2
    good_frame(m, second, 2200)
    checks.append('timeout enforced inside receiver before any renderer tick; explicit restart recovers')

    for alignment in (1, 2, 3):
        m = fresh()
        assert m.call('begin', RAM_BEGIN, alignment=alignment) == 1
        for p in frame_packets(first):
            assert m.call('data', p, alignment=alignment) == 1
        assert m.frames == [first]
    checks.append('all packet alignments work using byte loads, including odd original handler pointer')

    m = fresh()
    good_frame(m, first, chunk_size=1)
    good_frame(m, second, 2000, chunk_size=49)
    checks.append('CRC split across packets and variable fragment boundaries')

    rng = random.Random(0x50495845)
    m = fresh()
    for i in range(12):
        good_frame(m, rng.randbytes(1024), now=i * 100, chunk_size=rng.randint(7, 50))
    checks.append('12 reproducible random frames match an independent host CRC implementation')

    for i in range(160):
        m = fresh()
        m.call('begin', RAM_BEGIN)
        packet = rng.randbytes(rng.randint(0, 80))
        available = rng.randint(0, len(packet))
        result = m.call('data', packet, available=available)
        assert result == 2 and not m.frames
    checks.append('160 malformed/truncated packets stay inside declared input and RAM write bounds')

    assert all(not m.flash_calls for m in machines)
    return dict(checks=checks, checks_passed=len(checks), machine_instances=len(machines),
                arm_instructions=sum(m.instructions for m in machines),
                frames_committed=sum(len(m.frames) for m in machines),
                forbidden_flash_calls=0,
                monitored_write_regions=['24-byte experiment state', '1024-byte staging',
                                         '1024-byte framebuffer', 'upload flag', 'bounded call stack'])


def validate_themes(image, module, output):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QFont
    app = QGuiApplication.instance() or QGuiApplication([])
    sys.path.insert(0, str(ROOT))
    from halo.pixels import init_fonts, render, preview_image
    init_fonts()
    samples = [('kitty', '时钟', '20:26:08', 'Kitty / clock'),
               ('ion', '时钟', '20:26:09', 'Ion / clock'),
               ('peach', '歌词', '月光落在小猫的梦里', 'Peach / sample text'),
               ('matrix', '歌词', '让像素随着音乐跳动', 'Matrix / sample text'),
               ('paper', '系统监控', '', 'Paper / sample fan value'),
               ('terminal', '系统监控', '', 'Terminal / sample CPU value')]
    m = Machine(image, module)
    sheet = QImage(1072, 388, QImage.Format.Format_RGB32)
    sheet.fill(QColor('#111827'))
    p = QPainter(sheet)
    p.setFont(QFont('Arial', 11))
    p.setPen(QColor('#e5e7eb'))
    p.drawText(24, 26, 'OFFLINE ARM EMULATOR - NOT A DEVICE CAPTURE')
    try:
        for index, (theme, mode, text, label) in enumerate(samples):
            key = 'fan' if theme == 'paper' else 'cpu'
            config = dict(theme=theme, themes=True, monitor_metrics=[key], monitor_view='bar')
            snapshot = {'metrics': [dict(key=key, short='FAN' if key == 'fan' else 'CPU',
                                        text='1200 RPM' if key == 'fan' else '36%',
                                        value=1200 if key == 'fan' else 36, scale=2000 if key == 'fan' else 100)]}
            frame = render(text, mode, config, 0, snapshot=snapshot)
            assert m.call('begin', RAM_BEGIN, index * 100) == 1
            previous = m.framebuffer()
            packets = frame_packets(frame.pixels)
            for i, packet in enumerate(packets):
                assert m.call('data', packet, index * 100 + i) == 1
                if i < len(packets) - 1: assert m.framebuffer() == previous
            assert m.frames[-1] == frame.pixels
            x, y = 24 + (index % 2) * 524, 50 + (index // 2) * 110
            p.drawText(x, y + 14, label)
            im = preview_image(m.frames[-1]).scaled(512, 64, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                   Qt.TransformationMode.FastTransformation)
            p.drawImage(x, y + 25, im)
    finally:
        p.end()
    assert sheet.save(str(output / 'validated-graphics.png'))
    return dict(frames_committed=len(m.frames), byte_exact=True, forbidden_flash_calls=len(m.flash_calls),
                arm_instructions=m.instructions, preview='validated-graphics.png',
                preview_is_hardware_capture=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'firmware-analysis/ram-stream-lab')
    args = parser.parse_args()
    image = (ROOT / 'firmware-analysis/v137/mcu.bin').read_bytes()
    audit(image)
    source = (Path(__file__).with_name('ram_stream_thumb.s')).read_text(encoding='utf-8')
    source = '\n'.join(line.split('//', 1)[0] for line in source.splitlines())
    module = bytes(Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(source, addr=MODULE)[0])
    result = validate(image, module)
    args.output.mkdir(parents=True, exist_ok=True)
    result['existing_theme_pipeline'] = validate_themes(image, module, args.output)
    result.update(status='EMULATION_ONLY_NOT_INSTALLABLE', module_bytes=len(module),
                  module_sha256=hashlib.sha256(module).hexdigest(),
                  official_mcu_sha256=hashlib.sha256(image).hexdigest(),
                  virtual_module_address=hex(MODULE),
                  real_firmware_placement_verified=False, device_written=False,
                  limitations=['No actual dispatcher or renderer hooks installed',
                               'Real RAM ownership and monotonic time source unverified',
                               'Display peripheral and UART send mocked; interrupts not emulated',
                               'USB bridge scheduling and ACK delivery not emulated',
                               'Boot recovery and modified-image acceptance unresolved'])
    # A bare analysis module, deliberately not a combined MCU/update .bin.
    (args.output / 'ram_stream.thumb').write_bytes(module)
    dis = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    (args.output / 'ram_stream-disassembly.txt').write_text('\n'.join(
        f'{i.address:08x}: {i.bytes.hex():12} {i.mnemonic} {i.op_str}'
        for i in dis.disasm(module, MODULE)) + '\n', encoding='utf-8')
    (args.output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
