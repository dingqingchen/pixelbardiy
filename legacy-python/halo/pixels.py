"""256 x 32 monochrome canvas and Halo's 133-byte scene records.

All artwork is generated locally. The preview uses these same packed pixels.
ASCII is an embedded 5 x 7 font; Chinese uses an explicitly loaded Windows font.
"""
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import math, os

WIDTH, HEIGHT = 256, 32
SCENE = 2
# Seven rows, five columns; authored here so digits never depend on system fonts.
_FONT = {
 '0':'01110 10001 10011 10101 11001 10001 01110', '1':'00100 01100 00100 00100 00100 00100 01110',
 '2':'01110 10001 00001 00010 00100 01000 11111', '3':'11110 00001 00001 01110 00001 00001 11110',
 '4':'00010 00110 01010 10010 11111 00010 00010', '5':'11111 10000 10000 11110 00001 00001 11110',
 '6':'01110 10000 10000 11110 10001 10001 01110', '7':'11111 00001 00010 00100 01000 01000 01000',
 '8':'01110 10001 10001 01110 10001 10001 01110', '9':'01110 10001 10001 01111 00001 00001 01110',
 'A':'01110 10001 10001 11111 10001 10001 10001', 'B':'11110 10001 10001 11110 10001 10001 11110',
 'C':'01111 10000 10000 10000 10000 10000 01111', 'D':'11110 10001 10001 10001 10001 10001 11110',
 'E':'11111 10000 10000 11110 10000 10000 11111', 'F':'11111 10000 10000 11110 10000 10000 10000',
 'G':'01111 10000 10000 10111 10001 10001 01111', 'H':'10001 10001 10001 11111 10001 10001 10001',
 'I':'01110 00100 00100 00100 00100 00100 01110', 'J':'00111 00010 00010 00010 10010 10010 01100',
 'K':'10001 10010 10100 11000 10100 10010 10001', 'L':'10000 10000 10000 10000 10000 10000 11111',
 'M':'10001 11011 10101 10101 10001 10001 10001', 'N':'10001 11001 10101 10011 10001 10001 10001',
 'O':'01110 10001 10001 10001 10001 10001 01110', 'P':'11110 10001 10001 11110 10000 10000 10000',
 'Q':'01110 10001 10001 10001 10101 10010 01101', 'R':'11110 10001 10001 11110 10100 10010 10001',
 'S':'01111 10000 10000 01110 00001 00001 11110', 'T':'11111 00100 00100 00100 00100 00100 00100',
 'U':'10001 10001 10001 10001 10001 10001 01110', 'V':'10001 10001 10001 10001 10001 01010 00100',
 'W':'10001 10001 10001 10101 10101 10101 01010', 'X':'10001 10001 01010 00100 01010 10001 10001',
 'Y':'10001 10001 01010 00100 00100 00100 00100', 'Z':'11111 00001 00010 00100 01000 10000 11111',
 ':':'00000 00100 00100 00000 00100 00100 00000', '.':'00000 00000 00000 00000 00000 00110 00110',
 '%':'11001 11010 00010 00100 01000 01011 10011', '/':'00001 00001 00010 00100 01000 10000 10000',
 '-':'00000 00000 00000 11111 00000 00000 00000', '?':'01110 10001 00001 00010 00100 00000 00100',
 '+':'00000 00100 00100 11111 00100 00100 00000', ' ':'00000 00000 00000 00000 00000 00000 00000',
}
FONT = {k:tuple(int(row,2) for row in v.split()) for k,v in _FONT.items()}
_chinese_family = None

def init_fonts():
    """Run on the Qt main thread, once, before starting the engine."""
    global _chinese_family
    from PySide6.QtGui import QFontDatabase
    for filename in ('msyh.ttc','msyhbd.ttc','simsun.ttc'):
        path=os.path.join(os.environ.get('WINDIR',r'C:\Windows'),'Fonts',filename)
        if os.path.isfile(path):
            font_id=QFontDatabase.addApplicationFont(path)
            families=QFontDatabase.applicationFontFamilies(font_id)
            if families:_chinese_family=families[0];return

