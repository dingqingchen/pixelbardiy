using System.Drawing.Drawing2D;

namespace HaloStudio;

// Native menu keyboard/accessibility behavior, with the same surfaces and
// typography as the rest of the app. One popup lives as long as its owner.
public sealed class StudioCombo : ModernButton
{
    public sealed record Option(string Key, string Name);
    public List<Option> Options { get; } = [];
    readonly RoundedMenu menu = new();
    internal ContextMenuStrip Popup => menu;
    string value = ""; bool hover;
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public string Value { get => value; set { this.value = value; Text = Options.FirstOrDefault(o => o.Key == value)?.Name ?? value; Invalidate(); } }
    public event EventHandler? ValueChanged;
    public StudioCombo()
    {
        Width = 256; Height = 42; BackColor = Palette.Input; ForeColor = Palette.Text; AccessibleRole = AccessibleRole.ComboBox;
        menu.Closed += (_, _) => Invalidate();
    }
    void Choose(string key) { if (Value == key) return; Value = key; ValueChanged?.Invoke(this, EventArgs.Empty); }
    protected override void OnClick(EventArgs e)
    {
        if (menu.Visible) { menu.Close(); return; }
        if (Options.Count == 0 || !Enabled) return;
        // Do not dispose this menu from Closed: item-click dispatch is still
        // running then. Rebuild only the items before the next opening.
        foreach (var item in menu.Items.Cast<ToolStripItem>().ToArray()) item.Dispose();
        menu.Items.Clear(); menu.Font = Font;
        int pad = Palette.Px(this, 6), width = Math.Max(Width, Options.Max(o => TextRenderer.MeasureText(o.Name, Font).Width) + Palette.Px(this, 66));
        width = Math.Min(width, Screen.FromControl(this).WorkingArea.Width - Palette.Px(this, 24));
        menu.Padding = new(pad); menu.MinimumSize = new(width, 0);
        foreach (var option in Options)
        {
            var item = new ToolStripMenuItem(option.Name) { AutoSize = false, Size = new(width - pad * 2, Palette.Px(this, 42)), Checked = option.Key == Value, Tag = option.Key, AccessibleName = option.Name };
            item.Click += (_, _) => Choose(option.Key); menu.Items.Add(item);
        }
        menu.Show(this, new Point(0, Height + Palette.Px(this, 5)));
        menu.Items.Cast<ToolStripMenuItem>().FirstOrDefault(i => i.Checked)?.Select(); Invalidate(); base.OnClick(e);
    }
    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        if (keyData is Keys.F4 or (Keys.Alt | Keys.Down) or Keys.Space or Keys.Enter) { OnClick(EventArgs.Empty); return true; }
        if (!menu.Visible && Options.Count > 0 && keyData is Keys.Up or Keys.Down or Keys.Home or Keys.End)
        {
            int index = Options.FindIndex(o => o.Key == Value);
            int next = keyData == Keys.Home ? 0 : keyData == Keys.End ? Options.Count - 1 : Math.Clamp(index + (keyData == Keys.Down ? 1 : -1), 0, Options.Count - 1);
            Choose(Options[next].Key); return true;
        }
        return base.ProcessCmdKey(ref msg, keyData);
    }
    protected override void OnMouseEnter(EventArgs e) { hover = true; base.OnMouseEnter(e); }
    protected override void OnMouseLeave(EventArgs e) { hover = false; base.OnMouseLeave(e); }
    protected override void OnGotFocus(EventArgs e) { base.OnGotFocus(e); Invalidate(); }
    protected override void OnLostFocus(EventArgs e) { base.OnLostFocus(e); Invalidate(); }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics; g.Clear(Parent?.BackColor ?? Palette.Card); g.SmoothingMode = SmoothingMode.AntiAlias;
        bool active = menu.Visible || Focused;
        using var path = Palette.Rounded(new RectangleF(1, 1, Width - 3, Height - 3), Palette.Px(this, 10));
        using var fill = new SolidBrush(hover || menu.Visible ? Color.FromArgb(240, 243, 255) : Palette.Input);
        using var edge = new Pen(active ? Palette.Accent : hover ? Color.FromArgb(182, 192, 229) : Palette.Border, active ? 1.5f : 1);
        g.FillPath(fill, path); g.DrawPath(edge, path);
        int pad = Palette.Px(this, 14), x = Width - Palette.Px(this, 19), y = Height / 2, d = Palette.Px(this, 4), direction = menu.Visible ? -1 : 1;
        TextRenderer.DrawText(g, Text, Font, new Rectangle(pad, 0, Math.Max(1, Width - pad - Palette.Px(this, 36)), Height), Enabled ? Palette.Text : Palette.Muted, TextFormatFlags.VerticalCenter | TextFormatFlags.Left | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
        using var arrow = new Pen(active ? Palette.Accent : Palette.Muted, Math.Max(1.5f, DeviceDpi / 64f)) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round };
        g.DrawLines(arrow, [new(x-d, y-direction*d/2), new(x, y+direction*d/2), new(x+d, y-direction*d/2)]);
    }
    protected override void Dispose(bool disposing) { if (disposing) menu.Dispose(); base.Dispose(disposing); }

    sealed class RoundedMenu : ContextMenuStrip
    {
        public RoundedMenu() { BackColor = Palette.Card; ForeColor = Palette.Text; ShowImageMargin = ShowCheckMargin = false; Renderer = new MenuRenderer(); }
        protected override void OnSizeChanged(EventArgs e)
        {
            base.OnSizeChanged(e); if (Width < 4 || Height < 4) return;
            using var path = Palette.Rounded(new RectangleF(0, 0, Width, Height), Palette.Px(this, 10));
            var previous = Region; Region = new Region(path); previous?.Dispose();
        }
    }
    sealed class MenuRenderer : ToolStripRenderer
    {
        protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e) => e.Graphics.Clear(Palette.Card);
        protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using var p = Palette.Rounded(new RectangleF(.5f, .5f, e.ToolStrip.Width - 1, e.ToolStrip.Height - 1), Palette.Px(e.ToolStrip, 10));
            using var edge = new Pen(Palette.Border); e.Graphics.DrawPath(edge, p);
        }
        protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
        {
            if (e.ToolStrip == null) return;
            bool current = e.Item is ToolStripMenuItem { Checked: true };
            if (!e.Item.Selected && !current) return;
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias; int inset = Palette.Px(e.ToolStrip, 2);
            using var p = Palette.Rounded(new RectangleF(inset, inset, e.Item.Width - inset * 2, e.Item.Height - inset * 2), Palette.Px(e.ToolStrip, 7));
            using var fill = new SolidBrush(e.Item.Selected ? Palette.AccentSoft : Palette.Input); e.Graphics.FillPath(fill, p);
        }
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            if (e.ToolStrip == null) return;
            bool current = e.Item is ToolStripMenuItem { Checked: true }; int pad = Palette.Px(e.ToolStrip, 12);
            TextRenderer.DrawText(e.Graphics, e.Text, e.TextFont, new Rectangle(pad, 0, Math.Max(1, e.Item.Width - pad * 2 - Palette.Px(e.ToolStrip, 24)), e.Item.Height), !e.Item.Enabled ? Palette.Muted : current ? Palette.Accent : Palette.Text, TextFormatFlags.VerticalCenter | TextFormatFlags.Left | TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
            if (!current) return;
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias; int x = e.Item.Width - pad - Palette.Px(e.ToolStrip, 7), y = e.Item.Height / 2, d = Palette.Px(e.ToolStrip, 4);
            using var tick = new Pen(Palette.Accent, Math.Max(1.5f, e.ToolStrip.DeviceDpi / 64f)) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round };
            e.Graphics.DrawLines(tick, [new(x-d, y), new(x-d/4, y+d), new(x+d*3/2, y-d)]);
        }
        protected override void OnRenderItemCheck(ToolStripItemImageRenderEventArgs e) { }
    }
}
