import asyncio
import json
import pytest
from halo.device import HaloLink
from halo.engine import Engine
from halo.text_stream import TextTransition
from halo.vendor_core import _edifier_packet


def test_resource_writes_are_blocked_even_if_old_caller_attempts_upload():
    device = HaloLink()
    with pytest.raises(RuntimeError, match='禁止图片上传'):
        device._write(_edifier_packet(0x17, [0, 0, 0, 0, 4, 40]))
    with pytest.raises(RuntimeError, match='不使用图片'):
        device.begin_pixels(None, '#FFFFFF')
    assert device.write_count == 0


def test_old_saved_settings_cannot_restart_uploads(tmp_path):
    (tmp_path/'settings.json').write_text(json.dumps({'pixels': True, 'theme': 'kitty', 'monitor_view':'graph'}))
    engine = Engine(tmp_path)
    assert engine.config['pixels'] is False
    assert engine.config['theme'] == 'kitty'
    assert engine.config['monitor_view'] == 'value'


@pytest.mark.parametrize('used,fail', [(False,False),(True,False),(True,True)])
def test_release_display_restores_only_owned_screen_and_closes_after_failure(used, fail):
    class Handle:
        def __init__(self):self.writes=[];self.closed=False
        def write(self, packet):
            self.writes.append(packet)
            if fail:raise OSError('Device unplugged')
            return 64
        def close(self):self.closed=True
    device=HaloLink();handle=Handle();device.handle=handle
    if used:device.last_display=(b'previous', '#FFFFFF', 'center')
    if fail:
        with pytest.raises(OSError):device.release_display()
    else:
        device.release_display();device.release_display()
    assert handle.closed and device.handle is None
    assert len(handle.writes)==int(used)
    if used:
        assert handle.writes[0][3]==0xEF
        assert handle.writes[0][10:15]==bytes([0,1,0,0,255])


def test_fade_swaps_latest_line_and_disabling_finishes_immediately():
    effect = TextTransition()
    assert effect.frame('A', '#FFFFFF', 'center', 0, True) == ('A', '#FFFFFF', 'center')
    effect.frame('B', '#FFFFFF', 'center', 1, True)
    halfway = effect.frame('C', '#FFFFFF', 'center', 1.07, True)
    assert halfway[0] == 'A' and halfway[1] != '#FFFFFF'
    assert effect.frame('C', '#FFFFFF', 'center', 1.15, True)[0] == 'C'
    assert effect.frame('C', '#FFFFFF', 'center', 1.25, True) == ('C', '#FFFFFF', 'center')
    assert not effect.busy
    effect.frame('D', '#FFFFFF', 'center', 2, True)
    assert effect.frame('E', '#FFFFFF', 'center', 2.01, False) == ('E', '#FFFFFF', 'center')
    assert not effect.busy


def test_scroll_keeps_running_without_per_frame_text_or_layout_writes():
    class Handle:
        def __init__(self):self.writes=[]
        def write(self,p):self.writes.append(p);return 64
    device=HaloLink();device.handle=Handle()
    device.show_text('测试歌词', '#FFFFFF', 'scroll_right_to_left')
    assert any(p[3]==0xEF and p[6]==1 and p[12:15]==bytes([1,1,255]) for p in device.handle.writes)
    device.handle.writes.clear()
    for i in range(60):device.show_text('测试歌词', '#FFFFFF', 'scroll_right_to_left')
    assert not device.handle.writes
    device.show_text('下一句', '#FFFFFF', 'scroll_right_to_left')
    assert [p[3] for p in device.handle.writes]==[0xE8]
    device.handle.writes.clear()
    device.show_text('下一句', '#999999', 'scroll_right_to_left')
    assert len(device.handle.writes)==1 and device.handle.writes[0][3]==0xEF
    assert device.handle.writes[0][6]==3