class Canvas:
    def __init__(self):self.data=bytearray(1024)
    def dot(self,x,y,on=True):
        x,y=int(x),int(y)
        if 0<=x<WIDTH and 0<=y<HEIGHT:
            index=(y//8)*WIDTH+x;mask=1<<(y%8)
            if on:self.data[index]|=mask
            else:self.data[index]&=255-mask
    def line(self,x1,y1,x2,y2):
        steps=max(abs(x2-x1),abs(y2-y1),1)
        for i in range(steps+1):self.dot(round(x1+(x2-x1)*i/steps),round(y1+(y2-y1)*i/steps))
    def rect(self,x,y,w,h,fill=False):
        if fill:
            for yy in range(y,y+h):
                for xx in range(x,x+w):self.dot(xx,yy)
        else:
            self.line(x,y,x+w-1,y);self.line(x,y+h-1,x+w-1,y+h-1)
            self.line(x,y,x,y+h-1);self.line(x+w-1,y,x+w-1,y+h-1)
    def circle(self,x,y,r,start=0,end=360):
        for angle in range(start,end+1,3):
            a=math.radians(angle);self.dot(round(x+math.cos(a)*r),round(y+math.sin(a)*r))
    def text(self,text,x,y,scale=1):
        for char in text.upper():
            for row,mask in enumerate(FONT.get(char,FONT['?'])):
                for col in range(5):
                    if mask&(1<<(4-col)):self.rect(x+col*scale,y+row*scale,scale,scale,True)
            x+=6*scale
    def sprite(self,rows,x,y,scale=1):
        for yy,row in enumerate(rows):
            for xx,v in enumerate(row):
                if v!='.':self.rect(x+xx*scale,y+yy*scale,scale,scale,True)

CAT=('X.........X','XX.......XX','X.XXXXXXX.X','X.........X','X..X...X..X',
     'X.........X','X....X....X','X...X.X...X','.X.......X.','..XXXXXXX..')
BUNNY=('..XX...XX..','..XX...XX..','..XX...XX..','.XXXXXXXXX.','X.........X',
       'X..X...X..X','X.........X','.X...X...X.','..XXXXXXX..')
HEART=('.XX.XX.','XXXXXXX','XXXXXXX','.XXXXX.','..XXX..','...X...')

def decoration(c,key,mode):
    # Decorative regions leave x=38..235 available for readable content.
    if key in ('ion','matrix'):
        for x,sign in ((0,1),(255,-1)):
            c.line(x,1,x+sign*14,1);c.line(x,1,x,10)
            c.line(x,30,x+sign*14,30);c.line(x,30,x,21)
        if key=='ion':
            c.circle(17,16,11);c.circle(17,16,6);c.line(17,3,17,8);c.line(17,24,17,28)
            c.line(4,16,10,16);c.line(24,16,30,16)
        else:
            c.circle(17,16,12);c.circle(17,16,8,190,310);c.line(17,16,26,8)
            c.dot(12,12);c.dot(22,20)
        for x in range(43,239,8):c.line(x,30,x+3,30)
    elif key=='kitty':
        c.sprite(CAT,5,6,2);c.sprite(HEART,243,12)
        c.line(36,29,235,29);c.line(36,2,235,2)
        for x in (37,235):c.dot(x,3);c.dot(x,28)
    elif key=='peach':
        c.sprite(BUNNY,5,6,2);c.sprite(HEART,243,11)
        for x in range(40,239,5):c.dot(x,1);c.dot(x,30)
        c.circle(250,3,1);c.circle(250,28,1)
    elif key=='paper':
        c.line(18,26,18,9);c.line(18,17,10,10);c.line(18,20,26,13)
        c.circle(10,9,4);c.circle(26,12,4);c.rect(11,24,15,5)
        c.line(39,29,238,29);c.line(242,6,242,26)
    else:
        c.rect(1,1,254,30);c.rect(5,7,25,18);c.line(8,10,12,14);c.line(12,14,8,18)
        c.line(16,20,25,20);c.line(237,5,237,26)

def hardware_icon(c,key,x=214,y=7):
    if 'fan' in key:
        c.circle(x+10,y+9,9);c.circle(x+10,y+9,2)
        for a in (0,120,240):
            aa=math.radians(a);bx=round(x+10+math.cos(aa)*6);by=round(y+9+math.sin(aa)*6)
            c.circle(bx,by,3);c.line(x+10,y+9,bx,by)
    elif key in ('download','upload'):
        down=key=='download';c.line(x+10,y,x+10,y+15)
        for off in range(6):
            c.line(x+10-off,y+15-off if down else y+off,x+10+off,y+15-off if down else y+off)
        c.line(x+2,y+19,x+18,y+19)
    elif 'temp' in key:
        c.rect(x+8,y,5,13);c.circle(x+10,y+15,5);c.rect(x+9,y+5,3,12,True)
    elif key.startswith('disk'):
        c.rect(x,y,22,20);c.circle(x+11,y+8,5);c.dot(x+17,y+16)
    else:
        c.rect(x+3,y+3,15,14);c.rect(x+7,y+7,7,6)
        for v in range(5,18,4):c.line(x+v,y,x+v,y+2);c.line(x+v,y+18,x+v,y+20)

def selected_metrics(snapshot,config,elapsed):
    chosen=[m for key in config.get('monitor_metrics',[]) for m in snapshot.get('metrics',[]) if key==m['key']]
    if not chosen:return []
    index=int(elapsed/max(2,config.get('rotation_seconds',4)))%len(chosen) if config.get('monitor_rotate',True) else 0
    return [chosen[index],chosen[(index+1)%len(chosen)]] if len(chosen)>1 else [chosen[index]]

@lru_cache(maxsize=96)
def chinese_mask(text,size):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage,QPainter,QColor,QFont
    if not _chinese_family:raise RuntimeError('中文字体未加载；请确认 Windows 微软雅黑字体可用')
    im=QImage(200,24,QImage.Format.Format_RGB32);im.fill(QColor('black'))
    p=QPainter(im);font=QFont(_chinese_family);font.setPixelSize(size)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias);p.setFont(font);p.setPen(QColor('white'))
    p.drawText(im.rect(),Qt.AlignmentFlag.AlignCenter,text);p.end()
    return tuple((x,y) for y in range(24) for x in range(200) if im.pixelColor(x,y).red()>110)

