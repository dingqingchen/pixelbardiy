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
W = 2400
MARGIN, GAP = 64, 40
COL = (W - MARGIN*2 - GAP)//2
with Image.open(args.captures / "ui-0.png") as ui:
    WINDOW_H = round(ui.height*COL/ui.width)+48
STRIP_H = round(COL*216/1536)
NORMAL_Y = MARGIN + WINDOW_H + 50
TELEMETRY_Y = NORMAL_Y + 50 + 2*(STRIP_H+24) + 30
H = TELEMETRY_Y + 56 + 3*(STRIP_H+68) + MARGIN - 28
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


# Real client screenshots and rendered pixel frames; no promotional copy.
window("ui-0.png", MARGIN, MARGIN, COL)
window("ui-5.png", MARGIN+COL+GAP, MARGIN, COL)
text(MARGIN, NORMAL_Y, "时钟 · 歌词 · 系统监控", 30, bold=True)
for i, name in enumerate(["theme-kitty", "theme-amber", "lyric-1", "monitor-dense"]):
    strip(name, MARGIN+(i%2)*(COL+GAP), NORMAL_Y+50+(i//2)*(STRIP_H+24), COL)

text(MARGIN, TELEMETRY_Y, "地平线 6", 30, bold=True)
examples = [("05_subaru_xt", "Subaru XT"), ("15_vector_w8", "Vector W8"),
            ("02_citroen_bx_digit", "Citroën BX Digit"), ("08_renault_11_txe", "Renault 11"),
            ("10_alfa_romeo_90", "Alfa Romeo 90"), ("14_vauxhall_astra_gte", "Vauxhall Astra")]
for i,(key,label) in enumerate(examples):
    x=MARGIN+(i%2)*(COL+GAP); y=TELEMETRY_Y+56+(i//2)*(STRIP_H+68)
    text(x,y,label,26,color=MUTED)
    strip("telemetry-"+key,x,y+40,COL)
args.output.parent.mkdir(parents=True, exist_ok=True)
canvas.save(args.output, optimize=True)
print(f"{args.output}: {W} x {H}, {args.output.stat().st_size:,} bytes")
