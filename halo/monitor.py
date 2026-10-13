"""Read-only, demand-driven counters; no kernel drivers or polling subprocesses."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import os
import time
import psutil

@dataclass
class Metric:
    key: str
    name: str
    short: str
    value: float | None
    unit: str
    source: str
    scale: float | None = None

    def text(self):
        if self.value is None:return "--"
        if self.unit=="B/s":
            value=self.value
            for unit in ("B/s","K/s","M/s","G/s"):
                if value<1000:return f"{value:.0f}{unit}" if value>=10 else f"{value:.1f}{unit}"
                value/=1024
        if self.unit=="GHz":return f"{self.value:.2f}G"
        return f"{self.value:.0f}{self.unit}"

def rpm_percentage(rpm, rated_max):
    # An observed peak is not the rated maximum. Unknown stays unknown.
    return 100*rpm/rated_max if rpm is not None and rated_max and rated_max>0 else None

class HardwareMonitor:
    def __init__(self):
        self.nv=None; self.gpus=[]; self.nv_attempted=False
        self.wmi=None; self.wmi_checked=False
        self.last_time=None; self.last_net=None; self.last_disk=None
        self.metrics=[]; self.fans=[]; self.detail="尚未采样"
        psutil.cpu_percent(None)

    def _init_gpu(self):
        if self.nv_attempted:return
        self.nv_attempted=True
        try:
            import pynvml
            pynvml.nvmlInit(); self.nv=pynvml
            self.gpus=[pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(pynvml.nvmlDeviceGetCount())]
        except Exception:self.nv=None

    def _init_wmi(self):
        if self.wmi_checked:return
        self.wmi_checked=True
        # Reuse an already-running provider. Never open another kernel monitor.
        try:
            from comtypes.client import CreateObject
            locator=CreateObject("WbemScripting.SWbemLocator",dynamic=True)
            for namespace in (r"root\LibreHardwareMonitor",r"root\OpenHardwareMonitor"):
                try:self.wmi=locator.ConnectServer(".",namespace); break
                except Exception:pass
        except Exception:pass

    def sample(self,fan_limits=None):
        limits=fan_limits or {}; now=time.monotonic(); self._init_gpu(); self._init_wmi()
        metrics=[]; fans=[]
        def add(key,name,short,value,unit,source,scale=None):
            metrics.append(Metric(key,name,short,value,unit,source,scale))
        add("cpu","CPU 使用率","CPU",psutil.cpu_percent(None),"%","Windows / psutil",100)
        memory=psutil.virtual_memory(); add("ram","内存使用率","RAM",memory.percent,"%","Windows / psutil",100)
        add("ram_gb","已用内存","RAM",memory.used/1024**3,"GB","Windows / psutil")
        try:
            frequency=psutil.cpu_freq()
            if frequency:add("frequency","CPU 标称频率","CPU",frequency.current/1000,"GHz","Windows 报告频率（非实时核心频率）")
        except Exception:pass
        net=psutil.net_io_counters(); disk=psutil.disk_io_counters()
        span=now-self.last_time if self.last_time else 0
        for key,name,short,current,previous in (("upload","网络上传","UP",net.bytes_sent,self.last_net.bytes_sent if self.last_net else None),
                ("download","网络下载","DN",net.bytes_recv,self.last_net.bytes_recv if self.last_net else None),
                ("disk_read","磁盘读取","READ",disk.read_bytes if disk else 0,self.last_disk.read_bytes if self.last_disk else None),
                ("disk_write","磁盘写入","WRITE",disk.write_bytes if disk else 0,self.last_disk.write_bytes if self.last_disk else None)):
            add(key,name,short,max(0,(current-previous)/span) if previous is not None and span>0 else None,"B/s","Windows / psutil")
        self.last_time,self.last_net,self.last_disk=now,net,disk
        for index,handle in enumerate(self.gpus):
            n=self.nv; prefix=f"gpu{index}"; label="GPU" if index==0 else f"GPU{index+1}"
            def get(fn,*args):
                try:return getattr(n,fn)(handle,*args)
                except Exception:return None
            usage=get("nvmlDeviceGetUtilizationRates")
            add(prefix,"显卡使用率",label,usage.gpu if usage else None,"%","NVIDIA NVML",100)
            add(prefix+"_temp","显卡温度",label,get("nvmlDeviceGetTemperature",0),"C","NVIDIA NVML",100)
            power=get("nvmlDeviceGetPowerUsage")
            add(prefix+"_power","显卡功耗",label,power/1000 if power is not None else None,"W","NVIDIA NVML")
            for fan in range(get("nvmlDeviceGetNumFans") or 0):
                key=f"{prefix}_fan{fan}"; rpm=None
                try:
                    # NVIDIA's public C API permits selecting each fan; the Python wrapper selects only fan 0.
                    from ctypes import byref
                    info=n.c_nvmlFanSpeedInfo_t(); info.version=n.nvmlFanSpeedInfo_v1; info.fan=fan
                    n._nvmlCheckReturn(n._nvmlGetFunctionPointer("nvmlDeviceGetFanSpeedRPM")(handle,byref(info)))
                    rpm=info.speed
                except Exception:pass
                percent=get("nvmlDeviceGetFanSpeed_v2",fan)
                rated=rpm_percentage(rpm,limits.get(key))
                fans.append({"key":key,"name":f"{label} 风扇 {fan+1}","rpm":rpm,"driver_percent":percent,
                    "rated_max":limits.get(key,0),"rated_percent":rated,"source":"NVIDIA NVML"})
                add(key,f"{label} 风扇 {fan+1}",f"FAN{fan+1}",rpm,"RPM","NVML 驱动报告转速")
                add(key+"_percent",f"{label} 风扇 {fan+1} 驱动比例",f"F{fan+1}DRV",percent,"%","NVML 目标转速比例（非实测 RPM / 最大 RPM）",100)
                if rated is not None:add(key+"_rated",f"{label} 风扇 {fan+1} / 额定",f"F{fan+1}MAX",rated,"%","驱动报告 RPM / 手动额定最大 RPM",100)
        if self.wmi:
            try:
                sensors=self.wmi.ExecQuery("SELECT Identifier,Name,SensorType,Value FROM Sensor WHERE SensorType='Temperature' OR SensorType='Fan'","WQL",0x30)
                for sensor in sensors:
                    identifier=str(sensor.Identifier); kind=str(sensor.SensorType); value=sensor.Value
                    if value is None:continue
                    key="lhm:"+identifier
                    if kind=="Temperature":
                        short="CPU" if "cpu" in identifier else "TEMP"
                        add(key,str(sensor.Name),short,float(value),"C","现有硬件监控 WMI",100)
                    elif kind=="Fan":
                        rpm=float(value); rated=rpm_percentage(rpm,limits.get(key))
                        fans.append({"key":key,"name":str(sensor.Name),"rpm":rpm,"driver_percent":None,"rated_max":limits.get(key,0),"rated_percent":rated,"source":"现有硬件监控 WMI"})
                        add(key,str(sensor.Name),"FAN",rpm,"RPM","现有硬件监控 WMI")
                        if rated is not None:add(key+"_rated",str(sensor.Name)+" / 额定","FANMAX",rated,"%","实测 RPM / 手动额定最大 RPM",100)
            except Exception:self.wmi=None
        self.metrics=metrics; self.fans=fans
        self.detail="CPU / 内存 / 网络 / 磁盘：Windows；GPU / 风扇：NVML。" if self.gpus else "CPU / 内存 / 网络 / 磁盘：Windows。"
        self.detail+=" 已复用硬件监控 WMI。" if self.wmi else " CPU 温度、主板风扇：未发现可复用的传感器服务。"
        return {"metrics":[{**asdict(m),"text":m.text()} for m in metrics],"fans":fans,"detail":self.detail,"sampled_at":now}

    def close(self):
        if self.nv:
            try:self.nv.nvmlShutdown()
            except Exception:pass
        self.nv=None; self.wmi=None

def monitor_frame(snapshot,config,elapsed):
    metrics=snapshot.get("metrics",[])
    selected=config.get("monitor_metrics",["cpu","ram","gpu0","gpu0_temp","download","upload"])
    chosen=[m for key in selected for m in metrics if m["key"]==key]
    if not chosen:return "等待监控数据"
    interval=max(2,config.get("rotation_seconds",4))
    rotation=config.get("monitor_rotate",True)
    index=int(elapsed/interval)%len(chosen) if rotation else 0
    metric=chosen[index]; short=metric["short"]; value=metric["text"]
    view=config.get("monitor_view","value")
    if view=="bar" and metric.get("scale") and metric["value"] is not None:
        filled=max(0,min(4,round(metric["value"]/metric["scale"]*4)))
        return f"{short[:4]}{'|'*filled}{'.'*(4-filled)}{value}"[:16]
    if view=="compact" and len(chosen)>1:
        other=chosen[(index+1)%len(chosen)]
        def compact(m):return m['short'][:3]+m['text']
        text=compact(metric)+" "+compact(other)
        if len(text)<=16:return text
    return f"{short} {value}"[:16]
