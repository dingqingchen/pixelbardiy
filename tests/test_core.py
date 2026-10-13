from datetime import datetime
import pytest
from halo.device import parse_response,HaloLink
from halo import vendor_core as p
from halo.lyrics import parse_lrc,line_at,split_display,same_recording,LyricsStore
from halo.engine import choose_display,DEFAULTS
from halo.media import Track,netease_app
from halo.netease_native import SUPPORTED
from halo.netease_native import clean_lyric

def test_packet_checksum_and_fixed_size():
    frame=p.build_text_packet("时钟测试")
    length=int.from_bytes(frame[4:6],"big")
    assert len(frame)==64
    assert frame[:4]==b"\x2e\xaa\xed\xe8"
    assert frame[6+length]==sum(frame[1:6+length])&255
    assert frame[8:8+len("时钟测试".encode())].decode()=="时钟测试"

def test_corrupt_and_truncated_response_rejected():
    packet=bytearray([0x2f,0xbb,0xec,0x66,0,2,16,9])
    packet.append(sum(packet[1:])&255)
    assert parse_response(bytes(packet),0x66)==bytes([16,9])
    packet[-1]^=1
    with pytest.raises(p.HaloError):parse_response(bytes(packet),0x66)
    with pytest.raises(p.HaloError):parse_response(bytes(packet[:7]),0x66)

def test_short_hid_write_fails():
    class Broken:
        def write(self,p):return 10
    link=HaloLink();link.handle=Broken()
    with pytest.raises(p.HaloError):link._write(bytes(64))

def test_utf8_pages_preserve_entire_line():
    text="测试中文歌词显示"*8+"✨abcdef"
    pages=split_display(text)
    assert ''.join(pages)==text
    assert all(len(page)<=16 and len(page.encode())<=48 for page in pages)

def test_lrc_multiple_timestamps_offset_and_duplicate_translation():
    lines=parse_lrc("[offset:-100]\n[00:01.25][01:02.500]第一句\n[00:01.25]Translation\n[00:04.00]\n[00:05.9]第二句")
    assert [round(l.time,3) for l in lines]==[1.15,3.9,5.8,62.4]
    assert lines[0].text=="第一句"
    assert line_at(lines,0) is None
    assert line_at(lines,4) is None
    assert line_at(lines,2)["text"]=="第一句"

def test_seek_backward_and_forward():
    lines=parse_lrc("[00:01]甲\n[00:03]乙\n[00:07]丙")
    assert line_at(lines,8)["text"]=="丙"
    assert line_at(lines,1.1)["text"]=="甲"

def test_reject_same_title_wrong_artist_or_duration():
    song={"name":"测试曲","artists":[{"name":"歌手甲"}],"duration":180000}
    assert same_recording("测试曲","歌手甲",181,song)
    assert not same_recording("测试曲","歌手乙",180,song)
    assert not same_recording("测试曲","歌手甲",200,song)

def test_manual_lrc_has_priority_over_late_network_result(tmp_path):
    store=LyricsStore(tmp_path)
    store.save("测试曲","歌手甲",180,"[00:01]手动版本","本地 LRC")
    store.save("测试曲","歌手甲",180,"[00:01]网络版本","网易云音乐")
    lines,source=store.fetch("测试曲","歌手甲","",0,False)
    assert lines[0].text=="手动版本"
    store.invalidate("测试曲","歌手甲")
    assert store.fetch("测试曲","歌手甲","",0,False)[0][0].text=="手动版本"

def test_auto_clock_lyrics_pause_and_mode_override():
    now=datetime(2026,10,12,20,26,8)
    track=Track(title="测试曲",playing=True,position=2)
    lines=parse_lrc("[00:01]屏幕测试歌词")
    assert choose_display(DEFAULTS,track,lines,now)[0]=="屏幕测试歌词"
    assert choose_display(DEFAULTS,Track(title="测试曲",playing=False),lines,now)[0]=="20:26:08"
    assert choose_display({**DEFAULTS,"mode":"clock"},track,lines,now)[0]=="20:26:08"

def test_native_lyrics_without_smtc_and_long_line_pagination():
    text="这是用于验证音响屏幕分页的测试内容，需要完整显示"
    track=Track(title="测试曲",playing=True,provider="网易云本地 · 3.1.39",realtime_lyric=text,line_elapsed=2.5)
    result=choose_display(DEFAULTS,track,[],datetime.now())
    assert result[1]=="歌词"
    assert result[0]==split_display(text)[1]

def test_native_profile_is_strict_and_netease_filter():
    assert (1787745734,40951808) in SUPPORTED
    assert (1787745735,40951808) not in SUPPORTED
    assert netease_app("cloudmusic.exe")
    assert not netease_app("Spotify.exe")

def test_native_lyric_accepts_unicode_whitespace_and_rejects_controls():
    assert clean_lyric('曹：我愛你\u3000你是我的茱麗葉\u3000卓：茱麗葉')=='曹：我愛你 你是我的茱麗葉 卓：茱麗葉'
    assert clean_lyric('第一句\n第二句\t末尾\u00a0')=='第一句 第二句 末尾'
    assert clean_lyric('非法\x01字符')==''

def test_native_missing_lyric_does_not_use_unknown_position_as_zero():
    track=Track(title='歌曲',playing=True,provider='网易云本地 · 3.1.39')
    text,mode,_=choose_display(DEFAULTS,track,parse_lrc('[00:00]作词：歌手'),datetime(2026,10,12,20,26,8))
    assert mode=='时钟' and text=='20:26:08'
