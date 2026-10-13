"""Pinned MCU-only color/transition update. Default: read-only preflight.

Rollback is to the exact previously installed matrix build. It needs a working
MCU application; this is not a tested dead-MCU recovery method.
"""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'firmware-fullscreen'))
import stage_fullscreen as transfer
OLD='ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884'
NEW='9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e'
def prepared(rollback=False):
    report=transfer.read_json(HERE/'validation.json'); b=report['baseline']
    assert report['candidate_sha256']==NEW and report['installed_sha256']==OLD
    assert b['candidate_sha256']==NEW and b['baseline']['legacy']['checks_passed']==19
    assert b['baseline']['checks_passed']==8 and b['fullscreen_checks_passed']==11
    assert report['color_checks_passed']>=20 and report['forbidden_flash_calls']==0
    assert report['ota']['upgrade']['exact'] and report['ota']['rollback']['exact']
    assert b['stock_graphics']['theme_cases']==30
    backup=Path((transfer.PROJECT/'validation/color-backup-path.txt').read_text(encoding='utf-8-sig').strip()).resolve()
    assert backup.is_relative_to((transfer.PROJECT/'validation').resolve())
    for item in transfer.read_json(backup/'backup-manifest.json')['files']:
        path=(backup/item['path']).resolve()
        assert path.is_relative_to(backup) and transfer.digest(path)==item['sha256'],path
    assert transfer.digest(backup/'installed-matrix.bin')==OLD
    records=transfer.read_json(backup/'records.json')
    identities=[transfer.read_json(backup/r['backup']) for r in records]; identity=identities[0]
    assert all(r['candidate_sha256']==OLD and r['serial']==identity['serial'] and r['graphics_visually_confirmed'] for r in identities)
    file=backup/'installed-matrix.bin' if rollback else HERE/'mcu-hpl2-color.bin'
    expected=OLD if rollback else NEW; raw=file.read_bytes(); transfer.PinnedTransfer(raw,expected)
    _,notify=transfer.images()
    return raw,notify,expected,backup,records,identity
if __name__=='__main__':
    transfer.OLD,transfer.NEW=OLD,NEW
    transfer.prepared=prepared
    transfer.main('color-live')
