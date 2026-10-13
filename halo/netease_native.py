"""Narrow, read-only adapter for the locally validated NetEase 3.1.39 binary.

Pointer shape was researched using XFEstudio/HaloPixelToolBox (MIT).
RVA was independently located and exact-LRC-validated on this computer.
An unknown PE fingerprint is never read using these offsets. No injection,
process writes, full-process scanning, account or cookie access is performed.
"""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import struct
import time
import psutil

SUPPORTED = {(1787745734,40951808): (35641104,"3.1.39")}

def clean_lyric(text):
    # Ideographic spaces, NBSP and line separators are normal lyric typography.
    # Normalize them before rejecting control characters with isprintable().
    text=' '.join(text.split()).replace('\ufeff','').replace('\u200b','')
    return text if len(text)<=100 and text.isprintable() else ''
k=C.WinDLL("kernel32",use_last_error=True)
u=C.WinDLL("user32",use_last_error=True)
k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD]; k.OpenProcess.restype=W.HANDLE
k.ReadProcessMemory.argtypes=[W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]; k.ReadProcessMemory.restype=W.BOOL
k.CloseHandle.argtypes=[W.HANDLE]
k.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD]; k.CreateToolhelp32Snapshot.restype=W.HANDLE
class Module(C.Structure):
    _fields_=[("dwSize",W.DWORD),("th32ModuleID",W.DWORD),("th32ProcessID",W.DWORD),("GlblcntUsage",W.DWORD),("ProccntUsage",W.DWORD),("modBaseAddr",C.c_void_p),("modBaseSize",W.DWORD),("hModule",W.HMODULE),("szModule",W.WCHAR*256),("szExePath",W.WCHAR*260)]
k.Module32FirstW.argtypes=[W.HANDLE,C.POINTER(Module)]; k.Module32FirstW.restype=W.BOOL
k.Module32NextW.argtypes=[W.HANDLE,C.POINTER(Module)]; k.Module32NextW.restype=W.BOOL
CALLBACK=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
u.EnumWindows.argtypes=[CALLBACK,W.LPARAM]; u.EnumWindows.restype=W.BOOL
u.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
u.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]

def main_window_titles():
    result={}
    @CALLBACK
    def visit(hwnd,_):
        pid=W.DWORD(); u.GetWindowThreadProcessId(hwnd,C.byref(pid))
        text=C.create_unicode_buffer(1024); u.GetWindowTextW(hwnd,text,len(text))
        if " - " in text.value:result.setdefault(pid.value,text.value)
        return True
    u.EnumWindows(visit,0)
    return result

def find_module(pid):
    snap=k.CreateToolhelp32Snapshot(0x18,pid); entry=Module(); entry.dwSize=C.sizeof(entry)
    try:
        ok=k.Module32FirstW(snap,C.byref(entry))
        while ok:
            if entry.szModule.lower()=="cloudmusic.dll":return int(entry.modBaseAddr),entry.szExePath
            ok=k.Module32NextW(snap,C.byref(entry))
    finally:k.CloseHandle(snap)
    return None

def fingerprint(path):
    with open(path,"rb") as stream:
        head=stream.read(64)
        if head[:2]!=b"MZ":return None
        pe=struct.unpack_from("<I",head,60)[0]
        stream.seek(pe)
        header=stream.read(84)
        if header[:4]!=b"PE\0\0":return None
        return struct.unpack_from("<I",header,8)[0],struct.unpack_from("<I",header,80)[0]

class NativeNetEase:
    def __init__(self):
        self.handle=None; self.pid=0; self.base=0; self.rva=0; self.version=""
        self.next_find=0; self.next_audio=0; self.playing=False
        self.last_line=""; self.line_since=time.monotonic(); self.com_initialized=False
        import comtypes
        try:comtypes.CoInitializeEx(0); self.com_initialized=True
        except OSError:pass

    def close_handle(self):
        if self.handle:k.CloseHandle(self.handle)
        self.handle=None

    def close(self):
        self.close_handle()
        if self.com_initialized:
            import comtypes
            comtypes.CoUninitialize(); self.com_initialized=False

    def read(self,address,size):
        if not self.handle or not 0x10000<address<0x7fffffffffff:return b""
        buffer=C.create_string_buffer(size); count=C.c_size_t()
        if k.ReadProcessMemory(self.handle,address,buffer,size,C.byref(count)):return buffer.raw[:count.value]
        return b""

    def ptr(self,address):
        value=self.read(address,8)
        return int.from_bytes(value,"little") if len(value)==8 else 0

    def poll(self):
        now=time.monotonic(); titles=main_window_titles()
        if not self.handle or self.pid not in titles:
            if now<self.next_find:return None
            self.close_handle(); self.next_find=now+3
            for process in psutil.process_iter(["name"]):
                if (process.info["name"] or "").lower()!="cloudmusic.exe" or process.pid not in titles:continue
                module=find_module(process.pid)
                if not module:continue
                profile=SUPPORTED.get(fingerprint(module[1]))
                if not profile:continue
                self.handle=k.OpenProcess(0x1010,False,process.pid)
                if self.handle:self.pid=process.pid; self.base=module[0]; self.rva,self.version=profile; break
        if not self.handle:return None
        caption=titles.get(self.pid,"")
        if " - " not in caption:return None
        title,artist=caption.rsplit(" - ",1)
        if now>=self.next_audio:
            from .rhythm import netease_sessions
            self.playing=any(session.GetState()==1 for session in netease_sessions())
            self.next_audio=now+0.6
        root=self.ptr(self.base+self.rva)
        second=self.ptr(root+0x120) if root else 0
        final=self.ptr(second+8) if second else 0
        raw=self.read(final,200) if final else b""
        # Locate terminator before decoding, so unrelated trailing buffer bytes never matter.
        end=next((i for i in range(0,len(raw)-1,2) if raw[i:i+2]==b"\0\0"),len(raw))
        try:line=clean_lyric(raw[:end].decode("utf-16-le"))
        except UnicodeDecodeError:line=""
        if line!=self.last_line:self.last_line=line; self.line_since=now
        return {"title":title.strip(),"artist":artist.strip(),"playing":self.playing,
                "app":"cloudmusic.exe","provider":"网易云本地 · "+self.version,
                "realtime_lyric":line,"line_elapsed":now-self.line_since}
