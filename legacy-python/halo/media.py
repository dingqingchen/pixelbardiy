from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

@dataclass(frozen=True)
class Track:
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0
    position: float = 0
    playing: bool = False
    app: str = ""
    provider: str = "Windows 媒体会话"
    realtime_lyric: str = ""
    line_elapsed: float = 0
    @property
    def key(self):
        return self.title, self.artist, self.album

def netease_app(app_id):
    return any(token in app_id.casefold() for token in ("cloudmusic", "netease", "网易", "music163"))

class MediaMonitor:
    def __init__(self):
        self.manager = None
        self.metadata = {}
        self.last_properties = 0
        self.last_app = ""
        from .netease_native import NativeNetEase
        self.native = NativeNetEase()

    def close(self):
        self.manager = None
        self.native.close()

    async def poll(self):
        if self.manager is None:
            self.manager = await Manager.request_async()
        sessions = list(self.manager.get_sessions())
        relevant = [s for s in sessions if netease_app(s.source_app_user_model_id)]
        if not relevant:
            self.metadata = {}
            self.last_app = ""
            native = self.native.poll()
            return Track(**native) if native else Track()
        current = self.manager.get_current_session()
        current_app = current.source_app_user_model_id if current else ""
        session = next((s for s in relevant if s.source_app_user_model_id == current_app),relevant[0])
        app = session.source_app_user_model_id
        now = time.monotonic()
        if app != self.last_app or now-self.last_properties > 0.7:
            props = await session.try_get_media_properties_async()
            self.metadata = {"title":props.title or "", "artist":props.artist or "", "album":props.album_title or ""}
            self.last_properties, self.last_app = now, app
        playback = session.get_playback_info()
        playing = int(playback.playback_status) == 4
        timeline = session.get_timeline_properties()
        duration = max(0,(timeline.end_time-timeline.start_time).total_seconds())
        position = max(0,(timeline.position-timeline.start_time).total_seconds())
        if playing:
            updated = timeline.last_updated_time
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc)-updated).total_seconds()
            if 0 <= elapsed < 86400:
                position += elapsed * (playback.playback_rate or 1)
        if duration:
            position = min(position,duration)
        return Track(**self.metadata,duration=duration,position=position,playing=playing,app=app)
