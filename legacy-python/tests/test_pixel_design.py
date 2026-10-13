from datetime import datetime
from dataclasses import replace
import pytest
from PySide6.QtWidgets import QApplication
from halo.pixels import init_fonts, PixelFrame
from halo.pixel_design import render, THEMES, monitor_values, value_text
from halo.pixel_engine import DEFAULTS
from halo.pixel_scene import transition_frame
from halo.ram_codec import encode, decode


@pytest.fixture(scope='module', autouse=True)
def fonts():
    app=QApplication.instance() or QApplication([]); init_fonts(); yield app


def sample():
    return {'metrics':[
        dict(key='cpu',short='CPU',value=37,unit='%',text='37%',scale=100,history=[12,20,30,37]),
        dict(key='ram',short='RAM',value=42,unit='%',text='42%',scale=100),
        dict(key='ram_gb',short='RAM',value=11.48,unit='GB',text='11GB'),
        dict(key='gpu0',short='GPU',value=64,unit='%',text='64%',scale=100),
        dict(key='gpu0_temp',short='GPU',value=51,unit='C',text='51C',scale=100),
        dict(key='upload',short='UP',value=1280,unit='B/s',text='1.2K/s'),
        dict(key='download',short='DN',value=None,unit='B/s',text='--')]}


def crop(data,x0,y0,w,h):
    return tuple(bool(data[(y//8)*256+x] & (1<<(y%8))) for y in range(y0,y0+h) for x in range(x0,x0+w))


@pytest.mark.parametrize('mode,text',[('时钟','20:26:08'),('系统监控',''),('歌词','把每个明天写成一首歌')])
def test_theme_difference_in_content_not_only_avatar(mode,text):
    frames=[render(text,mode,{**DEFAULTS,'theme':key,'themes':True,'monitor_rotate':False},0,sample(),datetime(2026,10,13)) for key in THEMES]
    assert len({crop(f.pixels,40,4,195,24) for f in frames})==6
    for f in frames:
        assert len(f.pixels)==1024
        encoded=encode(f.pixels)
        assert decode(encoded)==f.pixels
        assert encoded.packets<29


def test_dense_values_missing_temperature_and_memory_precision():
    values=monitor_values(sample())
    assert values[2][0][1]['value'] is None  # CPU temperature is not GPU temperature
    assert values[2][1][1]['value']==51
    config={**DEFAULTS,'monitor_view':'dense','monitor_metrics':[]}
    frame=render('', '系统监控', config, 0, sample())
    assert all(v in frame.text for v in ('UP 1.25K','DN --','CPU 37%','GPU 64%','C --','G 51°C','11.48G'))
    assert frame.identity=='系统监控:dense'
    assert render('', '系统监控', config, 100, sample()).pixels==frame.pixels
    empty=render('', '系统监控', config, 0, {})
    assert empty.text.count('--')==8


def test_cpu_package_sensor_preferred_and_gpu_index_respected():
    snapshot={'metrics':[
        dict(key='gpu2',short='GPU3',unit='%',value=1),
        dict(key='gpu2_temp',short='GPU3',unit='C',value=52),
        dict(key='lhm:cpu/core0',short='CPU',unit='C',name='Core',value=30),
        dict(key='lhm:cpu/package',short='CPU',unit='C',name='Package',value=54)]}
    values=monitor_values(snapshot)
    assert values[2][0][1]['value']==54
    assert values[2][1][1]['value']==52


@pytest.mark.parametrize('key',list(THEMES))
def test_real_metric_changes_right_instrument_and_bar(key):
    snap=sample(); cfg={**DEFAULTS,'theme':key,'themes':True,'monitor_rotate':False}
    for view in ('value','bar','graph'):
        cfg['monitor_view']=view; a=render('','系统监控',cfg,0,snap)
        other={'metrics':[{**snap['metrics'][0],'value':81,'text':'81%','history':[12,20,30,81]}]}
        b=render('','系统监控',cfg,0,other)
        assert crop(a.pixels,138,0,118,32)!=crop(b.pixels,138,0,118,32)
        encoded=encode(b.pixels,a.pixels,1)
        assert decode(encoded,a.pixels,1)==b.pixels


@pytest.mark.parametrize('key',list(THEMES))
def test_monitor_views_and_static_animation_off(key):
    cfg={**DEFAULTS,'theme':key,'themes':True,'animations':False,'monitor_rotate':False}
    frames=[render('','系统监控',{**cfg,'monitor_view':v},0,sample()) for v in ('value','bar','compact','graph','dense')]
    # Paper intentionally treats its bar as an area chart; other compositions
    # still remain distinct, and every theme has at least four useful layouts.
    assert len({f.pixels for f in frames})>=4
    assert render('20:26','时钟',cfg,0,now=datetime(2026,10,13)).pixels==render('20:26','时钟',cfg,15,now=datetime(2026,10,13)).pixels


def test_full_width_monitor_transition_covers_edges_and_lyrics_stay_in_viewport():
    off=PixelFrame(bytes(1024),'','系统监控:cpu'); on=replace(off,pixels=bytes([255])*1024,identity='系统监控:ram')
    mid=transition_frame(off,on,'wipe')
    assert all(crop(mid.pixels,0,0,128,32))
    assert not any(crop(mid.pixels,128,0,128,32))
    lyric=replace(on,identity='歌词:test')
    mid=transition_frame(off,lyric,'wipe')
    assert all(crop(mid.pixels,0,0,38,32))
    assert not any(crop(mid.pixels,138,4,100,24))


def test_units_at_boundaries_are_not_cut_off_or_mislabelled():
    assert value_text(dict(value=1024,unit='B/s'))=='1.00K/S'
    assert value_text(dict(value=11.48,unit='GB'))=='11.48GB'
    assert value_text(dict(value=None,unit='C'))=='--'
    assert value_text(dict(value=54.3,unit='C',text='54C'))=='54°C'


def test_degree_ring_has_hollow_center_in_small_and_big_pixel_fonts():
    from halo.pixel_design import small,digits
    from halo.pixels import Canvas
    c=Canvas();small(c,'°C',0,0)
    ring=crop(bytes(c.data),0,0,3,3)
    assert sum(ring)==4 and not ring[4]
    assert not any(crop(bytes(c.data),3,0,1,7))
    assert any(crop(bytes(c.data),4,0,5,7))
    from halo.pixel_design import degree_ring, raster_text, raster_width
    for scale in (1,2,3,4):
        c=Canvas();raster_text(c,'°C',0,0,scale)
        size=3 if scale<=2 else 5
        # The physical circle stays smaller than a full scaled character,
        # with one empty pixel column before the C glyph cell.
        assert not any(crop(bytes(c.data),size,0,1,7*scale))
        assert any(crop(bytes(c.data),size+1,0,5*scale,7*scale))
        assert raster_width('°C',scale)==size+1+5*scale
