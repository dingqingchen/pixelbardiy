"""Pinned MCU-only update; default is preflight. Never updates the USB/audio SoC.

Requires exact offline validation and verified known-file backups. A completed
transfer does not prove reboot or display operation. No automatic retry/reset.
Rollback still requires a responsive MCU application; dead-MCU recovery unknown.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
ROOT = PROJECT.parent / 'halo-controller'
if (PROJECT.parent / 'legacy-python/halo').is_dir():
    ROOT = PROJECT.parent / 'legacy-python'  # Backup checks stay mandatory.
sys.path.insert(0, str(ROOT))
from references.stage_mcu_candidate import Transfer, images, packet, parse, SIZE

OLD = 'f7b8ee274ba2439b3211c5eea80206599acff6e80d73dc0c898ba143e2e32f62'
NEW = 'ab4698cf8e826a3c64472ea0af1125653f65f796cd7fcf9013667344e4c0fc50'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PinnedTransfer(Transfer):
    def __init__(self, image, expected):
        assert expected in (OLD, NEW) and len(image) == SIZE and hashlib.sha256(image).hexdigest() == expected
        self.image, self.sent, self.count, self.staged = image, 0, 0, False


def prepared(rollback=False):
    report = read_json(HERE / 'validation.json')
    assert report['candidate_sha256'] == NEW and report['installed_sha256'] == OLD
    assert report['baseline']['legacy']['checks_passed'] == 19 and report['baseline']['checks_passed'] == 8
    assert report['fullscreen_checks_passed'] == 11 and report['forbidden_flash_calls'] == 0
    assert report['ota']['upgrade']['exact'] and report['ota']['rollback']['exact']
    assert report['stock_graphics']['theme_cases'] == 30
    backup = Path((PROJECT / 'validation/fullscreen-backup-path.txt').read_text(encoding='utf-8-sig').strip()).resolve()
    assert backup.is_relative_to((PROJECT / 'validation').resolve())
    manifest = read_json(backup / 'backup-manifest.json')
    for item in manifest['files']:
        target = (backup / item['path']).resolve()
        assert target.is_relative_to(backup) and digest(target) == item['sha256'], str(target)
    assert digest(backup / 'installed-codec.bin') == OLD
    records = read_json(backup / 'records.json')
    identities = [read_json(backup / r['backup']) for r in records]
    identity = identities[0]
    assert all(r['candidate_sha256'] == OLD and r['serial'] == identity['serial'] and r['graphics_visually_confirmed'] for r in identities)
    file = backup / 'installed-codec.bin' if rollback else HERE / 'mcu-hpl2-fullscreen.bin'
    expected = OLD if rollback else NEW
    raw = file.read_bytes()
    PinnedTransfer(raw, expected)
    _, notify = images()
    return raw, notify, expected, backup, records, identity


def main(live_folder='fullscreen-live'):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--flash-authorized', action='store_true')
    cli.add_argument('--rollback', action='store_true')
    args = cli.parse_args()
    raw, notify, expected, backup, records, identity = prepared(args.rollback)
    import psutil
    assert not [p.info for p in psutil.process_iter(['name']) if (p.info['name'] or '').casefold()
                in ('halostudio.exe', 'halostudionet.exe', 'edifier tempohub.exe')], 'Exit display controllers first'
    from PySide6.QtCore import QCoreApplication, QLockFile
    app = QCoreApplication([])
    lock = QLockFile(str(Path(tempfile.gettempdir()) / 'halo-studio-2d99-a106.lock'))
    lock.setStaleLockTime(0)
    assert lock.tryLock(50), 'Display controller lock busy'
    import hid
    from halo.vendor_core import enumerate_halo_devices
    devices = enumerate_halo_devices()
    assert len(devices) == 1 and devices[0].serial_number == identity['serial']
    assert devices[0].path.decode().casefold() == identity['hid_path'].casefold()
    assert live_folder in ('fullscreen-live', 'matrix-live', 'color-live')
    out = PROJECT / 'validation' / live_folder
    out.mkdir(exist_ok=True)
    kind = 'rollback' if args.rollback else 'upgrade'
    trace = out / (kind + '-' + time.strftime('%Y%m%d-%H%M%S') + '.jsonl')
    with trace.open('x', encoding='utf-8') as log:
        def record(event, **data):
            row = dict(time=time.time(), event=event, **data)
            log.write(json.dumps(row) + '\n')
            log.flush()
            if event not in ('tx', 'rx'):
                print(json.dumps(row), flush=True)
        handle = hid.device()
        try:
            handle.open_path(devices[0].path)
            handle.set_nonblocking(True)
            def send(raw):
                record('tx', report=raw.hex())
                if handle.write(raw) != 64:
                    raise RuntimeError('Incomplete HID write; no retry')
            def receive(timeout):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    data = bytes(handle.read(64))
                    if data:
                        record('rx', report=data.hex())
                        return parse(data)
                    time.sleep(.003)
                raise TimeoutError('No response; no automatic retry or reset')
            time.sleep(2.2)  # Let any former process lease expire.
            for _ in range(64):
                if not handle.read(64):
                    break
            send(packet(0xC6, device_type=0xED))
            assert receive(3) == (0xC6, b'\x01\x03\x07')
            record('preflight', candidate=expected, backup=str(backup), files_verified=len(read_json(backup / 'backup-manifest.json')['files']))
            if not args.flash_authorized:
                return
            latch = out / (kind.upper() + '_STARTED.json')
            with latch.open('x', encoding='utf-8') as marker:
                json.dump(dict(candidate=expected, trace=str(trace), backup=str(backup)), marker)
                marker.flush()
                os.fsync(marker.fileno())
            for item in records:
                path = Path(item['source'])
                data = read_json(path)
                data.update(graphics_visually_confirmed=False, pending_candidate_sha256=expected, pending_trace=str(trace))
                path.write_text(json.dumps(data, indent=2), encoding='utf-8')
            record('staging_started', bytes=SIZE, boot_confirmed=False)
            tx = PinnedTransfer(raw, expected)
            send(packet(0x10, notify))
            started = time.monotonic()
            while not tx.staged:
                command, data = receive(12)
                if command != 0x11:
                    raise RuntimeError('Unexpected update command')
                wire = tx.accept(data)
                if wire is not None:
                    send(wire)
                    if tx.count % 200 == 0 or tx.sent == SIZE:
                        record('progress', bytes=tx.sent, packets=tx.count)
                if time.monotonic() - started > 300:
                    raise TimeoutError('Transfer deadline; no retry')
            record('mcu_transfer_complete', candidate=expected, bytes=tx.sent, packets=tx.count,
                   main_controller_bytes=0, seconds=time.monotonic() - started, boot_confirmed=False)
        except Exception as exc:
            record('stopped', reason=str(exc))
            raise
        finally:
            handle.close()
            lock.unlock()


if __name__ == '__main__':
    main()
