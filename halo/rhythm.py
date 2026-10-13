"""NetEase render-session peak meter. No recording, microphone, PCM or FFT."""
import math
import time
from collections import deque
from .themes import mix_color

def netease_sessions():
    """Yield render sessions on every active output, on the calling COM thread."""
    import comtypes,psutil
    from pycaw.pycaw import AudioUtilities
    from pycaw.api.audiopolicy import IAudioSessionControl2,IAudioSessionManager2
    endpoints=AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(0,1)
    for index in range(endpoints.GetCount()):
        try:
            endpoint=endpoints.Item(index)
            manager=endpoint.Activate(IAudioSessionManager2._iid_,comtypes.CLSCTX_ALL,None).QueryInterface(IAudioSessionManager2)
            sessions=manager.GetSessionEnumerator()
            for i in range(sessions.GetCount()):
                ctl=sessions.GetSession(i).QueryInterface(IAudioSessionControl2)
                try:
                    pid=ctl.GetProcessId()
                    if pid and psutil.Process(pid).name().lower()=='cloudmusic.exe':yield ctl
                except (psutil.Error,OSError):continue
        except OSError:continue

class MusicPeak:
    def __init__(self):self.meters=[]; self.next_find=0; self.message="等待音乐播放";self.raw_peak=0
    def read(self,now):
        from pycaw.pycaw import IAudioMeterInformation
        if now>=self.next_find:
            self.next_find=now+3; self.meters=[]
            try:
                self.meters=[ctl.QueryInterface(IAudioMeterInformation) for ctl in netease_sessions()]
                self.message="网易云瞬时信号 · 自动适应歌曲响度" if self.meters else "未找到网易云音频输出会话"
            except Exception:self.message="音频峰值暂不可用"
        try:
            self.raw_peak=max((m.GetPeakValue() for m in self.meters),default=0)
            return self.raw_peak
        except Exception:self.meters=[]; self.next_find=0; return 0
    def close(self):self.meters=[]; self.next_find=0

class Envelope:
    def __init__(self):self.level=0; self.last=None;self.history=deque(maxlen=100)
    def update(self,peak,now,gain=2.5):
        peak=max(0,min(1,float(peak)))
        if not self.history or now-self.history[-1][0]>=.04:self.history.append((now,peak))
        while self.history and now-self.history[0][0]>4:self.history.popleft()
        values=sorted(value for _,value in self.history)
        low=values[int((len(values)-1)*.15)];high=values[int((len(values)-1)*.9)]
        # Stretch *changes within the song*, rather than clipping peak*gain to
        # 100%. A compressed track at fixed volume must retain contrast.
        if peak<.002:target=0
        elif len(values)<8:target=min(.8,peak/(max(.1,high)*1.3))
        else:
            span=max(.025,high-low)
            relative=max(0,min(1,(peak-low)/span))
            target=max(0,min(1,(relative-.5)*max(.4,gain/2.5)+.5))
        dt=max(0,now-self.last) if self.last is not None else .2
        # Faster attack, slower release; decay depends on elapsed time, not CPU speed.
        weight=1-math.exp(-dt/(.035 if target>self.level else .12))
        self.level+=(target-self.level)*weight; self.last=now
        return self.level

def rhythm_color(base,accent,level,style):
    # Smooth enough for 20/30 Hz updates; the engine still deduplicates RGB.
    level=round(max(0,min(1,level))*64)/64
    if style=="beat":level=1 if level>.55 else .12
    color=mix_color(base,accent,level) if style=="color" else base
    return mix_color("#000000",color,.06+.94*level)
