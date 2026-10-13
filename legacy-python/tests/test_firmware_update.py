from pathlib import Path
import hashlib
import pytest
from halo.firmware_update import Transfer, SIZE, validate_image, parse, packet, backup

IMAGE = Path(__file__).parents[1]/'firmware/hpl2-codec/mcu-hpl2-codec.bin'


def test_full_transfer_is_byte_exact_and_only_mcu_sent():
    image = IMAGE.read_bytes(); tx = Transfer(image); recovered = bytearray(); final = 0
    while tx.sent < SIZE:
        wire = tx.accept(bytes.fromhex('09003700000000'))
        length = int.from_bytes(wire[4:6], 'big')
        assert wire[3] == 0x11 and wire[6] == 9 and len(wire) == 64
        part = wire[8:6+length]
        assert 1 <= len(part) <= 55 and part[0] < 128
        recovered.extend(part); final += wire[7]
    assert recovered == image and tx.count == 1057 and final == 1
    assert tx.accept(bytes.fromhex('0a003700000000')) is None and tx.staged
    with pytest.raises(ValueError): tx.accept(bytes.fromhex('0a003700000000'))


@pytest.mark.parametrize('payload', [b'', bytes.fromhex('0a003700000000'), bytes.fromhex('09003600000000'), bytes.fromhex('09003700000001'), bytes.fromhex('08003700000000')])
def test_invalid_or_premature_request_stops(payload):
    tx = Transfer(IMAGE.read_bytes())
    with pytest.raises(ValueError): tx.accept(payload)
    assert tx.sent == 0 and tx.count == 0


def test_image_pin_and_checksum_and_backup_before_directory_creation(tmp_path):
    with pytest.raises(ValueError): validate_image(bytes(SIZE))
    wire = bytearray(packet(0xC6))
    wire[0:3] = b'\x2f\xbb\xec'; wire[6] = sum(wire[1:6]) & 255
    assert parse(wire) == (0xC6, b'')
    wire[6] ^= 1
    with pytest.raises(ValueError): parse(wire)
    bad = tmp_path/'bad.bin'; bad.write_bytes(b'bad')
    with pytest.raises(ValueError): backup(tmp_path, bad, tmp_path/'backup')
    assert not (tmp_path/'backup').exists()
