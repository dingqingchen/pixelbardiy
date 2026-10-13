"""Latest-value text transitions. Uses glyph/color commands, never image resources."""
from .themes import mix_color


class TextTransition:
    duration = .24

    def __init__(self):
        self.shown = None
        self.target = None
        self.started = None
        self.busy = False

    def frame(self, text, color, layout, now, animate=False):
        target = (text, layout)
        if self.shown is None or not animate:
            self.shown = self.target = target
            self.started = None
        elif target != self.target:
            # During fade-out replace the pending line; never queue stale lyrics.
            if self.started is None or now - self.started >= self.duration / 2:
                self.started = now
            self.target = target
        factor = 1.0
        if self.started is not None:
            phase = (now - self.started) / self.duration
            if phase >= 1:
                self.shown = self.target
                self.started = None
            elif phase >= .5:
                self.shown = self.target
                factor = (phase - .5) * 2
            else:
                factor = 1 - phase * 2
        self.busy = self.started is not None
        return self.shown[0], mix_color('#000000', color, factor), self.shown[1]
