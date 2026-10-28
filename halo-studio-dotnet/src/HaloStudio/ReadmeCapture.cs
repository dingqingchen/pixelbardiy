namespace HaloStudio;

public sealed partial class StudioForm
{
    // Render the real controls and theme code with explicit, non-personal demo
    // data. Never connect to USB or use the user's runtime for documentation.
    public void CaptureReadme(string directory)
    {
        if (!previewMode) throw new InvalidOperationException("README capture requires --preview");
        Directory.CreateDirectory(directory); auditing = true;
        current = new Settings { Theme = "ion", Mode = "idle", CpuTemperatureEnabled = false, Seconds = true, MonitorRotate = false }.Validated();
        var demo = Showcase.Sample(3); var time = new DateTime(2026, 10, 29, 20, 26, 18);
        ClientSize = new(Palette.Px(this,1280),Palette.Px(this,900));
        PixelFrame Frame(string theme, string mode, string view = "bar", string text = "") =>
            Designs.Render(text, mode, current with { Theme = theme, MonitorView = view }, 3, demo, time);
        void StripColor(string name, PixelFrame pixels, string color)
        {
            using var control = new PixelPreview { Size = new(1536, 216), Frame = pixels, PixelColor = ColorTranslator.FromHtml(ScreenPalette.Preview(color)) };
            control.CreateControl(); using var bitmap = new Bitmap(control.Width, control.Height);
            control.DrawToBitmap(bitmap, new(Point.Empty, bitmap.Size)); bitmap.Save(Path.Combine(directory, name + ".png"));
        }
        void Strip(string name,PixelFrame pixels,string theme) => StripColor(name,pixels,Designs.All[theme].Color);
        foreach(var (key,design) in TelemetryDesigns.All) StripColor("telemetry-"+key,TelemetryDesigns.Render(key,TelemetrySprint.At(9),true,time),design.Color);
        foreach (var key in Designs.All.Keys) Strip("theme-" + key, Frame(key, "时钟"), key);
        foreach (var (view, theme) in new[] { ("dense", "matrix"), ("compact", "peach"), ("bar", "ion"), ("graph", "amber") })
            Strip("monitor-" + view, Frame(theme, "系统监控", view), theme);
        string[] verses = ["把夜色折成远航的帆", "让星光落在你的肩", "我们在黎明之前相见"];
        for (int i = 0; i < verses.Length; i++) Strip("lyric-" + (i + 1), Frame("paper", "歌词", text: verses[i]), "paper");
        foreach (int page in new[]{0,1,2,5})
        {
            current = current with { Theme = page == 1 ? "matrix" : page == 2 ? "paper" : "ion", MonitorView = "dense", Mode = page == 2 ? "auto" : "idle", IdleContent = page == 1 ? "monitor" : "clock" };
            if(page==5) current=current with {TelemetryTheme="05_subaru_xt",TelemetryEnabled=false};
            Sync(); SelectPage(page); pages[page].AutoScrollPosition = Point.Empty;
            preview.Frame = Frame(current.Theme, page == 1 ? "系统监控" : page == 2 ? "歌词" : "时钟", "dense", verses[0]);
            preview.PixelColor = ColorTranslator.FromHtml(ScreenPalette.Preview(current.ScreenColor()));
            if(page==5) { preview.Frame=TelemetryDesigns.Render(current.TelemetryTheme,TelemetrySprint.At(9),true,time); preview.PixelColor=ColorTranslator.FromHtml(ScreenPalette.Preview(TelemetryDesigns.All[current.TelemetryTheme].Color)); }
            status.Text = "离线功能演示"; sidebarStatus.Text = "○  离线功能演示"; sidebarTemp.Text = "CPU 温度  —";
            song.Text = "星际来信 · 原创演示歌词"; performance.Text = "演示数据 · 未连接音响";
            thermal.Text = "首次使用：独立温度采集关闭";
            musicTitle.Text = "星际来信 / 原创演示"; lyric.Text = verses[0]; musicDetail.Text = "网易云歌词显示 · 此截图使用原创演示文本";
            UpdateSensors(demo); PerformLayout(); Application.DoEvents();
            if(page==5) { pages[5].AutoScrollPosition=new Point(0,telemetryGallery.Top+telemetryTiles.Single(t=>t.Key==current.TelemetryTheme).Top); Application.DoEvents(); }
            // DrawToBitmap's non-client frame uses classic GDI decorations,
            // not Windows 11 DWM. Export only real client controls; the collage
            // script supplies a clearly documented Windows 11-style frame.
            using var window = new Bitmap(Width, Height);
            DrawToBitmap(window, new(0, 0, Width, Height));
            Point clientOrigin = PointToScreen(Point.Empty);
            using var client = window.Clone(new Rectangle(clientOrigin.X - Left, clientOrigin.Y - Top, ClientSize.Width, ClientSize.Height), window.PixelFormat);
            client.Save(Path.Combine(directory, "ui-" + page + ".png"));
        }
        Files.Save(Path.Combine(directory, "capture.json"), new { Version = "2.7.0", Source = "Real WinForms client controls and Designs.Render; collage adds Windows 11-style frame", Data = "Showcase.Sample; original demo lyrics; TelemetrySprint.At(9)", UsbConnected = false });
        // Keep async live state hidden until this short-lived preview exits.
    }
}
