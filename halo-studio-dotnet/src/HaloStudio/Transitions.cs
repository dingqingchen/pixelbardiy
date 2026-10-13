namespace HaloStudio;

public static class Transitions
{
    public static byte Style(string style) => style switch { "wipe" => 2, "center" => 6, "dissolve" => 7, _ => 1 };
    public static byte ThemeStyle(string theme) => Style(Designs.All.GetValueOrDefault(theme)?.Transition ?? "center");
    // The installed MCU animates only x=38..237, y=4..27. A monitor page uses
    // all 8192 pixels and therefore needs complete, atomically committed frames.
    public static bool NativeCompatible(PixelFrame old, PixelFrame next)
    {
        if (!old.Identity.StartsWith("歌词:") || !next.Identity.StartsWith("歌词:")) return false;
        for (int y = 0; y < 32; y++) for (int x = 0; x < 256; x++)
            if ((x < 38 || x >= 238 || y < 4 || y >= 28) && At(old.Pixels, x, y) != At(next.Pixels, x, y)) return false;
        return true;
    }

    public static PixelFrame Compose(PixelFrame old, PixelFrame next, byte style, double progress)
    {
        progress = Math.Clamp(progress, 0, 1);
        if (progress == 0) return old;
        if (progress == 1) return next;
        var canvas = new PixelCanvas();
        int shift = (int)Math.Round(progress * 32), reveal = (int)Math.Round(progress * 256);
        for (int y = 0; y < 32; y++) for (int x = 0; x < 256; x++)
        {
            bool on = style == 2 ? At(x < reveal ? next.Pixels : old.Pixels, x, y)
                : y + shift < 32 ? At(old.Pixels, x, y + shift) : At(next.Pixels, x, y + shift - 32);
            canvas.Dot(x, y, on);
        }
        return new(canvas.Data, next.Text, "transition:" + next.Identity);
    }
    static bool At(byte[] pixels, int x, int y) => (pixels[y / 8 * 256 + x] & (1 << (y % 8))) != 0;
}
