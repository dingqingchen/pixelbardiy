import asyncio
from datetime import datetime
from types import SimpleNamespace
import pytest
from halo.themes import THEMES,style_frame
from halo.engine import DEFAULTS,choose_display,poll_delay,Engine
from halo.media import Track
from halo.monitor import monitor_frame,rpm_percentage
from halo.rhythm import Envelope,rhythm_color
from halo.device import HaloLink
from halo import vendor_core

@pytest.mark.parametrize("key",THEMES)
def test_all_themes_fit_real_device_and_do_not_cut_lyrics(key):
    config={**DEFAULTS,"theme":key,"animations":True}
    for phase in (0,1,7,40):
        frame=style_frame("20:26:08","时钟",config,phase)
        assert len(frame[0])<=16 and len(frame[0].encode())<=48
        vendor_core.build_layout_packet(frame[2],vendor_core.parse_color(frame[1]))
        for lyric in ("短句歌词","这是一句刚好占满十六个汉字的歌词"):
            # Long lyrics arrive already paginated by choose_display.
            lyric=lyric[:16];styled=style_frame(lyric,"歌词",config,phase)[0]
            assert lyric in styled and len(styled)<=16 and len(styled.encode())<=48

def test_theme_and_motion_switches_are_independent():
    c={**DEFAULTS,"themes":False,"animations":False}
    assert style_frame("20:26","时钟",c,1)==("20:26",c["color"],"center")
    c.update(animations=True,motion="scroll")
    assert style_frame("歌词","歌词",c,1)[2]=="scroll_right_to_left"
    c.update(animations=False)
    assert style_frame("歌词","歌词",c,1)[2]=="center"

def metrics():
    return {"metrics":[{"key":"cpu","short":"CPU","value":50,"text":"50%","scale":100},
                       {"key":"ram","short":"RAM","value":25,"text":"25%","scale":100}]}

def test_monitor_rotation_fixed_compact_bar_and_missing():
    c={**DEFAULTS,"monitor_metrics":["cpu","ram"],"rotation_seconds":4}
    assert monitor_frame(metrics(),c,0)=="CPU 50%"
    assert monitor_frame(metrics(),c,4)=="RAM 25%"
    assert monitor_frame(metrics(),{**c,"monitor_rotate":False},4)=="CPU 50%"
    assert monitor_frame(metrics(),{**c,"monitor_view":"compact"},0)=="CPU50% RAM25%"
    assert monitor_frame(metrics(),{**c,"monitor_view":"bar"},0)=="CPU||..50%"
    assert monitor_frame({},c,0)=="等待监控数据"

def test_auto_lyrics_returns_to_monitor_on_pause():
    c={**DEFAULTS,"idle_content":"monitor","monitor_metrics":["cpu"]}
    now=datetime(2026,10,12,20,26)
    playing=Track(title="测试",playing=True,provider="网易云本地",realtime_lyric="歌词")
    assert choose_display(c,playing,[],now,metrics())[1]=="歌词"
    assert choose_display(c,Track(),[],now,metrics())[:2]==("CPU 50%","系统监控")
    assert choose_display({**c,"mode":"idle"},playing,[],now,metrics())[1]=="系统监控"

def test_unknown_fan_max_never_invented_or_derived_from_driver_percent():
    assert rpm_percentage(1200,0) is None
    assert rpm_percentage(None,2000) is None
    assert rpm_percentage(1200,2400)==50
    assert rpm_percentage(0,2400)==0
    assert rpm_percentage(2600,2400)>100

def test_envelope_decay_and_bounded_quantized_colors():
    e=Envelope();attack=e.update(.8,1);release=e.update(0,1.1)
    assert 0<release<attack<=1
    assert e.update(0,5)<.001
    for style in ("pulse","color","beat"):
        colors={rhythm_color("#FFBBDD","#66FFFF",v/100,style) for v in range(101)}
        assert len(colors)<=65
        assert all(len(v)==7 for v in colors)

def test_color_animation_does_not_rewrite_same_text():
    class Handle:
        def __init__(self):self.writes=[]
        def write(self,p):self.writes.append(p);return 64
    d=HaloLink();d.handle=Handle();d.show_text("20:26","#FFFFFF")
    d.handle.writes.clear();d.show_text("20:26","#FFCCFF")
    assert [p[3] for p in d.handle.writes]==[0xEF]
    d.handle.writes.clear();d.show_text("20:26","#FFCCFF")
    assert not d.handle.writes

def test_background_poll_rate_scales_to_enabled_features():
    assert poll_delay(DEFAULTS,Track())>=.8
    assert poll_delay({**DEFAULTS,"enabled":False},Track(playing=True))>=1
    assert .008<=poll_delay({**DEFAULTS,"rhythm":True},Track(playing=True))<=.02

def test_engine_restores_lights_on_pause_and_only_samples_monitor_on_demand(tmp_path,monkeypatch):
    import halo.engine as module
    clock=[100.0];holder={};samples=[];actions=[]
    class Device:
        write_count=0;handle=True
        last_display=None
        pixel_job=None;pixel_frame=None;pixel_seconds=0
        def connect(self):self.handle=True
        def close(self):self.handle=False
        def query(self,*args):return bytes([16,9])
        def show_text(self,*args,**kwargs):pass
        def ambient_power(self,*args):actions.append("power")
        def rhythm_frame(self,*args):actions.append("rhythm")
        def set_ambient(self,*args):actions.append("static" if args[0]=='static' else "restore")
    class Media:
        async def poll(self):
            if clock[0]>103:holder["engine"].exit_event.set()
            return Track(playing=clock[0]<101)
        def close(self):pass
    class Hardware:
        def sample(self,*args):samples.append(1);return metrics()
        def close(self):pass
    class Meter:
        message="test"
        def read(self,*args):return .6
        def close(self):pass
    async def sleep(delay):clock[0]+=delay
    monkeypatch.setattr(module,"HaloLink",Device);monkeypatch.setattr(module,"MediaMonitor",Media)
    monkeypatch.setattr(module,"HardwareMonitor",Hardware);monkeypatch.setattr(module,"MusicPeak",Meter)
    monkeypatch.setattr(module.time,"monotonic",lambda:clock[0]);monkeypatch.setattr(module.asyncio,"sleep",sleep)
    e=Engine(tmp_path);holder["engine"]=e;e.config.update(rhythm=True,online=False,pixels=False);e.visible=False
    asyncio.run(e._loop())
    assert actions[0]=="static" and "rhythm" in actions and actions[-1]=="restore"
    assert actions.count("restore")==1
    assert not samples

def test_minimize_stops_ui_refresh(tmp_path):
    from PySide6.QtWidgets import QApplication
    from halo.ui import StudioWindow
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(Engine(tmp_path),start=False);w.show();app.processEvents()
    assert w.ui_timer.isActive()
    w.hide();app.processEvents();assert not w.ui_timer.isActive()
    w.real_quit=True;w.close()
