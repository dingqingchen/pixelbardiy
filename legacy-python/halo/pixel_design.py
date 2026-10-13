"""Six complete 256 × 32 art directions for the RAM display only.

No hardware access, sensor polling or wall-clock reads during painting. The old
renderer and palette registry remain available to the legacy application.
"""
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import math
from . import pixels
from .pixels import Canvas, PixelFrame, selected_metrics, CAT, BUNNY, HEART


@dataclass(frozen=True)
class Design:
    name: str
    color: str
    accent: str
    description: str


THEMES = {
    'ion': Design('科幻 · 离子仪表', '#64DFFF', '#677FFF', '切角数字 / 航空刻度 / 信号舷窗'),
    'matrix': Design('科幻 · 雷达终端', '#8DF5B4', '#27BD8F', '等宽数据 / 扫描栅格 / 指令字幕'),
    'peach': Design('可爱 · 桃兔甜点', '#FFB9CC', '#FFDAB0', '圆润字形 / 奶油卡片 / 兔兔气泡'),
    'kitty': Design('可爱 · 猫咪乐谱', '#D6BBFF', '#FFC1E3', '跳跃像素 / 钢琴键盘 / 猫咪五线谱'),
    'paper': Design('简约 · 月白书页', '#DAE9F2', '#90B2CC', '衬线数字 / 编辑排版 / 山形留白'),
    'amber': Design('复古 · 琥珀音响', '#FFC27A', '#FF915D', '点阵数字 / 磁带双盘 / 模拟电平'),
}

# A compact hollow ring. Keep this local to the
# new renderer so the legacy embedded typeface remains unchanged.
RASTER_FONT={**pixels.FONT,'°':(0b01000,0b10100,0b01000,0,0,0,0)}

def degree_size(scale):return 3 if scale<=2 else 5

def glyph_advance(char,scale=1):return degree_size(scale)+1 if char=='°' else 6*scale

def raster_width(text,scale=1):return max(0,sum(glyph_advance(ch,scale) for ch in str(text))-scale)

def degree_ring(c,x,y,size=3):
    rows=(0b010,0b101,0b010) if size==3 else (0b01110,0b10001,0b10001,0b10001,0b01110)
    for yy,bits in enumerate(rows):
        for xx in range(size):
            if bits & (1<<(size-1-xx)):c.dot(x+xx,y+yy)


def raster_text(c,text,x,y,scale=1,dotted=False):
    for char in str(text).upper():
        if char=='°':
            degree_ring(c,x,y,degree_size(scale));x+=glyph_advance(char,scale);continue
        for row,mask in enumerate(RASTER_FONT.get(char,RASTER_FONT['?'])):
            for col in range(5):
                if mask & (1<<(4-col)):
                    c.rect(x+col*scale,y+row*scale,scale-(dotted and scale>1),scale-(dotted and scale>1),True)
        x+=6*scale


def erase(c, x, y, w, h):
    for yy in range(y, y+h):
        for xx in range(x, x+w): c.dot(xx, yy, False)