@dataclass(frozen=True)
class PixelFrame:
    pixels: bytes
    text: str
    identity: str

def render(text,mode,config,elapsed,snapshot=None,now=None):
    c=Canvas();key=config.get('theme','ion');themed=config.get('themes',True)
    if themed:decoration(c,key,mode)
    identity=mode
    if mode=='时钟':
        scale=3;start=41 if len(text)>=8 else 69
        c.text(text,start,5,scale)
        if len(text)<=5:
            c.text((now or datetime.now()).strftime('%m/%d'),174,11)
    elif mode=='系统监控':
        chosen=selected_metrics(snapshot or {},config,elapsed)
        if not chosen:c.text('WAITING DATA',44,12)
        else:
            m=chosen[0];identity+=':'+m['key'];view=config.get('monitor_view','value')
            hardware_icon(c,m['key']);value=m['text'].replace('°','')
            if view=='compact' and len(chosen)>1:
                for index,item in enumerate(chosen[:2]):
                    x=40+index*84;c.text(item['short'][:7],x,4)
                    c.text(item['text'].replace('°','')[:9],x,15)
                    c.line(x,25,x+68,25)
                c.line(119,5,119,25)
            else:
                c.text(m['short'][:8],42,4)
                scale=2 if len(value)<=11 else 1;c.text(value[:20],42,14 if scale==1 else 12,scale)
                if view=='bar':
                    c.rect(105,3,95,6)
                    if m.get('scale') and m.get('value') is not None:
                        c.rect(107,5,int(91*max(0,min(1,m['value']/m['scale']))),2,True)
                elif view=='graph':
                    history=m.get('history',[])[-24:]
                    ceiling=m.get('scale') or max(history or [1]) or 1
                    for i,v in enumerate(history):
                        h=round(7*max(0,min(1,v/ceiling)));c.line(111+i*3,10,111+i*3,10-h)
    else:
        identity+= ':'+text
        if text.isascii():
            scale=2 if len(text)<=16 else 1;c.text(text[:32],max(39,138-len(text)*3*scale),9,scale)
        else:
            size=min(17,max(10,198//max(1,len(text))))
            for x,y in chinese_mask(text,size):c.dot(x+38,y+4)
    return PixelFrame(bytes(c.data),text,identity)

def encode(pixels,category=SCENE,duration=65535):
    if len(pixels)!=1024:raise ValueError('Expected a 256 x 32 packed bitmap')
    if not 1<=category<=8:raise ValueError('Unsupported graphic scene category')
    return b''.join(bytes([category,0,i])+int(duration).to_bytes(2,'big')+pixels[i*128:(i+1)*128] for i in range(8))

def decode(data):
    if len(data)!=1064:raise ValueError('Expected eight scene records')
    return b''.join(data[i*133+5:(i+1)*133] for i in range(8))

def preview_image(pixels,color='#86D8F6'):
    from PySide6.QtGui import QImage,QColor
    im=QImage(WIDTH,HEIGHT,QImage.Format.Format_RGB32);im.fill(QColor('#050a12'))
    on=QColor(color)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if pixels[(y//8)*WIDTH+x] & (1<<(y%8)):im.setPixelColor(x,y,on)
    return im
