"""Independent HaloStudio pixel-mode engine. Legacy Engine remains unchanged."""
from __future__ import annotations
import asyncio
from collections import deque
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import queue
import threading
import time
import psutil
from PySide6.QtCore import QObject
from .engine import Engine, DEFAULTS as LEGACY_DEFAULTS, PROFILES, choose_display
from .lyrics import LyricsStore
from .media import MediaMonitor, Track
from .pixel_monitor import HardwareMonitor
from .pixel_scene import scene, transition_frame
from .ram_display import RamDisplay
from .rhythm import MusicPeak, Envelope, rhythm_color
from .pixel_design import THEMES

DEFAULTS = {**LEGACY_DEFAULTS, 'pixels': True, 'seconds': False, 'theme': 'kitty',
            'monitor_view': 'bar', 'rotation_seconds': 8, 'animations': False,
            'transitions': False, 'pixel_transition': 'up', 'rhythm': True}


def competing_controller():
    for proc in psutil.process_iter(['name']):
        name = (proc.info.get('name') or '').casefold()
        if proc.pid != os.getpid() and name in ('edifier tempohub.exe', 'halostudio.exe'):
            return proc.info['name']
    return ''


class PixelEngine(Engine):
    def __init__(self, directory: Path):
        # Do not call the legacy constructor: it intentionally forces text mode.
        QObject.__init__(self)
        self.runtime = directory
        self.directory = directory/'pixel'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config_path = self.directory/'settings.json'
        self.config = deepcopy(DEFAULTS)
        try:
            saved = json.loads(self.config_path.read_text(encoding='utf-8'))
            self.config.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError, TypeError):
            pass
        self.config['pixels'] = True
        self.commands = queue.Queue()
        self.exit_event = threading.Event()
        self.thread = None
        self.visible = True
        self.monitor_visible = False
        self.stop_error = None
        self.last_state = {}

    async def _loop(self):
        device = RamDisplay(self.runtime/'mcu-installation.json')
        media, hardware, meter = MediaMonitor(), HardwareMonitor(), MusicPeak()
        envelope = Envelope()
        lyrics = LyricsStore(self.runtime/'lyrics')
        process = psutil.Process(); process.cpu_percent(None)
        snapshot = {'metrics': [], 'fans': [], 'detail': '需要时采样硬件。'}
        history = {}
        track, previous_key, lines = Track(), None, []
        source, media_message = '等待网易云音乐', '等待播放'
        fetch_task = fetch_key = attempted_key = media_task = None
        next_media = next_monitor = next_emit = next_perf = next_connect = next_owner = 0
        last_perf = time.monotonic(); last_writes = 0
        next_rhythm = 0; last_rhythm = desired_rhythm = None; rhythm_active = False
        performance = {}; connected = False; competitor = ''
        display = '--:--'; display_mode = '时钟'; active = None
        device_message = '准备 RAM 直绘…'
        render_key = None; render_revision = snapshot_revision = 0
        desired = None; last_identity = None; transition_target = None
        urgent_visual = False

        def restore_lights():
            nonlocal rhythm_active, last_rhythm
            if rhythm_active and device.handle:
                device.set_ambient(self.config['effect'], self.config['ambient_color'],
                    self.config['brightness'], self.config['speed'], self.config['ambient_enabled'])
            rhythm_active = False; last_rhythm = None; meter.close()

        def release():
            nonlocal connected, render_key, transition_target, rhythm_active
            # Screen release/clock comes first. Lighting restoration happens
            # only after pending DATA is settled, but before the handle closes.
            try:
                device.shutdown(after_release=restore_lights)
            finally:
                connected = False; render_key = None; transition_target = None
                rhythm_active = False; meter.close()

        try:
            while not self.exit_event.is_set():
                now = time.monotonic()
                profile = PROFILES.get(self.config['power_profile'], PROFILES['eco'])
                while not self.commands.empty():
                    kind, value = self.commands.get_nowait()
                    try:
                        if kind == 'config':
                            urgent_visual |= any(k in value and value[k] != self.config.get(k)
                                for k in ('theme', 'themes', 'color', 'mode', 'idle_content'))
                            self.config.update({k: v for k, v in value.items() if k in DEFAULTS})
                            self.config['pixels'] = True
                            self._save(); render_revision += 1; next_emit = next_monitor = 0
                            if 'online' in value: attempted_key = None
                            if value.get('enabled') is False: release()
                            if value.get('enabled') is True: next_connect = 0
                        elif kind == 'visibility':
                            self.visible = bool(value['visible']); self.monitor_visible = bool(value.get('monitor'))
                            next_emit = 0
                        elif kind == 'reconnect':
                            release(); next_connect = next_owner = 0
                        elif kind == 'cpu_temperature':
                            hardware.cpu_temperature.enable();next_monitor=0
                            self.notice.emit('请在 Windows 弹窗中确认独立温度采集器。')
                        elif kind == 'ambient':
                            if not connected: raise RuntimeError('请先连接音响')
                            if not device.ready_for_lights:
                                self.commands.put((kind, value))
                                break
                            device.set_ambient(value['effect'], value['ambient_color'], value['brightness'], value['speed'], value['ambient_enabled'])
                            self.config.update(value); self._save()
                            rhythm_active = False; last_rhythm = None
                            self.notice.emit('日常灯光已应用')
                        elif kind == 'lrc':
                            if not track.title or tuple(value['key']) != track.key:
                                raise ValueError('歌曲已切换，请为当前歌曲导入 LRC')
                            lines, source = lyrics.save(track.title, track.artist, track.duration, value['text'], '本地 LRC')
                            attempted_key = track.key; fetch_key = None; render_revision += 1
                        elif kind == 'retry_lyrics':
                            lyrics.invalidate(track.title, track.artist, track.duration); attempted_key = None
                    except Exception as exc:
                        logging.exception('Pixel command %s failed', kind)
                        self.notice.emit(str(exc))
                if self.exit_event.is_set(): break
                if now >= next_owner:
                    competitor = competing_controller(); next_owner = now+3
                    if competitor and connected:
                        release(); self.notice.emit('检测到 '+competitor+'，已释放屏幕，请退出它后继续。')
                if self.config['enabled'] and not connected and now >= next_connect:
                    try:
                        if competitor: raise RuntimeError('请先退出 '+competitor+'，避免同时控制屏幕')
                        self.notice.emit('正在同步原厂回退状态并取得 RAM 显示权…')
                        color = THEMES.get(self.config['theme'], THEMES['ion']).color if self.config['themes'] else self.config['color']
                        device.connect(color); connected = True; render_key = None; self.stop_error = None
                        device_message = 'RAM 直绘已连接'; now = time.monotonic()
                        self.notice.emit('已连接。图案、时钟、监控和歌词均在 RAM 中更新。')
                    except Exception as exc:
                        device_message = str(exc); next_connect = time.monotonic()+5
                        logging.warning('Pixel connection: %s', exc)
                if media_task and media_task.done():
                    try:
                        track = media_task.result()
                        media_message = '正在播放' if track.playing else '已暂停' if track.title else '等待网易云播放'
                    except Exception:
                        logging.exception('Media polling failed'); track = Track(); media_message = '暂时无法读取播放器'
                    media_task = None
                    next_media = now + (profile['media'] if track.playing and self.config['enabled'] else profile['idle_media'])
                if now >= next_media and media_task is None:
                    media_task = asyncio.create_task(asyncio.wait_for(media.poll(), timeout=2))
                if now >= next_monitor and ((self.config['enabled'] and self.config['idle_content'] == 'monitor') or (self.visible and self.monitor_visible)):
                    try:
                        snapshot = hardware.sample(self.config['fan_limits'])
                        for metric in snapshot.get('metrics', []):
                            values = history.setdefault(metric['key'], deque(maxlen=24))
                            if metric.get('value') is not None: values.append(metric['value'])
                            metric['history'] = list(values)
                        snapshot_revision += 1
                    except Exception: logging.exception('Hardware sampling failed')
                    next_monitor = time.monotonic()+profile['monitor']
                if track.key != previous_key:
                    previous_key = track.key; attempted_key = None; lines = []
                    source = '正在查找歌词上下文…' if track.title else '等待网易云音乐'
                if fetch_task and fetch_task.done():
                    try:
                        result = fetch_task.result()
                        if fetch_key == track.key: lines, source = result; render_revision += 1
                    except Exception:
                        if fetch_key == track.key: source = '可重试或导入 LRC'
                        logging.exception('Lyrics lookup failed')
                    fetch_task = None
                if track.title and attempted_key != track.key and fetch_task is None:
                    fetch_key = attempted_key = track.key
                    fetch_task = asyncio.create_task(asyncio.to_thread(lyrics.fetch, track.title, track.artist, track.album, track.duration, self.config['online']))
                wall = datetime.now()
                display, display_mode, active = choose_display(self.config, track, lines, wall, snapshot, now)
                key = (display, display_mode, render_revision,
                       snapshot_revision if display_mode == '系统监控' else 0,
                       int(now/max(2, self.config['rotation_seconds'])) if display_mode == '系统监控' and self.config['monitor_rotate'] and self.config['monitor_view'] != 'dense' else 0,
                       int(now/2) if self.config['animations'] else 0,
                       wall.date() if display_mode == '时钟' else None)
                if key != render_key:
                    desired = scene(display, display_mode, self.config, now, snapshot, wall)
                    render_key = key
                    if connected:
                        frame, color = desired
                        urgent = urgent_visual or (display_mode == '歌词' and frame.identity != last_identity)
                        committed = device.committed
                        animate = (self.config['transitions'] and display_mode != '时钟'
                                   and committed and frame.identity != last_identity)
                        if animate and device.native_animation and display_mode == '歌词':
                            device.offer(frame, color, urgent=urgent,
                                         animation=2 if self.config['pixel_transition'] == 'wipe' else 1)
                            transition_target = None
                        elif animate and not device.busy:
                            device.offer(transition_frame(committed[0], frame, self.config['pixel_transition']), color, urgent=urgent)
                            transition_target = desired
                        else:
                            # New content supersedes an intermediate animation.
                            device.offer(frame, color, urgent=urgent); transition_target = None
                        last_identity = frame.identity
                        urgent_visual = False
                if connected:
                    try:
                        # Drain DATA first, then give lights a slot before
                        # sending the next fragment. Never send a light command
                        # while the bridge is still awaiting the DATA response.
                        device.tick(time.monotonic(), send=False)
                        if transition_target and not device.busy:
                            device.offer(*transition_target); transition_target = None
                        requested = self.config['rhythm'] and self.config['ambient_enabled'] and track.playing
                        if requested:
                            if not rhythm_active and device.ready_for_lights:
                                device.set_ambient('static', self.config['ambient_color'], self.config['brightness'], 8, True)
                                rhythm_active = True; envelope = Envelope(); last_rhythm = None; next_rhythm = 0
                            if rhythm_active and now >= next_rhythm:
                                level = envelope.update(meter.read(now), now, self.config['rhythm_gain'])
                                accent = THEMES.get(self.config['theme'], THEMES['ion']).accent
                                desired_rhythm = rhythm_color(self.config['ambient_color'], accent, level, self.config['rhythm_style'])
                                next_rhythm = now+profile['rhythm']
                            if rhythm_active and device.ready_for_lights and desired_rhythm is not None and desired_rhythm != last_rhythm:
                                device.rhythm_frame(desired_rhythm, self.config['brightness']); last_rhythm = desired_rhythm
                        elif rhythm_active and device.ready_for_lights: restore_lights(); envelope = Envelope()
                        device.tick(time.monotonic())
                    except Exception as exc:
                        device_message = str(exc)
                        logging.exception('Pixel transport interrupted')
                        try: release()
                        except Exception: logging.exception('Pixel recovery failed')
                        next_connect = time.monotonic()+5
                if now >= next_perf:
                    span = max(.1, now-last_perf)
                    performance = {'cpu_percent': round(process.cpu_percent(None)/(psutil.cpu_count() or 1), 2),
                        'memory_mb': round(process.memory_info().rss/1024**2, 1),
                        'hid_per_second': round((device.write_count-last_writes)/span, 1),
                        'monitor_seconds': profile['monitor'], 'rhythm_hz': round(1/profile['rhythm']),
                        'frames_sent': device.frames_sent, 'frame_seconds': round(device.frame_seconds, 3),
                        'frames_dropped': device.frames_dropped, 'frame_age': round(device.frame_age, 3),
                        'palette_seconds': round(device.palette_seconds, 3)}
                    performance.update(frame_codec=device.frame_codec, frame_bytes=device.frame_bytes,
                                       frame_packets=device.frame_packets)
                    last_perf = now; last_writes = device.write_count; next_perf = now+5
                if now >= next_emit:
                    sent = device.committed
                    self.last_state = {'connected': connected, 'device_message': device_message, 'media_message': media_message,
                        'track': asdict(track), 'source': source, 'display': sent[0].text if sent else display,
                        'display_mode': display_mode, 'active': active, 'enabled': self.config['enabled'],
                        'verified': bool(connected and sent), 'lines': [asdict(line) for line in lines],
                        'color': sent[1] if sent else desired[1], 'pixels': sent[0].pixels if sent else None,
                        'preview_target': desired[0].pixels, 'monitor': snapshot, 'performance': performance,
                        'rhythm_active': rhythm_active, 'rhythm_raw': getattr(meter, 'raw_peak', 0),
                        'rhythm_level': envelope.level if rhythm_active else 0, 'rhythm_message': meter.message,
                        'pixel_busy': device.busy, 'pixel_seconds': device.frame_seconds, 'transport': 'HPL2 RAM',
                        'native_animation': device.native_animation, 'frame_codec': device.frame_codec,
                        'frame_bytes': device.frame_bytes, 'frame_packets': device.frame_packets}
                    self.changed.emit(self.last_state)
                    next_emit = now + (.5 if self.visible else 3)
                # Fast only while a packet is pending or sound is being sampled.
                await asyncio.sleep(.008 if connected and device.busy else .025 if rhythm_active else .1)
        finally:
            try:
                release()
            except Exception as exc:
                self.stop_error = str(exc)
                logging.exception('Pixel shutdown restoration failed')
                self.notice.emit('退出时恢复屏幕失败：'+str(exc))
            meter.close(); hardware.close(); media.close()
            for task in (fetch_task, media_task):
                if task: task.cancel()
            await asyncio.gather(*(task for task in (fetch_task, media_task) if task), return_exceptions=True)
