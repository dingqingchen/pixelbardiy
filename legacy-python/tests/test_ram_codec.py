import random
import pytest
from halo.ram_codec import encode, decode, pack, unpack, packets, Encoded


def test_all_patterns_roundtrip_and_choose_smallest_codec():
    rng=random.Random(123)
    for data in [bytes(1024), b'\xff'*1024, bytes(range(256))*4]+[rng.randbytes(1024) for _ in range(20)]:
        assert unpack(pack(data))==data
        item=encode(data); assert decode(item)==data and len(item.data)<=1024
        changed=bytearray(data);changed[42:46]=b'abcd'
        delta=encode(bytes(changed),data,7)
        assert decode(delta,data,7)==changed
        assert len(delta.data)<=len(pack(bytes(changed)))
        assert len(packets(123,8,delta))==delta.packets


def test_stale_base_and_bad_crc_are_rejected():
    base=bytes(range(256))*4; new=bytearray(base);new[42]=99
    item=encode(bytes(new),base,1);assert item.codec==2
    for actual,number in [(base,2),(bytes(1024),1),(None,1)]:
        with pytest.raises(ValueError): decode(item,actual,number)
    bad=item.metadata[:-1]+bytes([item.metadata[-1]^1])
    with pytest.raises(ValueError):decode(Encoded(2,item.data,bad),base,1)


@pytest.mark.parametrize('raw',[b'',b'\xff',b'\x7fabc',b'\xff\x00'*9])
def test_rle_truncation_and_overflow(raw):
    with pytest.raises(ValueError):unpack(raw)


def test_extension_metadata_and_fragment_boundaries():
    item=encode(bytes(range(256))*4,animation=2)
    batch=packets(123,5,item)
    assert batch[0][4]==6 and batch[0][13:]==item.metadata
    assert [p[11] for p in batch[1:]]==list(range(len(batch)-1))
    assert all(p[:4]==b'HPL2' and len(p)<=50 for p in batch)
    assert b''.join(p[13:] for p in batch[1:])==item.data