def invert(c, x, y, w, h):
    for yy in range(max(0, y), min(32, y+h)):
        for xx in range(max(0, x), min(256, x+w)):
            c.dot(xx, yy, not (c.data[(yy//8)*256+xx] & (1 << (yy%8))))


def round_rect(c, x, y, w, h, r=3):
    c.line(x+r,y,x+w-r-1,y); c.line(x+r,y+h-1,x+w-r-1,y+h-1)
    c.line(x,y+r,x,y+h-r-1); c.line(x+w-1,y+r,x+w-1,y+h-r-1)
    for i in range(r):
        c.dot(x+r-i,y+i); c.dot(x+w-r-1+i,y+i)
        c.dot(x+r-i,y+h-i-1); c.dot(x+w-r-1+i,y+h-i-1)


def small(c, text, x, y, *, right=None):
    text = str(text).upper()
    if right is not None: x = right - raster_width(text)
    raster_text(c,text,x,y)


def tag(c, text, x, y, w=None):
    w = w or len(text)*6+5
    small(c,text,x+3,y+2); invert(c,x,y,w,11)


def star(c,x,y,r=2):
    c.line(x-r,y,x+r,y); c.line(x,y-r,x,y+r)


def font(family, size, bold=False):
    from PySide6.QtGui import QFont
    # The known-loaded Chinese family prevents the tofu regression.
    family = {'body':pixels._chinese_family or 'Microsoft YaHei',
              'round':'Segoe UI', 'serif':'Georgia', 'song':'SimSun'}.get(family,family)
    f=QFont(family); f.setPixelSize(size); f.setBold(bold)
    f.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    return f


@lru_cache(maxsize=256)
def text_mask(text,w,h,family='body',size=17,bold=False,align='center'):
    """Fit actual glyph advances, then wrap. Masks are bounded and cached."""
    from PySide6.QtGui import QImage,QPainter,QFontMetrics,QColor
    from PySide6.QtCore import Qt
    # Long source lyrics are paginated upstream. Two lines also cover previews
    # and longer Latin phrases without painting over adjacent instruments.
    lines=[text]; f=font(family,size,bold)
    for n in range(size,8,-1):
        f=font(family,n,bold); fm=QFontMetrics(f)
        if fm.horizontalAdvance(text)<=w and fm.height()<=h: break
        if n<=12 and h>=22:
            lines=[]; line=''
            for char in text:
                if line and fm.horizontalAdvance(line+char)>w:
                    lines.append(line); line=''
                line+=char
            if line: lines.append(line)
            if len(lines)*fm.height()<=h: break
            lines=[text]
    im=QImage(w,h,QImage.Format.Format_Grayscale8); im.fill(0)
    painter=QPainter(im); painter.setFont(f); painter.setPen(QColor('white'))
    fm=QFontMetrics(f); line_h=fm.height(); y=(h-line_h*len(lines))//2+fm.ascent()
    for line in lines:
        x=0 if align=='left' else w-fm.horizontalAdvance(line) if align=='right' else (w-fm.horizontalAdvance(line))//2
        painter.drawText(x,y,line); y+=line_h
    painter.end(); raw=bytes(im.constBits()); stride=im.bytesPerLine()
    return tuple((x,y) for y in range(h) for x in range(w) if raw[y*stride+x]>110)


@lru_cache(maxsize=256)
def temperature_mask(text,w,h,family,size,bold,align):
    """Keep the small degree ring beside C as one tightly fitted numeric unit."""
    from PySide6.QtGui import QFontMetrics
    ring=3 if h<=25 else 5
    n=size
    for n in range(size,8,-1):
        fm=QFontMetrics(font(family,n,bold))
        if fm.height()<=h and fm.horizontalAdvance(text[:-2]+'C')+ring+3<=w:break
    numeric=text_mask(text[:-2],w,h,family,n,bold,'left')
    letter=text_mask('C',w,h,family,n,bold,'left')
    if not numeric or not letter:return text_mask(text,w,h,family,n,bold,align)
    nx=min(xx for xx,yy in numeric);nw=max(xx for xx,yy in numeric)-nx+1
    cx=min(xx for xx,yy in letter);cw=max(xx for xx,yy in letter)-cx+1
    total=nw+2+ring+1+cw
    left=0 if align=='left' else w-total if align=='right' else (w-total)//2
    points=[(left+xx-nx,yy) for xx,yy in numeric]
    ring_x=left+nw+2;letter_x=ring_x+ring+1
    points.extend((letter_x+xx-cx,yy) for xx,yy in letter)
    top=max(0,min(yy for xx,yy in letter)-1)
    rows=(0b010,0b101,0b010) if ring==3 else (0b01110,0b10001,0b10001,0b10001,0b01110)
    points.extend((ring_x+xx,top+yy) for yy,bits in enumerate(rows)
                  for xx in range(ring) if bits&(1<<(ring-1-xx)))
    return tuple(points)


def typeset(c,text,x,y,w,h,family='body',size=17,bold=False,align='center'):
    text=str(text)
    mask=(temperature_mask(text,w,h,family,size,bold,align) if text.endswith('°C')
          else text_mask(text,w,h,family,size,bold,align))
    for xx,yy in mask: c.dot(x+xx,y+yy)


SEGMENTS={'0':'abcedf','1':'bc','2':'abged','3':'abgcd','4':'fgbc',
          '5':'afgcd','6':'afgecd','7':'abc','8':'abcdefg','9':'abfgcd','-':'g'}


def digits(c,text,x,y,w,h,style='ion'):
    """Numerals deliberately use different construction, not just colours."""
    if text.endswith('°C') and style not in ('pixel','dots','round','serif'):
        family='serif' if style=='serif' else 'round'
        points=text_mask('C',max(10,h),h,family,h+2,style=='round','left')
        if points:
            xmin=min(p[0] for p in points);xmax=max(p[0] for p in points);top=min(p[1] for p in points)
            cw=xmax-xmin+1;size=3 if h<21 else 5;cx=x+w-cw;unit=cw+size+3
            digits(c,text[:-2],x,y,max(1,w-unit),h,style)
            for xx,yy in points:c.dot(cx+xx-xmin,y+yy)
            degree_ring(c,cx-size-1,y+max(0,top-2),size)
            return
    if style in ('round','serif'):
        typeset(c,text,x,y,w,h,style,h+2,style=='round'); return
    if style in ('pixel','dots'):
        scale=max(1,h//7)
        while scale>1 and raster_width(text,scale)>w:scale-=1
        px=x+(w-raster_width(text,scale))//2;py=y+(h-7*scale)//2
        raster_text(c,text,px,py,scale,style=='dots')
        return
    advance=max(4,w//max(1,len(text))); dw=advance-4; thick=2; mid=h//2
    for char in text:
        if char==':': c.rect(x+dw//2,y+7,2,2,True); c.rect(x+dw//2,y+h-9,2,2,True)
        elif char in SEGMENTS:
            for segment in SEGMENTS[char]:
                if segment in 'agd':
                    yy=y+{'a':0,'g':mid-1,'d':h-2}[segment]
                    c.rect(x+3,yy,dw-6,thick,True); c.dot(x+2,yy+1); c.dot(x+dw-3,yy)
                else:
                    xx=x if segment in 'fe' else x+dw-2
                    yy=y+2 if segment in 'fb' else y+mid+1
                    c.rect(xx,yy,thick,max(1,mid-4),True)
        else: typeset(c,char,x,y,dw,h,'round',h-1)
        x+=advance


def ratio(metric):
    value=metric.get('value')
    if value is None:return None
    ceiling=metric.get('scale') or max(metric.get('history') or [value,1]) or 1
    return max(0,min(1,value/ceiling))


def history(c,m,x,y,w,h,area=False):
    values=m.get('history',[])[-24:]
    if not values:
        small(c,'NO HISTORY',x,y+(h-7)//2); return
    ceiling=m.get('scale') or max(values or [1]) or 1
    points=[(x+round(i*(w-1)/max(1,len(values)-1)), y+h-1-round(max(0,min(1,v/ceiling))*(h-1))) for i,v in enumerate(values)]
    for i,(xx,yy) in enumerate(points):
        if area:
            end=points[i+1][0] if i+1<len(points) else xx+1
            for col in range(xx,end,2):c.line(col,yy,col,y+h-1)
        if i:c.line(*points[i-1],xx,yy)
        else:c.dot(xx,yy)


def segments(c,x,y,w,h,value,count=14,slant=False):
    on=round((value or 0)*count)
    step=w/count
    for i in range(count):
        xx=x+round(i*step); ww=max(1,round(step)-2)
        if i<on:
            if slant:
                for k in range(ww): c.line(xx+k,y+h-1,xx+k+3,y)
            else:c.rect(xx,y,ww,h,True)
        else:c.line(xx,y+h-1,xx+ww-1,y+h-1)


def metric_label(m):
    key=m['key']
    if m.get('unit')=='C' or 'temp' in key:return m.get('short','TEMP')+' TEMP'
    return {'ram':'MEMORY','ram_gb':'MEMORY GB','upload':'UPLOAD','download':'DOWNLOAD',
            'disk_read':'DISK READ','disk_write':'DISK WRITE'}.get(key,m.get('short',key).upper())


def value_text(m, compact=False):
    v=m.get('value'); unit=m.get('unit','')
    if v is None:return '--'
    if unit in ('C','°C','℃'):return f'{v:.0f}°C'
    if unit=='GB':return f'{v:.2f}G' if compact else f'{v:.2f}GB'
    if unit=='B/s':
        n=float(v)
        for suffix in ('B','K','M','G','T'):
            if abs(n)<1024 or suffix=='T':break
            n/=1024
        precision=2 if n<10 else 1 if n<100 else 0
        return f'{n:.{precision}f}{suffix}'+('' if compact else '/S')
    return m.get('text',str(v)).upper()


def monitor_values(snapshot):
    """Stable TrafficMonitor-style columns; never substitute GPU temp for CPU."""
    metrics=snapshot.get('metrics',[]); bykey={m['key']:m for m in metrics}
    def missing(key,short,unit=''):
        return bykey.get(key,dict(key=key,short=short,unit=unit,value=None,text='--'))
    temperatures=[m for m in metrics if m.get('unit')=='C' and ('cpu' in m['key'].lower() or m.get('short')=='CPU')]
    # A package sensor is more representative than an arbitrary individual core.
    cpu_temp=next((m for m in temperatures if 'package' in (m['key']+' '+m.get('name','')).lower()), temperatures[0] if temperatures else missing('cpu_temp','CPU','C'))
    gpu=next((m for m in metrics if m['key'].startswith('gpu') and '_' not in m['key']), missing('gpu0','GPU','%'))
    return [[('UP',missing('upload','UP','B/s')),('DN',missing('download','DN','B/s'))],
            [('CPU',missing('cpu','CPU','%')),('GPU',gpu)],
            [('C',cpu_temp),('G',missing(gpu['key']+'_temp','GPU','C'))],
            [('RAM',missing('ram','RAM','%')),('',missing('ram_gb','RAM','GB'))]]


def dense(c,key,snapshot,phase):
    columns=monitor_values(snapshot); bounds=[(0,68),(68,61),(129,56),(185,71)]
    texts=[]
    for col,((x,w),items) in enumerate(zip(bounds,columns)):
        for row,(label,m) in enumerate(items):
            y=3+row*16; value=value_text(m,True); texts.append(f'{label} {value}'.strip())
            # Fixed 5×7 raster keeps all eight readings legible at native size.
            if col==0:
                xx=x+6; c.line(xx,y+1,xx,y+6)
                yy=y+1 if row==0 else y+6; sign=1 if row==0 else -1
                c.line(xx-2,yy+sign*2,xx,yy); c.line(xx+2,yy+sign*2,xx,yy)
                small(c,value,x+14,y)
            elif col==1:small(c,label+' '+value,x+4,y)
            elif col==2:small(c,label+' '+value,x+4,y)
            elif row==0:small(c,'RAM '+value,x+3,y)
            else:small(c,value+'B' if m.get('value') is not None else '-- GB',x+3,y)
            if key=='ion':
                c.line(x+3,y+10,x+w-4,y+10)
                if ratio(m) is not None: c.line(x+3,y+9,x+3+round((w-7)*ratio(m)),y+9)
            elif key=='peach':round_rect(c,x+1,row*16,w-2,15,2)
            elif key=='kitty':
                for i in range(x+4,x+w-4,6):c.dot(i,y+11)
                if ratio(m) is not None: c.rect(x+4+round((w-12)*ratio(m)),y+10,3,2,True)
            elif key=='amber':
                segments(c,x+4,y+9,w-8,2,ratio(m),max(3,(w-8)//5))
        if key=='matrix':
            if col%2==0:invert(c,x,0,w,32)
            c.line(x,15,x+w-1,15)
        elif key=='paper':
            if col:c.line(x,3,x,28)
            c.line(x+4,14,x+w-5,14)
        elif key not in ('peach',):
            if col:c.line(x,1,x,30)
    if key=='kitty':
        # Keyboard rhythm at the lower edge, without obscuring any reading.
        for x in range(0,256,8): c.line(x,31,x+4,31)
    return ' | '.join(texts)


def clock(c,key,text,now,phase):
    hhmm=text[:5]; seconds=text[6:8] if len(text)>5 else ''; date=now.strftime('%m/%d'); day=now.strftime('%a').upper()
    if key=='ion':
        digits(c,hhmm,8,3,159,26)
        c.line(174,0,168,31); tag(c,day,184,1,32)
        small(c,date,224,3,right=255); small(c,'SEC '+seconds if seconds else 'LOCAL',184,17)
        for i in range(16):c.line(181+i*4,29-(3 if i%4==0 else 1),181+i*4,30)
        c.rect(181+phase*8,26,5,2,True)
    elif key=='matrix':
        tag(c,'TIME',0,0,57); small(c,date,3,15); small(c,day,3,25)
        digits(c,hhmm,62,1,152,23,'pixel'); small(c,'SYS / LOCAL',67,25)
        if seconds:small(c,seconds,199,25)
        for row in range(4):
            bits=(now.hour,now.minute,now.second if seconds else now.day,now.month)[row]
            for col in range(6):
                if bits & (1<<col):c.rect(220+col*6,row*8,4,5,True)
                else:c.dot(221+col*6,row*8+2)
    elif key=='peach':
        # Two cream-coloured number tiles, a low meadow and a peeking rabbit.
        c.line(0,29,255,29)
        for x in (7,25,232,248):star(c,x,25-(x%3),1)
        round_rect(c,39,1,72,29,5); round_rect(c,121,1,72,29,5)
        digits(c,hhmm[:2],45,0,60,30,'round'); digits(c,hhmm[3:],127,0,60,30,'round')
        c.dot(116,11); c.dot(116,20)
        c.sprite(BUNNY,205,9 if phase%2==0 else 8,2)
        small(c,seconds if seconds else day,3,4)
        if not seconds:small(c,now.strftime('%d'),11,14)
    elif key=='kitty':
        # Clock as a toy piano: numbers sit on the lid, the cat sleeps on it.
        digits(c,hhmm,53,0,151,22,'pixel')
        c.sprite(CAT,6,0,2); c.line(5,22,29,22); c.circle(34,19,5,0,270)
        small(c,seconds if seconds else day,219,3); small(c,now.strftime('%d'),225,14)
        c.line(0,24,255,24)
        for x in range(0,256,12):
            c.line(x,25,x,31)
            if (x//12)%7 not in (2,6):c.rect(x+8,25,4,4,True)
        c.rect(54+phase*18,25,8,6,True)
    elif key=='paper':
        typeset(c,hhmm,50,-1,139,34,'serif',33)
        small(c,now.strftime('%d'),5,4); small(c,day,4,20)
        c.line(40,3,40,28); c.line(198,3,198,28)
        small(c,seconds+' S' if seconds else now.strftime('%m/%d'),213,6)
        c.line(211,24,251,24)
        for i in range(9): c.dot(211+i*5,22-(i%4==0))
    else:
        # Radio dial + perforated dot numerals and a right-side date cartridge.
        digits(c,hhmm,1,0,177,24,'dots')
        c.rect(185,1,70,30); small(c,'FM LOCAL',191,4)
        small(c,seconds+' SEC' if seconds else date,195,20)
        for x in range(4,177,5):c.line(x,28,x,31 if x%4==0 else 29)
        c.rect(5+phase*21,26,7,2,True)


def gauge(c,key,m,phase,graph=False):
    r=ratio(m); label='100' if m.get('scale')==100 else 'AUTO'
    if graph:
        history(c,m,142,5,109,21,area=key in ('peach','paper'))
        c.line(142,28,252,28); return
    if key=='ion':
        c.line(141,4,250,4); small(c,'0',140,23); small(c,label,0,23,right=253)
        segments(c,143,10,108,10,r,18,True)
        for x in range(145,251,14):c.dot(x,6)
    elif key=='matrix':
        # A true trace sits under an inverted acquisition header.
        tag(c,'TRACE / '+label,138,0,118)
        history(c,m,140,14,112,14)
        for x in range(142,252,12):c.dot(x,31)
    elif key=='peach':
        # Fill a row of six sweet jars in proportion to the actual metric.
        for i in range(6):
            x=143+i*18; round_rect(c,x,8,13,19,3); c.line(x+3,5,x+9,5)
            fill=max(0,min(1,(r or 0)*6-i)); h=round(fill*13)
            if h:c.rect(x+3,24-h,7,h,True)
        star(c,247,3+phase%2,1)
    elif key=='kitty':
        # Real load becomes piano keys, with a curled cat above the keyboard.
        c.sprite(CAT,229,0); c.circle(248,8,4,0,270)
        for i in range(12):
            x=140+i*9; c.rect(x,14,8,16)
            if i<round((r or 0)*12):c.rect(x+2,17,4,11,True)
            if i%7 not in (2,6):c.rect(x+6,14,3,5,True)
        small(c,label,143,2)
    elif key=='paper':
        history(c,m,147,4,104,21,area=True)
        c.line(141,28,252,28); small(c,'0',132,22)
    else:
        # Two opposing VU rails, one target and one history peak, both real.
        values=m.get('history') or []
        peak=ratio({**m,'value':max(values) if values else m.get('value')})
        small(c,'NOW',135,2); segments(c,158,2,96,7,r,16)
        small(c,'MAX',135,14); segments(c,158,14,96,7,peak,16)
        for x in range(158,255,8):c.dot(x,26)
        small(c,label,0,25,right=255)


def instrument(c,key,m,phase):
    """The value view is a dial/object; the bar view is a quantitative rail."""
    r=ratio(m) or 0
    if key in ('ion','paper','amber'):
        center=171 if key!='amber' else 187
        radius=14 if key!='amber' else 20
        c.circle(center,25,radius,190,350)
        angle=math.radians(190+160*r)
        end=(round(center+math.cos(angle)*(radius-3)),round(25+math.sin(angle)*(radius-3)))
        c.line(center,25,*end); c.circle(center,25,1)
        for a in range(190,351,40):
            rad=math.radians(a)
            c.line(round(center+math.cos(rad)*radius),round(25+math.sin(rad)*radius),round(center+math.cos(rad)*(radius-3)),round(25+math.sin(rad)*(radius-3)))
        small(c,'LEVEL',207,5); small(c,'100' if m.get('scale')==100 else 'AUTO',214,20)
        if key=='amber':c.rect(141,1,65,30)
        elif key=='ion':c.line(142,30,198,30); c.line(142,1,151,1)
        else:c.line(140,30,254,30)
    elif key=='matrix':
        c.circle(157,16,14); c.circle(157,16,7); c.line(142,16,172,16); c.line(157,1,157,31)
        a=math.radians(phase*45); c.line(157,16,round(157+math.cos(a)*13),round(16+math.sin(a)*13))
        c.rect(153+round(r*13),10,2,2,True)
        history(c,m,184,4,69,22); c.line(184,29,254,29)
    elif key=='peach':
        # A graduated milk bottle, with a rabbit perched on its shelf.
        round_rect(c,150,6,33,25,4); c.rect(159,1,15,4)
        h=round(r*18)
        if h:c.rect(154,27-h,25,h,True)
        for y in (12,18,24):c.line(185,y,191,y)
        c.sprite(BUNNY,218,6,2); c.line(202,29,254,29)
    else:
        # A cat's bowl fills from the same measured ratio as the number.
        c.line(142,11,201,11); c.line(145,14,154,29); c.line(198,14,189,29); c.line(154,29,189,29)
        for yy in range(round(27-r*12),28):
            inset=max(0,yy-14)//2; c.line(149+inset,yy,194-inset,yy)
        c.sprite(CAT,219,4,2); c.circle(248,22,5,0,270)


def single(c,key,m,phase,view):
    name=metric_label(m); value=value_text(m); valuewidth=128
    if key=='ion':
        tag(c,name[:15],1,0,126); typeset(c,value,1,11,valuewidth,21,'round',23,True)
        c.line(132,2,132,29)
    elif key=='matrix':
        small(c,name,3,1); c.line(2,17,6,21); c.line(6,21,2,25)
        digits(c,value,13,10,115,21,'pixel')
    elif key=='peach':
        round_rect(c,1,0,130,32,5); typeset(c,value,5,7,121,24,'round',24,True)
        erase(c,12,0,86,2); small(c,name[:14],13,0)
    elif key=='kitty':
        small(c,name,4,1); digits(c,value,0,11,130,21,'pixel'); c.line(2,9,126,9)
    elif key=='paper':
        small(c,name,2,1); typeset(c,value,1,7,124,25,'serif',27,False,'left'); c.line(128,2,128,30)
    else:
        tag(c,name[:16],1,0,127); digits(c,value,0,11,130,21,'dots')
    if view=='value':instrument(c,key,m,phase)
    else:gauge(c,key,m,phase,view=='graph')
    if m.get('value') is None:
        erase(c,140,1,116,31); small(c,'NO SENSOR',147,12)
    elif m.get('scale') is None and view!='graph':
        # Unbounded units use the observed history peak, never a fake rating.
        erase(c,197,25,59,7); small(c,'AUTO',226,25)


def pair(c,key,chosen,phase):
    for index,m in enumerate(chosen[:2]):
        x=index*128
        name=metric_label(m); value=value_text(m)
        if key in ('matrix','amber'):tag(c,name[:18],x,0,124)
        else:small(c,name[:18],x+4,1)
        if key=='peach':round_rect(c,x,0,125,32,4)
        elif key=='paper':c.line(x+3,11,x+123,11)
        elif key=='kitty':
            for xx in range(x+3,x+124,6):c.dot(xx,10)
        style={'ion':'round','matrix':'pixel','peach':'round','kitty':'pixel','paper':'serif','amber':'dots'}[key]
        digits(c,value,x+3,11,118,18,style)
        segments(c,x+4,30,117,2,ratio(m),23)
    c.line(127,2,127,29)


def lyric(c,key,text,phase):
    # The native MCU moves x38..237, y4..27. Put the complete lyric inside
    # that viewport; the surrounding 56 columns carry a DIFFERENT composition
    # per design, rather than six interchangeable avatar/border templates.
    if key=='ion':
        for i in range(4):c.line(1+i*5,30,12+i*5,1)
        c.line(37,0,214,0); c.line(76,31,239,31)
        for y in range(2,30,4):c.line(243,y,251 if y%8==2 else 247,y)
        c.rect(245,2+phase*4,10,2,True)
        typeset(c,text,39,4,197,24,size=18,bold=True)
    elif key=='matrix':
        tag(c,'TXT',0,0,33); small(c,'IN',3,15); small(c,'01',3,25)
        small(c,'STREAM / LYRICS',39,4)
        typeset(c,text,39,12,195,16,size=14,align='left')
        for x in range(39,238,4):c.dot(x,1)
        if phase%2==0:c.rect(243,19,10,3,True)
        c.line(38,30,255,30)
    elif key=='peach':
        round_rect(c,30,1,211,30,6); c.line(30,19,24,25); c.line(24,25,34,25)
        c.sprite(BUNNY,3,9,2); c.sprite(HEART,246,4+phase%2)
        typeset(c,text,39,4,197,24,size=17,bold=True)
    elif key=='kitty':
        for y in (1,8,15,22,29):c.line(0,y,31,y); c.line(241,y,255,y)
        c.sprite(CAT,3,3,2); c.line(30,19,35,16); c.circle(29,21,2)
        c.rect(245,8+phase%3*3,4,3,True); c.line(249,2+phase%3*3,249,10+phase%3*3)
        # Typeset the sentence as two phrases on the musical staff.
        if len(text)>9 and not text.isascii():
            split=(len(text)+1)//2
            typeset(c,text[:split],40,4,194,12,size=12,align='left')
            typeset(c,text[split:],40,16,194,12,size=12,align='right')
        else:typeset(c,text,39,4,197,24,size=18)
        for x in range(47,233,12):c.line(x,31,x+4,31)
    elif key=='paper':
        typeset(c,'“',0,0,34,30,'serif',32)
        typeset(c,text,44,4,188,24,'song',18,align='left')
        c.line(43,30,116,30); c.line(159,30,234,30)
        c.rect(132,29,6,2,True); c.line(248,5,248,27)
        small(c,'I',243,0)
    else:
        # Cassette reels extend over the full left edge; the caption is a tape.
        for x in (9,27):
            c.circle(x,10,7); c.circle(x,10,2)
            a=phase*math.pi/4; c.line(x,10,round(x+math.cos(a)*6),round(10+math.sin(a)*6))
        c.line(6,22,31,22); c.line(6,22,3,29); c.line(31,22,34,29); c.line(3,29,34,29)
        for x in range(41,236,8):c.rect(x,0,3,2,True); c.rect(x,30,3,2,True)
        typeset(c,text,42,4,193,24,size=16,bold=True)
        for y in range(4,29,4):c.rect(243,y,11,2,True)


def render(text,mode,config,elapsed,snapshot=None,now=None):
    c=Canvas(); key=config.get('theme','ion'); key=key if key in THEMES else 'ion'
    now=now or datetime.now(); snapshot=snapshot or {}
    themed=config.get('themes',True); phase=int(elapsed/2)%8 if config.get('animations') and themed else 0
    if not themed:key='paper'
    identity=mode
    if mode=='时钟':clock(c,key if themed else 'paper',text,now,phase)
    elif mode=='系统监控':
        view=config.get('monitor_view','value')
        if view=='dense':
            text=dense(c,key if themed else 'paper',snapshot,phase); identity+=':dense'
        else:
            chosen=selected_metrics(snapshot,config,elapsed)
            if chosen:
                identity+=':'+chosen[0]['key']
                if view=='compact' and len(chosen)>1:
                    pair(c,key,chosen,phase); text=' | '.join(metric_label(m)+' '+value_text(m) for m in chosen[:2])
                else:single(c,key,chosen[0],phase,view); text=metric_label(chosen[0])+' '+value_text(chosen[0])
            else:typeset(c,'等待监控数据',0,0,256,32,size=18)
    else:
        identity+=':'+text
        if themed:lyric(c,key,text,phase)
        else:typeset(c,text,39,4,197,24,size=18)
    return PixelFrame(bytes(c.data),text,identity)
