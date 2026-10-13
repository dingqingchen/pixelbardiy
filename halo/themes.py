"""Theme palettes; pixel artwork is in pixels.py. Text styling is the plain-mode fallback."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Theme:
    name: str
    color: str
    accent: str
    left: str
    right: str
    description: str

THEMES = {
    "ion": Theme("科幻 · 离子舱", "#64DFFF", "#677FFF", "[", "]", "环形仪表 · 分段框线 · 冰蓝像素"),
    "matrix": Theme("科幻 · 雷达站", "#8DF5B4", "#27BD8F", "> ", "_", "雷达图案 · 定位光点 · 薄荷终端"),
    "peach": Theme("可爱 · 桃桃兔", "#FFB9CC", "#FFDAB0", "(", ")", "像素兔子 · 小爱心 · 点缀花边"),
    "kitty": Theme("可爱 · 猫咪", "#D6BBFF", "#FFC1E3", "^", "^", "像素猫咪 · 爱心角标 · 紫粉边框"),
    "paper": Theme("简约 · 月白", "#DAE9F2", "#90B2CC", "", "", "盆栽小景 · 留白刻度 · 月白线条"),
    "amber": Theme("复古 · 琥珀", "#FFC27A", "#FF915D", "", "", "迷你终端 · 完整像素框 · 琥珀光"),
}

def mix_color(a, b, fraction):
    fraction=max(0,min(1,fraction))
    aa=tuple(int(a[i:i+2],16) for i in (1,3,5))
    bb=tuple(int(b[i:i+2],16) for i in (1,3,5))
    return "#"+"".join(f"{round(x+(y-x)*fraction):02X}" for x,y in zip(aa,bb))

def style_frame(text, mode, config, elapsed):
    theme=THEMES.get(config.get("theme"),THEMES["ion"])
    enabled=config.get("themes",False)
    animate=config.get("animations",False)
    color=theme.color if enabled else config["color"]
    layout="center"
    if enabled and mode=="时钟":
        if theme.name.startswith("可爱 · 猫咪") and animate and int(elapsed)%8==7:
            text="-"+text+"-"
        else:
            text=theme.left+text+theme.right
        if config.get("theme")=="matrix" and animate and int(elapsed)%2:
            text=text[:-1]+" "
    elif enabled and mode=="歌词" and len(text)<=12 and len(text.encode("utf-8"))<=44:
        text=("( "+text+" )") if config.get("theme") in ("peach","kitty") else ("> "+text if config.get("theme") in ("ion","matrix") else text)
    if animate:
        motion=config.get("motion","breath")
        if motion=="scroll" and mode!="时钟":
            layout="scroll_right_to_left"
        elif motion=="blink" and mode=="时钟" and int(elapsed)%2:
            text=text.replace(":"," ")
        else:
            wave=(1-math.cos(elapsed*math.tau/8))/2
            color=mix_color(color,theme.accent if enabled else "#526978",wave*.65)
    return text,color,layout
