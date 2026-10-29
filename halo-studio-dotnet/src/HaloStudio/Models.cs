using System.Text.Json;
using System.Text.Json.Serialization;

namespace HaloStudio;

public sealed record Settings
{
    public bool TelemetryEnabled { get; init; }
    public int TelemetryPort { get; init; } = 20777;
    public string TelemetryTheme { get; init; } = "01_lagonda_led84";
    public bool Enabled { get; init; } = true;
    public string Mode { get; init; } = "auto";
    public bool Seconds { get; init; }
    public string Color { get; init; } = "#86D8F6";
    public double Offset { get; init; }
    public double LyricLeadSeconds { get; init; } = .8;
    public bool Online { get; init; } = true;
    public string Effect { get; init; } = "color_tide";
    public string AmbientColor { get; init; } = "#C3B9FF";
    public string Brightness { get; init; } = "high";
    public int Speed { get; init; } = 8;
    public bool AmbientEnabled { get; init; } = true;
    public string IdleContent { get; init; } = "clock";
    // A missing field in pre-2.7 settings inherits the user's old idle choice.
    bool? monitorEnabled;
    public bool MonitorEnabled { get => monitorEnabled ?? IdleContent == "monitor"; init => monitorEnabled = value; }
    [JsonIgnore] public bool WantsMonitor => Enabled && MonitorEnabled && (Designs.All.GetValueOrDefault(Theme)?.Monitor ?? false);
    public bool Themes { get; init; } = true;
    public string Theme { get; init; } = "kitty";
    public Dictionary<string, string> ThemeColors { get; init; } = [];
    public Dictionary<string, bool> ThemeOfficialColors { get; init; } = [];
    public int ScreenWhiteBlue { get; init; } = 255;
    public bool CpuTemperatureEnabled { get; init; }
    public bool CpuTemperatureElevation { get; init; }
    // Missing in older settings: only the old explicit authorization flag is
    // evidence of opting in; the old Enabled=true default was not consent.
    public bool? CpuTemperatureOptIn { get; init; }
    public Settings WithTemperatureChoice(bool enabled) => this with
    { CpuTemperatureEnabled = enabled, CpuTemperatureElevation = enabled, CpuTemperatureOptIn = true };
    public bool Animations { get; init; }
    public string MonitorView { get; init; } = "bar";
    public string PairAdvance { get; init; } = "pair";
    public bool MonitorRotate { get; init; } = true;
    public int RotationSeconds { get; init; } = 8;
    public string[] MonitorMetrics { get; init; } = ["cpu", "cpu_temp", "ram", "gpu0", "gpu0_temp", "download", "upload"];
    // Only an explicit "apply" in the hardware page replaces the theme's curated
    // dense slots; the default list must not rewrite a theme's dense design.
    public bool MonitorMetricsCustom { get; init; }
    public Dictionary<string, double> FanLimits { get; init; } = [];
    public bool Rhythm { get; init; } = true;
    public string RhythmStyle { get; init; } = "pulse";
    public double RhythmGain { get; init; } = 2.5;
    public string PowerProfile { get; init; } = "eco";
    public bool Transitions { get; init; }
    public string PixelTransition { get; init; } = "up";
    public Settings Validated() => this with
    {
        MonitorEnabled = MonitorEnabled,
        TelemetryPort = TelemetryReceiver.ValidPort(TelemetryPort) ? TelemetryPort : 20777,
        TelemetryTheme = TelemetryDesigns.All.ContainsKey(TelemetryTheme) ? TelemetryTheme : TelemetryDesigns.All.Keys.FirstOrDefault() ?? TelemetryTheme,
        Theme = Designs.All.ContainsKey(Theme) ? Theme : Designs.All.Keys.FirstOrDefault() ?? Theme,
        IdleContent = IdleContent=="monitor"?"monitor":"clock",
        PowerProfile = PowerProfile=="balanced"?"balanced":"eco",
        Mode = Mode == "auto" ? "auto" : "idle",
        MonitorView = new[] { "value", "bar", "graph", "compact", "dense" }.Contains(MonitorView) ? MonitorView : "bar",
        PairAdvance = PairAdvance == "single" ? "single" : "pair",
        PixelTransition = PixelTransition is "up" or "wipe" or "center" or "dissolve" ? PixelTransition : "up",
        ScreenWhiteBlue = Math.Clamp(ScreenWhiteBlue, 0, 255),
        CpuTemperatureOptIn = CpuTemperatureOptIn ?? (CpuTemperatureEnabled && CpuTemperatureElevation),
        CpuTemperatureEnabled = CpuTemperatureEnabled && (CpuTemperatureOptIn ?? CpuTemperatureElevation),
        CpuTemperatureElevation = CpuTemperatureEnabled && CpuTemperatureElevation && (CpuTemperatureOptIn ?? CpuTemperatureElevation),
        RotationSeconds = Math.Clamp(RotationSeconds, 2, 120),
        Offset = Math.Clamp(Offset, -30, 30),
        LyricLeadSeconds = Math.Clamp(LyricLeadSeconds, 0, 3),
        Speed = Math.Clamp(Speed, 1, 10),
        RhythmGain = Math.Clamp(RhythmGain, .4, 6),
        FanLimits = FanLimits ?? [],
        ThemeColors = (ThemeColors ?? []).Where(p => IsColor(p.Value)).ToDictionary(p => p.Key, p => p.Value.ToUpperInvariant()),
        ThemeOfficialColors = (ThemeOfficialColors ?? []).Where(p => p.Value && IsColor((ThemeColors ?? []).GetValueOrDefault(p.Key))).ToDictionary(p => p.Key, p => true),
        Color = IsColor(Color) ? Color.ToUpperInvariant() : "#86D8F6",
        MonitorMetrics = MonitorMetrics ?? ["cpu", "ram"]
    };
    public static bool IsColor(string? value) => value is { Length: 7 } && value[0] == '#' && value.AsSpan(1).IndexOfAnyExcept("0123456789abcdefABCDEF") < 0;
    // Existing theme/settings values remain device inputs for compatibility.
    // Appearance metadata lives in ScreenPalette and must not enter this path.
    // White correction only reduces blue; ambient lighting stays unchanged.
    public bool OfficialScreenColor(string? theme = null) => (Themes || theme != null) && ThemeColors.ContainsKey(theme ?? Theme) && ThemeOfficialColors.GetValueOrDefault(theme ?? Theme);
    public string DeviceScreenColor(string? color = null, bool? official = null) => !(official ?? OfficialScreenColor()) && (color ?? ScreenColor()).Equals("#FFFFFF", StringComparison.OrdinalIgnoreCase)
        ? $"#FFFF{Math.Clamp(ScreenWhiteBlue, 0, 255):X2}" : color ?? ScreenColor();
    public string ScreenColor(string? theme = null)
    {
        string key = theme ?? Theme;
        return Themes || theme != null ? ThemeColors.GetValueOrDefault(key) ?? Designs.All.GetValueOrDefault(key)?.Color ?? Color : Color;
    }
}
public sealed record Track(string Title = "", string Artist = "", string Album = "", double Duration = 0,
    double Position = 0, bool Playing = false, string App = "", string Provider = "Windows 媒体会话",
    string RealtimeLyric = "", double LineElapsed = 0, string SongId = "", bool NativeTimeline = false)
{
    public string Key => $"{Title}\0{Artist}\0{Album}\0{SongId}";
}
public sealed record Metric(string Key, string Name, string Short, double? Value, string Unit, string Source, double? Scale = null)
{
    public double[] History { get; init; } = [];
    public string Text(bool compact = false)
    {
        if (Value is not double v) return "--";
        if (Unit is "C" or "°C" or "℃") return $"{v:0}°C";
        if (Unit == "GB") return $"{v:0.00}" + (compact ? "G" : "GB");
        if (Unit == "GHz") return $"{v:0.00}G";
        if (Unit == "B/s")
        {
            string[] units = ["B", "K", "M", "G", "T"]; int i = 0;
            while (Math.Abs(v) >= 1024 && i < 4) { v /= 1024; i++; }
            return v.ToString(v < 10 ? "0.00" : v < 100 ? "0.0" : "0") + (compact ? units[i] : new[] { "B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s" }[i]);
        }
        return $"{v:0}{Unit}";
    }
    public double Ratio => Math.Clamp((Value ?? 0) / (Scale ?? Math.Max(1, History.DefaultIfEmpty(Value ?? 1).Max())), 0, 1);
    public string Label => Unit == "C" ? Short + " TEMP" : Key switch
    {
        "ram" => "MEMORY",
        "ram_gb" => "MEMORY GB",
        "upload" => "UPLOAD",
        "download" => "DOWNLOAD",
        "disk_read" => "DISK READ",
        "disk_write" => "DISK WRITE",
        _ => Short.ToUpperInvariant()
    };
}
public sealed record Snapshot(Metric[] Metrics, string Detail)
{
    public static readonly Snapshot Empty = new([], "选择系统监控后按需采样");
    public Metric Get(string key, string name = "", string unit = "") =>
        Metrics.FirstOrDefault(m => m.Key == key) ?? new(key, name, name, null, unit, "未发现传感器");
}
public sealed record PixelFrame(byte[] Pixels, string Text, string Identity, bool Scrolling = false, int LyricPart = 0);
public sealed record StudioState(string Status, Track Track, Snapshot Snapshot, PixelFrame? Frame,
    long Frames, long Dropped, long Writes, string Codec, int EncodedBytes, double FrameSeconds,
    double CpuPercent, double MemoryMB, double Peak, string TemperatureStatus, bool Connected,
    string DemoStage = "", double DemoProgress = 0, string ScreenColor = "#86D8F6", string AudioDetail = "", bool OfficialColor = false, string TelemetryStatus = "", bool TelemetryActive = false, bool TelemetryDemo = false);

public static class Files
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };
    public static void Save<T>(string path, T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string tmp = path + ".tmp"; File.WriteAllText(tmp, JsonSerializer.Serialize(value, Json)); File.Move(tmp, path, true);
    }
    public static T? Load<T>(string path) { try { return JsonSerializer.Deserialize<T>(File.ReadAllText(path), Json); } catch { return default; } }
}
