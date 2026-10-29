using System.Diagnostics;
using System.Text.Json;
namespace HaloStudio;

public sealed partial class StudioForm : Form
{
    readonly Engine engine; readonly string runtime; readonly bool previewMode; readonly NotifyIcon tray;
    readonly PixelPreview preview = new() { Dock = DockStyle.Fill };
    readonly Panel body = new() { Dock = DockStyle.Fill };
    readonly Label heading = Label("主题与屏幕", 21, true), subtitle = Label("", 9), status = Label("正在连接", 9), song = Label("", 9), performance = Label("", 8);
    readonly Label musicTitle = Label("等待网易云播放", 18, true), lyric = Label("歌词将在这里同步出现", 13), musicDetail = Label("", 9), thermal = Hint("正在检查独立温度采集"), demoStatus = Label("准备播放", 11, true);
    readonly Label colorStatus = Label("", 9), sidebarStatus = Label("正在连接", 9), sidebarTemp = Label("CPU 温度  —", 9);
    readonly ProgressBar demoProgress = new() { Height = 5, Width = 680, Maximum = 1000, Margin = new(0, 10, 0, 10) };
    readonly List<Action> bindings = []; readonly List<ThemeTile> tiles = []; readonly List<ModernButton> navigation = []; readonly List<PagePanel> pages = []; readonly List<ColorSwatch> swatches = [];
    readonly ThemeGallery gallery = new();
    readonly FlowLayoutPanel colorChips = Row();
    readonly FlowLayoutPanel officialChips = Row();
    readonly MetricPicker metrics = new();
    readonly SensorTable sensors = new();
    readonly TextBox fanKey = new() { PlaceholderText = "传感器键，例如 gpu0_fan0", AccessibleName = "风扇传感器键" }, fanMax = new() { PlaceholderText = "例如 3000", AccessibleName = "风扇额定最大 RPM" };
    readonly FileSystemWatcher themeWatch; readonly System.Windows.Forms.Timer reloadTimer = new() { Interval = 500 };
    readonly InputCommit inputCommit;
    readonly Icon appIcon = Branding.Icon(); readonly Image logo = Branding.Logo();
    bool suppressInitialShow, workerStarted;
    internal bool WorkerStarted => workerStarted;
    bool loading, quitting, allowClose, auditing; volatile bool themeDirty; int pageIndex; Settings current; string? legacyLaunch; StudioState? latestState; string sensorSignature = "";

