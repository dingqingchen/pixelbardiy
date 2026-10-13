"""Read-only, version-pinned audit of PixelBar display-firmware patch candidates.

Does not generate firmware, connect to a device, or perform an update.
Repeated bytes are reported for inspection, never classified as free code space.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

BASE = 0x08002000
SHA256 = "8fb58ded25d23b5148dc9a37ec57b380e03d65681c13c7f445eff62102010e3b"
SITES = [
    (0x08005EC8, "02f010fa", "DIY start writes resource metadata to SPI Flash"),
    (0x08005F7C, "fef7b4ff", "Complete pixel frame copied into RAM staging buffer"),
    (0x08005FB2, "02f09bf9", "DIY data writes pixel frame to SPI Flash"),
    (0x0800604C, "02f04ef9", "DIY completion writes resource metadata to SPI Flash"),
    (0x08006238, "03f013f8", "OTA data completion calls update-marker writer"),
    (0x080092BC, "fff740ff", "Marker writer calls internal Flash erase/program helper"),
    (0x08009324, "00180008", "Update-marker address literal below application base"),
    (0x080092F4, "fef7faff", "Conditional self-backup calls SPI Flash writer"),
    (0x0800A2CC, "fff703f8", "Initialization calls conditional self-backup routine"),
]


def audit(data):
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        raise ValueError("Unsupported image: SHA-256 does not match official 1.3.7 MCU")
    sites = []
    for address, expected, meaning in SITES:
        offset = address - BASE
        actual = data[offset:offset + len(bytes.fromhex(expected))].hex()
        if actual != expected:
            raise ValueError(f"Evidence bytes differ at {address:#010x}")
        sites.append(dict(address=f"{address:#010x}", file_offset=offset,
                          bytes=actual, meaning=meaning))
    runs = [dict(address=f"{BASE + m.start():#010x}", length=len(m.group()),
                 byte=f"{m.group()[0]:02x}")
            for m in re.finditer(rb"\x00{64,}|\xff{64,}", data)]
    return dict(
        evidence="Offline byte checks against official MCU 1.3.7; no device access",
        sha256=digest, image_size=len(data), application_base=f"{BASE:#010x}",
        application_end_exclusive=f"{BASE + len(data):#010x}",
        initial_sp=f"{struct.unpack_from('<I', data, 0)[0]:#010x}",
        reset_vector=f"{struct.unpack_from('<I', data, 4)[0]:#010x}",
        verified_sites=sites, repeated_byte_runs=runs,
        repeated_run_warning="May be used tables/assets. Not evidence of free executable space.",
        patch_generated=False, device_written=False,
        unresolved=[
            "How the actual bootloader consumes update and backup markers",
            "Recovery entry independent of a functioning display application",
            "Device-side selection of MCU-only update and modified-image acceptance",
            "Reachability of all Flash calls and display-buffer writers in a stream mode",
            "Safe code placement, RAM ownership, and measured USB/UART pacing",
        ],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.image.read_bytes())
    result = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    print(result)
