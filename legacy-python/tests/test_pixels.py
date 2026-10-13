import math
import pytest
from halo.pixels import Canvas,render,encode,decode,PixelFrame,init_fonts,chinese_mask
from halo.themes import THEMES
from halo.engine import DEFAULTS
from halo.device import HaloLink
from halo.rhythm import Envelope

def test_canvas_coordinates_record_headers_and_round_trip():
    c=Canvas()
    for x,y in ((0,0),(255,31),(127,7),(128,8),(30,23)):c.dot(x,y)
    assert c.data[0]==1 and c.data[1023]==128
    assert c.data[127]==128 and c.data[384]==1 and c.data[542]==128
    data=encode(c.data)
    assert len(data)==1064 and decode(data)==bytes(c.data)
    assert [data[i*133:i*133+5] for i in range(8)]==[bytes([2,0,i,255,255]) for i in range(8)]
    with pytest.raises(ValueError):encode(b'bad')

def test_all_themes_contain_distinct_graphic_regions_and_font_is_not_tofu():
    regions=[]
    for theme in THEMES:
        f=render('20:26:08','时钟',{**DEFAULTS,'theme':theme},0)
        assert len(f.pixels)==1024
        region=b''.join(f.pixels[i:i+34] for i in range(0,1024,256))
        assert sum(v.bit_count() for v in region)>40
        regions.append(region)
    assert len(set(regions))==len(THEMES)
    letters=[]
    for text in ('PIXEL','TEST','20:26'):
        c=Canvas();c.text(text,0,0);letters.append(bytes(c.data))
    assert len(set(letters))==3

def test_monitor_layouts_and_selection_have_real_shapes():
    snapshot={'metrics':[{'key':'cpu','short':'CPU','value':45,'text':'45%','scale':100,'history':[10,60,20,90]},
                         {'key':'ram','short':'RAM','value':30,'text':'30%','scale':100}]}
    config={**DEFAULTS,'monitor_metrics':['cpu','ram']}
    frames=[render('CPU 45%','系统监控',{**config,'monitor_view':v},0,snapshot) for v in ('value','bar','compact','graph')]
    assert len(set(f.pixels for f in frames))==4
    assert frames[0].identity!=render('RAM 30%','系统监控',config,4,snapshot).identity

def test_loaded_chinese_font_has_different_glyph_shapes():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    init_fonts()
    a=chinese_mask('时间',17);b=chinese_mask('歌词',17)
    assert len(a)>50 and len(b)>50 and a!=b

@pytest.mark.parametrize('explicit_end',[False,True])
def test_fragmented_upload_commit_and_no_audio_volume_write(explicit_end):
    d=HaloLink(allow_resource_upload=True);writes=[];queries=[];now=0
    d._write=lambda p:writes.append(p)
    def query(command,payload=(),**kwargs):
        queries.append((command,bytes(payload)))
        if command==0xEE:return bytes([0,100,200,255,0,1,2,0,255])
        if payload[1]==0:return bytes([0,1,0,50])
        if payload[1]==4:return bytes([0,5])
        index=int.from_bytes(bytes(payload[2:4]),'big')
        return bytes([0,3 if index<21 or explicit_end else 5])
    d._pixel_query=query
    target=render('20:26:08','时钟',DEFAULTS,0);d.begin_pixels(target,'#64DFFF',True)
    for i in range(50):
        d.step_pixels(i*.2)
        if not d.pixel_job:break
    assert not d.pixel_job and d.pixel_frame==target
    fragments=[payload[4:] for cmd,payload in queries if cmd==0x17 and payload[1]==2]
    assert b''.join(fragments)==encode(target.pixels)
    assert all(cmd not in (0x67,0x11) for cmd,_ in queries)
    assert all(p[3]==0xEF for p in writes)

def test_rejected_upload_never_claims_a_frame_was_displayed():
    d=HaloLink(allow_resource_upload=True);d._pixel_query=lambda *a,**kw:bytes([0,8])
    d.begin_pixels(PixelFrame(bytes(1024),'test','clock'),'#FFFFFF')
    with pytest.raises(RuntimeError):d.step_pixels(0)
    assert d.pixel_frame is None

def test_loud_music_does_not_pin_energy_to_full_at_fixed_volume():
    e=Envelope();levels=[]
    for i in range(160):
        value=.65+.12*math.sin(i*.43)
        levels.append(e.update(value,i*.05,3))
    assert max(levels[40:])-min(levels[40:])>.5
    assert sum(v>.95 for v in levels[40:])<len(levels[40:])*.4
    assert e.update(0,20,3)<.001

def test_pixel_ack_wait_is_nonblocking_and_survives_other_queries():
    from collections import deque
    def response(command,data):
        p=bytearray([0x2f,0xbb,0xec,command,0,len(data),*data])
        p.append(sum(p[1:])&255)
        return bytes(p)
    class Handle:
        def __init__(self):self.incoming=deque();self.writes=[]
        def read(self,size):return self.incoming.popleft() if self.incoming else []
        def write(self,p):
            self.writes.append(p)
            if p[3]==0x66:self.incoming.append(response(0x66,[16,9]))
            return 64
    d=HaloLink(allow_resource_upload=True);d.handle=Handle()
    d.begin_pixels(PixelFrame(bytes(1024),'test','clock'),'#FFFFFF')
    d.step_pixels(0)
    assert d.pending_query and len(d.handle.writes)==1
    # An unavailable ACK must leave the loop free to update music immediately.
    for _ in range(10):d.step_pixels(0)
    assert len(d.handle.writes)==1
    d.rhythm_frame('#123456','high')
    assert d.handle.writes[-1][3]==0x6b
    d.handle.incoming.append(response(0x17,[0,1,0,50]))
    assert d.query(0x66)==bytes([16,9])
    d.step_pixels(0)
    assert d.pending_query is None and d.pixel_job['size']==50
