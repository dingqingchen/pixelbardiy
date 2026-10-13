"""Offline experiment encoder. No HID, serial, network, or updater access.

These packets are NOT safe to send to stock firmware. They require a display
extension that has NOT been installed on the soundbar. No hardware sender exists.
"""
import binascii

RAM_BEGIN = bytes.fromhex('000480000402')


def frame_packets(pixels, *, chunk_size=50, prefix=b'\x00\x00'):
    if len(pixels) != 1024:
        raise ValueError('Expected a 1024-byte monochrome frame')
    if not 1 <= chunk_size <= 50 or len(prefix) != 2:
        raise ValueError('Unsupported offline fragment size or bridge prefix')
    payload = pixels + binascii.crc_hqx(pixels, 0).to_bytes(2, 'big')
    packets = []
    for index, offset in enumerate(range(0, len(payload), chunk_size)):
        part = prefix + index.to_bytes(2, 'big') + payload[offset:offset + chunk_size]
        packets.append(len(part).to_bytes(2, 'big') + part)
    return packets
