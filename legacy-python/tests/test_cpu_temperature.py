from halo.cpu_temperature import FORMAT,decode_snapshot,decode_amd_temperature
from halo.pixel_monitor import HardwareMonitor

def packet(**changes):
    values=dict(magic=b'HALOTC02',version=2,parent=123,request=10000,stamp=10000,
                sequence=2,status=0,raw=432<<21,family=0x1a,model=0x44,cpu=54.,pid=456,stop=0,
                backend=1,reused=1,samples=1,error=0)
    values.update(changes);return FORMAT.pack(*values.values())

def test_snapshot_only_accepts_fresh_complete_real_cpu_reading():
    assert decode_snapshot(packet(),12000)==dict(pid=456,cpu=54.0,age_ms=2000,raw=432<<21,family=0x1a,model=0x44,
                                               backend='WinRing0',reused=True,samples=1)
    assert decode_snapshot(packet(backend=2,reused=0),12000)['backend']=='PawnIO'
    for updates in (dict(sequence=3),dict(sequence=0),dict(magic=b'BADMAGIC'),dict(version=1),
                    dict(status=4),dict(cpu=0),dict(cpu=-1),dict(cpu=float('nan')),
                    dict(cpu=500),dict(stop=1),dict(pid=0),dict(parent=0),dict(raw=0xffffffff),dict(family=6),
                    dict(backend=0),dict(reused=2),dict(samples=0)):
        assert decode_snapshot(packet(**updates),12000) is None
    assert decode_snapshot(packet(),20001) is None
    assert decode_snapshot(packet(),9000) is None
    assert decode_snapshot(packet()[:-1],12000) is None

def test_amd_zen_range_and_new_tj_sel_match_upstream():
    assert decode_amd_temperature(432<<21)==54
    assert decode_amd_temperature((824<<21)|0x80000)==54
    assert decode_amd_temperature((824<<21)|0x30000)==54
    assert decode_amd_temperature((824<<21)|0x10000)==103
    assert decode_amd_temperature(432<<21,'AMD Ryzen 7 2700X')==44

def test_adapter_adds_independent_cpu_and_preserves_nvml_gpu(monkeypatch):
    from halo.monitor import HardwareMonitor as Base
    monkeypatch.setattr(Base,'sample',lambda *a:dict(metrics=[dict(key='gpu0_temp',unit='C',value=51,short='GPU',text='51C')],detail='test'))
    h=HardwareMonitor()
    monkeypatch.setattr(h.cpu_temperature,'read',lambda:dict(cpu=54,age_ms=500))
    result=h.sample();assert result['metrics'][0]['text']=='51°C'
    cpu=result['metrics'][1]
    assert cpu['key']=='cpu_temp' and cpu['value']==54 and cpu['text']=='54°C' and cpu['sample_age_ms']==500
    assert 'TrafficMonitor' not in cpu['source'];h.close()

def test_wmi_has_priority_and_later_provider_can_be_discovered(monkeypatch):
    from halo.monitor import HardwareMonitor as Base
    monkeypatch.setattr(Base,'sample',lambda *a:dict(metrics=[dict(key='lhm:/cpu/package',short='CPU',unit='C',value=57,text='57C')],detail='test'))
    h=HardwareMonitor();h.wmi_checked=True
    monkeypatch.setattr(h.cpu_temperature,'read',lambda:(_ for _ in ()).throw(AssertionError('must not poll redundant source')))
    result=h.sample()
    assert len(result['metrics'])==1 and result['metrics'][0]['text']=='57°C'
    assert not h.wmi_checked;h.close()
