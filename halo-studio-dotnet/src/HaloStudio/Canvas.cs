using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Text;

namespace HaloStudio;

public sealed class PixelCanvas
{
    public byte[] Data { get; } = new byte[1024];
    public static readonly string[] Cat = ["X.........X", "XX.......XX", "X.XXXXXXX.X", "X.........X", "X..X...X..X", "X.........X", "X....X....X", "X...X.X...X", ".X.......X.", "..XXXXXXX.."];
    public static readonly string[] Bunny = ["..XX...XX..", "..XX...XX..", "..XX...XX..", ".XXXXXXXXX.", "X.........X", "X..X...X..X", "X.........X", ".X...X...X.", "..XXXXXXX.."];
    public static readonly string[] Heart = [".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."];
    public void Dot(int x, int y, bool on = true) { if (x < 0 || x >= 256 || y < 0 || y >= 32) return; int i = y / 8 * 256 + x; byte mask = (byte)(1 << (y % 8)); if (on) Data[i] |= mask; else Data[i] &= (byte)~mask; }
    public bool IsOn(int x, int y) => x >= 0 && x < 256 && y >= 0 && y < 32 && (Data[y / 8 * 256 + x] & (1 << (y % 8))) != 0;
    public void Line(int x1, int y1, int x2, int y2) { int steps = Math.Max(1, Math.Max(Math.Abs(x2 - x1), Math.Abs(y2 - y1))); for (int i = 0; i <= steps; i++) Dot((int)Math.Round(x1 + (x2 - x1) * i / (double)steps), (int)Math.Round(y1 + (y2 - y1) * i / (double)steps)); }
    public void Rect(int x, int y, int w, int h, bool fill = false) { if (w <= 0 || h <= 0) return; if (fill) { for (int yy = Math.Max(0, y); yy < Math.Min(32, y + h); yy++) for (int xx = Math.Max(0, x); xx < Math.Min(256, x + w); xx++) Dot(xx, yy); } else { Line(x, y, x + w - 1, y); Line(x, y + h - 1, x + w - 1, y + h - 1); Line(x, y, x, y + h - 1); Line(x + w - 1, y, x + w - 1, y + h - 1); } }
    public void Erase(int x, int y, int w, int h) { for (int yy = Math.Max(0, y); yy < Math.Min(32, y + h); yy++) for (int xx = Math.Max(0, x); xx < Math.Min(256, x + w); xx++) Dot(xx, yy, false); }
    public void Invert(int x, int y, int w, int h) { for (int yy = Math.Max(0, y); yy < Math.Min(32, y + h); yy++) for (int xx = Math.Max(0, x); xx < Math.Min(256, x + w); xx++) Dot(xx, yy, !IsOn(xx, yy)); }
    public void Circle(int x, int y, int r, int start = 0, int end = 360) { for (int a = start; a <= end; a += 3) Dot(x + (int)Math.Round(Math.Cos(a * Math.PI / 180) * r), y + (int)Math.Round(Math.Sin(a * Math.PI / 180) * r)); }
    public void Round(int x, int y, int w, int h, int r = 3) { Line(x + r, y, x + w - r - 1, y); Line(x + r, y + h - 1, x + w - r - 1, y + h - 1); Line(x, y + r, x, y + h - r - 1); Line(x + w - 1, y + r, x + w - 1, y + h - r - 1); for (int i = 0; i < r; i++) { Dot(x + r - i, y + i); Dot(x + w - r - 1 + i, y + i); Dot(x + r - i, y + h - i - 1); Dot(x + w - r - 1 + i, y + h - i - 1); } }
    public void Sprite(string[] rows, int x, int y, int scale = 1) { for (int yy = 0; yy < rows.Length; yy++) for (int xx = 0; xx < rows[yy].Length; xx++) if (rows[yy][xx] != '.') Rect(x + xx * scale, y + yy * scale, scale, scale, true); }
    public void Star(int x, int y, int r = 2) { Line(x - r, y, x + r, y); Line(x, y - r, x, y + r); }
    public void Ring(int x, int y, int size = 3) { var rows = size == 3 ? new[] { 2, 5, 2 } : new[] { 14, 17, 17, 17, 14 }; for (int yy = 0; yy < size; yy++) for (int xx = 0; xx < size; xx++) if ((rows[yy] & (1 << (size - 1 - xx))) != 0) Dot(x + xx, y + yy); }
    public static int RasterWidth(string text, int scale = 1) => Math.Max(0, text.Sum(c => c == '°' ? (scale <= 2 ? 4 : 6) : 6 * scale) - scale);
    public void Raster(string text, int x, int y, int scale = 1, bool dotted = false)
    {
        foreach (char ch in text.ToUpperInvariant())
        {
            if (ch == '°') { int ring = scale <= 2 ? 3 : 5; Ring(x, y, ring); x += ring + 1; continue; }
            var rows = RasterFont.Glyphs.GetValueOrDefault(ch, RasterFont.Glyphs['?']);
            for (int row = 0; row < 7; row++) for (int col = 0; col < 5; col++) if ((rows[row] & (1 << (4 - col))) != 0) Rect(x + col * scale, y + row * scale, scale - (dotted && scale > 1 ? 1 : 0), scale - (dotted && scale > 1 ? 1 : 0), true);
            x += 6 * scale;
        }
    }
    public void Small(string text, int x, int y, int? right = null) => Raster(text, right is int r ? r - RasterWidth(text) : x, y);
    public void Tag(string text, int x, int y, int w) { Small(text, x + 3, y + 2); Invert(x, y, w, 11); }
    // Masks are shared by rendering and preview. A bounded cache avoids repeated Chinese glyph rasterization.
    static readonly Dictionary<string, Point[]> maskCache = []; static readonly Queue<string> maskKeys = new(); static readonly object maskGate = new();
    sealed record LineMask(int Width, byte[] Columns);
    static readonly Dictionary<string, LineMask> lineCache = []; static readonly Queue<string> lineKeys = new(); static int lineBytes;
    static LineMask CachedLine(string text, int h, string family, int size, bool bold)
    {
        string key = $"{text}\0{h},{family},{size},{bold}"; LineMask mask;
        lock (maskGate)
        {
            if (!lineCache.TryGetValue(key, out mask!))
            {
                mask = MakeLine(text, h, family, size, bold); lineCache[key] = mask; lineKeys.Enqueue(key); lineBytes += mask.Columns.Length;
                while (lineKeys.Count > 32 || lineBytes > 1_048_576) { string oldest = lineKeys.Dequeue(); lineBytes -= lineCache[oldest].Columns.Length; lineCache.Remove(oldest); }
            }
        }
        return mask;
    }
    public static int LyricWidth(string text, int h, string family, int size, bool bold) => CachedLine(text, h, family, size, bold).Width;
    public void LyricPage(string text, int x, int y, int w, int h, string family, int size, bool bold, string align)
    {
        var mask = CachedLine(text, h, family, size, bold);
        int left = align == "left" ? x : align == "right" ? x + w - mask.Width : x + (w - mask.Width) / 2;
        for (int xx = 0; xx < mask.Width; xx++) for (int yy = 0; yy < Math.Min(32, h); yy++)
            if (left + xx >= x && left + xx < x + w && (mask.Columns[xx * 4 + yy / 8] & (1 << (yy % 8))) != 0) Dot(left + xx, y + yy);
    }
    public int Lyric(string text, int x, int y, int w, int h, LyricScroll scroll, string family, int size, bool bold, string align)
    {
        if (w <= 0 || h <= 0 || text.Length == 0) return 0;
        var whole = CachedLine(text, h, family, size, bold);
        if (whole.Width <= w) { Typeset(text, x, y, w, h, family, size, bold, align); return 0; }
        bool tail = scroll.Progress == 1; int room = Math.Max(0, w - 10);
        // Fit complete Unicode characters, not a pixel crop through a glyph.
        var runes = text.EnumerateRunes().Select(r => r.ToString()).ToArray(); int lo = 0, hi = runes.Length;
        LineMask chosen = new(0, []);
        while (lo < hi)
        {
            int n = (lo + hi + 1) / 2;
            var candidate = CachedLine(string.Concat(tail ? runes.TakeLast(n) : runes.Take(n)), h, family, size, bold);
            if (candidate.Width <= room) { lo = n; chosen = candidate; } else hi = n - 1;
        }
        int left = tail ? x + w - chosen.Width : x;
        for (int xx = 0; xx < chosen.Width; xx++) for (int yy = 0; yy < Math.Min(32, h); yy++)
            if ((chosen.Columns[xx * 4 + yy / 8] & (1 << (yy % 8))) != 0) Dot(left + xx, y + yy);
        int dots = tail ? x : x + w - 7, baseline = y + Math.Clamp(h / 2 + size / 3, 0, h - 1);
        for (int i = 0; i < 3; i++) if (dots + i * 3 >= x && dots + i * 3 < x + w) Dot(dots + i * 3, baseline);
        return tail ? 2 : 1;
    }
    static LineMask MakeLine(string text, int h, string family, int size, bool bold)
    {
        if (text.Length > 4096) throw new InvalidDataException("单句歌词超过 4096 字符");
        string face = family switch { "round" => "Segoe UI", "serif" => "Georgia", "song" => "SimSun", "body" => "Microsoft YaHei", _ => family };
        using var measure = new Bitmap(1, 1); using var mg = Graphics.FromImage(measure);
        using var format = (StringFormat)StringFormat.GenericTypographic.Clone(); format.FormatFlags |= StringFormatFlags.NoWrap | StringFormatFlags.NoClip;
        int n = Math.Clamp(size, 9, 64); Font font;
        while (true) { font = new Font(face, n, bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Pixel); if (font.GetHeight(mg) <= h || n <= 9) break; font.Dispose(); n--; }
        using (font)
        {
            int width = (int)Math.Ceiling(mg.MeasureString(text, font, int.MaxValue, format).Width) + 8;
            using var bitmap = new Bitmap(width, Math.Clamp(h, 1, 32), PixelFormat.Format32bppArgb); using var g = Graphics.FromImage(bitmap);
            g.Clear(Color.Black); g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit;
            g.DrawString(text, font, Brushes.White, 4, (h - font.GetHeight(g)) / 2, format);
            var columns = new byte[width * 4]; int left = width, right = -1;
            var data = bitmap.LockBits(new(0, 0, width, bitmap.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
            try { unsafe { for (int yy = 0; yy < bitmap.Height; yy++) { byte* row = (byte*)data.Scan0 + yy * data.Stride; for (int xx = 0; xx < width; xx++) if (row[xx * 4 + 2] > 110) { columns[xx * 4 + yy / 8] |= (byte)(1 << (yy % 8)); left = Math.Min(left, xx); right = Math.Max(right, xx); } } } }
            finally { bitmap.UnlockBits(data); }
            return right < left ? new(0, []) : new(right - left + 1, columns[(left * 4)..((right + 1) * 4)]);
        }
    }
    public void Typeset(string text, int x, int y, int w, int h, string family = "body", int size = 17, bool bold = false, string align = "center")
    {
        if (w <= 0 || h <= 0 || string.IsNullOrEmpty(text)) return;
        string key = $"{text}\0{w},{h},{family},{size},{bold},{align}"; Point[] points;
        lock (maskGate) { if (!maskCache.TryGetValue(key, out points!)) { points = MakeMask(text, w, h, family, size, bold, align); maskCache[key] = points; maskKeys.Enqueue(key); while (maskKeys.Count > 256) maskCache.Remove(maskKeys.Dequeue()); } }
        foreach (var p in points) Dot(x + p.X, y + p.Y);
    }
    static Point[] MakeMask(string text, int w, int h, string family, int size, bool bold, string align)
    {
        string face = family switch { "round" => "Segoe UI", "serif" => "Georgia", "song" => "SimSun", "body" => "Microsoft YaHei", _ => family };
        using var bitmap = new Bitmap(w, h, PixelFormat.Format32bppArgb); using var g = Graphics.FromImage(bitmap); g.Clear(Color.Black);
        g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit; g.SmoothingMode = SmoothingMode.None; g.PixelOffsetMode = PixelOffsetMode.None;
        using var format = (StringFormat)StringFormat.GenericTypographic.Clone(); format.FormatFlags |= StringFormatFlags.NoClip; format.Trimming = StringTrimming.None;
        Font? font = null; var lines = new List<string> { text }; bool temperature = text.EndsWith("°C", StringComparison.Ordinal);
        for (int n = size; n >= 9; n--)
        {
            font?.Dispose(); font = new Font(face, n, bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Pixel);
            string measured = temperature ? text[..^2] + "C" : text; var dimensions = g.MeasureString(measured, font, 10000, format);
            if (dimensions.Width + (temperature ? 7 : 0) <= w && font.GetHeight(g) <= h) break;
            if (n <= 12 && h >= 22 && !temperature) { lines = []; string line = ""; foreach (char c in text) { if (line.Length > 0 && g.MeasureString(line + c, font, 10000, format).Width > w) { lines.Add(line); line = ""; } line += c; } if (line.Length > 0) lines.Add(line); if (lines.Count * font.GetHeight(g) <= h) break; lines = [text]; }
        }
        using (font!)
        {
            float lineHeight = font!.GetHeight(g), yy = (h - lineHeight * lines.Count) / 2;
            if (temperature)
            {
                string num = text[..^2]; float nw = g.MeasureString(num, font, 10000, format).Width, cw = g.MeasureString("C", font, 10000, format).Width;
                int ring = h <= 25 ? 3 : 5; float total = nw + 2 + ring + 1 + cw; float xx = align == "left" ? 0 : align == "right" ? w - total : (w - total) / 2;
                g.DrawString(num, font, Brushes.White, xx, yy, format); g.DrawString("C", font, Brushes.White, xx + nw + ring + 3, yy, format);
                int rx = (int)Math.Round(xx + nw + 2), ry = Math.Max(0, (int)Math.Round(yy + font.Size * .15)); int[] rows = ring == 3 ? [2, 5, 2] : [14, 17, 17, 17, 14];
                for (int iy = 0; iy < ring; iy++) for (int ix = 0; ix < ring; ix++) if ((rows[iy] & (1 << (ring - 1 - ix))) != 0) g.FillRectangle(Brushes.White, rx + ix, ry + iy, 1, 1);
            }
            else foreach (string line in lines) { float width = g.MeasureString(line, font, 10000, format).Width; float xx = align == "left" ? 0 : align == "right" ? w - width : (w - width) / 2; g.DrawString(line, font, Brushes.White, xx, yy, format); yy += lineHeight; }
        }
        var result = new List<Point>(); var locked = bitmap.LockBits(new(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        try { unsafe { for (int iy = 0; iy < h; iy++) { byte* row = (byte*)locked.Scan0 + iy * locked.Stride; for (int ix = 0; ix < w; ix++) if (row[ix * 4 + 2] > 110) result.Add(new(ix, iy)); } } } finally { bitmap.UnlockBits(locked); }
        return result.ToArray();
    }
    public void Digits(string text, int x, int y, int w, int h, string style = "ion")
    {
        if (style is "round" or "serif") { Typeset(text, x, y, w, h, style, h + 2, style == "round"); return; }
        if (style is "pixel" or "dots") { int scale = Math.Max(1, h / 7); while (scale > 1 && RasterWidth(text, scale) > w) scale--; Raster(text, x + (w - RasterWidth(text, scale)) / 2, y + (h - 7 * scale) / 2, scale, style == "dots"); return; }
        int advance = Math.Max(4, w / Math.Max(1, text.Length)), dw = advance - 4, mid = h / 2;
        foreach (char ch in text)
        {
            if (ch == ':') { Rect(x + dw / 2, y + 7, 2, 2, true); Rect(x + dw / 2, y + h - 9, 2, 2, true); }
            else if (segments.TryGetValue(ch, out string? parts)) foreach (char segment in parts) { if ("agd".Contains(segment)) { int yy = y + (segment == 'a' ? 0 : segment == 'g' ? mid - 1 : h - 2); Rect(x + 3, yy, dw - 6, 2, true); Dot(x + 2, yy + 1); Dot(x + dw - 3, yy); } else { int xx = x + ("fe".Contains(segment) ? 0 : dw - 2), yy = y + ("fb".Contains(segment) ? 2 : mid + 1); Rect(xx, yy, 2, Math.Max(1, mid - 4), true); } }
            else Typeset(ch.ToString(), x, y, dw, h, "round", h - 1); x += advance;
        }
    }
    static readonly Dictionary<char, string> segments = new() { ['0'] = "abcdef", ['1'] = "bc", ['2'] = "abged", ['3'] = "abgcd", ['4'] = "fgbc", ['5'] = "afgcd", ['6'] = "afgecd", ['7'] = "abc", ['8'] = "abcdefg", ['9'] = "abfgcd", ['-'] = "g" };
    public Bitmap Bitmap(Color color, int scale = 1) { var b = new Bitmap(256 * scale, 32 * scale); using var g = Graphics.FromImage(b); g.Clear(Color.FromArgb(8, 12, 18)); using var brush = new SolidBrush(color); for (int y = 0; y < 32; y++) for (int x = 0; x < 256; x++) if (IsOn(x, y)) g.FillRectangle(brush, x * scale, y * scale, scale, scale); return b; }
}
