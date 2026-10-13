"""Pixel artwork and optional low-bandwidth motion; no USB or Flash APIs."""
from .pixels import Canvas, PixelFrame
from .pixel_design import render, THEMES


def scene(text, mode, config, elapsed, snapshot, now):
    frame = render(text, mode, config, elapsed, snapshot, now)
    color = THEMES.get(config.get('theme'), THEMES['ion']).color if config.get('themes') else config['color']
    return frame, color


def transition_frame(old, new, style):
    """One optional intermediate graphic frame, bounded by USB frame latency.

    No claim of smooth 30/60 fps; the default is an immediate atomic switch.
    Lyrics keep the native 200-pixel viewport. Full-width monitor layouts use
    a complete half-frame transition, so numbers at the left edge never tear.
    """
    canvas = Canvas()
    canvas.data[:] = new.pixels
    def at(raw, x, y):
        return 0 <= y < 32 and bool(raw[(y//8)*256+x] & (1 << (y%8)))
    full = new.identity.startswith('系统监控')
    left, top, width, height = (0, 0, 256, 32) if full else (38, 4, 200, 24)
    half = height//2
    for y in range(top, top+height):
        for x in range(left, left+width):
            if style == 'wipe':
                on = at(new.pixels if x < left+width//2 else old.pixels, x, y)
            else:
                on = at(old.pixels, x, y+half) if y < top+half else at(new.pixels, x, y-half)
            canvas.dot(x, y, on)
    return PixelFrame(bytes(canvas.data), new.text, 'transition:'+new.identity)
