"""Pinned 1.3.7 display-MCU updater. CLI actions are explicit, never automatic.

Ordinary preflight only reads version. Flash sends the reviewed MCU image only;
the USB/audio image and bootloader are absent. A staged image is not boot proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import time

from .ram_codec import FIRMWARE_SHA
from references.ota_chunks import next_end, plan

SIZE = 57252
FACTORY_SHA = '71c6274c982715c56c99ef61fa568dd88a92c883d97ea7784721fba9de96fd60'
NOTIFY = bytes.fromhex('000c48dc0103070040010000dfa4000b68f9')


def packet(command, payload=b'', device_type=0xEC):
    if len(payload) > 57: raise ValueError('Oversized HID payload')
    raw = bytes((0x2E, 0xAA, device_type, command)) + len(payload).to_bytes(2, 'big') + payload
    return (raw + bytes((sum(raw[1:]) & 255,))).ljust(64, b'\0')


def parse(raw):
    if len(raw) < 7 or raw[:3] != b'\x2f\xbb\xec': raise ValueError('Unexpected report header')
    size = int.from_bytes(raw[4:6], 'big')
    if size > 57 or len(raw) < size+7 or raw[6+size] != sum(raw[1:6+size]) & 255:
        raise ValueError('Invalid report length/checksum')
    return raw[3], raw[6:6+size]


def validate_image(image):
    if len(image) != SIZE or hashlib.sha256(image).hexdigest() != FIRMWARE_SHA:
        raise ValueError('Only the reviewed HPL2 codec MCU image is allowed')
    boundaries = plan(image)
    if len(boundaries) != 1057: raise ValueError('Unexpected packet plan')
    return boundaries


class Transfer:
    def __init__(self, image):
        validate_image(image)
        self.image = image
        self.sent = self.count = 0
        self.staged = False

    def accept(self, payload):
        if self.staged or len(payload) != 7: raise ValueError('Unexpected DFU state or format')
        status = payload[0]
        count = int.from_bytes(payload[1:3], 'big')
        requested = int.from_bytes(payload[3:7], 'big')
        if status == 10:
            if self.sent != SIZE: raise ValueError('Premature USB-main firmware request')
            self.staged = True
            return None
        if status != 9 or count != 55 or self.sent >= SIZE or requested not in (0, self.sent):
            raise ValueError('Unsupported status, size or offset; no retry')
        end = next_end(self.image, self.sent)
        wire = packet(0x11, bytes((9, int(end == SIZE))) + self.image[self.sent:end])
        self.sent = end
        self.count += 1
        return wire


def controllers():
    import psutil
    return [p.info['name'] for p in psutil.process_iter(['name'])
            if p.pid != os.getpid() and (p.info['name'] or '').casefold()
            in ('halostudio.exe', 'edifier tempohub.exe')]


def backup(app_dir, factory, destination):
    raw = factory.read_bytes()
    if len(raw) != 805084 or hashlib.sha256(raw).hexdigest() != FACTORY_SHA:
        raise ValueError('Backup must be the exact original Halo PixelBar-PC_137 full package')
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(factory, destination/'factory-PC_137.bin')
    for name in ('mcu-installation.json', 'settings.json', 'pixel/settings.json'):
        source = app_dir/'runtime'/name
        if source.is_file():
            target = destination/'runtime'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    exe = app_dir/'HaloStudio.exe'
    if exe.is_file(): shutil.copy2(exe, destination/'HaloStudio.exe')
    manifest = {'device_flash_readback': False, 'dead_mcu_usb_recovery_established': False,
                'factory_package_sha256': FACTORY_SHA, 'files': []}
    for file in sorted(destination.rglob('*')):
        if file.is_file():
            manifest['files'].append({'path':file.relative_to(destination).as_posix(),
                'sha256':hashlib.sha256(file.read_bytes()).hexdigest(), 'bytes':file.stat().st_size})
    (destination/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for item in manifest['files']:
        if hashlib.sha256((destination/item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Backup readback mismatch')
    return manifest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def verify_display(app_dir, device, image, pending):
    # USB bridge ACK cannot identify installed MCU code. This is an explicit
    # operator test after a completed transfer (or an existing confirmed record).
    from .ram_display import RamDisplay
    from .pixels import Canvas, PixelFrame
    record = dict(candidate_sha256=FIRMWARE_SHA, serial=device.serial_number,
                  hid_path=device.path.decode(), graphics_visually_confirmed=True)
    with tempfile.TemporaryDirectory(prefix='halo-commission-') as temp:
        probe_record = Path(temp)/'installation.json'
        write_json(probe_record, record)
        link = RamDisplay(probe_record)
        try:
            link.connect('#8DF5B4')
            for number in (1, 2):
                canvas = Canvas(); canvas.rect(0,0,256,32)
                canvas.text(f'RAM LIVE 0{number}', 50, 12)
                # Cat ears/eyes are independent of Windows fonts.
                canvas.line(8,22,8,6); canvas.line(8,6,16,11)
                canvas.line(16,11,24,6); canvas.line(24,6,24,22)
                canvas.line(8,22,24,22); canvas.dot(12,16); canvas.dot(20,16)
                frame = PixelFrame(bytes(canvas.data), 'RAM LIVE', 'RAM LIVE')
                link.offer(frame, '#8DF5B4', urgent=True, animation=number-1)
                deadline = time.monotonic()+4
                while time.monotonic() < deadline:
                    link.tick(time.monotonic()); time.sleep(.01)
                if link.busy: raise RuntimeError('RAM frame did not finish')
        finally:
            link.shutdown()
    print('Verify cat, border, RAM LIVE 01 -> 02, no upload prompt, then stable stock clock.')
    if input('If ALL were correct, type YES (anything else leaves graphics disabled): ').strip() != 'YES':
        raise RuntimeError('Visual verification not confirmed; installation record was not written')
    record.update(verified_at=time.strftime('%Y-%m-%dT%H:%M:%S'),
                  image_bytes=len(image), verification='operator visual RAM test and stock-clock restoration')
    write_json(app_dir/'runtime/mcu-installation.json', record)
    if pending.exists():
        pending.replace(pending.with_name('verified-'+time.strftime('%Y%m%d-%H%M%S')+'.json'))
    print('Verified. HaloStudio can now use RAM graphics on this USB interface.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--flash', action='store_true', help='Explicitly stage the pinned display MCU image')
    action.add_argument('--verify-display', action='store_true', help='Run the post-reboot visual RAM test')
    parser.add_argument('--offline-check', action='store_true', help='Validate files/packet plan without opening USB')
    parser.add_argument('--app-dir', type=Path)
    parser.add_argument('--serial', help='Exact serial printed by preflight; mandatory before flash')
    parser.add_argument('--backup-file', type=Path, help='Exact original PC_137 full factory package')
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args(argv)
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    image = (base/'firmware/hpl2-codec/mcu-hpl2-codec.bin').read_bytes()
    boundaries = validate_image(image)
    print(json.dumps(dict(candidate_sha256=FIRMWARE_SHA, bytes=len(image), packets=len(boundaries),
                         usb_main_bytes=0, bootloader_included=False, device_flash_readback=False)))
    if args.offline_check:
        if args.flash or args.verify_display: parser.error('Offline check cannot flash or verify hardware')
        return 0
    if (args.flash or args.verify_display) and not args.app_dir:
        parser.error('--app-dir must point to the HaloStudio application directory')
    if controllers(): raise RuntimeError('Exit HaloStudio and TempoHub completely before using this tool')
    from PySide6.QtCore import QCoreApplication, QLockFile
    app = QCoreApplication([])
    lock = QLockFile(str(Path(tempfile.gettempdir())/'halo-studio-2d99-a106.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(50): raise RuntimeError('Another display controller owns the lock')
    from .vendor_core import enumerate_halo_devices
    devices = enumerate_halo_devices()
    if len(devices) != 1: raise RuntimeError('Connect exactly one supported VID 2D99/PID A106 MI04 device')
    device = devices[0]
    import hid
    handle = hid.device()
    try:
        handle.open_path(device.path); handle.set_nonblocking(True)
        for _ in range(64):
            if not handle.read(64): break
        if handle.write(packet(0xC6, device_type=0xED)) != 64: raise RuntimeError('Short version query write')
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            response = bytes(handle.read(64))
            if response:
                command, version = parse(response)
                if command != 0xC6 or version != b'\x01\x03\x07': raise RuntimeError('Only bridge 1.3.7 has been tested')
                break
            time.sleep(.003)
        else: raise TimeoutError('No version response')
        print(json.dumps(dict(serial=device.serial_number, version='1.3.7', mode='preflight'), ensure_ascii=False))
        if not args.flash and not args.verify_display: return 0
        app_dir = args.app_dir.resolve()
        if not (app_dir/'HaloStudio.exe').is_file() and not (app_dir/'main.py').is_file():
            raise ValueError('--app-dir is not a HaloStudio installation')
        pending = app_dir/'runtime/firmware-update/pending.json'
        installed = app_dir/'runtime/mcu-installation.json'
        if args.verify_display:
            receipt = json.loads((pending if pending.exists() else installed).read_text(encoding='utf-8'))
            if receipt.get('serial') != device.serial_number or receipt.get('candidate_sha256') != FIRMWARE_SHA:
                raise ValueError('No matching transfer receipt or existing installation record')
            if not receipt.get('transfer_complete') and receipt.get('graphics_visually_confirmed') is not True:
                raise ValueError('Transfer incomplete; RAM verification is not allowed')
            handle.close(); handle = None
            verify_display(app_dir, device, image, pending)
            return 0
        if not args.serial or args.serial != device.serial_number:
            raise ValueError('Pass --serial with the exact preflight serial')
        if pending.exists(): raise RuntimeError('Prior attempt exists; inspect it before any further flash. No automatic retry.')
        if installed.exists():
            current = json.loads(installed.read_text(encoding='utf-8'))
            if current.get('candidate_sha256') == FIRMWARE_SHA and current.get('graphics_visually_confirmed') is True:
                raise RuntimeError('This image is already verified. Do not reflash; use --verify-display if needed.')
        if not args.backup_file: raise ValueError('--backup-file is required before flash')
        backup_dir = (args.backup_dir or app_dir/'backups')/('before-mcu-'+time.strftime('%Y%m%d-%H%M%S'))
        backup(app_dir, args.backup_file.resolve(), backup_dir)
        print('WARNING: independent USB recovery of a dead display MCU is NOT established.')
        if input('To flash this MCU image once, type FLASH '+device.serial_number+': ').strip() != 'FLASH '+device.serial_number:
            raise RuntimeError('Flash not confirmed')
        receipt = dict(serial=device.serial_number, candidate_sha256=FIRMWARE_SHA,
                       backup=str(backup_dir), transfer_complete=False, boot_confirmed=False)
        write_json(pending, receipt)
        if installed.exists():
            current = json.loads(installed.read_text(encoding='utf-8'))
            current.update(graphics_visually_confirmed=False, pending_candidate_sha256=FIRMWARE_SHA)
            write_json(installed, current)
        trace = pending.with_name('transfer-'+time.strftime('%Y%m%d-%H%M%S')+'.jsonl')
        transfer = Transfer(image)
        with trace.open('x', encoding='utf-8') as log:
            def send(wire):
                log.write(json.dumps({'direction':'tx','report':wire.hex()})+'\n'); log.flush()
                if handle.write(wire) != 64: raise RuntimeError('Short write; STOPPED, no retry')
            send(packet(0x10, NOTIFY)); started = time.monotonic()
            while not transfer.staged:
                deadline = time.monotonic()+12
                while time.monotonic() < deadline:
                    response = bytes(handle.read(64))
                    if response: break
                    time.sleep(.003)
                else: raise TimeoutError('No DFU response; STOPPED, no retry')
                log.write(json.dumps({'direction':'rx','report':response.hex()})+'\n'); log.flush()
                command, payload = parse(response)
                if command != 0x11: raise RuntimeError('Unexpected DFU command; STOPPED')
                wire = transfer.accept(payload)
                if wire is not None:
                    send(wire)
                    if transfer.count % 100 == 0 or transfer.sent == SIZE:
                        print(f'{transfer.sent}/{SIZE} bytes, {transfer.count} packets', flush=True)
                if time.monotonic()-started > 300: raise TimeoutError('Total DFU deadline; STOPPED')
        receipt.update(transfer_complete=True, bytes_sent=transfer.sent, packets=transfer.count, trace=str(trace))
        write_json(pending, receipt)
        print('MCU transfer completed; BOOT NOT YET CONFIRMED. Keep power on and wait for normal clock.')
        print('Then run --verify-display --app-dir <HaloStudio directory>. No reset or USB-main update was sent.')
        return 0
    finally:
        if handle is not None: handle.close()


if __name__ == '__main__':
    sys.exit(main() or 0)