    public StudioForm(Engine worker, string directory, bool previewOnly, bool backgroundStart)
    {
        SuspendLayout();
        engine = worker; runtime = directory; previewMode = previewOnly; current = engine.Config;
        suppressInitialShow = backgroundStart; ShowInTaskbar = !backgroundStart; engine.Visible = !backgroundStart;
        Text = previewOnly ? "HaloStudio · 离线预览" : "HaloStudio"; Icon = appIcon; ClientSize = new(1280, 900); MinimumSize = new(1020, 720); StartPosition = FormStartPosition.CenterScreen;
        BackColor = Palette.Background; ForeColor = Palette.Text; Font = Palette.Font(); AutoScaleMode = AutoScaleMode.None;
        var shell = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Margin = new(0) };
        shell.ColumnStyles.Add(new(SizeType.Absolute, 276)); shell.ColumnStyles.Add(new(SizeType.Percent, 100)); Controls.Add(shell);
        var sidebar = new Panel { Dock = DockStyle.Fill, BackColor = Palette.Sidebar, Padding = new(20, 24, 20, 18), Margin = new(0) }; shell.Controls.Add(sidebar, 0, 0);
        var nav = Stack(); nav.Dock = DockStyle.Top; nav.AutoSize = true; sidebar.Controls.Add(nav);
        var brand = new Panel { Width = 212, Height = 65, Margin = new(2, 0, 0, 20), BackColor = Palette.Sidebar };
        brand.Controls.Add(new PictureBox { Image = logo, SizeMode = PictureBoxSizeMode.Zoom, Location = new(0, 4), Size = new(43, 43) });
        var name = Label("HaloStudio", 13, true); name.Location = new(53, 5); brand.Controls.Add(name);
        var edition = Label("PIXEL BAR", 9, false, Palette.Muted); edition.Location = new(54, 32); brand.Controls.Add(edition); nav.Controls.Add(brand);
        string[] labels = ["主题与屏幕", "硬件监控", "音乐与灯光", "演示剧场", "设置", "驾驶遥测"];
        string[] glyphs = ["\uE790", "\uE9D9", "\uE8D6", "\uE768", "\uE713", "\uE7F4"];
        for (int i = 0; i < labels.Length; i++)
        {
            int index = i; var b = Button(labels[i], () => SelectPage(index)); b.Glyph = glyphs[i]; b.Width = 212; b.Height = 50; b.BackColor = Palette.Sidebar; b.Margin = new(0, 0, 0, 6); navigation.Add(b); nav.Controls.Add(b);
        }
        // Reorder visually while keeping the existing page IDs stable.
        nav.Controls.SetChildIndex(navigation[5], 4);
        var bottom = Stack(); bottom.Dock = DockStyle.Bottom; bottom.AutoSize = true; bottom.AutoSizeMode = AutoSizeMode.GrowAndShrink;
        bottom.Controls.Add(sidebarStatus); bottom.Controls.Add(sidebarTemp); bottom.Controls.Add(Label("256 × 32  ·  全像素直绘", 8, false, Palette.Muted));
        var hide = Button("隐藏到托盘", Hide); hide.Width = 210; hide.Margin = new(0, 5, 0, 5); hide.BackColor = Palette.Sidebar; bottom.Controls.Add(hide); sidebar.Controls.Add(bottom);
        void FitSidebar()
        {
            foreach (Control child in nav.Controls) child.Width = Math.Max(1, nav.ClientSize.Width - nav.Padding.Horizontal - child.Margin.Horizontal - 2);
            hide.Width = Math.Max(1, bottom.ClientSize.Width - 2);
            foreach (Control child in bottom.Controls) if (child is Label label) label.MaximumSize = new(Math.Max(1, bottom.Width - 2), 0);
        }
        nav.SizeChanged += (_, _) => FitSidebar(); bottom.SizeChanged += (_, _) => FitSidebar();
        var main = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4, Padding = new(26, 16, 26, 12), Margin = new(0) };
        main.RowStyles.Add(new(SizeType.Absolute, 88)); main.RowStyles.Add(new(SizeType.Absolute, 218)); main.RowStyles.Add(new(SizeType.Percent, 100)); main.RowStyles.Add(new(SizeType.Absolute, 27)); shell.Controls.Add(main, 1, 0);
        void FitPreview() { int w = main.ClientSize.Width - main.Padding.Horizontal; main.RowStyles[1].Height = Math.Clamp(w / 8 + Palette.Px(main, 108), Palette.Px(main, 196), Palette.Px(main, 320)); }
        main.SizeChanged += (_, _) => FitPreview();
        var header = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, Margin = new(0) }; header.ColumnStyles.Add(new(SizeType.Percent, 100)); header.ColumnStyles.Add(new(SizeType.Absolute, 148));
        var titles = Stack(); titles.AutoSize = true; titles.Controls.Add(heading); subtitle.ForeColor = Palette.Muted; titles.Controls.Add(subtitle); header.Controls.Add(titles, 0, 0);
        var launch = Button("▶  一键演示", StartDemo, true); launch.Width = 136; launch.Height = 37; launch.Anchor = AnchorStyles.Right | AnchorStyles.Top; header.Controls.Add(launch, 1, 0); main.Controls.Add(header, 0, 0);
        var live = new StudioCard { Dock = DockStyle.Fill, Padding = new(14, 10, 14, 10), Margin = new(0, 0, 0, 17) };
        var liveGrid = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 3, Margin = new(0) };
        liveGrid.ColumnStyles.Add(new(SizeType.Percent, 55)); liveGrid.ColumnStyles.Add(new(SizeType.Percent, 45)); liveGrid.RowStyles.Add(new(SizeType.Absolute, 28)); liveGrid.RowStyles.Add(new(SizeType.Percent, 100)); liveGrid.RowStyles.Add(new(SizeType.Absolute, 26));
        liveGrid.Controls.Add(Label("屏幕预览", 8.5f, true), 0, 0); status.AutoSize = false; status.Dock = DockStyle.Fill; status.TextAlign = ContentAlignment.MiddleRight; liveGrid.Controls.Add(status, 1, 0);
        liveGrid.Controls.Add(preview, 0, 1); liveGrid.SetColumnSpan(preview, 2); song.AutoSize = false; song.AutoEllipsis = true; song.Dock = DockStyle.Fill; song.Margin = new(0, 5, 0, 0); song.ForeColor = Palette.Muted; liveGrid.Controls.Add(song, 0, 2); liveGrid.SetColumnSpan(song, 2); live.Controls.Add(liveGrid); main.Controls.Add(live, 0, 1);
        main.Controls.Add(body, 0, 2); performance.AutoSize = false; performance.Dock = DockStyle.Fill; performance.TextAlign = ContentAlignment.MiddleRight; performance.ForeColor = Palette.Muted; main.Controls.Add(performance, 0, 3);
        for (int i = 0; i < labels.Length; i++) { var page = new PagePanel { Dock = DockStyle.Fill }; body.Controls.Add(page); pages.Add(page); }
        BuildDisplay(); BuildMonitor(); BuildMusic(); BuildDemo(); BuildDevice(); BuildTelemetry(); LoadThemes(); Sync(); SelectPage(0);
        inputCommit = new(this); Application.AddMessageFilter(inputCommit);
        Deactivate += (_, _) => { if (!quitting) inputCommit.Commit(false); };
        tray = new NotifyIcon { Icon = appIcon, Text = "HaloStudio", Visible = true }; var menu = new ContextMenuStrip();
        menu.Items.Add("打开 HaloStudio", null, (_, _) => ShowStudio()); menu.Items.Add("播放像素演示", null, (_, _) => { ShowStudio(); StartDemo(); }); menu.Items.Add("退出并恢复原厂显示", null, async (_, _) => await QuitAsync()); tray.ContextMenuStrip = menu; tray.DoubleClick += (_, _) => ShowStudio();
        VisibleChanged += (_, _) => { engine.Visible = Visible; engine.MonitorVisible = Visible && pageIndex == 1; if (Visible && latestState != null) OnState(latestState); };
        FormClosing += async (_, e) => { if (allowClose) return; e.Cancel = true; if (e.CloseReason == CloseReason.WindowsShutDown) await QuitAsync(); else Hide(); };
        engine.Changed += OnState; themeWatch = new(Designs.DirectoryPath, "*.json") { NotifyFilter = NotifyFilters.FileName | NotifyFilters.LastWrite, EnableRaisingEvents = true };
        themeWatch.Changed += (_, _) => themeDirty = true; themeWatch.Created += (_, _) => themeDirty = true; themeWatch.Deleted += (_, _) => themeDirty = true; themeWatch.Renamed += (_, _) => themeDirty = true;
        reloadTimer.Tick += (_, _) => { if (themeDirty) { themeDirty = false; ReloadThemes(); } }; reloadTimer.Start();
        Shown += (_, _) => { FitSidebar(); FitPreview(); foreach (var page in pages) { ResizePage(page); foreach (Control child in page.Controls) if (child.Tag is Action reflow) reflow(); } StartWorker(); };
        // This form is composed at runtime: scale the completed tree once. Setting
        // AutoScaleMode before adding children scales only the empty form on high DPI.
        float dpiScale = DeviceDpi / 96f; Scale(new SizeF(dpiScale, dpiScale));
        AutoScaleDimensions = new SizeF(DeviceDpi, DeviceDpi); AutoScaleMode = AutoScaleMode.Dpi;
        ResumeLayout(true);
        if (backgroundStart) { _ = Handle; BeginInvoke((Action)StartWorker); }
    }
    void StartWorker() { if (workerStarted) return; workerStarted = true; engine.Visible = Visible; engine.Start(previewMode); }
    protected override void SetVisibleCore(bool value)
    {
        // Suppress Application.Run's initial Show before any visible window is
        // created. A hidden handle/message loop still services the tray/worker.
        if (value && suppressInitialShow) { suppressInitialShow = false; base.SetVisibleCore(false); return; }
        base.SetVisibleCore(value);
    }
    void OnState(StudioState value)
    {
        latestState = value; if (!engine.Visible || IsDisposed) return;
        try
        {
            BeginInvoke(() =>
        {
            if (auditing || IsDisposed || !Visible) return;
            preview.Frame = value.Frame; preview.PixelColor = ColorTranslator.FromHtml(ScreenPalette.Preview(value.ScreenColor, value.OfficialColor));
            status.Text = previewMode ? "离线预览" : value.Connected ? "●  USB 已连接" : value.Status; status.ForeColor = value.Connected ? Color.FromArgb(28, 150, 111) : Palette.Muted;
            sidebarStatus.Text = value.Connected ? "●  Halo PixelBar 在线" : "○  等待音响连接"; sidebarStatus.ForeColor = status.ForeColor;
            sidebarTemp.Text = "CPU 温度  " + value.Snapshot.Get("cpu_temp").Text();
            song.Text = value.TelemetryActive ? value.Frame?.Text ?? "驾驶遥测" : value.DemoStage.Length > 0 ? value.DemoStage : value.Track.Title.Length > 0 ? (value.Track.Playing ? "正在播放  " : "已暂停  ") + value.Track.Title + " · " + value.Track.Artist : "默认显示 · " + (current.IdleContent == "clock" ? "时钟" : "系统监控");
            performance.Text = $"CPU {value.CpuPercent:F2}%   ·   内存 {value.MemoryMB:F0} MB   ·   {value.Frames} 帧已确认   ·   {value.FrameSeconds:F2} s / 帧";
            musicTitle.Text = value.Track.Title.Length > 0 ? value.Track.Title + "  /  " + value.Track.Artist : "等待网易云播放";
            lyric.Text = value.Frame?.Identity.StartsWith("歌词:") == true ? value.Frame.Text : value.Track.RealtimeLyric.Length > 0 ? value.Track.RealtimeLyric : "暂无当前句";
            musicDetail.Text = value.Track.Provider + " · " + value.Status; thermal.Text = value.TemperatureStatus;
            demoStatus.Text = value.DemoStage.Length > 0 ? value.DemoStage : "准备播放 · 结束后自动回到日常"; demoProgress.Value = Math.Clamp((int)(value.DemoProgress * 1000), 0, 1000);
            telemetryStatusLabel.Text=value.TelemetryStatus;
            bool wasLoading=loading; loading=true; telemetryDemoToggle.Checked=value.TelemetryDemo; loading=wasLoading;
            if (engine.MonitorVisible) UpdateSensors(value.Snapshot);
        });
        }
        catch (InvalidOperationException) { }
    }
    void UpdateSensors(Snapshot snap)
    {
        string signature = string.Join("|", snap.Metrics.Select(m => m.Key + m.Text())); if (signature == sensorSignature) return; sensorSignature = signature;
        sensors.Update(snap); metrics.Update(snap, current.MonitorMetrics);
    }
    void Set(Settings s)
    {
        if (loading) return;
        bool previewChanged = current.IdleContent != s.IdleContent || current.MonitorView != s.MonitorView
            || current.MonitorEnabled != s.MonitorEnabled
            || current.MonitorMetricsCustom != s.MonitorMetricsCustom || current.Themes != s.Themes
            || !current.MonitorMetrics.SequenceEqual(s.MonitorMetrics);
        current = s.Validated(); engine.Configure(current);
        if (previewChanged) LoadThemes();
        Sync();
    }
    void Sync()
    {
        loading = true; try
        {
            foreach (var tile in telemetryTiles) tile.Selected=tile.Key==current.TelemetryTheme;
            foreach (var bind in bindings) bind(); foreach (var tile in tiles) { tile.Selected = tile.Key == current.Theme; tile.SetColor(ScreenPalette.Preview(current.ScreenColor(tile.Key), current.OfficialScreenColor(tile.Key))); }
            string hex = current.ScreenColor(); foreach (var swatch in swatches) { swatch.Selected = swatch.Official == current.OfficialScreenColor() && swatch.Hex.Equals(hex, StringComparison.OrdinalIgnoreCase); swatch.Invalidate(); }
            colorStatus.Text = ScreenPalette.Description(hex, current.OfficialScreenColor()) + "\n发送 RGB " + current.DeviceScreenColor(hex) + (current.ThemeColors.ContainsKey(current.Theme) ? " · 自定义" : " · 主题原色");
        }
        finally { loading = false; }
    }
    void SetThemeColor(string? color, bool official = false)
    {
        var colors = new Dictionary<string, string>(current.ThemeColors); var origins = new Dictionary<string, bool>(current.ThemeOfficialColors);
        if (color == null) colors.Remove(current.Theme); else colors[current.Theme] = color;
        if (color != null && official) origins[current.Theme] = true; else origins.Remove(current.Theme);
        Set(current with { ThemeColors = colors, ThemeOfficialColors = origins });
    }
    void PickThemeColor() => PickThemeColor(false);
    void PickThemeColor(bool official) { using var d = new ColorDialog { FullOpen = true, Color = ColorTranslator.FromHtml(current.ScreenColor()), CustomColors = ScreenPalette.Official.Keys.Take(16).Select(h => ColorTranslator.ToOle(ColorTranslator.FromHtml(h))).ToArray() }; if (d.ShowDialog(this) == DialogResult.OK) SetThemeColor($"#{d.Color.R:X2}{d.Color.G:X2}{d.Color.B:X2}", official); }
    void LoadColorChips()
    {
        colorChips.SuspendLayout(); officialChips.SuspendLayout(); foreach (var chip in swatches) chip.Dispose(); swatches.Clear(); colorChips.Controls.Clear(); officialChips.Controls.Clear();
        foreach (bool official in new[] { false, true })
        foreach (var entry in (official ? ScreenPalette.Official : ScreenPalette.All).Values.Where(e => e.Quick))
        {
            string input = entry.Input; var chip = new ColorSwatch(input, entry.Name, official) { AccessibleName = entry.Name + "，设备 RGB " + input + "，" + entry.Observation };
            // Startup scales the completed control tree once. Hot-loaded controls
            // are created after that pass and need the current DPI explicitly.
            if (AutoScaleMode == AutoScaleMode.Dpi) chip.Scale(new SizeF(DeviceDpi / 96f, DeviceDpi / 96f));
            chip.Click += (_, _) => SetThemeColor(input, official); swatches.Add(chip); (official ? officialChips : colorChips).Controls.Add(chip);
        }
        colorChips.ResumeLayout(true); officialChips.ResumeLayout(true);
    }
    void ReloadColors() { var error = ScreenPalette.Reload(ScreenPalette.FilePath); LoadColorChips(); Sync(); if (latestState != null) preview.PixelColor = ColorTranslator.FromHtml(ScreenPalette.Preview(latestState.ScreenColor, latestState.OfficialColor)); if (error != null) MessageBox.Show(this, error, "配色表"); }
    public void ApplyTestSettings(Settings s) { current = s.Validated(); engine.Configure(current); Sync(); }
    void LoadThemes()
    {
        gallery.SuspendLayout(); foreach (var tile in tiles) tile.Dispose(); tiles.Clear(); gallery.Controls.Clear();
        foreach (var (key, design) in Designs.All) { var tile = new ThemeTile(key, design, current); tile.Click += (_, _) => Set(current with { Theme = tile.Key, Themes = true }); gallery.Controls.Add(tile); tiles.Add(tile); }
        gallery.ResumeLayout(true);

    }
    void ReloadThemes() { Safe(() => { var errors = Designs.Reload(Designs.DirectoryPath); current = current.Validated(); engine.Configure(current); LoadThemes(); Sync(); if (errors.Length > 0) MessageBox.Show(this, string.Join("\n", errors), "部分主题未能加载"); }); }
    void StartDemo() { Safe(engine.StartShowcase); SelectPage(3); }
    public void ShowPage(int index) => SelectPage(Math.Clamp(index, 0, pages.Count-1));
    void SelectPage(int index)
    {
        pageIndex = index; for (int i = 0; i < pages.Count; i++) { pages[i].Visible = i == index; navigation[i].Selected = i == index; navigation[i].Invalidate(); }
        pages[index].BringToFront(); heading.Text = navigation[index].Text;
        subtitle.Text = new[] { "选择设计，调好颜色，让屏幕属于你。", "实时状态、温度与显示编排。", "当前这一句，与音乐的每一次起伏。", "从代码之雨启程，走过六种像素设计。", "启动、连接与应用管理。", "15 款复古电子仪表，让游戏数据变成车速与刻度。" }[index];
        engine.MonitorVisible = Visible && index == 1; ResizePage(pages[index]);
    }
    void ImportLrc() { using var d = new OpenFileDialog { Filter = "同步歌词|*.lrc|文本|*.txt" }; if (d.ShowDialog(this) == DialogResult.OK) Safe(() => engine.ImportLrc(d.FileName)); }
    void ImportDevice() { using var d = new OpenFileDialog { Filter = "本机验证记录|*.json" }; if (d.ShowDialog(this) != DialogResult.OK) return; Safe(() => { using var doc = JsonDocument.Parse(File.ReadAllText(d.FileName)); if (!doc.RootElement.TryGetProperty("candidate_sha256", out _)) throw new InvalidDataException("这不是 MCU 验证记录"); File.Copy(d.FileName, Path.Combine(runtime, "mcu-installation.json"), true); }); }
    void Safe(Action action) { try { action(); } catch (Exception e) { MessageBox.Show(this, e.Message, "HaloStudio"); } }
    void ShowStudio() { ShowInTaskbar = true; Show(); WindowState = FormWindowState.Normal; Activate(); }
    static void OpenFolder(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
    async Task SwitchLegacyAsync() { string? path = FindLegacy(); if (path == null) { using var d = new OpenFileDialog { Filter = "HaloStudio 旧版|HaloStudio.exe" }; if (d.ShowDialog(this) != DialogResult.OK) return; path = d.FileName; } legacyLaunch = path; await QuitAsync(); }
    static string? FindLegacy() { string? p = AppContext.BaseDirectory; for (int i = 0; i < 7 && p != null; i++, p = Path.GetDirectoryName(p.TrimEnd(Path.DirectorySeparatorChar))) { string f = Path.Combine(p, "halo-controller", "dist", "HaloStudio", "HaloStudio.exe"); if (File.Exists(f)) return f; } return null; }
    public async Task QuitAsync() { if (quitting) return; quitting = true; status.Text = "正在恢复原厂显示…"; Enabled = false; await engine.DisposeAsync(); tray.Visible = false; themeWatch.Dispose(); reloadTimer.Stop(); Program.ReleaseOwner(); allowClose = true; if (engine.LastError.Length > 0) { legacyLaunch = null; MessageBox.Show(this, engine.LastError, "退出诊断"); } if (legacyLaunch != null) Process.Start(new ProcessStartInfo(legacyLaunch) { UseShellExecute = true }); Close(); }
    protected override void Dispose(bool disposing) { if (disposing) { inputCommit?.Dispose(); tray?.Dispose(); themeWatch?.Dispose(); reloadTimer?.Dispose(); appIcon?.Dispose(); logo?.Dispose(); } base.Dispose(disposing); }
    public void SaveScreenshot(string path) { using var bitmap = new Bitmap(Width, Height); DrawToBitmap(bitmap, new(0, 0, Width, Height)); bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png); }
    sealed record Choice(string Key, string Name) { public override string ToString() => Name; }
}
