from __future__ import annotations
import asyncio
from dataclasses import asdict
from datetime import datetime
import json
import logging
from pathlib import Path
import queue
import threading
import time
from collections import deque
import psutil
from PySide6.QtCore import QObject, Signal
from .device import HaloLink
from .lyrics import LyricsStore, line_at, split_display, normalize
from .media import MediaMonitor, Track
from .themes import style_frame,THEMES
from .monitor import HardwareMonitor,monitor_frame
from .rhythm import MusicPeak,Envelope,rhythm_color
from .text_stream import TextTransition

DEFAULTS = {"enabled":True,"mode":"auto","seconds":True,"color":"#86D8F6",
            "offset":0.0,"online":True,"effect":"color_tide","ambient_color":"#C3B9FF",
            "brightness":"high","speed":8,"ambient_enabled":True,
            "idle_content":"clock","themes":True,"theme":"ion","animations":False,"motion":"breath",
            "monitor_view":"value","monitor_rotate":True,"rotation_seconds":4,
            "monitor_metrics":["cpu","ram","gpu0","gpu0_temp","download","upload"],"fan_limits":{},
            "rhythm":False,"rhythm_style":"pulse","rhythm_gain":2.5,"power_profile":"eco",
            "pixels":False,"transitions":True,"text_motion":"scroll"}

PROFILES={"eco":{"media":.2,"idle_media":1.5,"monitor":3,"animation":.5,"rhythm":.05,"loop":.01},
          "balanced":{"media":.1,"idle_media":1,"monitor":2,"animation":.33,"rhythm":1/30,"loop":.008}}

def poll_delay(config,track):
    if not config["enabled"]:return 1.5
    profile=PROFILES.get(config.get("power_profile"),PROFILES["eco"])
    if track.playing and config.get("rhythm"):return profile["loop"]
    if track.playing:return profile['media']
    if config.get("animations"):return profile["animation"]
    return profile["media"] if track.playing else .8

def choose_display(config, track, lines, now, snapshot=None, elapsed=0):
    clock = now.strftime("%H:%M:%S" if config["seconds"] else "%H:%M")
    if config["mode"] == "auto" and track.playing and track.title:
        if track.provider.startswith("网易云本地") and track.realtime_lyric:
            pages=split_display(track.realtime_lyric)
            page=min(len(pages)-1,int(track.line_elapsed/2))
            index=next((i for i,l in enumerate(lines) if normalize(l.text)==normalize(track.realtime_lyric)),-1)
            return pages[page],"歌词",{"text":pages[page],"full":track.realtime_lyric,
                "index":index,"page":page+1,"pages":len(pages),"start":0,"end":0}
        # The native adapter has no playback timeline. Position 0 is unknown,
        # not a reason to display the LRC's first credit line indefinitely.
        active = None if track.provider.startswith("网易云本地") else line_at(lines,track.position+config["offset"],track.duration)
        if active:
            return active["text"],"歌词",active
        # Instrumental intro / missing lyric retains the accurate clock.
    if config.get("idle_content")=="monitor" and config["mode"]!="clock":
        return monitor_frame(snapshot or {},config,elapsed),"系统监控",None
    return clock,"时钟",None

