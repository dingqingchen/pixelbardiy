"""Bounded post-reboot RAM-only commissioning. No fake validation record.

Requires exact completed update, observed reboot, device binding and shared lock.
This script sends only HPL2 RAM/display commands; never update or resource data.
"""
import argparse
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
from stage_fullscreen import HERE, PROJECT, ROOT, NEW, read_json


def main(live_folder='fullscreen-live', expected=NEW, rain=False):
    assert live_folder in ('fullscreen-live', 'matrix-live')
    parser = argparse.ArgumentParser()
    parser.add_argument('--after-observed-reboot', action='store_true', required=True)
    parser.add_argument('--timeout-release', action='store_true')
    args = parser.parse_args()
    import psutil
    assert not [p for p in psutil.process_iter(['name']) if (p.info['name'] or '').casefold()
                in ('halostudio.exe', 'halostudionet.exe', 'edifier tempohub.exe')]
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QLockFile
    from halo.pixels import Canvas
    from halo.device import HaloLink
    from halo.ram_display import RamDisplay, body, ACQUIRE, HEARTBEAT, restore_clock
    from halo.ram_codec import encode, Encoded, packets
    from halo.vendor_core import enumerate_halo_devices
    app = QApplication([])
    lock = QLockFile(str(Path(tempfile.gettempdir()) / 'halo-studio-2d99-a106.lock'))
    lock.setStaleLockTime(0)
    assert lock.tryLock(50)
    out = PROJECT / 'validation' / live_folder
    latch = read_json(out / 'UPGRADE_STARTED.json')
    trace = [json.loads(s) for s in Path(latch['trace']).read_text().splitlines()]
    assert latch['candidate'] == expected and any(e['event'] == 'mcu_transfer_complete' and e['candidate'] == expected
        and e['bytes'] == 57252 and e['main_controller_bytes'] == 0 for e in trace)
    record = read_json(PROJECT / 'dist/HaloStudioNet/runtime/mcu-installation.json')
    devices = enumerate_halo_devices()
    assert len(devices) == 1 and devices[0].serial_number == record['serial']
    assert devices[0].path.decode().casefold() == record['hid_path'].casefold()
    assert record.get('pending_candidate_sha256') == expected or record['candidate_sha256'] == expected
    events = []
    def event(kind, **data):
        row = dict(event=kind, time=time.time(), **data)
        events.append(row)
        print(json.dumps(row), flush=True)
    d = RamDisplay(Path('unused-commissioning-record'))
    try:
        # Commissioning bypass is limited to this bounded diagnostic, tied to
        # the exact transfer above. Normal clients retain the visual gate.
        HaloLink.connect(d)
        assert d.query(0xC6) == b'\x01\x03\x07'
        d.authorized = d.codec_enabled = True
        time.sleep(2.2)
        status = d.query(0xEE)
        d.restore_color = '#' + status[1:4].hex()
        d.screen_color('#90EFCA')
        restore_clock(d, '#90EFCA')
        d.sid = secrets.randbits(32) or 1
        d.owned = True
        d._control(body(ACQUIRE, d.sid), 3)
        base = None
        count = (1 if args.timeout_release else 3) if rain else (2 if args.timeout_release else 8)
        for number in range(1, count + 1):
            c = Canvas()
            c.text(f'{number:02}', 0, 1, 2)
            c.text(f'{99-number:02}', 232, 17, 2)
            c.text('FULL SCREEN', 50, 1, 2)
            for x in range(2, 252, 10):
                c.rect(x, 22 if number % 2 else 14, 6, 7, fill=True)
            if rain:
                c = Canvas()
                c.text('HALO STUDIO', 63, 9, 2)
                c.rect(3, 3, 250, 26)
            pixels = bytes(c.data)
            style = 5 if rain else 0 if number == 1 else 3 if number <= 5 else 4
            item = encode(pixels, base, number - 1)
            metadata = bytearray(item.metadata)
            metadata[1] = style
            if rain:
                metadata[2] = 32
            batch = packets(d.sid, number, Encoded(item.codec, item.data, bytes(metadata)))
            started = time.monotonic()
            for index, request in enumerate(batch):
                d._control(request, 5 if index == len(batch) - 1 else 3)
            event('frame', number=number, animation=style, bytes=len(item.data), packets=len(batch), seconds=time.monotonic()-started)
            base = pixels
            until = time.monotonic() + ((.35 if args.timeout_release else 6) if rain else 2.3)
            while time.monotonic() < until:
                d._control(body(HEARTBEAT, d.sid), 3)
                time.sleep(.35)
        if args.timeout_release:
            event('heartbeat_stopped')
            d.owned = False
            HaloLink.close(d)
            time.sleep(8)
    finally:
        d.shutdown()
    link = HaloLink()
    states = []
    try:
        link.connect()
        for delay in (0, 3, 4):
            time.sleep(delay)
            raw = link.query(0xEE)
            states.append(raw.hex())
            assert raw[5:8] == b'\x01\x00\x00'
    finally:
        link.close()
        lock.unlock()
    file = out / ('timeout-' if args.timeout_release else 'smoke-')
    file = file.with_name(file.name + time.strftime('%Y%m%d-%H%M%S') + '.json')
    file.write_text(json.dumps(dict(candidate_sha256=expected, events=events, post_exit=states,
        firmware_writes=0, visual_verification_required=True), indent=2), encoding='utf-8')
    event('complete', report=str(file), post_exit=states)


if __name__ == '__main__':
    main()
