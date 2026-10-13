import json
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from halo.pixel_engine import PixelEngine, DEFAULTS
from halo.pixel_scene import scene, transition_frame
from halo.pixels import init_fonts
from halo.studio_host import StudioHost


def test_settings_are_independent_and_graph_mode_persists(tmp_path):
    old = json.dumps({'theme': 'matrix', 'pixels': False, 'idle_content': 'monitor'})
    (tmp_path/'settings.json').write_text(old)
    e = PixelEngine(tmp_path)
    assert e.config['pixels'] and e.config['idle_content'] == 'clock'
    e.config.update(monitor_view='graph'); e._save()
    assert PixelEngine(tmp_path).config['monitor_view'] == 'graph'
    assert (tmp_path/'settings.json').read_text() == old


def test_graphic_modes_have_art_and_optional_transitions():
    app = QApplication.instance() or QApplication([]); init_fonts()
    snapshot = {'metrics': [{'key': 'cpu', 'short': 'CPU', 'value': 37, 'text': '37%', 'scale': 100, 'history': [20, 45, 10, 37]}]}
    from datetime import datetime
    frames = [scene(text, mode, DEFAULTS, 0, snapshot, datetime.now())[0] for text, mode in
              [('20:26', '时钟'), ('CPU 37%', '系统监控'), ('听见每一颗星星', '歌词')]]
    assert len({f.pixels for f in frames}) == 3
    # Shared animal/decoration pixels are retained by all three modes.
    assert all(sum(v.bit_count() for v in f.pixels[:34]) > 0 for f in frames)
    assert transition_frame(frames[1], frames[2], 'up').pixels not in (frames[1].pixels, frames[2].pixels)
    assert transition_frame(frames[1], frames[2], 'wipe').pixels != frames[2].pixels


def test_handoff_waits_for_actual_worker_completion():
    # Exercise the real coordinator method without starting a GUI or USB worker.
    actions = []; alive = [True]
    stub = SimpleNamespace(engine=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: alive[0]), stop_error=None),
        stop_started=10**12, timer=SimpleNamespace(stop=lambda: actions.append('timer-stop')),
        pending='legacy', mode='pixel', _activate=lambda mode: actions.append(mode))
    StudioHost._poll_stop(stub)
    assert actions == [] and stub.pending == 'legacy'
    alive[0] = False; StudioHost._poll_stop(stub)
    assert actions == ['timer-stop', 'legacy'] and stub.pending is None


def test_engine_uses_graphics_for_all_modes_and_transition_switch_is_independent(tmp_path, monkeypatch):
    import asyncio
    import halo.pixel_engine as module
    from halo.media import Track
    app = QApplication.instance() or QApplication([]); init_fonts()
    tick = [100.0]; holder = {}; offers = []; polls = [0]
    real_sleep = asyncio.sleep
    class Device:
        write_count = 0; handle = None; committed = None; target = None
        busy = False; request = None; frame_seconds = 1.5; frames_sent = 0
        ready_for_lights = True; frames_dropped = 0; frame_age = 0; palette_seconds = 0
        native_animation = False; frame_codec = 'raw'; frame_bytes = 1024; frame_packets = 29
        def __init__(self, *args): pass
        def connect(self, color): self.handle = True
        def offer(self, frame, color, *, urgent=False, animation=0): self.target = (frame, color); offers.append(frame)
        def tick(self, now, send=True):
            if send and self.target:
                self.committed = self.target; self.target = None; self.frames_sent += 1
        def shutdown(self, after_release=None):
            if after_release: after_release()
            self.handle = None
        def set_ambient(self, *args): pass
        def rhythm_frame(self, *args): pass
    class Media:
        async def poll(self):
            polls[0] += 1; n = polls[0]
            if n > 9: holder['e'].exit_event.set()
            if n > 6: holder['e'].config.update(mode='idle', idle_content='monitor')
            elif n > 3: holder['e'].config.update(mode='idle', idle_content='clock')
            return Track(title='测试', playing=True, provider='网易云本地', realtime_lyric='歌词甲' if n == 1 else '歌词乙')
        def close(self): pass
    class Hardware:
        def sample(self, *args): return {'metrics':[dict(key='cpu', short='CPU', text='45%', value=45, scale=100)]}
        def close(self): pass
    class Lyrics:
        def __init__(self, *args): pass
        def fetch(self, *args): return [], 'test'
    async def sleep(delay):
        tick[0] += delay
        await real_sleep(0)
    monkeypatch.setattr(module, 'RamDisplay', Device); monkeypatch.setattr(module, 'MediaMonitor', Media)
    monkeypatch.setattr(module, 'HardwareMonitor', Hardware); monkeypatch.setattr(module, 'LyricsStore', Lyrics)
    monkeypatch.setattr(module, 'competing_controller', lambda: '')
    monkeypatch.setattr(module.time, 'monotonic', lambda: tick[0]); monkeypatch.setattr(module.asyncio, 'sleep', sleep)
    e = PixelEngine(tmp_path); holder['e'] = e
    e.config.update(rhythm=False, online=False, transitions=True, animations=False)
    asyncio.run(e._loop())
    assert all(len(f.pixels) == 1024 for f in offers)
    assert {'时钟', '系统监控:cpu', '歌词:歌词甲', '歌词:歌词乙'} <= {f.identity for f in offers}
    assert any(f.identity.startswith('transition:') for f in offers)
    assert e.stop_error is None