class Engine(QObject):
    changed = Signal(dict)
    notice = Signal(str)

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory
        directory.mkdir(parents=True,exist_ok=True)
        self.config_path = directory/"settings.json"
        self.config = dict(DEFAULTS)
        try:
            saved = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.config.update({k:v for k,v in saved.items() if k in DEFAULTS})
            if self.config["mode"]=="clock":self.config["mode"]="idle"
        except (OSError,ValueError,TypeError):
            pass
        # Old configurations must not silently resume per-frame resource uploads.
        self.config['pixels'] = False
        if self.config['monitor_view'] == 'graph':self.config['monitor_view'] = 'value'
        self.commands = queue.Queue()
        self.exit_event = threading.Event()
        self.thread = None
        self.visible=True
        self.monitor_visible=False

    def start(self):
        self.thread = threading.Thread(target=self._run,name="Halo engine",daemon=True)
        self.thread.start()

    def submit(self, kind, value=None):
        self.commands.put((kind,value))

    def stop(self):
        self.exit_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _save(self):
        temp = self.config_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.config,ensure_ascii=False,indent=2),encoding="utf-8")
        temp.replace(self.config_path)

    def _run(self):
        from winrt.runtime import init_apartment,uninit_apartment,ApartmentType
        init_apartment(ApartmentType.MULTI_THREADED)
        try:
            asyncio.run(self._loop())
        except Exception:
            logging.exception("Engine stopped")
            self.notice.emit("后台服务停止，请重新启动应用。详情见 runtime/studio.log")
        finally:
            uninit_apartment()

    async def _loop(self):
        device, media = HaloLink(), MediaMonitor()
        hardware=HardwareMonitor(); meter=MusicPeak(); envelope=Envelope()
        snapshot={"metrics":[],"fans":[],"detail":"打开监控页或选择系统监控后开始采样。"}
        process=psutil.Process(); process.cpu_percent(None)
        performance={}; next_perf=next_monitor=next_media=next_emit=next_visual=next_rhythm=0
        last_writes=0; last_perf=time.monotonic(); last_rhythm=None; rhythm_active=False
        frame=("--:--",self.config["color"],"center"); display_mode="时钟"; active=None
        lyrics = LyricsStore(self.directory/"lyrics")
        track, previous_key, lines = Track(),None,[]
        source = "等待网易云音乐"
        fetch_task = None
        fetch_key = None
        attempted_key = None
        connected = False
        next_connect = next_health = 0
        device_message = "连接音响…"
        media_message = "等待网易云播放"
        verified = False
        previous_mode=None;previous_display=None
        history={};transition=TextTransition();sent_frame=frame
        try:
            while not self.exit_event.is_set():
                while not self.commands.empty():
                    kind, value = self.commands.get_nowait()
                    try:
                        if kind == "config":
                            self.config.update({k:v for k,v in value.items() if k in DEFAULTS})
                            self.config['pixels']=False
                            self._save()
                            if "online" in value:attempted_key=None
                            next_visual=0; next_monitor=0
                            if value.get("enabled") is False:
                                try:
                                    if rhythm_active and connected:
                                        device.set_ambient(self.config["effect"],self.config["ambient_color"],self.config["brightness"],self.config["speed"],self.config["ambient_enabled"])
                                finally:
                                    rhythm_active=False; meter.close(); connected=False
                                    device.release_display(self.config["color"])
                        elif kind == "visibility":
                            self.visible=bool(value["visible"]); self.monitor_visible=bool(value.get("monitor")); next_emit=0
                        elif kind == "reconnect":
                            if rhythm_active and connected:
                                device.set_ambient(self.config["effect"],self.config["ambient_color"],self.config["brightness"],self.config["speed"],self.config["ambient_enabled"])
                            rhythm_active=False; device.close(); connected=False; next_connect=0; verified=False
                        elif kind == "ambient":
                            if not connected:
                                raise RuntimeError("请先连接音响")
                            device.set_ambient(value["effect"],value["ambient_color"],value["brightness"],value["speed"],value["ambient_enabled"])
                            self.config.update(value); self._save()
                            rhythm_active=False; last_rhythm=None
                            self.notice.emit("灯光设置已写入，设备已响应")
                        elif kind == "lrc":
                            if not track.title:
                                raise ValueError("请先在网易云播放需要导入歌词的歌曲")
                            if value["key"] != track.key:
                                raise ValueError("歌曲已切换，请为当前歌曲重新导入")
                            lines, source = lyrics.save(track.title,track.artist,track.duration,value["text"],"本地 LRC")
                            attempted_key = track.key
                            if fetch_task:
                                # A stale network result must never replace this manual selection.
                                fetch_key = None
                            self.notice.emit("已关联当前歌曲，后续自动使用这份 LRC")
                        elif kind == "retry_lyrics":
                            lyrics.invalidate(track.title,track.artist,track.duration)
                            attempted_key=None
                    except Exception as exc:
                        logging.exception("Command %s failed",kind)
                        self.notice.emit(str(exc))
                now = time.monotonic()
                if self.config["enabled"] and not connected and now >= next_connect:
                    try:
                        device.connect(); connected=True; verified=False;transition=TextTransition()
                        device_message="USB 已连接"; next_health=now+8
                    except Exception as exc:
                        device_message=str(exc); next_connect=now+3
                profile=PROFILES.get(self.config["power_profile"],PROFILES["eco"])
                if now>=next_media:
                    try:
                        track = await asyncio.wait_for(media.poll(),timeout=2)
                        media_message = "正在播放" if track.playing else "已暂停" if track.title else "等待网易云播放会话"
                    except Exception as exc:
                        track = Track()
                        media_message="媒体读取失败："+str(exc)
                    next_media=now+(profile["media"] if track.playing else profile["idle_media"])
                if now>=next_monitor and ((self.config["enabled"] and self.config["idle_content"]=="monitor") or (self.visible and self.monitor_visible)):
                    try:
                        snapshot=hardware.sample(self.config["fan_limits"])
                        for metric in snapshot.get('metrics',[]):
                            values=history.setdefault(metric['key'],deque(maxlen=24))
                            if metric.get('value') is not None:values.append(metric['value'])
                            metric['history']=list(values)
                    except Exception:logging.exception("Hardware sample failed")
                    next_monitor=now+profile["monitor"]
                if track.key != previous_key:
                    lines=[]; source="正在查找同步歌词…" if track.title else "等待网易云音乐"
                    previous_key=track.key
                    attempted_key=None
                if fetch_task and fetch_task.done():
                    try:
                        result = fetch_task.result()
                        if fetch_key == track.key:
                            lines,source=result
                    except Exception:
                        if fetch_key == track.key:
                            source="歌词获取失败，可重试或导入 LRC"
                        logging.exception("Lyrics lookup failed")
                    fetch_task=None
                if track.title and attempted_key != track.key and fetch_task is None:
                    fetch_key=track.key; attempted_key=track.key
                    fetch_task=asyncio.create_task(asyncio.to_thread(lyrics.fetch,track.title,track.artist,track.album,track.duration,self.config["online"]))
                display,display_mode,active = choose_display(self.config,track,lines,datetime.now(),snapshot,now)
                if display_mode!=previous_mode:transition=TextTransition()
                if now>=next_visual or display_mode!=previous_mode or display!=previous_display:
                    frame=style_frame(display,display_mode,{**self.config,'motion':'breath'},now)
                    scrolling=(self.config['animations'] and self.config['transitions']
                               and self.config['text_motion']=='scroll' and display_mode!='时钟')
                    native=(self.config['animations'] and self.config['transitions']
                            and self.config['text_motion']=='native_up' and display_mode=='歌词')
                    frame=(frame[0],frame[1],'native_lyric_up' if native else 'scroll_right_to_left' if scrolling else 'center')
                    next_visual=now+(profile["animation"] if self.config["animations"] else 0)
                previous_display=display
                if connected and self.config["enabled"]:
                    try:
                        fade=(self.config['animations'] and self.config['transitions']
                              and (self.config['text_motion']=='fade' or
                                   (self.config['text_motion']=='native_up' and display_mode=='系统监控'))
                              and display_mode!='时钟')
                        sent_frame=transition.frame(*frame,now,animate=fade)
                        device.show_text(*sent_frame,verify=not verified or display_mode!=previous_mode)
                        verified=True
                        if display_mode!=previous_mode:
                            logging.info("Display requested mode=%s; source=%s",display_mode,track.provider)
                            previous_mode=display_mode
                        rhythm_requested=self.config["rhythm"] and self.config["ambient_enabled"] and track.playing
                        if rhythm_requested:
                            if not rhythm_active:
                                device.set_ambient('static',self.config['ambient_color'],self.config['brightness'],8,True)
                                rhythm_active=True; last_rhythm=None; next_rhythm=0;envelope=Envelope()
                            level=envelope.update(meter.read(now),now,self.config["rhythm_gain"])
                            theme=THEMES.get(self.config["theme"],THEMES["ion"])
                            rgb=rhythm_color(self.config["ambient_color"],theme.accent,level,self.config["rhythm_style"])
                            if now>=next_rhythm:
                                if rgb!=last_rhythm:device.rhythm_frame(rgb,self.config["brightness"]); last_rhythm=rgb
                                # Keep a fixed cadence rather than accumulating
                                # Windows timer rounding after every frame.
                                period=profile['rhythm']
                                next_rhythm+=(max(0,int((now-next_rhythm)/period))+1)*period
                        elif rhythm_active:
                            device.set_ambient(self.config["effect"],self.config["ambient_color"],self.config["brightness"],self.config["speed"],self.config["ambient_enabled"])
                            rhythm_active=False; last_rhythm=None; meter.close(); envelope=Envelope()
                        if now >= next_health:
                            device.query(0x66); next_health=now+8
                    except Exception as exc:
                        logging.warning('Device synchronization failed: %s',exc)
                        device_message=str(exc); device.close(); connected=False; next_connect=now+3;verified=False;rhythm_active=False
                if now>=next_perf:
                    span=max(.1,now-last_perf)
                    performance={"cpu_percent":round(process.cpu_percent(None)/(psutil.cpu_count() or 1),2),
                        "memory_mb":round(process.memory_info().rss/1024**2,1),"hid_per_second":round((device.write_count-last_writes)/span,1),
                        "monitor_seconds":profile["monitor"],"rhythm_hz":round(1/profile["rhythm"],1),"visible":self.visible}
                    last_perf=now; last_writes=device.write_count; next_perf=now+5
                if now>=next_emit:
                    self.changed.emit({"connected":connected,"device_message":device_message,
                    "media_message":media_message,"track":asdict(track),"source":source,
                    "display":sent_frame[0],"display_mode":display_mode,"active":active,
                    "enabled":self.config["enabled"],"verified":verified,
                    "lines":[asdict(l) for l in lines],"color":sent_frame[1],"layout":sent_frame[2],
                    "monitor":snapshot,"performance":performance,"rhythm_active":rhythm_active,
                    "pixels":None,"pixel_uploading":False,"pixel_seconds":0,
                    "transport":"实时文字 E8 / EF · 禁止图片上传",
                    "rhythm_raw":getattr(meter,'raw_peak',0),
                    "rhythm_level":envelope.level if rhythm_active else 0,"rhythm_message":meter.message})
                    next_emit=now+(.5 if self.visible else 3)
                await asyncio.sleep(min(.03,poll_delay(self.config,track)) if transition.busy and connected and self.config['enabled'] else poll_delay(self.config,track))
        finally:
            # Restore the screen first: lighting restoration may wait for ACKs.
            # Keep its handle open until that restoration is attempted as well.
            if device.handle and device.last_display is not None:
                try:device.native_clock(self.config["color"])
                except Exception:logging.exception("Restore stock display on exit failed")
            if rhythm_active and device.handle:
                try:device.set_ambient(self.config["effect"],self.config["ambient_color"],self.config["brightness"],self.config["speed"],self.config["ambient_enabled"])
                except Exception:logging.exception("Restore lighting on exit failed")
            meter.close(); hardware.close()
            device.close()
            media.close()
            if fetch_task:
                fetch_task.cancel()
