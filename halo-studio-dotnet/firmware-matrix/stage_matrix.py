"""Character-rain update using the proven, pinned MCU-only transfer state machine.

Default is backup validation and read-only version query. No automatic retry.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'firmware-fullscreen'))
import stage_fullscreen as transfer

OLD = 'ab4698cf8e826a3c64472ea0af1125653f65f796cd7fcf9013667344e4c0fc50'
NEW = 'ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884'


def prepared(rollback=False):
    report = transfer.read_json(HERE / 'validation.json')
    assert report['candidate_sha256'] == NEW and report['installed_sha256'] == OLD
    b = report['baseline']
    assert b['candidate_sha256'] == NEW and b['baseline']['legacy']['checks_passed'] == 19
    assert b['baseline']['checks_passed'] == 8 and b['fullscreen_checks_passed'] == 11
    assert report['rain_checks_passed'] == 7 and report['forbidden_flash_calls'] == 0
    assert report['ota']['upgrade']['exact'] and report['ota']['rollback']['exact']
    assert b['stock_graphics']['theme_cases'] == 30
    backup = Path((transfer.PROJECT / 'validation/matrix-backup-path.txt').read_text(encoding='utf-8-sig').strip()).resolve()
    assert backup.is_relative_to((transfer.PROJECT / 'validation').resolve())
    manifest = transfer.read_json(backup / 'backup-manifest.json')
    for item in manifest['files']:
        path = (backup / item['path']).resolve()
        assert path.is_relative_to(backup) and transfer.digest(path) == item['sha256']
    assert transfer.digest(backup / 'installed-fullscreen.bin') == OLD
    records = transfer.read_json(backup / 'records.json')
    identities = [transfer.read_json(backup / r['backup']) for r in records]
    identity = identities[0]
    assert all(r['candidate_sha256'] == OLD and r['serial'] == identity['serial'] and r['graphics_visually_confirmed'] for r in identities)
    file = backup / 'installed-fullscreen.bin' if rollback else HERE / 'mcu-hpl2-matrix.bin'
    expected = OLD if rollback else NEW
    raw = file.read_bytes()
    transfer.PinnedTransfer(raw, expected)
    _, notify = transfer.images()
    return raw, notify, expected, backup, records, identity


if __name__ == '__main__':
    # Select the two fixed reviewed hashes and dedicated backup/attempt files.
    # Reuse unchanged packet handling, ownership, invalidation and one-shot latch.
    transfer.OLD, transfer.NEW = OLD, NEW
    transfer.prepared = prepared
    transfer.main('matrix-live')
