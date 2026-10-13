"""Rebuild/verify pinned display firmware offline; never opens a USB device."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'firmware-lab'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-mcu',type=Path,required=True)
    args=parser.parse_args()
    from references.audit_pixel_patch import audit
    raw=args.original_mcu.read_bytes(); audit(raw)
    work=ROOT/'firmware-analysis/v137';work.mkdir(parents=True,exist_ok=True)
    if args.original_mcu.resolve() != (work/'mcu.bin').resolve(): shutil.copy2(args.original_mcu,work/'mcu.bin')
    import validate_codec
    import validate_ota_compat
    from halo.ram_codec import FIRMWARE_SHA
    original,image,entries,layout=validate_codec.build()
    if hashlib.sha256(image).hexdigest()!=FIRMWARE_SHA: raise RuntimeError('Rebuilt image hash differs; do not flash')
    result=validate_codec.check(image,entries)
    validate_ota_compat.main()
    if result['checks_passed']!=8 or result['legacy']['checks_passed']!=19:
        raise RuntimeError('Firmware validation counts differ')
    out=ROOT/'firmware-analysis/rebuilt';out.mkdir(parents=True,exist_ok=True)
    (out/'mcu-hpl2-codec.bin').write_bytes(image)
    (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(sha256=FIRMWARE_SHA,bytes=len(image),checks=8,legacy_checks=19,usb_access=False,output=str(out))))


if __name__=='__main__':main()
