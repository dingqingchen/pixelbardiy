using System.Text.Json;

namespace HaloStudio;

public sealed record DemoStage(string Kind, string Name, double Seconds, string Theme = "ion", string Mode = "clock", string View = "bar", string Text = "", string Color = "#8DE9FF", string Transition = "up");
public sealed record DemoScene(PixelFrame Frame, string Color, byte Animation, bool Urgent, byte Interval = 16);
public sealed class Showcase
{
    readonly DemoStage[] stages; int index; long stageAt, nextFrame; string lastIdentity = "";
    public string Title { get; }
    public string Description { get; }
    public string StageName => Finished ? "演示结束" : stages[index].Name;
    public bool Finished => index >= stages.Length;
    public double Progress { get; private set; }
    public double Duration => stages.Sum(s => s.Seconds);
    public Showcase(string file)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(file)); var root = doc.RootElement;
        Title = root.GetProperty("title").GetString() ?? "像素剧场"; Description = root.GetProperty("description").GetString() ?? "";
        stages = JsonSerializer.Deserialize<DemoStage[]>(root.GetProperty("stages"), Files.Json) ?? [];
        if (stages.Length is < 1 or > 40 || stages.Any(s => s.Seconds is < 1 or > 30 || s.Kind is not ("matrix" or "warp" or "wave" or "title" or "theme" or "lyric" or "outro"))) throw new InvalidDataException("演示编排无效");
        foreach (var stage in stages) { Protocol.Rgb(stage.Color); if (stage.Kind is "theme" or "lyric" && !Designs.All.ContainsKey(stage.Theme)) throw new InvalidDataException("演示引用了缺失的主题：" + stage.Theme); }
        stageAt = 0;
    }
    public DemoScene? Poll(Settings settings)
    {
        if (Finished) return null; long now = Environment.TickCount64; if (stageAt == 0) stageAt = now;
        while (!Finished && now - stageAt >= stages[index].Seconds * 1000) { stageAt += (long)(stages[index].Seconds * 1000); index++; }
        if (Finished) return null;
        if (now < nextFrame) return null;
        var stage = stages[index]; double t = (now - stageAt) / 1000.0;
        bool effect = stage.Kind is "warp" or "wave" or "title" or "outro";
        // Sparse keyframes plus MCU interpolation, instead of saturating the
        // request-paced USB bridge with intermediate animation frames.
        nextFrame = now + (effect ? 900 : 250);
        Progress = (stages.Take(index).Sum(s => s.Seconds) + t) / Duration;
        var scene = Render(stage, settings, t, index); bool changed = scene.Frame.Identity != lastIdentity; lastIdentity = scene.Frame.Identity;
        if(stage.Kind == "matrix") return changed ? scene with { Animation = 5, Interval = 32, Urgent = true } : null;
        byte animation = changed ? (stage.Kind == "theme" ? Transitions.ThemeStyle(stage.Theme) : Transitions.Style(stage.Transition)) : effect ? (byte)2 : (byte)0;
        return scene with { Animation = animation, Urgent = changed && stage.Kind is "theme" or "lyric" };
    }
    public static DemoScene Render(DemoStage stage, Settings settings, double t, int index = 0)
    {
        if (stage.Kind is "theme" or "lyric")
        {
            var s = settings with { Theme = stage.Theme, Themes = true, Animations = true, Seconds = true, MonitorRotate = false, MonitorView = stage.View, MonitorMetrics = ["cpu", "ram", "gpu0", "gpu0_temp", "upload", "download"] };
            string mode = stage.Kind == "lyric" ? "歌词" : stage.Mode == "monitor" ? "系统监控" : "时钟";
            var frame = Designs.Render(stage.Text, mode, s, t, Sample(t), new DateTime(2026, 10, 13, 20, 26, Math.Min(59, (int)t)));
            // Preserve lyric identity so the known, bounded MCU text viewport remains available.
            return new(frame with { Identity = frame.Identity + ":demo:" + index }, settings.ScreenColor(stage.Theme), 0, false);
        }
        var c = new PixelCanvas();
        if(stage.Kind == "matrix")
        {
            // The MCU draws 160 intermediate rain frames locally, then reveals this target.
            c.Raster("HALO STUDIO", 63, 9, 2); c.Line(8, 2, 247, 2); c.Line(8, 29, 247, 29);
            c.Rect(1, 12, 3, 8, true); c.Rect(252, 12, 3, 8, true);
        }
        else if (stage.Kind == "warp")
        {
            for (int i = 0; i < 30; i++)
            {
                double a = i * 2.39996323, z = (i * .6180339 + t * .55) % 1, r = z * z;
                int x = 128 + (int)(Math.Cos(a) * 150 * r), y = 16 + (int)(Math.Sin(a) * 20 * r);
                c.Line(x, y, 128 + (int)(Math.Cos(a) * 150 * Math.Max(0, r - .08)), 16 + (int)(Math.Sin(a) * 20 * Math.Max(0, r - .08)));
            }
            if (t > 2.7) { c.Erase(87, 9, 82, 14); c.Raster("HALO", 104, 9, 2); }
        }
        else if (stage.Kind == "wave")
        {
            for (int x = 0; x < 256; x += 2)
            {
                double envelope = Math.Pow(Math.Sin(x * Math.PI / 255), .7);
                for (int band = 0; band < 3; band++) c.Dot(x, 16 + (int)(Math.Sin(x * .065 - t * 4 + band * 1.8) * (12 - band * 3) * envelope));
                if (x % 8 == 0) c.Dot(x, 31);
            }
            int cursor = (int)(t * 50) % 256; c.Line(cursor, 0, cursor, 31); c.Circle(cursor, 16, 3);
        }
        else
        {
            var logo = new PixelCanvas(); logo.Raster(stage.Kind == "outro" ? "SEE YOU" : "HALO STUDIO", stage.Kind == "outro" ? 85 : 63, 9, 2);
            int reach = (int)Math.Min(128, t * 100);
            for (int y = 0; y < 32; y++) for (int x = Math.Max(0, 128 - reach); x < Math.Min(256, 128 + reach); x++) c.Dot(x, y, logo.IsOn(x, y));
            c.Line(0, 2, Math.Min(255, (int)(t * 100)), 2); c.Line(255, 29, Math.Max(0, 255 - (int)(t * 100)), 29);
            for (int i = 0; i < 7; i++) { c.Dot((int)(i * 37 + t * 30) % 256, 5); c.Dot(255 - (int)(i * 37 + t * 30) % 256, 26); }
        }
        return new(new(c.Data, stage.Name, "demo-effect:" + index), stage.Color, 0, false);
    }
    public static Snapshot Sample(double t) => new([
        new("cpu", "CPU", "CPU", 26 + Math.Sin(t) * 18, "%", "演示数据", 100) { History = Enumerable.Range(0, 24).Select(i => 35 + 25 * Math.Sin(i * .4 + t)).ToArray() },
        new("ram", "内存", "RAM", 43, "%", "演示数据", 100), new("ram_gb", "内存", "RAM", 13.72, "GB", "演示数据"),
        new("cpu_temp", "CPU 温度", "CPU", 54, "C", "演示数据", 100), new("gpu0", "GPU", "GPU", 38, "%", "演示数据", 100), new("gpu0_temp", "GPU 温度", "GPU", 51, "C", "演示数据", 100),
        new("upload", "上传", "UP", 152400, "B/s", "演示数据"), new("download", "下载", "DN", 2621440, "B/s", "演示数据")], "演示数据");
}
