using System.Drawing.Drawing2D;
namespace HaloStudio;

internal static class Palette
{
    public static readonly Color Background = Color.FromArgb(245, 247, 251), Sidebar = Color.FromArgb(239, 242, 249), Card = Color.White,
        Input = Color.FromArgb(247, 248, 252), Border = Color.FromArgb(225, 230, 240), Text = Color.FromArgb(31, 40, 61),
        Muted = Color.FromArgb(118, 128, 149), Accent = Color.FromArgb(81, 105, 239), AccentSoft = Color.FromArgb(228, 234, 255);
    public static Font Font(float size = 10, FontStyle style = FontStyle.Regular) => new("Microsoft YaHei UI", Math.Max(10, size + 1), style, GraphicsUnit.Point);
    public static int Px(Control c, int n) => (int)Math.Round(n * c.DeviceDpi / 96.0);
    public static GraphicsPath Rounded(RectangleF r, float radius = 12)
    {
        float d = Math.Min(radius * 2, Math.Min(r.Width, r.Height)); var p = new GraphicsPath();
        p.AddArc(r.X, r.Y, d, d, 180, 90); p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90); p.AddArc(r.X, r.Bottom - d, d, d, 90, 90); p.CloseFigure(); return p;
    }
}
internal static class Branding
{
    public static Icon Icon() { using var s = typeof(Branding).Assembly.GetManifestResourceStream("HaloStudio.Icon")!; return new Icon(s, 32, 32); }
    public static Image Logo() { using var s = typeof(Branding).Assembly.GetManifestResourceStream("HaloStudio.Logo")!; using var image = Image.FromStream(s); return new Bitmap(image); }
}
public class ModernButton : Button
{
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public bool Primary { get; set; }
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public bool Selected { get; set; }
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public string Glyph { get; set; } = "";
    bool hover;
    public ModernButton() { FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; Cursor = Cursors.Hand; DoubleBuffered = true; ResizeRedraw = true; Height = 42; BackColor = Palette.Card; Font = Palette.Font(9); }
    protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics; g.SmoothingMode = SmoothingMode.AntiAlias; g.Clear(Parent?.BackColor ?? Palette.Background);
        Color bg = Primary ? Palette.Accent : Selected ? Palette.AccentSoft : hover ? Palette.AccentSoft : BackColor;
        using var path = Palette.Rounded(new RectangleF(0, 0, Width - 1, Height - 1), Palette.Px(this, 10)); using var fill = new SolidBrush(bg); g.FillPath(fill, path);
        if (!Primary && !Selected && Glyph.Length == 0) { using var border = new Pen(Palette.Border); g.DrawPath(border, path); }
        Color fg = !Enabled ? Palette.Muted : Primary ? Color.White : Selected ? Palette.Accent : ForeColor;
        int left = Palette.Px(this, Glyph.Length > 0 ? 46 : 12);
        if (Glyph.Length > 0) { using var font = new Font("Segoe MDL2 Assets", 13, FontStyle.Regular, GraphicsUnit.Point); TextRenderer.DrawText(g, Glyph, font, new Rectangle(Palette.Px(this, 16), 0, Palette.Px(this, 24), Height), fg, TextFormatFlags.VerticalCenter | TextFormatFlags.HorizontalCenter); }
        TextRenderer.DrawText(g, Text, Font, new Rectangle(left, 0, Width - left - Palette.Px(this, 12), Height), fg, TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis | (Glyph.Length > 0 ? TextFormatFlags.Left : TextFormatFlags.HorizontalCenter));
        if (Focused) ControlPaint.DrawFocusRectangle(g, new Rectangle(4, 4, Width - 8, Height - 8));
    }
}
public sealed class ToggleSwitch : CheckBox
{
    public ToggleSwitch() { SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer, true); AutoSize = false; Width = 54; Height = 30; Cursor = Cursors.Hand; Text = ""; }
    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias; e.Graphics.Clear(Parent?.BackColor ?? Palette.Card);
        int pad = Palette.Px(this, 3), dot = Height - pad * 2; using var p = Palette.Rounded(new RectangleF(0, 0, Width - 1, Height - 1), Height / 2); using var brush = new SolidBrush(Checked ? Palette.Accent : Color.FromArgb(205, 212, 225)); e.Graphics.FillPath(brush, p);
        e.Graphics.FillEllipse(Brushes.White, Checked ? Width - dot - pad : pad, pad, dot, dot);
        if (Focused) ControlPaint.DrawFocusRectangle(e.Graphics, ClientRectangle);
    }
}
public class StudioCard : Panel
{
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public bool FullWidth { get; set; }
    public StudioCard() { DoubleBuffered = true; ResizeRedraw = true; BackColor = Palette.Card; Padding = new(22); Margin = new(0, 0, 0, 18); }
    protected override void OnPaintBackground(PaintEventArgs e)
    {
        e.Graphics.Clear(Parent?.BackColor ?? Palette.Background); e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        using var p = Palette.Rounded(new RectangleF(1, 1, Width - 3, Height - 3), Palette.Px(this, 14));
        using var fill = new SolidBrush(BackColor); e.Graphics.FillPath(fill, p);
    }
    protected override void OnPaint(PaintEventArgs e) { e.Graphics.SmoothingMode = SmoothingMode.AntiAlias; using var p = Palette.Rounded(new RectangleF(1, 1, Width - 3, Height - 3), Palette.Px(this, 14)); using var pen = new Pen(Palette.Border); e.Graphics.DrawPath(pen, p); }
}
public sealed class InputSurface : StudioCard
{
    public InputSurface(Control input, int width)
    {
        Width = width; Height = 42; Padding = new(12, 8, 12, 8); Margin = new(0, 5, 12, 5); BackColor = Palette.Input;
        input.BackColor = Palette.Input; input.ForeColor = Palette.Text; input.Font = Palette.Font();
        if (input is TextBox text) text.BorderStyle = BorderStyle.None;
        if (input is NumericUpDown number) number.BorderStyle = BorderStyle.None;
        Controls.Add(input);
        void Arrange() { input.SetBounds(Padding.Left, Math.Max(Padding.Top, (Height - input.PreferredSize.Height) / 2), Math.Max(20, Width - Padding.Horizontal), input.PreferredSize.Height); }
        SizeChanged += (_, _) => Arrange(); Arrange();
        Layout += (_, _) => Arrange(); input.FontChanged += (_, _) => Arrange();
    }
}
public sealed class ColorSwatch : Button
{
    public string Hex { get; }
    public bool Official { get; }
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public bool Selected { get; set; }
    public ColorSwatch(string hex, string label, bool official = false) { Hex = hex; Official = official; Text = label; AccessibleName = label + " " + hex; Width = 84; Height = 78; FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; Cursor = Cursors.Hand; DoubleBuffered = true; Font = Palette.Font(8); Margin = new(0, 4, 8, 0); }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics; g.Clear(Parent?.BackColor ?? Palette.Card); g.SmoothingMode = SmoothingMode.AntiAlias;
        int d = Palette.Px(this, 30), x = (Width - d) / 2, y = Palette.Px(this, 5), gap = Palette.Px(this, 4);
        using var brush = new SolidBrush(ColorTranslator.FromHtml(ScreenPalette.Preview(Hex, Official))); g.FillEllipse(brush, x, y, d, d);
        using var edge = new Pen(Selected ? Palette.Accent : Palette.Border, Selected ? 2 : 1); g.DrawEllipse(edge, x - gap, y - gap, d + gap * 2, d + gap * 2);
        TextRenderer.DrawText(g, Text, Font, new Rectangle(0, y + d + gap * 2, Width, Height - y - d - gap * 2), Selected ? Palette.Accent : Palette.Text, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        if (Focused) ControlPaint.DrawFocusRectangle(g, ClientRectangle);
    }
}
public sealed class ThemeTile : Control
{
    readonly PixelFrame pixels; readonly string caption, description; bool selected, hover; string color; Bitmap? thumbnail;
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public bool Selected { get => selected; set { if (selected != value) { selected = value; Invalidate(); } } }
    public string Key { get; }
    public void SetColor(string hex) { if (color != hex) { color = hex; thumbnail?.Dispose(); thumbnail = null; Invalidate(); } }
    public ThemeTile(string key, Design design, Settings preview)
    {
        Key = key; caption = design.Name; description = design.Description; color = ScreenPalette.Preview(design.Color);
        // Themes that carry a monitor dashboard preview it while the hardware
        // monitor switch is on; clock-only themes always preview their clock.
        bool monitor = preview.MonitorEnabled && design.Monitor;
        var settings = preview with { Theme = key, Themes = true };
        pixels = Designs.Render(monitor ? "" : "20:26", monitor ? "系统监控" : "时钟", settings, 0, Showcase.Sample(0), new(2026, 10, 13, 20, 26, 0));
        Init();
    }
    public ThemeTile(string key, TelemetryDesign design)
    {
        Key=key; caption=design.Name; description=design.Description; color=ScreenPalette.Preview(design.Color);
        pixels=TelemetryDesigns.Render(key,TelemetrySprint.At(9),true); Init();
    }
    void Init()
    {
        DoubleBuffered = true; ResizeRedraw = true; Cursor = Cursors.Hand; Height = 158; Margin = new(0); TabStop = true; AccessibleRole = AccessibleRole.PushButton; AccessibleName = caption;
        MouseEnter += (_, _) => { hover = true; Invalidate(); }; MouseLeave += (_, _) => { hover = false; Invalidate(); }; KeyDown += (_, e) => { if (e.KeyCode is Keys.Enter or Keys.Space) OnClick(EventArgs.Empty); };
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics; g.SmoothingMode = SmoothingMode.AntiAlias; g.Clear(Parent?.BackColor ?? Palette.Background); int pad = Palette.Px(this, 16);
        using var p = Palette.Rounded(new RectangleF(1, 1, Width - 3, Height - 3), Palette.Px(this, 12)); using var bg = new SolidBrush(selected ? Color.FromArgb(244, 246, 255) : Palette.Card); g.FillPath(bg, p);
        using var edge = new Pen(selected ? Palette.Accent : hover ? Color.FromArgb(181, 192, 230) : Palette.Border, selected ? 2 : 1); g.DrawPath(edge, p);
        using var font = Palette.Font(10, FontStyle.Bold); TextRenderer.DrawText(g, caption, font, new Rectangle(pad, pad, Width - pad * 2, Palette.Px(this, 26)), Palette.Text, TextFormatFlags.EndEllipsis);
        if (thumbnail == null) { var c = new PixelCanvas(); pixels.Pixels.CopyTo(c.Data, 0); thumbnail = c.Bitmap(ColorTranslator.FromHtml(color), 1); }
        var box = new Rectangle(pad, Palette.Px(this, 51), Width - pad * 2, Palette.Px(this, 48));
        using var strip = new SolidBrush(Color.FromArgb(20, 26, 39)); using var stripPath = Palette.Rounded(box, Palette.Px(this, 6)); g.FillPath(strip, stripPath);
        int w = Math.Min(box.Width - Palette.Px(this, 12), box.Height * 8 - Palette.Px(this, 16)); w -= w % 8; int h = w / 8;
        g.InterpolationMode = InterpolationMode.NearestNeighbor; g.PixelOffsetMode = PixelOffsetMode.Half; g.DrawImage(thumbnail, new Rectangle(box.X + (box.Width - w) / 2, box.Y + (box.Height - h) / 2, w, h), 0, 0, 256, 32, GraphicsUnit.Pixel);
        using var small = Palette.Font(9); TextRenderer.DrawText(g, description, small, new Rectangle(pad, Palette.Px(this, 113), Width - pad * 2, Height - Palette.Px(this, 119)), Palette.Muted, TextFormatFlags.WordBreak | TextFormatFlags.EndEllipsis);
        if (Focused) ControlPaint.DrawFocusRectangle(g, new Rectangle(5, 5, Width-10, Height-10));
    }
    protected override void Dispose(bool disposing) { if (disposing) { thumbnail?.Dispose(); } base.Dispose(disposing); }
}
public sealed class ThemeGallery : Panel
{
    readonly int minimumTileWidth, tileHeight;
    public ThemeGallery(int minimumTileWidth = 290, int tileHeight = 164) { this.minimumTileWidth = minimumTileWidth; this.tileHeight = tileHeight; DoubleBuffered = true; ResizeRedraw = true; Margin = new(0, 0, 0, 8); }
    protected override void OnLayout(LayoutEventArgs e)
    {
        base.OnLayout(e); int gap = Palette.Px(this, 14), min = Palette.Px(this, minimumTileWidth), h = Palette.Px(this, tileHeight);
        int columns = Math.Clamp((Width + gap) / (min + gap), 1, 3), tileWidth = (Width - gap * (columns - 1)) / columns;
        for (int i = 0; i < Controls.Count; i++) Controls[i].SetBounds(i % columns * (tileWidth + gap), i / columns * (h + gap), tileWidth, h);
        int rows = (Controls.Count + columns - 1) / columns; int height = rows == 0 ? 0 : rows * (h + gap) - gap; if (Height != height) Height = height;
    }
}
public sealed class PixelPreview : Control
{
    PixelFrame? frame; Color pixelColor = Palette.Accent; Bitmap? cached; bool dirty = true;
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public PixelFrame? Frame { get => frame; set { if (ReferenceEquals(frame, value)) return; if (frame != null && value != null && frame.Pixels.AsSpan().SequenceEqual(value.Pixels)) { frame = value; return; } frame = value; dirty = true; Invalidate(); } }
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)] public Color PixelColor { get => pixelColor; set { if (pixelColor == value) return; pixelColor = value; dirty = true; Invalidate(); } }
    public PixelPreview() { DoubleBuffered = true; ResizeRedraw = true; BackColor = Color.FromArgb(7, 11, 17); MinimumSize = new(256, 48); }
    public Rectangle Viewport
    {
        get { int w = Math.Max(256, Math.Min(Width - Palette.Px(this, 20), (Height - Palette.Px(this, 12)) * 8)); w -= w % 8; return new((Width - w) / 2, (Height - w / 8) / 2, w, w / 8); }
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var viewport = Viewport; int scale = Math.Max(1, (int)Math.Ceiling(viewport.Width / 256.0));
        if (cached == null || cached.Width != 256 * scale)
        {
            cached?.Dispose(); cached = new Bitmap(256 * scale, 32 * scale, System.Drawing.Imaging.PixelFormat.Format32bppArgb); dirty = true;
        }
        if (dirty)
        {
            // One cached bitmap replaces 8,192 GDI calls on every UI update.
            var bits = cached.LockBits(new(0, 0, cached.Width, cached.Height), System.Drawing.Imaging.ImageLockMode.WriteOnly, System.Drawing.Imaging.PixelFormat.Format32bppArgb);
            try
            {
                unsafe
                {
                    int on = pixelColor.ToArgb(), off = Color.FromArgb(17, 24, 33).ToArgb(), background = BackColor.ToArgb(), dot = Math.Max(1, scale - 1);
                    for (int y = 0; y < cached.Height; y++) new Span<int>((byte*)bits.Scan0 + y * bits.Stride, cached.Width).Fill(background);
                    for (int y = 0; y < 32; y++) for (int x = 0; x < 256; x++)
                    {
                        int value = frame != null && (frame.Pixels[y / 8 * 256 + x] & (1 << (y % 8))) != 0 ? on : off;
                        for (int yy = 0; yy < dot; yy++) new Span<int>((byte*)bits.Scan0 + (y * scale + yy) * bits.Stride + x * scale * 4, dot).Fill(value);
                    }
                }
            }
            finally { cached.UnlockBits(bits); }
            dirty = false;
        }
        e.Graphics.InterpolationMode = InterpolationMode.NearestNeighbor; e.Graphics.PixelOffsetMode = PixelOffsetMode.Half;
        e.Graphics.DrawImage(cached, viewport, 0, 0, cached.Width, cached.Height, GraphicsUnit.Pixel);
    }
    protected override void Dispose(bool disposing) { if (disposing) cached?.Dispose(); base.Dispose(disposing); }
}
