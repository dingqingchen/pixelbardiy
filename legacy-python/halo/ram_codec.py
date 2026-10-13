"""Bounded lossless HPL2 extension: raw, RLE, or XOR/RLE against a known frame.

No device I/O. Extended BEGIN carries codec, animation, encoded length, base ID,
base CRC and target CRC. Every result is exactly 1024 bytes before publication.
"""
import binascii
from dataclasses import dataclass
import struct

EXT_BEGIN, EXT_DATA = 6, 7
RAW, RLE, XOR_RLE = 0, 1, 2
FIRMWARE_SHA = 'f7b8ee274ba2439b3211c5eea80206599acff6e80d73dc0c898ba143e2e32f62'
FULLSCREEN_SHA = 'ab4698cf8e826a3c64472ea0af1125653f65f796cd7fcf9013667344e4c0fc50'
MATRIX_SHA = 'ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884'
COLOR_SHA = '9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e'


def crc(data):
    return binascii.crc_hqx(data, 0)


def pack(data):
    result = bytearray(); i = 0
    while i < len(data):
        run = 1
        while i+run < len(data) and data[i+run] == data[i] and run < 128: run += 1
        if run >= 3:
            result.extend((0x80 | (run-1), data[i])); i += run
        else:
            start = i; i += run
            while i < len(data) and i-start < 128:
                run = 1
                while i+run < len(data) and data[i+run] == data[i] and run < 128: run += 1
                if run >= 3: break
                i += min(run, 128-(i-start))
            result.append(i-start-1); result.extend(data[start:i])
    return bytes(result)


def unpack(data):
    out = bytearray(); i = 0
    while i < len(data):
        token = data[i]; i += 1; count = (token & 127)+1
        size = 1 if token & 128 else count
        if i+size > len(data) or len(out)+count > 1024: raise ValueError('Invalid RLE span')
        out.extend(data[i:i+1]*count if token & 128 else data[i:i+count]); i += size
    if len(out) != 1024: raise ValueError('Incomplete RLE frame')
    return bytes(out)


@dataclass(frozen=True)
class Encoded:
    codec: int
    data: bytes
    metadata: bytes

    @property
    def packets(self): return 1+(len(self.data)+36)//37


def encode(pixels, base=None, base_id=0, animation=0, interval=16):
    if len(pixels) != 1024 or (base is not None and len(base) != 1024): raise ValueError('Invalid frame')
    if animation not in (0, 1, 2) or not 8 <= interval <= 64: raise ValueError('Invalid animation')
    choices = [(RAW, pixels), (RLE, pack(pixels))]
    if base is not None and 0 < base_id <= 65535:
        choices.append((XOR_RLE, pack(bytes(a^b for a,b in zip(base, pixels)))))
    codec, data = min(choices, key=lambda item: len(item[1]))
    # A fresh keyframe must not depend on a base; animation still uses old pixels.
    source_id = base_id if codec == XOR_RLE else 0
    source_crc = crc(base) if codec == XOR_RLE else 0
    metadata = struct.pack('>BBBBHHHH', codec, animation, interval, 0,
                           len(data), source_id, source_crc, crc(pixels))
    return Encoded(codec, data, metadata)


def decode(encoded, base=None, base_id=0):
    codec, animation, interval, reserved, size, source, source_crc, target_crc = struct.unpack('>BBBBHHHH', encoded.metadata)
    if codec != encoded.codec or reserved or animation > 2 or not 8 <= interval <= 64 or size != len(encoded.data):
        raise ValueError('Invalid metadata')
    pixels = encoded.data if codec == RAW else unpack(encoded.data)
    if codec == XOR_RLE:
        if not source or source != base_id or base is None or crc(base) != source_crc: raise ValueError('Stale base')
        pixels = bytes(a^b for a,b in zip(base, pixels))
    elif codec not in (RAW, RLE) or source or source_crc: raise ValueError('Invalid codec/base')
    if len(pixels) != 1024 or crc(pixels) != target_crc: raise ValueError('Frame CRC mismatch')
    return pixels


def packets(sid, number, encoded):
    def body(op, index, data):
        return b'HPL2'+bytes([op])+struct.pack('>IHB', sid, number, index)+bytes([len(data)])+data
    if not 0 < sid <= 0xffffffff or not 0 < number <= 65535: raise ValueError('Invalid session/frame')
    return [body(EXT_BEGIN, 0, encoded.metadata)]+[
        body(EXT_DATA, i, encoded.data[o:o+37]) for i,o in enumerate(range(0,len(encoded.data),37))]
