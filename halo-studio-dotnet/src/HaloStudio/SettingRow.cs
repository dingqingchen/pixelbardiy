namespace HaloStudio;

// Wide inputs move below the labels on narrow cards; switches stay alongside.
public sealed class SettingRow : Panel
{
    readonly Label title, detail;
    readonly Control input;
    readonly int inputWidth;
    bool arranging;
    public SettingRow(string name, string explanation, Control control)
    {
        Width = 800; Height = 82; Margin = new(0); DoubleBuffered = true; ResizeRedraw = true;
        input = control; inputWidth = control.Width; input.Margin = new(0);
        title = new() { Text = name, AutoSize = true, Font = Palette.Font(9.5f, FontStyle.Bold), ForeColor = Palette.Text };
        detail = new() { Text = explanation, AutoSize = true, Font = Palette.Font(8), ForeColor = Palette.Muted };
        Controls.AddRange([title, detail, input]); PerformLayout();
    }
    protected override void OnLayout(LayoutEventArgs e)
    {
        base.OnLayout(e); if (arranging || input == null) return; arranging = true;
        try
        {
            int pad = Palette.Px(this, 13), gap = Palette.Px(this, 16), w = Math.Max(40, ClientSize.Width);
            int desired = Math.Min(Palette.Px(this, inputWidth), w - 2);
            bool below = input is not ToggleSwitch && w < desired + Palette.Px(this, 180) + gap;
            int textWidth = Math.Max(40, below ? w : w - desired - gap);
            title.MaximumSize = detail.MaximumSize = new(textWidth, 0);
            title.Location = new(0, pad); detail.Location = new(0, title.Bottom + Palette.Px(this, 4));
            input.Width = desired;
            int textHeight = detail.Bottom + pad;
            int height = below ? textHeight + input.Height + Palette.Px(this, 10) : Math.Max(Palette.Px(this, 82), Math.Max(textHeight, input.Height + pad * 2));
            input.Location = new(below ? 0 : w - desired - 2, below ? textHeight : (height - input.Height) / 2);
            Height = height;
        }
        finally { arranging = false; }
    }
    protected override void OnPaint(PaintEventArgs e) { base.OnPaint(e); using var line = new Pen(Palette.Border); e.Graphics.DrawLine(line, 0, Height - 1, Width, Height - 1); }
}
