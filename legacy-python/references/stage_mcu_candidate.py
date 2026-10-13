"""One-shot, request-paced MCU staging through the stock 1.3.7 USB bridge.

Uses the exact archived MIX notification. Sends ONLY the pinned MCU candidate;
never sends BLE/main-controller bytes, an empty BLE completion, or a reset.
Status 10 after the complete MCU transfer means staging ended, NOT installation
or successful boot. The stock timeout may reset the main controller; whether it
resets the display is unknown. Independent display recovery remains unverified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CANDIDATE_SHA = 'fe18bc92afd790cd2f2248b98091033f8d8d76cac674b60540cbf5c644f389ae'
OFFICIAL_SHA = '71c6274c982715c56c99ef61fa568dd88a92c883d97ea7784721fba9de96fd60'
SIZE = 57252


def packet(command, payload=b'', *, device_type=0xEC):
    if len(payload) > 57:
        raise ValueError('Oversized HID payload')
    raw = bytes((0x2E, 0xAA, device_type, command)) + len(payload).to_bytes(2, 'big') + payload
    return (raw + bytes((sum(raw[1:]) & 255,))).ljust(64, b'\0')


def parse(raw):
    if len(raw) < 7 or raw[:3] != b'\x2f\xbb\xec':
        raise ValueError('Unexpected report header')
    size = int.from_bytes(raw[4:6], 'big')
    if size > 57 or len(raw) < size + 7 or raw[6+size] != sum(raw[1:6+size]) & 255:
        raise ValueError('Invalid report length/checksum')
    return raw[3], raw[6:6+size]


def images():
    candidate = (ROOT/'firmware-candidates/hpl2-review/mcu-hpl2-review-only.bin').read_bytes()
    official = (ROOT/'firmware-archive/20261012/Halo PixelBar-PC_137.71c6274c982715c5.bin').read_bytes()
    if len(candidate) != SIZE or hashlib.sha256(candidate).hexdigest() != CANDIDATE_SHA:
        raise ValueError('Candidate identity mismatch')
    if len(official) != 805084 or hashlib.sha256(official).hexdigest() != OFFICIAL_SHA:
        raise ValueError('Official archive identity mismatch')
    # Byte-for-byte equivalent to TempoHub's MIX notify for the original package.
    notify = len(official).to_bytes(4, 'big') + bytes((1, 3, 7, 0, 64, 1)) + official[5:13]
    return candidate, notify


class Transfer:
    def __init__(self, image):
        if len(image) != SIZE or hashlib.sha256(image).hexdigest() != CANDIDATE_SHA:
            raise ValueError('Unreviewed image')
        self.image = image
        self.sent = 0
        self.count = 0
        self.staged = False

    def accept(self, payload):
        if self.staged:
            raise ValueError('Transfer already ended')
        if len(payload) != 7:
            raise ValueError('Unknown DFU status format')
        status = payload[0]
        count = int.from_bytes(payload[1:3], 'big')
        requested = int.from_bytes(payload[3:7], 'big')
        if status == 10:
            if self.sent != SIZE:
                raise ValueError('Premature main-controller request')
            self.staged = True
            return None
        if status != 9:
            raise ValueError(f'Unreviewed device state {status}')
        if self.sent >= SIZE or not 1 <= count <= 55:
            raise ValueError('Repeated completion or invalid requested size')
        # Stock bridge requests offset 0 for each sequential packet. A nonzero
        # offset is accepted only if it exactly agrees with our next position.
        if requested not in (0, self.sent):
            raise ValueError(f'Unexpected offset {requested}, expected {self.sent}')
        end = min(SIZE, self.sent + count)
        data = bytes((9, int(end == SIZE))) + self.image[self.sent:end]
        self.sent = end
        self.count += 1
        return packet(0x11, data)


# Library only: use the reviewed firmware-specific updater, which verifies
# backups, device identity, exclusive access and a one-shot attempt latch.
