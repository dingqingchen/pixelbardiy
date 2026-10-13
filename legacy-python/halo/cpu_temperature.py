"""Independent, on-demand AMD Tctl/Tdie sampler; no TrafficMonitor plugin/API.

The native helper ports LibreHardwareMonitor's fixed AMD SMN path. An explicit
UI action requests UAC for this helper, not for the whole UI. Loaded drivers are
reused; otherwise the pinned, signed PawnIO package prepares an independent path.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes as W
import json
import math
import mmap
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import uuid

FORMAT=struct.Struct('<8sIIQQIIIIIfIIIIII')
MAX_AGE_MS=10000
STATUS={0:'AMD Tctl/Tdie 直读',1:'等待管理员确认或首次采样',2:'本机 CPU 不属于支持的 AMD Zen 系列',
        3:'独立硬件驱动暂不可用',4:'Windows 拒绝驱动访问，请启用独立采集器',
        5:'PCI 总线忙，等待下次采样',6:'温度寄存器读取失败',7:'采集器已关闭',8:'独立采集器尚未启用',
        9:'管理员确认已取消',10:'独立采集器文件缺失',11:'驱动安装完成，需要重启 Windows',
        12:'正在准备独立硬件驱动',13:'驱动安装包或模块校验失败'}

def decode_snapshot(raw,now):
    if len(raw)!=FORMAT.size:return None
    magic,version,parent,request,stamp,sequence,status,register,family,model,t,pid,stop,backend,reused,samples,error=FORMAT.unpack(raw)
    if magic!=b'HALOTC02' or version!=2 or not parent or not pid or not sequence or sequence&1 or status!=0 or stop:return None
    if backend not in (1,2) or reused not in (0,1) or not samples:return None
    if family not in (0x17,0x19,0x1a) or register in (0,0xffffffff):return None
    if now<stamp or now-stamp>MAX_AGE_MS or not math.isfinite(t) or not 0<t<=150:return None
    return dict(cpu=t,age_ms=now-stamp,pid=pid,raw=register,family=family,model=model,
                backend='WinRing0' if backend==1 else 'PawnIO',reused=bool(reused),samples=samples)

def decode_amd_temperature(raw,brand=''):
    """Pure reference function for regression checks against upstream logic."""
    t=(raw>>21)*0.125
    if raw&0x80000 or raw&0x30000==0x30000:t-=49
    if any(n in brand for n in ('1600X','1700X','1800X')):t-=20
    elif 'Threadripper 19' in brand or 'Threadripper 29' in brand:t-=27
    elif '2700X' in brand:t-=10
    return t

class CpuTemperature:
    def __init__(self):
        self.memory=None;self.event=None;self.api=None;self.process=None
        self.status=8;self.launching=False;self.closed=False;self.thread=None;self.exit_confirmed=None
        base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
        self.executable=(base/'native'/'HaloThermal.exe').resolve()

    @property
    def detail(self):return STATUS.get(self.status,'采集器暂不可用')

    def _init_api(self):
        if self.api:return
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateEventW.argtypes=[W.LPVOID,W.BOOL,W.BOOL,W.LPCWSTR];api.CreateEventW.restype=W.HANDLE
        api.SetEvent.argtypes=[W.HANDLE];api.SetEvent.restype=W.BOOL
        api.CloseHandle.argtypes=[W.HANDLE];api.CloseHandle.restype=W.BOOL
        api.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];api.WaitForSingleObject.restype=W.DWORD
        api.GetProcessId.argtypes=[W.HANDLE];api.GetProcessId.restype=W.DWORD
        api.GetTickCount64.restype=ctypes.c_uint64
        self.api=api

    def probe(self):
        if not self.executable.is_file():self.status=10;return {}
        try:
            row=json.loads(subprocess.check_output([str(self.executable),'--probe'],timeout=3,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
            self.status=row['status'] if not row.get('supported') or row['status'] else 8
            return row
        except (OSError,ValueError,subprocess.SubprocessError):self.status=6;return {}

    def enable(self,elevate=True):
        if self.closed or self.launching:return
        if elevate:
            probe=self.probe()
            if not probe.get('supported'):return
        self._init_api()
        if self.process and self.api.WaitForSingleObject(self.process,0)==258:return
        self._dispose()
        if not self.executable.is_file():self.status=10;return
        token=uuid.uuid4().hex;name=f'Local\\HaloStudioCpu-{os.getpid()}-{token}'
        self.memory=mmap.mmap(-1,FORMAT.size,tagname=name,access=mmap.ACCESS_WRITE)
        self.memory[:]=FORMAT.pack(b'HALOTC02',2,os.getpid(),0,0,0,1,0,0,0,0,0,0,0,0,0,0)
        self.event=self.api.CreateEventW(None,False,False,name+'-request')
        if not self.event:self._dispose();self.status=6;return
        self.status=1;self.launching=True
        def launch():
            # Only the fixed compiled helper is elevated. No shell command/script.
            class Info(ctypes.Structure):
                _fields_=[('size',W.DWORD),('mask',W.ULONG),('hwnd',W.HWND),('verb',W.LPCWSTR),
                    ('file',W.LPCWSTR),('parameters',W.LPCWSTR),('directory',W.LPCWSTR),('show',ctypes.c_int),
                    ('instance',W.HINSTANCE),('idlist',W.LPVOID),('class_',W.LPCWSTR),('key',W.HKEY),
                    ('hotkey',W.DWORD),('icon',W.HANDLE),('process',W.HANDLE)]
            try:
                shell=ctypes.WinDLL('shell32',use_last_error=True)
                shell.ShellExecuteExW.argtypes=[ctypes.POINTER(Info)];shell.ShellExecuteExW.restype=W.BOOL
                info=Info();info.size=ctypes.sizeof(Info);info.mask=0x40|0x100
                info.verb='runas' if elevate else 'open';info.file=str(self.executable)
                info.parameters=f'{os.getpid()} {token}';info.directory=str(self.executable.parent);info.show=0
                if shell.ShellExecuteExW(ctypes.byref(info)):
                    if self.closed:self.api.CloseHandle(info.process)
                    else:self.process=info.process;self.api.SetEvent(self.event)
                else:self.status=9 if ctypes.get_last_error()==1223 else 6
            except OSError:self.status=6
            finally:self.launching=False
        self.thread=threading.Thread(target=launch,name='CPU temperature approval',daemon=True);self.thread.start()

    def read(self):
        if not self.memory or self.closed:return None
        if self.launching or not self.process:return None
        if self.process and self.api.WaitForSingleObject(self.process,0)!=258:
            status=struct.unpack_from('<I',self.memory,36)[0]
            self.status=status if status not in (0,1) else 7;return None
        request=self.api.GetTickCount64()
        self.memory[16:24]=struct.pack('<Q',request);self.api.SetEvent(self.event)
        # A short bounded wait obtains a fresh register reading; no polling thread.
        until=time.monotonic()+0.015
        while True:
            before=struct.unpack_from('<I',self.memory,32)[0];raw=self.memory[:]
            after=struct.unpack_from('<I',self.memory,32)[0]
            if before==after and not before&1:
                self.status=struct.unpack_from('<I',raw,36)[0]
                row=decode_snapshot(raw,self.api.GetTickCount64())
                if row and row['pid']!=self.api.GetProcessId(self.process):row=None
                if row and struct.unpack_from('<Q',raw,24)[0]>=request:return row
            if time.monotonic()>=until:return row if before==after and not before&1 else None
            time.sleep(0.001)

    def _dispose(self):
        if self.process:self.api.CloseHandle(self.process);self.process=None
        if self.event:self.api.CloseHandle(self.event);self.event=None
        if self.memory:self.memory.close();self.memory=None

    def close(self):
        self.closed=True
        if self.memory:
            self.memory[60:64]=struct.pack('<I',1);self.api.SetEvent(self.event)
        if self.process:self.exit_confirmed=self.api.WaitForSingleObject(self.process,1000)==0
        self._dispose()
