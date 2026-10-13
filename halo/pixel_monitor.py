"""New studio's sensor adapter; retained legacy monitor stays independent."""
import time
from .monitor import HardwareMonitor as BaseMonitor
from .cpu_temperature import CpuTemperature


class HardwareMonitor(BaseMonitor):
    def __init__(self):
        super().__init__();self.cpu_temperature=CpuTemperature();self.next_wmi_probe=0

    def sample(self,fan_limits=None):
        # The sensor provider may start after HaloStudio. Retry at low frequency.
        now=time.monotonic()
        if self.wmi is None and now>=self.next_wmi_probe:
            self.wmi_checked=False;self.next_wmi_probe=now+30
        snapshot=super().sample(fan_limits)
        temperatures=[m for m in snapshot['metrics'] if m['unit']=='C' and m['value'] is not None
                      and ('cpu' in m['key'].casefold() or m['short']=='CPU')]
        if not temperatures:
            row=self.cpu_temperature.read()
            if row:
                snapshot['cpu_temperature_register']=row.get('raw')
                snapshot['cpu_temperature_backend']={k:row.get(k) for k in ('backend','reused','samples')}
                snapshot['metrics'].append(dict(key='cpu_temp',name='CPU 温度（Tctl/Tdie）',
                    short='CPU',value=row['cpu'],unit='C',scale=100,text=f"{row['cpu']:.0f}°C",
                    source='AMD SMN / LibreHardwareMonitor 源码移植',sample_age_ms=row['age_ms']))
                snapshot['detail']=snapshot['detail'].replace(' CPU 温度、主板风扇：未发现可复用的传感器服务。',
                    ' CPU 温度：AMD 寄存器直读；主板风扇未发现传感器。')
            else:
                snapshot['detail']+=' CPU 温度：'+self.cpu_temperature.detail+'。'
        for metric in snapshot['metrics']:
            if metric['unit']=='C' and metric['value'] is not None:metric['text']=f"{metric['value']:.0f}°C"
        snapshot['cpu_temperature_status']=self.cpu_temperature.status
        return snapshot

    def close(self):
        self.cpu_temperature.close();super().close()