def test_native_lyrics_use_lrc_ram_once_and_can_switch_back_to_diy():
    class Handle:
        def __init__(self):self.writes=[]
        def write(self,p):self.writes.append(p);return 64
    device=HaloLink();device.handle=Handle()
    device.show_text('原生歌词', '#FFFFFF', 'native_lyric_up')
    assert device.handle.writes[0][3]==0xEF
    assert device.handle.writes[0][6:15]==bytes([1,255,255,255,0,0,1,0,0])
    assert device.handle.writes[1][3]==0xE8 and device.handle.writes[1][6]==14
    device.handle.writes.clear()
    for _ in range(60):device.show_text('原生歌词', '#FFFFFF', 'native_lyric_up')
    assert device.handle.writes==[]
    device.show_text('换句', '#FFFFFF', 'native_lyric_up')
    assert len(device.handle.writes)==1 and device.handle.writes[0][3]==0xE8
    device.handle.writes.clear()
    device.show_text('换句', '#FFFFFF', 'center')
    assert device.handle.writes[0][3]==0xE8 and device.handle.writes[0][6]==0
    assert device.handle.writes[1][3]==0xEF


def test_native_lyric_verification_does_not_read_unrelated_diy_buffer():
    device=HaloLink();device._write=lambda packet:None
    queries=[]
    device.query=lambda command,*args:queries.append(command) or bytes([16,9])
    device.show_text('歌词', '#FFFFFF', 'native_lyric_up', verify=True)
    assert queries==[0x66]


@pytest.mark.parametrize('motion', ['scroll','fade','native_up'])
def test_real_engine_only_sends_live_text_for_lyrics_clock_and_monitor(tmp_path, monkeypatch, motion):
    import halo.engine as module
    from halo.media import Track
    clock=[100.0];holder={};seen=[];commands=[];packets=[]
    class Device(HaloLink):
        def connect(self):self.handle=True
        def close(self):self.handle=None;self.last_display=None
        def _write(self, packet):
            assert packet[3] != 0x17
            commands.append(packet[3]);self.write_count+=1
            packets.append(packet)
        def query(self,cmd,payload=(),**kwargs):
            if cmd==0xE7:
                # Return text used in the matching show_text invocation.
                return bytes([0,16,50,len(self.expected)])+self.expected
            return bytes([16,9])
        def show_text(self,text,*args,**kwargs):
            from halo.vendor_core import _truncate_utf8
            self.expected=_truncate_utf8(text)
            seen.append(text)
            return super().show_text(text,*args,**kwargs)
    class Media:
        async def poll(self):
            t=clock[0]-100
            if t>3:holder['e'].config.update(idle_content='monitor')
            if t>5:holder['e'].exit_event.set()
            return Track(playing=t<2,title='测试' if t<2 else '',provider='网易云本地',realtime_lyric='歌词甲' if t<1 else '歌词乙')
        def close(self):pass
    class Hardware:
        def sample(self,*args):return {'metrics':[{'key':'cpu','short':'CPU','value':50,'text':'50%','scale':100}]}
        def close(self):pass
    class Lyrics:
        def __init__(self,*args):pass
        def fetch(self,*args):return [],'test'
    async def sleep(delay):clock[0]+=delay
    monkeypatch.setattr(module,'HaloLink',Device);monkeypatch.setattr(module,'MediaMonitor',Media)
    monkeypatch.setattr(module,'HardwareMonitor',Hardware);monkeypatch.setattr(module,'LyricsStore',Lyrics)
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(module.asyncio,'sleep',sleep)
    e=Engine(tmp_path);holder['e']=e
    e.config.update(pixels=True,animations=True,transitions=True,text_motion=motion,online=False)
    asyncio.run(e._loop())
    assert any('歌词甲' in t for t in seen) and any('歌词乙' in t for t in seen)
    assert any('CPU' in t for t in seen) and any(':' in t for t in seen)
    assert commands and set(commands)<= {0xE8,0xEF}
    # Normal engine exit returns to the built-in clock without an image upload.
    assert packets[-1][3]==0xEF and packets[-1][10:15]==bytes([0,1,0,0,255])
