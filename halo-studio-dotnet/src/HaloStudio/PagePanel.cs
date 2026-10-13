namespace HaloStudio;

// Responsive columns pack cards beneath the shortest column; full-width content
// follows every preceding card. Breakpoints use the actual available width.
public sealed class PagePanel : Panel
{
    bool arranging;
    public int Columns { get; private set; } = 1;
    public PagePanel() { AutoScroll = true; DoubleBuffered = true; ResizeRedraw = true; Padding = new(0, 0, 8, 0); }
    protected override void OnControlAdded(ControlEventArgs e) { base.OnControlAdded(e); e.Control!.SizeChanged += (_, _) => PerformLayout(); PerformLayout(); }
    protected override void OnSizeChanged(EventArgs e) { base.OnSizeChanged(e); PerformLayout(); }
    protected override void OnLayout(LayoutEventArgs e)
    {
        if (arranging) return; arranging = true;
        try
        {
            int offset = AutoScrollPosition.Y, gap = Palette.Px(this, 18);
            int width = Math.Max(200, ClientSize.Width - Padding.Horizontal - SystemInformation.VerticalScrollBarWidth - 4);
            Columns = Math.Clamp((width + gap) / (Palette.Px(this, 400) + gap), 1, 3);
            int cellWidth = (width - gap * (Columns - 1)) / Columns;
            var nextY = Enumerable.Repeat(Padding.Top, Columns).ToArray();
            void Arrange(Control child, int w) { child.Width = w; if (child.Tag is Action reflow) reflow(); }
            foreach (Control child in Controls)
            {
                if (child is not StudioCard || child is StudioCard { FullWidth: true })
                {
                    int top = nextY.Max(); Arrange(child, width); child.Location = new(Padding.Left, top + offset);
                    Array.Fill(nextY, top + child.Height + gap);
                }
                else
                {
                    int column = 0;
                    for (int i = 1; i < Columns; i++) if (nextY[i] < nextY[column]) column = i;
                    Arrange(child, cellWidth); child.Location = new(Padding.Left + column * (cellWidth + gap), nextY[column] + offset);
                    nextY[column] += child.Height + gap;
                }
            }
            AutoScrollMinSize = new(0, nextY.Max() + Padding.Bottom); base.OnLayout(e);
        }
        finally { arranging = false; }
    }
}
