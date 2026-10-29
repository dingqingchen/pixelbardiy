using System.Drawing.Drawing2D;
namespace HaloStudio;

// Use the same card typography, input fill and accent for all hardware controls.
public sealed class SensorTable : Control
{
    Metric[] rows = [];
    public SensorTable() { DoubleBuffered = true; ResizeRedraw = true; Width = 700; Height = 100; Margin = new(0, 10, 0, 10); BackColor = Palette.Card; }
    public void Update(Snapshot snapshot) { rows = snapshot.Metrics; Height = Palette.Px(this, 44 * (rows.Length + 1)); Invalidate(); }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g = e.Graphics; int h = Palette.Px(this, 44), pad = Palette.Px(this, 12);
        using var fill = new SolidBrush(Palette.Input); using var line = new Pen(Palette.Border);
        using var head = Palette.Font(9, FontStyle.Bold); using var font = Palette.Font(10);
        g.FillRectangle(fill, 0, 0, Width, h);
        int a = Width * 36 / 100, b = Width * 58 / 100;
        void Cell(string text, int x, int y, int width, Font f, Color c) => TextRenderer.DrawText(g, text, f, new Rectangle(x + pad, y, Math.Max(1, width - pad * 2), h), c, TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
        Cell("指标", 0, 0, a, head, Palette.Muted); Cell("当前值", a, 0, b-a, head, Palette.Muted); Cell("数据来源", b, 0, Width-b, head, Palette.Muted);
        for (int i = 0; i < rows.Length; i++)
        {
            int y = (i+1)*h; var m = rows[i]; Cell(m.Name, 0, y, a, font, Palette.Text); Cell(m.Text(), a, y, b-a, head, Palette.Accent); Cell(m.Source, b, y, Width-b, font, Palette.Muted); g.DrawLine(line, 0, y+h-1, Width, y+h-1);
        }
    }
}
public sealed class MetricPicker : Panel
{
    readonly Dictionary<string, MetricChip> chips = [];
    bool arranging; int viewportLimit; bool updating;
    public event Action? SelectionChanged;
    public string[] SelectedKeys => chips.Where(x => x.Value.Checked).Select(x => x.Key).ToArray();
    public MetricPicker() { DoubleBuffered = true; ResizeRedraw = true; AutoScroll = true; BackColor = Palette.Card; Width = 700; Height = 100; Margin = new(0, 10, 0, 10); AccessibleName = "可滚动的显示指标列表"; }
    public void SetViewportLimit(int height) { if (viewportLimit == height) return; viewportLimit = height; PerformLayout(); }
    public void Update(Snapshot snapshot, string[] selected)
    {
        // Preserve pending selections across sensor polls; only add newly discovered metrics.
        if (snapshot.Metrics.All(m => chips.ContainsKey(m.Key))) return;
        SuspendLayout();
        updating = true;
        try
        {
            foreach (var m in snapshot.Metrics) if (!chips.ContainsKey(m.Key)) { var chip = new MetricChip(m.Name, m.Key) { Checked = selected.Contains(m.Key) }; chip.Changed += () => { if (!updating) SelectionChanged?.Invoke(); }; chips.Add(m.Key, chip); Controls.Add(chip); }
        }
        finally { updating = false; }
        ResumeLayout(true);
    }
    protected override void OnLayout(LayoutEventArgs e)
    {
        if (arranging) return; arranging = true;
        try
        {
            int gap = Palette.Px(this, 10), h = Palette.Px(this, 56);
            // Reserve the scrollbar gutter even before it appears, avoiding a
            // one/two-column oscillation at the responsive breakpoint.
            int width = Math.Max(1, Width - SystemInformation.VerticalScrollBarWidth - Palette.Px(this, 4));
            int columns = width >= Palette.Px(this, 560) ? 2 : 1, w = Math.Max(1, (width - gap * (columns-1))/columns);
            int rows = (Controls.Count+columns-1)/columns, contentHeight = Math.Max(h, rows*(h+gap)-gap);
            int limit = viewportLimit > 0 ? viewportLimit : Palette.Px(this, 340);
            Height = Math.Min(contentHeight, limit);
            int offset = Math.Clamp(AutoScrollPosition.Y, -Math.Max(0, contentHeight - ClientSize.Height), 0);
            for (int i = 0; i < Controls.Count; i++) Controls[i].SetBounds(i%columns*(w+gap), i/columns*(h+gap) + offset, w, h);
            AutoScrollMinSize = new(0, contentHeight); base.OnLayout(e);
            VerticalScroll.SmallChange = Math.Max(1, h / 2); VerticalScroll.LargeChange = Math.Max(h, ClientSize.Height);
        }
        finally { arranging = false; }
    }
}
public sealed class MetricChip : CheckBox
{
    readonly string title, key;
    public event Action? Changed;
    public MetricChip(string title, string key) { this.title=title; this.key=key; Text=title; AccessibleName=title+" "+key; Cursor=Cursors.Hand; AutoSize=false; SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true); }
    protected override void OnCheckedChanged(EventArgs e) { base.OnCheckedChanged(e); Changed?.Invoke(); }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g=e.Graphics; g.Clear(Parent?.BackColor ?? Palette.Card); g.SmoothingMode=SmoothingMode.AntiAlias;
        using var p=Palette.Rounded(new RectangleF(1,1,Width-3,Height-3),Palette.Px(this,9)); using var fill=new SolidBrush(Checked?Palette.AccentSoft:Palette.Input); using var border=new Pen(Checked?Palette.Accent:Palette.Border); g.FillPath(fill,p);g.DrawPath(border,p);
        int pad=Palette.Px(this,14), d=Palette.Px(this,18), y=(Height-d)/2;
        using var box=Palette.Rounded(new RectangleF(pad,y,d,d),Palette.Px(this,4)); using var boxFill=new SolidBrush(Checked?Palette.Accent:Palette.Card);g.FillPath(boxFill,box);g.DrawPath(border,box);
        if(Checked) { using var tick=new Pen(Color.White,Palette.Px(this,2));g.DrawLines(tick,[new(pad+d/5,y+d/2),new(pad+d*2/5,y+d*3/4),new(pad+d*4/5,y+d/4)]); }
        int x=pad*2+d;using var font=Palette.Font(10);using var small=Palette.Font(9);
        TextRenderer.DrawText(g,title,font,new Rectangle(x,Palette.Px(this,6),Width-x-pad,Palette.Px(this,23)),Palette.Text,TextFormatFlags.EndEllipsis);
        TextRenderer.DrawText(g,key,small,new Rectangle(x,Palette.Px(this,29),Width-x-pad,Palette.Px(this,21)),Palette.Muted,TextFormatFlags.EndEllipsis);
        if(Focused) ControlPaint.DrawFocusRectangle(g,new Rectangle(4,4,Width-8,Height-8));
    }
}
