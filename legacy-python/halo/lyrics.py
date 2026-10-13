from __future__ import annotations
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import requests

STAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")

@dataclass(frozen=True)
class LyricLine:
    time: float
    text: str

def parse_lrc(text: str) -> list[LyricLine]:
    offset = re.search(r"\[offset:([+-]?\d+)\]", text, re.I)
    shift = int(offset.group(1)) / 1000 if offset else 0
    lines = {}
    for raw in text.splitlines():
        stamps = list(STAMP.finditer(raw))
        content = STAMP.sub("", raw).strip()
        # Strip optional word-timing tags, but keep actual Unicode lyric text.
        content = re.sub(r"<\d+:\d+(?:\.\d+)?>", "", content)
        for stamp in stamps:
            minute, second, fraction = stamp.groups()
            t = int(minute)*60 + int(second) + int((fraction or "0").ljust(3, "0"))/1000 + shift
            # Prefer the first nonempty line (original language) over translation duplicates.
            if t not in lines or not lines[t]:
                lines[t] = content
    return [LyricLine(t, v) for t, v in sorted(lines.items())]

def split_display(text: str, max_chars=16, max_bytes=48) -> list[str]:
    pages, part = [], ""
    for char in text:
        if unicodedata.category(char).startswith("C"):
            continue
        if part and (len(part)+1 > max_chars or len((part+char).encode("utf-8")) > max_bytes):
            pages.append(part)
            part = ""
        part += char
    if part.strip():
        pages.append(part.strip())
    return pages or ["♪"]

def line_at(lines: list[LyricLine], position: float, duration: float=0):
    if not lines:
        return None
    index = bisect_right([line.time for line in lines], position)-1
    if index < 0:
        return None
    line = lines[index]
    end = lines[index+1].time if index+1 < len(lines) else max(duration, line.time+6)
    if not line.text:
        return None
    pages = split_display(line.text)
    page_seconds = max(0.7, (end-line.time)/len(pages))
    page = min(len(pages)-1, int(max(0,position-line.time)/page_seconds))
    return {"text": pages[page], "full": line.text, "index": index, "page": page+1,
            "pages": len(pages), "start": line.time, "end": end}

def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())

def same_recording(title, artist, duration, candidate):
    if normalize(title) != normalize(candidate.get("name", "")):
        return False
    artists = candidate.get("artists", candidate.get("ar", []))
    actual = normalize(" ".join(a.get("name", "") for a in artists))
    expected = normalize(artist)
    if expected and not (expected == actual or expected in actual or actual and actual in expected):
        return False
    seconds = candidate.get("duration", candidate.get("dt", 0))/1000
    return not duration or not seconds or abs(seconds-duration) <= 5

class LyricsStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.http = requests.Session()
        self.http.headers.update({"User-Agent":"HaloStudio/1.0 (personal desktop lyrics display)",
                                  "Referer":"https://music.163.com/"})

    def key(self, title, artist, duration=0):
        # Metadata identifies local overrides even if a player's duration arrives late.
        return hashlib.sha256((normalize(title)+"|"+normalize(artist)).encode()).hexdigest()

    def save(self, title, artist, duration, lrc, source):
        lines = parse_lrc(lrc)
        if not lines:
            raise ValueError("文件中没有有效的 LRC 时间标签")
        suffix=".manual.json" if source=="本地 LRC" else ".json"
        target = self.directory / (self.key(title,artist,duration)+suffix)
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps({"lrc":lrc,"source":source},ensure_ascii=False),encoding="utf-8")
        temp.replace(target)
        return lines, source

    def invalidate(self,title,artist,duration=0):
        (self.directory / (self.key(title,artist,duration)+".json")).unlink(missing_ok=True)

    def fetch(self, title, artist, album, duration, allow_online=True):
        for suffix in (".manual.json",".json"):
            target = self.directory / (self.key(title,artist,duration)+suffix)
            if not target.exists():continue
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
                parsed = parse_lrc(data["lrc"])
                if parsed:
                    return parsed, data["source"]+" · 缓存"
            except (ValueError,KeyError,OSError):
                pass
        if not allow_online:
            return [], "联网获取已关闭，可导入本地 LRC"
        errors = []
        try:
            response = self.http.post("https://music.163.com/api/search/get/web",
                data={"s":f"{title} {artist}","type":1,"limit":15,"offset":0},timeout=(4,7))
            response.raise_for_status()
            songs = response.json().get("result",{}).get("songs",[])
            for song in songs:
                if not same_recording(title,artist,duration,song):
                    continue
                response = self.http.get("https://music.163.com/api/song/lyric",
                    params={"id":song["id"],"lv":-1,"kv":-1,"tv":-1},timeout=(4,7))
                response.raise_for_status()
                lrc = response.json().get("lrc",{}).get("lyric", "")
                if parse_lrc(lrc):
                    return self.save(title,artist,duration,lrc,"网易云音乐")
        except (requests.RequestException,ValueError,KeyError) as exc:
            errors.append(type(exc).__name__)
        try:
            params = {"track_name":title,"artist_name":artist}
            if duration:
                params["duration"] = round(duration)
            if album:
                params["album_name"] = album
            response = self.http.get("https://lrclib.net/api/get",params=params,timeout=(4,7))
            if response.status_code == 200:
                data = response.json()
                lrc = data.get("syncedLyrics") or ""
                if lrc:
                    return self.save(title,artist,duration,lrc,"LRCLIB")
        except (requests.RequestException,ValueError,KeyError) as exc:
            errors.append(type(exc).__name__)
        return [], "暂无匹配的同步歌词；可导入 LRC" + ("（网络请求失败）" if errors else "")
