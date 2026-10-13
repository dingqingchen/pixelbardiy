"""Compose actual HaloStudio client captures with a Windows 11 style frame.

Development-only dependency: Pillow. Screenshots use explicit demo data.
Usage: python scripts/compose-readme.py <capture-folder> docs/images/halostudio-overview.png
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("captures", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
W, H = 2400, 3470
canvas = Image.new("RGB", (W, H), "#F2F5FC")
d = ImageDraw.Draw(canvas)
INK, MUTED, ACCENT = "#182840", "#617189", "#5367ED"
fontdir = Path("C:/Windows/Fonts")


def font(size, bold=False):
    return ImageFont.truetype(str(fontdir / ("msyhbd.ttc" if bold else "msyh.ttc")), size)


def text(x, y, value, size=28, color=INK, bold=False):
    d.text((x, y), value, font=font(size, bold), fill=color)


def rounded_image(image, box, radius=20):
    x, y, width, height = box
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width-1, height-1), radius, fill=255)
    canvas.paste(image, (x, y), mask)


def window(name, x, y, width):
    client = Image.open(args.captures / name).convert("RGB")
    height = round(client.height * width / client.width)
    title = 48
    shadow = Image.new("RGBA", canvas.size)
    ImageDraw.Draw(shadow).rounded_rectangle((x, y+10, x+width, y+height+title+10), 17, fill=(36, 50, 80, 40))
    canvas.paste(Image.alpha_composite(Image.new("RGBA", canvas.size), shadow.filter(ImageFilter.GaussianBlur(16))), (0, 0), shadow.filter(ImageFilter.GaussianBlur(16)))
    framed = Image.new("RGB", (width, height+title), "#F8F9FC")
    f = ImageDraw.Draw(framed)
    f.rounded_rectangle((16, 13, 38, 35), 5, fill=ACCENT)
    for bx in [21, 30]:
        f.rounded_rectangle((bx, 18, bx+3, 30), 1, fill="white")
    f.text((49, 9), "HaloStudio", font=font(21), fill=INK)
    for cx in [width-121, width-73, width-25]:
        if cx == width-121:
            f.line((cx-6, 25, cx+6, 25), fill="#536174", width=1)
        elif cx == width-73:
            f.rectangle((cx-6, 18, cx+6, 30), outline="#536174", width=1)
        else:
            f.line((cx-5, 19, cx+5, 29), fill="#536174", width=1)
            f.line((cx-5, 29, cx+5, 19), fill="#536174", width=1)
    framed.paste(client.resize((width, height), Image.Resampling.LANCZOS), (0, title))
    rounded_image(framed, (x, y, width, height+title), 16)
    d.rounded_rectangle((x, y, x+width-1, y+height+title-1), 16, outline="#D4DCEB", width=2)
    return height + title


def strip(name, x, y, width):
    im = Image.open(args.captures / (name + ".png")).convert("RGB")
    height = round(width * im.height / im.width)
    rounded_image(im, (x, y, width, height), 10)
    return height


def section(n, heading, detail, y):
    d.rounded_rectangle((80, y+3, 139, y+54), 13, fill=ACCENT)
    text(94, y+7, n, 26, "white", True)
    text(158, y, heading, 36, bold=True)
    text(158, y+57, detail, 25, MUTED)


text(80, 57, "HALO STUDIO", 72, bold=True)
text(83, 158, "把音乐、时间与电脑状态，放进 256 × 32 像素。", 34, MUTED)
text(2045, 80, "PIXEL BAR", 25, ACCENT, True)
text(2078, 121, "C#  2.6.2", 24, MUTED)
for x, label in [(83, "网易云歌词"), (320, "系统监控"), (539, "主题与配色")]:
    d.rounded_rectangle((x, 229, x+198, 282), 26, fill="#E4E9FF")
    text(x+24, 237, label, 26, ACCENT, True)

section("01", "一个界面，六种性格", "外部 JSON 主题 · 统一覆盖时钟、歌词与监控", 340)
window("ui-0.png", 80, 465, 1400)
themes = [("ion", "科幻 · 离子仪表"), ("matrix", "科幻 · 雷达终端"),
          ("amber", "复古 · 琥珀音响"), ("kitty", "可爱 · 猫咪乐谱"),
          ("peach", "可爱 · 桃兔甜点"), ("paper", "简约 · 月白书页")]
for i, (key, label) in enumerate(themes):
    y = 455 + i * 170
    text(1540, y, label, 28, bold=True)
    strip("theme-"+key, 1540, y+51, 780)

section("02", "听见歌词，也看见状态", "真实客户端页面 · 独立温度采集首次关闭，主动开启后记住选择", 1570)
window("ui-1.png", 80, 1695, 1090)
window("ui-2.png", 1230, 1695, 1090)

section("03", "每一帧，都有自己的表达", "原生点阵渲染 · 多种监控编排 · 按歌词时间切换", 2590)
d.rounded_rectangle((80, 2710, 1170, 3305), 28, fill="white", outline="#DFE5F2", width=2)
d.rounded_rectangle((1230, 2710, 2320, 3305), 28, fill="white", outline="#DFE5F2", width=2)
text(113, 2730, "歌词片段 / 原创示例", 27, bold=True)
text(1263, 2730, "监控编排 / 模拟指标", 27, bold=True)
for i in range(3):
    strip("lyric-" + str(i+1), 113, 2792+i*162, 1024)
for i, kind in enumerate(["dense", "compact", "bar"]):
    strip("monitor-"+kind, 1263, 2792+i*162, 1024)
text(80, 3345, "真实客户端控件与主题渲染器截图，使用模拟指标及原创歌词；窗口配 Win11 风格展示边框。", 24, MUTED)
text(80, 3387, "非音响实拍，颜色仅为近似预览。日常画面写入 RAM，退出或心跳超时后恢复原厂时钟。", 24, MUTED)
args.output.parent.mkdir(parents=True, exist_ok=True)
canvas.save(args.output, optimize=True)
print(f"{args.output}: {W} x {H}, {args.output.stat().st_size:,} bytes")
