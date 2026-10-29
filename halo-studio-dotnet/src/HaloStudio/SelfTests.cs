using System.Text.Json;
using System.Security.Cryptography;

namespace HaloStudio;

public static class SelfTests
{
    public static void Run(string output, string fixturePath)
    {
        var checks = new List<string>(); void Assert(bool value, string name) { if (!value) throw new Exception("验证失败: " + name); checks.Add(name); }
        TelemetryTests.Run(Assert, Path.GetDirectoryName(output)!);
        MonitorRegressionTests.Run(Assert, Path.GetDirectoryName(output)!);
        Assert(Protocol.Crc("123456789"u8) == 0x31C3, "CRC16-CCITT independent vector");
        var random = new Random(12345); for (int n = 0; n < 40; n++) { byte[] pixels = new byte[1024]; random.NextBytes(pixels); if (n % 2 == 0) for (int i = 0; i < 700; i++) pixels[i] = 0; Assert(Protocol.Unrle(Protocol.Rle(pixels)).AsSpan().SequenceEqual(pixels), "RLE random / sparse " + n); }
        Assert(Protocol.Rle(new byte[1024]).Length == 16, "Zero frame compresses to 16 bytes");
        try { Protocol.Unrle([128]); throw new Exception("Malformed accepted"); } catch (InvalidDataException) { checks.Add("Truncated RLE rejected"); }
        byte[] raw = new byte[1024]; random.NextBytes(raw); byte[] target = (byte[])raw.Clone(); target[0] ^= 3; var delta = Protocol.Choose(target, raw, 41); Assert(delta.Codec == 2 && delta.BaseId == 41, "XOR uses acknowledged base");
        Assert(Protocol.Choose(target, null, 0).Codec != 2, "Fresh keyframe independent"); var fragments = Protocol.Fragments(123, 42, target, delta, true, 1).ToArray(); Assert(fragments[0][8] == 6 && fragments[0][17] == 2 && fragments[0][18] == 1, "Codec BEGIN animation metadata");
        foreach (var p in fragments) { var packet = Protocol.Packet(0x17, p); Assert(packet.Length == 64 && p.Length <= 54, "HID framing bounded"); }
        if (fixturePath.Length > 0) { using var doc = JsonDocument.Parse(File.ReadAllText(fixturePath)); int i = 0; foreach (var e in doc.RootElement.EnumerateArray()) { byte[] frame = Convert.FromHexString(e.GetProperty("pixels").GetString()!); byte[]? basis = e.TryGetProperty("base", out var b) ? Convert.FromHexString(b.GetString()!) : null; ushort id = (ushort)e.GetProperty("base_id").GetInt32(); var plan = Protocol.Choose(frame, basis, id); Assert(plan.Codec == e.GetProperty("codec").GetByte() && Convert.ToHexString(plan.Data).Equals(e.GetProperty("data").GetString(), StringComparison.OrdinalIgnoreCase) && plan.TargetCrc == e.GetProperty("crc").GetInt32(), "Python validated codec oracle " + i++); } }
        var lrc = LyricsStore.Parse("[offset:-200]\n[00:01.20]中文歌词\n[00:01.20]translation\n[00:03.000][00:04.0]下一句"); Assert(lrc.Count == 3 && lrc[0].Time == 1 && lrc[0].Text == "中文歌词", "LRC timing / offset / original language"); Assert(LyricsStore.At(lrc, 3, 5) == "下一句", "LRC next sentence"); LyricTests.Run(Assert);
        Assert(Math.Abs(Expression.Evaluate("clamp(phase*2,0,7)+round(cos(pi)*3)", new Dictionary<string, double> { { "phase", 5 } }) - 4) < .001, "Theme arithmetic parser");
        string originalThemes = Designs.DirectoryPath; string testThemes = Path.Combine(Path.GetDirectoryName(output)!, "test-themes"); Directory.CreateDirectory(testThemes);
        string paper = File.ReadAllText(Path.Combine(originalThemes, "paper.json")); File.WriteAllText(Path.Combine(testThemes, "new.json"), paper.Replace("\"paper\"", "\"custom_new\"").Replace("月白书页", "自定义书页"));
        Designs.Reload(testThemes); Assert(Designs.All.ContainsKey("custom_new"), "New external theme loads without compilation");
        var custom = Designs.Render("12:34", "时钟", new Settings { Theme = "custom_new" }, 0, Snapshot.Empty, DateTime.Now); Assert(custom.Pixels.Any(x => x != 0), "New external theme paints independently");
        File.WriteAllText(Path.Combine(testThemes, "bad.json"), "{\"version\":1}"); Assert(Designs.Reload(testThemes).Length == 1 && Designs.All.ContainsKey("custom_new"), "Malformed theme isolated"); Designs.Reload(originalThemes);
        try { Expression.Evaluate("Process.Start('cmd')", new Dictionary<string, double>()); throw new Exception("Theme executable accepted"); } catch (InvalidDataException) { checks.Add("Executable theme expression rejected"); }
        var metrics = new Snapshot([new("cpu", "CPU", "CPU", 6, "%", "test", 100) { History = [1, 2, 3, 6] }, new("ram", "RAM", "RAM", 57, "%", "test", 100), new("ram_gb", "RAM", "RAM", 11.48, "GB", "test"), new("cpu_temp", "CPU", "CPU", 54, "C", "test", 100), new("gpu0", "GPU", "GPU", 4, "%", "test", 100), new("gpu0_temp", "GPU", "GPU", 51, "C", "test", 100), new("upload", "UP", "UP", 1280, "B/s", "test"), new("download", "DN", "DN", 1147, "B/s", "test")], "test");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!); string atlas = Path.Combine(Path.GetDirectoryName(output)!, "theme-atlas.png"); using var image = new Bitmap(1024, Designs.All.Count * 424); using var g = Graphics.FromImage(image); g.Clear(Color.FromArgb(14, 19, 28)); int row = 0;
        foreach (var (key, design) in Designs.All)
        {
            int y = row++ * 424; using var labelFont = new Font("Microsoft YaHei UI", 12); g.DrawString(design.Name, labelFont, Brushes.White, 0, y); int column = 0; foreach (string mode in new[] { "时钟", "系统监控", "歌词" })
            {
                string text = mode == "时钟" ? "12:34:56" : mode == "歌词" ? "让每个像素都有温度" : ""; var s = new Settings { Theme = key, Animations = true, Seconds = true, MonitorView = "dense" }; var f = Designs.Render(text, mode, s, 4, metrics, new(2026, 10, 13, 12, 34, 56)); Assert(f.Pixels.Length == 1024 && f.Pixels.Any(v => v != 0), key + " " + mode + " full scene"); var canvas = new PixelCanvas(); f.Pixels.CopyTo(canvas.Data, 0); using var preview = canvas.Bitmap(ColorTranslator.FromHtml(design.Color), 4); g.DrawImageUnscaled(preview, 0, y + 24 + column++ * 132);
            }
            foreach (string view in new[] { "value", "bar", "graph", "compact" }) { var f = Designs.Render("", "系统监控", new Settings { Theme = key, MonitorView = view }, 4, metrics, DateTime.Now); Assert(f.Pixels.Any(v => v != 0), key + " monitor " + view); }
        }
        var pairing = new Settings { Theme = "paper", MonitorView = "compact", MonitorMetrics = ["cpu", "ram", "upload", "gpu0", "cpu_temp", "download", "ram_gb", "gpu0_temp"], RotationSeconds = 5, MonitorRotate = true, PixelTransition = "wipe" };
        string[][] expectedPairs = [["cpu", "cpu_temp"], ["ram_gb", "ram"], ["upload", "download"], ["gpu0", "gpu0_temp"]];
        for (int i = 0; i < 5; i++)
        {
            var keys = expectedPairs[i % 4]; var actual = Designs.Render("", "系统监控", pairing, i * 5, metrics, new(2026,10,13));
            var expected = Designs.Render("", "系统监控", pairing with { MonitorMetrics = keys, MonitorRotate = false }, 0, metrics, new(2026,10,13));
            Assert(actual.Pixels.AsSpan().SequenceEqual(expected.Pixels) && actual.Identity.EndsWith(string.Join("+", keys)), "Pair rotation groups same-family metrics and advances both " + i);
        }
        var solo = MonitorPairing.Pages([metrics.Get("cpu"), metrics.Get("ram"), metrics.Get("upload"), metrics.Get("download")]);
        Assert(solo.Length == 2 && solo[0].Select(m => m.Key).SequenceEqual(new[] { "upload", "download" }) && solo[1].Select(m => m.Key).SequenceEqual(new[] { "cpu", "ram" }), "Same-family pairs first; CPU and RAM leftovers share one page");
        var priority = MonitorPairing.Pages([metrics.Get("cpu"), new("frequency", "CPU 频率", "CPU", 4, "GHz", "test"), metrics.Get("cpu_temp"), metrics.Get("ram")]);
        Assert(priority[0].Select(m => m.Key).SequenceEqual(new[] { "cpu", "cpu_temp" }) && priority[1].Select(m => m.Key).SequenceEqual(new[] { "frequency", "ram" }), "CPU temperature pairs ahead of frequency; remaining frequency and RAM pair");
        var devices = MonitorPairing.Pages([metrics.Get("gpu0"), new("gpu1", "GPU 2", "GPU2", 5, "%", "test"), metrics.Get("gpu0_temp"), new("gpu1_temp", "GPU 2 温度", "GPU2", 50, "C", "test")]);
        Assert(devices[0].All(m => m.Key.StartsWith("gpu0")) && devices[1].All(m => m.Key.StartsWith("gpu1")), "Complete same-device GPU pairs take priority over fallback pairing");
        Assert(MonitorPairing.Pages([]).Length == 0 && MonitorPairing.Pages([metrics.Get("cpu")])[0].Length == 1, "Empty and single metric selections are safe");
        var disk = new Metric("disk_read", "磁盘读取", "DISK", 1000, "B/s", "test");
        var nearest = MonitorPairing.Pages([metrics.Get("cpu"), disk, metrics.Get("upload")]);
        Assert(nearest.Length == 2 && nearest[0].Select(m => m.Key).SequenceEqual(new[] { "disk_read", "upload" }) && nearest[1][0].Key == "cpu", "Closest leftover categories pair first; odd singleton is last");
        var tied = MonitorPairing.Pages([metrics.Get("gpu0"), metrics.Get("ram"), metrics.Get("cpu")]);
        Assert(tied[0].Select(m => m.Key).SequenceEqual(new[] { "cpu", "ram" }) && tied[1][0].Key == "gpu0", "Equal distances use fixed category priority, not click order");
        var fourSingles = MonitorPairing.Pages([metrics.Get("upload"), metrics.Get("cpu"), disk, metrics.Get("gpu0")]);
        Assert(fourSingles.Length == 2 && fourSingles.All(p => p.Length == 2) && fourSingles[0].Select(m => m.Key).SequenceEqual(new[] { "gpu0", "disk_read" }), "Even leftover count always produces complete closest pairs");
        string PairKeys(Metric[][] pages) => string.Join("|", pages.Select(p => string.Join("+", p.Select(m => m.Key))));
        var pool = metrics.Metrics.Concat(new[] { disk, new Metric("fan", "风扇", "FAN", 900, "RPM", "test"), new Metric("other", "其他", "OTHER", null, "W", "test") }).ToArray();
        bool parity = true, exactMetrics = true, stableFallback = true;
        for (int mask = 0; mask < 1 << pool.Length; mask++)
        {
            var selection = pool.Where((_, i) => (mask & (1 << i)) != 0).ToArray();
            var groups = MonitorPairing.Pages(selection);
            parity &= groups.Length == (selection.Length + 1) / 2 && groups.Count(p => p.Length == 1) == selection.Length % 2 && groups.Take(Math.Max(0, groups.Length - 1)).All(p => p.Length == 2);
            exactMetrics &= groups.SelectMany(p => p).Select(m => m.Key).Order().SequenceEqual(selection.Select(m => m.Key).Order());
            stableFallback &= PairKeys(groups) == PairKeys(MonitorPairing.Pages(selection.Select(m => m with { Value = null, History = [] })));
        }
        Assert(parity, "All 2048 metric subsets have at most one final singleton, only for odd totals");
        Assert(exactMetrics, "All 2048 metric subsets preserve each selected sensor exactly once");
        Assert(stableFallback && PairKeys(nearest) == PairKeys(MonitorPairing.Pages([metrics.Get("upload"), disk, metrics.Get("cpu")])), "Fallback pairing stays stable across reading changes and selection order");
        Assert(PairKeys(MonitorPairing.Pages([metrics.Get("cpu"), metrics.Get("cpu"), metrics.Get("ram")])) == "cpu+ram", "Duplicate selections do not create duplicate cards or false odd totals");
        var fallbackSettings = pairing with { MonitorMetrics = ["cpu", "ram", "upload", "download"] };
        var fallbackFrame = Designs.Render("", "系统监控", fallbackSettings, 5, metrics, new(2026,10,13));
        var fallbackExpected = Designs.Render("", "系统监控", pairing with { MonitorMetrics = ["cpu", "ram"], MonitorRotate = false }, 0, metrics, new(2026,10,13));
        Assert(fallbackFrame.Identity.EndsWith("cpu+ram") && fallbackFrame.Pixels.AsSpan().SequenceEqual(fallbackExpected.Pixels), "Fallback pairs render both cards together during whole-pair rotation");
        var absentFrame = Designs.Render("", "系统监控", pairing with { MonitorMetrics = ["cpu", "gpu0_temp"], MonitorRotate = false }, 0, new Snapshot([metrics.Get("cpu")], "temporarily missing GPU"), new(2026,10,13));
        Assert(absentFrame.Identity.EndsWith("cpu+gpu0_temp") && absentFrame.Text.Contains("--"), "Temporarily absent selected sensor keeps its slot and does not change parity");
        var singleStep = Designs.Render("", "系统监控", pairing with { PairAdvance = "single" }, 5, metrics, new(2026,10,13));
        Assert(singleStep.Identity.EndsWith("cpu_temp+ram_gb"), "Horizontal single mode shifts one metric in grouped order");
        var wholeUp = Designs.Render("", "系统监控", pairing with { PairAdvance = "single", PixelTransition = "up" }, 5, metrics, new(2026,10,13));
        Assert(wholeUp.Identity.EndsWith("ram_gb+ram"), "Up transition retains paired pages");
        Assert(new Settings { PairAdvance = "invalid" }.Validated().PairAdvance == "pair" && JsonSerializer.Deserialize<Settings>(JsonSerializer.Serialize(pairing with { PairAdvance = "single" }, Files.Json), Files.Json)!.PairAdvance == "single", "Pair advance setting default and persistence");
        image.Save(atlas); var temp = new PixelCanvas(); temp.Raster("54°C", 0, 0); Assert(temp.IsOn(13, 0) && temp.IsOn(12, 1) && temp.IsOn(14, 1) && temp.IsOn(13, 2), "Compact 3x3 degree ring");
        var envelope = new Envelope(); var levels = new List<double>(); for (int i = 0; i < 100; i++) levels.Add(envelope.Update(.3 + .1 * Math.Sin(i * .3), i * .05)); Assert(levels.Max() - levels.Min() > .3, "Fixed-volume musical dynamics retained");
        var oldCanvas = new PixelCanvas(); oldCanvas.Dot(0, 20); oldCanvas.Dot(255, 29); var newCanvas = new PixelCanvas(); newCanvas.Dot(0, 3); newCanvas.Dot(255, 7);
        var oldMonitor = new PixelFrame(oldCanvas.Data, "CPU", "系统监控:matrix:cpu"); var newMonitor = new PixelFrame(newCanvas.Data, "RAM", "系统监控:matrix:ram");
        Assert(!Transitions.NativeCompatible(oldMonitor, newMonitor), "Full-width monitor never uses 200x24 MCU viewport");
        var half = Transitions.Compose(oldMonitor, newMonitor, 1, .5); var halfCanvas = new PixelCanvas(); half.Pixels.CopyTo(halfCanvas.Data, 0);
        Assert(halfCanvas.IsOn(0, 4) && halfCanvas.IsOn(255, 13) && halfCanvas.IsOn(0, 19) && halfCanvas.IsOn(255, 23) && !halfCanvas.IsOn(0, 20), "Up transition moves both screen edges with the content");
        Assert(Transitions.Compose(oldMonitor, newMonitor, 1, 1) == newMonitor, "Transition finishes at exact target");
        Assert(!Transitions.NativeCompatible(oldMonitor with { Identity = "歌词:a" }, newMonitor with { Identity = "歌词:b" }), "Lyric decoration changes outside native viewport use whole frame");
        var inner = new PixelCanvas(); inner.Dot(100, 12);
        Assert(Transitions.NativeCompatible(new(new byte[1024], "", "歌词:a"), new(inner.Data, "", "歌词:b")), "Safe lyric viewport retains MCU animation");
        Assert(RamController.Capabilities(Protocol.FullscreenSha) == (true, true, false, false), "Whole-screen MCU instructions gated by exact new firmware SHA");
        Assert(RamController.Capabilities(Protocol.MatrixSha) == (true, true, true, false), "Local character rain gated by exact MCU firmware SHA");
        Assert(RamController.Capabilities(Protocol.ColorSha) == (true, true, true, true), "Atomic RGB and expanded transitions require exact validated color firmware");
        Assert(RamController.Capabilities(Protocol.FirmwareSha) == (true, false, false, false) && RamController.Capabilities(Protocol.LegacySha) == (false, false, false, false), "Previous MCU revisions retain their original capabilities");
        var rainBegin = Protocol.Fragments(123, 1, target, delta, true, 5, 32).Peek();
        Assert(rainBegin[18] == 5 && rainBegin[19] == 32, "Character rain carries local animation ID and 32ms tick interval");
        try { RamController.Capabilities(new string('0', 64)); throw new Exception("Unknown firmware accepted"); } catch (InvalidOperationException) { checks.Add("Unknown MCU installation rejected"); }
        Assert(NetEaseNative.Profile(1787745734, 40951808).Rva == 35641104 && NetEaseNative.Profile(1791636812, 41054208).Rva == 35736240, "Exact NetEase 3.1.39 and 3.1.41 module profiles");
        Assert(NetEaseNative.Profile(1791636812, 41054209).Rva == 0, "Unknown NetEase module never reuses an old pointer");
        foreach (string effect in new[] { "matrix", "warp", "wave", "title", "outro" }) { var demo = Showcase.Render(new(effect, effect, 5), new(), 2); Assert(demo.Frame.Pixels.Length == 1024 && demo.Frame.Pixels.Any(v => v != 0), "Showcase " + effect + " has bounded pixels"); }
        var demoFile = Path.Combine(AppContext.BaseDirectory, "demos", "showcase.json"); if (File.Exists(demoFile)) { var show = new Showcase(demoFile); Assert(show.Duration is >= 50 and <= 90 && show.Poll(new()) != null, "External showcase loads and starts at opening scene"); }
        var tinted = new Settings { Theme = "kitty", ThemeColors = new() { ["kitty"] = "#ffacca", ["matrix"] = "#75FF92", ["invalid"] = "not a color" } }.Validated();
        Assert(tinted.ScreenColor() == "#FFACCA" && tinted.ScreenColor("matrix") == "#75FF92" && !tinted.ThemeColors.ContainsKey("invalid"), "Per-theme colors validated and isolated");
        var roundtrip = System.Text.Json.JsonSerializer.Deserialize<Settings>(System.Text.Json.JsonSerializer.Serialize(tinted, Files.Json), Files.Json)!;
        Assert(roundtrip.ScreenColor() == "#FFACCA" && (tinted with { ThemeColors = [] }).ScreenColor() == Designs.All["kitty"].Color, "Theme color persistence and factory reset");
        Assert(Showcase.Render(new("theme", "demo", 5, "kitty"), tinted, 0).Color == "#FFACCA", "Showcase respects saved theme color");
        var whiteCal = (tinted with { ThemeColors = new() { ["kitty"] = "#FFFFFF" }, ScreenWhiteBlue = 96 }).Validated();
        Assert(whiteCal.ScreenColor() == "#FFFFFF" && whiteCal.DeviceScreenColor() == "#FFFF60" && whiteCal.DeviceScreenColor("#ffffff") == "#FFFF60", "White calibration changes wire RGB while preview remains white");
        Assert(whiteCal.DeviceScreenColor("#FF4080") == "#FF4080" && whiteCal.DeviceScreenColor("#808080") == "#808080", "White correction leaves other colors and gray unchanged");
        Assert(Protocol.ScreenColor(whiteCal.DeviceScreenColor()).AsSpan(1, 3).SequenceEqual(new byte[] { 255, 255, 96 }) && whiteCal.AmbientColor == tinted.AmbientColor && whiteCal.Brightness == tinted.Brightness, "White wire command only reduces blue without changing light brightness");
        Assert(new Settings().DeviceScreenColor("#FFFFFF") == "#FFFFFF" && (whiteCal with { ScreenWhiteBlue = -20 }).Validated().ScreenWhiteBlue == 0 && (whiteCal with { ScreenWhiteBlue = 300 }).Validated().ScreenWhiteBlue == 255, "White calibration defaults and bounds are safe");
        Assert(JsonSerializer.Deserialize<Settings>(JsonSerializer.Serialize(whiteCal, Files.Json), Files.Json)!.DeviceScreenColor() == "#FFFF60", "White calibration persists across app restart");
        var colorSettings = new Settings { Theme = "amber", ScreenWhiteBlue = 144 };
        Assert(ScreenPalette.All.Count >= 6 && ScreenPalette.Preview("#ff6000") == "#C7A34A", "External palette resolves amber appearance case-insensitively");
        Assert(colorSettings.ScreenColor() == "#FF6000" && colorSettings.DeviceScreenColor() == "#FF6000" && Protocol.ScreenColor(colorSettings.DeviceScreenColor()).AsSpan(1, 3).SequenceEqual(new byte[] { 255, 96, 0 }), "Amber preview correction preserves exact original USB bytes");
        Assert(colorSettings.DeviceScreenColor("#FFFFFF") == "#FFFF90" && ScreenPalette.Preview("#FFFFFF") == "#FFFFFF", "Confirmed white 144 stays separate from appearance palette");
        Assert(colorSettings.ScreenColor("matrix") == "#60FF30" && colorSettings.ScreenColor("peach") == "#FF6048", "Observed G1 and P2 calibration is loaded by radar and peach themes");
        Assert(Designs.All["peach"].Transition=="dissolve" && Transitions.ThemeStyle("peach")==7 && Transitions.ThemeStyle("matrix")==6, "External theme transition selects local dissolve or center reveal");
        Assert((colorSettings with { PixelTransition="dissolve" }).Validated().PixelTransition=="dissolve" && (colorSettings with { PixelTransition="invalid" }).Validated().PixelTransition=="up", "Transition choices validated without changing animation enable switch");
        Assert(ScreenPalette.Preview("#123456") == "#123456" && ScreenPalette.Description("#123456").StartsWith("未校准"), "Unknown colors are explicitly uncalibrated, never interpolated");
        foreach (var entry in ScreenPalette.All.Values)
        {
            var selectedColor = (colorSettings with { ThemeColors = new() { [colorSettings.Theme] = entry.Input } }).Validated();
            Assert(selectedColor.ScreenColor() == entry.Input && selectedColor.DeviceScreenColor() == (entry.Input == "#FFFFFF" ? "#FFFF90" : entry.Input), "Palette selection keeps device RGB for " + entry.Name);
        }
        string palettePath = ScreenPalette.FilePath, badPalette = Path.Combine(Path.GetDirectoryName(output)!, "invalid-palette.json");
        var paletteBefore = ScreenPalette.All; File.WriteAllText(badPalette, "{\"version\":1,\"colors\":[{\"input\":\"#FF6000\",\"preview\":\"bad\"}]}");
        Assert(ScreenPalette.Reload(badPalette) != null && ReferenceEquals(ScreenPalette.All, paletteBefore), "Invalid palette is rejected atomically without losing known colors");
        Assert(ScreenPalette.Reload(palettePath) == null && ScreenPalette.All["#FF4080"].Name == "桃紫", "Palette reload restores external appearance metadata");
        Assert(ScreenPalette.Official.Count == 30 && ScreenPalette.Official["#00FF74"].Name == "官方翠绿" && ScreenPalette.Official["#FF9455"].Preview == "#FF9455", "TempoHub thirty presets retain official RGB and separate names");
        var officialWhite = (whiteCal with { ThemeOfficialColors = new() { [whiteCal.Theme] = true } }).Validated();
        Assert(officialWhite.OfficialScreenColor() && officialWhite.DeviceScreenColor() == "#FFFFFF" && whiteCal.DeviceScreenColor() == "#FFFF60", "Official white bypasses calibration without changing saved calibrated white");
        Assert(JsonSerializer.Deserialize<Settings>(JsonSerializer.Serialize(officialWhite, Files.Json), Files.Json)!.DeviceScreenColor() == "#FFFFFF", "Official origin survives settings roundtrip");
        Assert(!(officialWhite with { ThemeColors = [] }).Validated().OfficialScreenColor(), "Removing a custom color removes orphaned official origin");
        Assert(!(officialWhite with { Themes = false }).OfficialScreenColor(), "Disabled themes do not apply a theme's official origin to the global color");
        Assert(officialWhite.DeviceScreenColor("#FFFFFF", false) == "#FFFF60" && whiteCal.DeviceScreenColor("#FFFFFF", true) == "#FFFFFF", "Demo color origin explicitly overrides the selected theme");
        foreach (var entry in ScreenPalette.Official.Values)
        {
            var chosen = (officialWhite with { ThemeColors = new() { [officialWhite.Theme] = entry.Input } }).Validated();
            Assert(chosen.DeviceScreenColor() == entry.Input && Protocol.ScreenColor(chosen.DeviceScreenColor()).AsSpan(1, 3).SequenceEqual(Protocol.Rgb(entry.Input)), "Official preset preserves USB RGB: " + entry.Name);
        }
        var demoSettings = officialWhite with { Theme = "ion", ThemeColors = new() { ["paper"] = "#FFFFFF" }, ThemeOfficialColors = new() { ["paper"] = true } };
        var officialDemo = Showcase.Render(new("theme", "official white", 5, "paper"), demoSettings, 0);
        Assert(officialDemo.OfficialColor && demoSettings.DeviceScreenColor(officialDemo.Color, officialDemo.OfficialColor) == "#FFFFFF", "Showcase uses each stage's origin instead of active theme origin");
        Assert(!Showcase.Render(new("title", "title", 5), demoSettings, 0).OfficialColor, "Fixed demo effect colors keep legacy calibration semantics");
        var officialBefore = ScreenPalette.Official;
        File.WriteAllText(badPalette, "{\"version\":1,\"colors\":[{\"input\":\"#FF6000\",\"preview\":\"#C7A34A\",\"name\":\"ok\",\"observation\":\"ok\",\"quick\":true}],\"official_colors\":[{\"input\":\"broken\",\"name\":\"bad\"}]}");
        Assert(ScreenPalette.Reload(badPalette) != null && ReferenceEquals(officialBefore, ScreenPalette.Official), "Malformed official palette cannot replace either loaded group");
        Assert(ScreenPalette.Reload(palettePath) == null, "Restore full palette after rejected official metadata");
        StartupNetworkTests.Run(Assert); DeviceOwnerTests.Run(Assert);
        var freshTemperature = new Settings().Validated();
        Assert(!freshTemperature.CpuTemperatureEnabled && !freshTemperature.CpuTemperatureElevation && freshTemperature.CpuTemperatureOptIn == false, "First launch has no temperature collection or elevation opt-in");
        var legacyDefaultTemperature = JsonSerializer.Deserialize<Settings>("{\"cpu_temperature_enabled\":true,\"cpu_temperature_elevation\":false}", Files.Json)!.Validated();
        Assert(!legacyDefaultTemperature.CpuTemperatureEnabled, "Legacy enabled-by-default setting is not treated as explicit consent");
        var legacyAuthorizedTemperature = JsonSerializer.Deserialize<Settings>("{\"cpu_temperature_enabled\":true,\"cpu_temperature_elevation\":true}", Files.Json)!.Validated();
        Assert(legacyAuthorizedTemperature.CpuTemperatureEnabled && legacyAuthorizedTemperature.CpuTemperatureOptIn == true, "Legacy explicit authorization remains opted in");
        var enabledTemperature = freshTemperature.WithTemperatureChoice(true).Validated();
        Assert(enabledTemperature.CpuTemperatureEnabled && enabledTemperature.CpuTemperatureElevation && enabledTemperature.CpuTemperatureOptIn == true, "Explicit on action enables and records temperature consent");
        var restartedTemperature = JsonSerializer.Deserialize<Settings>(JsonSerializer.Serialize(enabledTemperature, Files.Json), Files.Json)!.Validated();
        Assert(restartedTemperature.CpuTemperatureEnabled && restartedTemperature.CpuTemperatureElevation, "Explicit temperature choice restores after restart");
        var disabledTemperature = restartedTemperature.WithTemperatureChoice(false).Validated();
        Assert(!disabledTemperature.CpuTemperatureEnabled && !disabledTemperature.CpuTemperatureElevation && disabledTemperature.CpuTemperatureOptIn == true, "Explicit off persists without retaining automatic elevation");
        Assert(!(enabledTemperature with { CpuTemperatureOptIn = false }).Validated().CpuTemperatureElevation, "False consent blocks stale elevation flag");
        using (var dormantTemperature = new CpuTemperature())
        {
            Assert(dormantTemperature.ReadAsync().GetAwaiter().GetResult() == null && dormantTemperature.Detail == "CPU 温度采集已关闭", "Default temperature read exits without probing a driver or spawning a helper");
            Assert(dormantTemperature.ReadAsync(false, true).GetAwaiter().GetResult() == null && dormantTemperature.Detail == "CPU 温度采集已关闭", "Disabled temperature blocks elevation request");
        }
        byte[] thermalSample = new byte[80]; "HALOTC02"u8.CopyTo(thermalSample);
        void Write32(int at, uint value) => System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(thermalSample.AsSpan(at), value);
        Write32(8, 2); Write32(12, 123); System.Buffers.Binary.BinaryPrimitives.WriteUInt64LittleEndian(thermalSample.AsSpan(24), 9000);
        Write32(32, 2); Write32(40, 432u << 21); Write32(44, 0x1a); Write32(56, 456); Write32(64, 1); Write32(68, 1); Write32(72, 1);
        System.Buffers.Binary.BinaryPrimitives.WriteSingleLittleEndian(thermalSample.AsSpan(52), 54);
        Assert(CpuTemperature.Decode(thermalSample, 123, 456, 9500) == 54, "Accept coherent fresh temperature even after previous 15ms window");
        Assert(CpuTemperature.Decode(thermalSample, 123, 456, 19001) == null && CpuTemperature.Decode(thermalSample, 123, 456, 8999) == null, "Reject expired or future temperature");
        Assert(CpuTemperature.Decode(thermalSample, 124, 456, 9500) == null && CpuTemperature.Decode(thermalSample, 123, 457, 9500) == null, "Reject wrong temperature IPC owner or helper");
        Write32(32, 3); Assert(CpuTemperature.Decode(thermalSample, 123, 456, 9500) == null, "Reject in-progress temperature write"); Write32(32, 4);
        Write32(36, 4); Assert(CpuTemperature.Decode(thermalSample, 123, 456, 9500) == null, "Permission error cannot masquerade as cached temperature"); Write32(36, 0);
        Write32(60, 1); Assert(CpuTemperature.Decode(thermalSample, 123, 456, 9500) == null, "Reject stopped temperature helper");
        using var appIcon = Branding.Icon(); using var logo = Branding.Logo(); Assert(appIcon.Width == 32 && logo.Width == 256, "Application and tray use embedded Halo branding");
        LyricTests.Cache(Assert, Path.Combine(Path.GetDirectoryName(output)!, "lyric-cache-" + Guid.NewGuid().ToString("N"))).GetAwaiter().GetResult();
        LyricTests.Atlas(Path.Combine(Path.GetDirectoryName(output)!, "lyric-endpoints.png"));
        Lifecycle().GetAwaiter().GetResult(); checks.Add("Exclusive acquire / heartbeat / CRC commit / release / stable stock clock");
        LiveColors().GetAwaiter().GetResult(); checks.Add("Color changes keep one lease, commit same-pixel tint, retain animation and restore on exit");
        Files.Save(output, new { Passed = true, Count = checks.Count, Checks = checks, Atlas = atlas, Time = DateTimeOffset.Now });
    }
    static async Task Lifecycle()
    {
        var mock = new MockDevice(); var controller = new RamController(mock, true, "#86D8F6", true); await controller.ConnectAsync(); if (!controller.Owned) throw new Exception("No acquire");
        using var stop = new CancellationTokenSource(); var pump = controller.PumpAsync(() => new Settings(), () => (null, false), stop.Token); byte[] data = new byte[1024]; data[0] = 3; controller.Offer(new(data, "one", "lyric:one"), "#86D8F6", 1, true);
        long deadline = Environment.TickCount64 + 1500; while (controller.Frames < 1 && Environment.TickCount64 < deadline) await Task.Delay(10); if (controller.Frames != 1 || !mock.Committed.AsSpan().SequenceEqual(data)) throw new Exception("Frame commit");
        if (controller.LastCommit is not { Identity: "lyric:one", LyricPart: 0 } || controller.LastCommit.At > Environment.TickCount64) throw new Exception("ACK receipt must identify the committed frame");
        byte[] second = new byte[1024]; second[255] = 255; controller.Offer(new(second, "two", "系统监控:matrix:ram"), "#86D8F6", 1, true);
        deadline = Environment.TickCount64 + 1600; while (controller.Frames < 2 && Environment.TickCount64 < deadline) await Task.Delay(10);
        if (controller.Frames != 2 || mock.LastAnimation != 3 || !mock.Committed.AsSpan().SequenceEqual(second)) throw new Exception("Fullscreen target must be one commit using MCU animation 3");
        mock.ForwardDelay = 1200;
        controller.Offer(new(data, "old tint", "color:old"), "#FFACCA", 0, true);
        await Task.Delay(400);
        controller.Offer(new(second, "latest tint", "color:latest"), "#EDF4FF", 0, true);
        deadline = Environment.TickCount64 + 8500; while (controller.Frames < 3 && Environment.TickCount64 < deadline) { if (pump.IsFaulted) await pump; await Task.Delay(20); }
        if (controller.Frames != 3 || !mock.Committed.AsSpan().SequenceEqual(second) || !mock.Rgb.AsSpan().SequenceEqual(Protocol.Rgb("#EDF4FF"))) throw new Exception("Deferred display color must settle before acquire; newest target replaces pending tint");
        await Task.Delay(550); stop.Cancel(); try { await pump; } catch (OperationCanceledException) { }
        await controller.ShutdownAsync(); if (mock.Owned || mock.HeartbeatCount == 0 || mock.ClockWrites < 2) throw new Exception("Lease lifecycle");
    }
    static async Task LiveColors()
    {
        var mock = new MockDevice(); await using var controller = new RamController(mock, true, "#60FF30", true, true, true); await controller.ConnectAsync();
        using var stop = new CancellationTokenSource(); var pump = controller.PumpAsync(() => new Settings(), () => (null,false), stop.Token);
        async Task Offer(byte[] pixels, string color, byte animation, int count)
        {
            controller.Offer(new(pixels,color,color), color, animation, true);
            long until=Environment.TickCount64+2500;
            while(controller.Frames<count && Environment.TickCount64<until) { if(pump.IsCompleted) await pump; await Task.Delay(10); }
            if(controller.Frames!=count || !mock.Rgb.AsSpan().SequenceEqual(Protocol.Rgb(color))) throw new Exception("Live color commit");
        }
        try
        {
            byte[] a=new byte[1024], b=new byte[1024]; a[0]=15; b[255]=255;
            int clocks=mock.ClockWrites;
            await Offer(a,"#60FF30",0,1); await Offer(b,"#FF6048",7,2);
            if(mock.LastAnimation!=7) throw new Exception("Dissolve lost");
            await Offer(b,"#FFFF90",6,3); // identical pixels must still submit new RGB
            if(mock.LastAnimation!=6 || mock.ClockWrites!=clocks || mock.AcquireCount!=1 || mock.ReleaseCount!=0) throw new Exception("Color switch released or restored stock clock");
            // Simulate the host's end of a long session; no reconnect at wrap.
            typeof(RamController).GetField("frame",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic)!.SetValue(controller,ushort.MaxValue);
            await Offer(a,"#FF6000",6,4);
            if(mock.LastFrame!=1 || mock.AcquireCount!=1 || mock.ReleaseCount!=0) throw new Exception("Sequence wrap released display");
        }
        finally { stop.Cancel(); try { await pump; } catch(OperationCanceledException) {} }
        await controller.ShutdownAsync();
        if(mock.Owned || mock.ReleaseCount!=1 || mock.HeartbeatCount==0) throw new Exception("Live color lifecycle");
    }
    sealed class MockDevice : IHaloTransport
    {
        public long Writes { get; private set; }
        public bool Owned; public byte LastAnimation; public int ClockWrites, HeartbeatCount; public byte[] Committed = new byte[1024]; readonly List<byte> chunks = []; int encodedSize; byte codec; ushort crc;
        public byte[] Rgb = [0x86, 0xD8, 0xF6]; public int ForwardDelay, AcquireCount, ReleaseCount; public ushort LastFrame; long pendingUntil; byte[]? frameRgb;
        public Task WriteAsync(byte command, byte[] payload, CancellationToken token = default) { Writes++; if (command == 0xEF) { if (Owned) throw new Exception("EF during lease"); if (payload[0] == 1) ClockWrites++; if (payload[0] == 3) { Rgb=payload[1..4]; pendingUntil=Environment.TickCount64+ForwardDelay; } } return Task.CompletedTask; }
        public async Task<byte[]> QueryAsync(byte command, byte[] payload, CancellationToken token = default)
        {
            await WriteAsync(command, payload, token); if (command == 0xC6) return [1, 3, 7]; if (command == 0xEE) return [1, .. Rgb, 0, 1, 0, 0];
            byte op = payload[8]; if (op == 1) { if (Environment.TickCount64 < pendingUntil) throw new Exception("Acquired before deferred color reached MCU"); Owned = true; AcquireCount++; } if (op == 2) { if (!Owned) throw new Exception("Heartbeat after release"); HeartbeatCount++; } if (op == 5) { Owned = false; ReleaseCount++; return [0, 5]; }
            if (op == 6) { chunks.Clear(); codec = payload[17]; LastAnimation = payload[18]; LastFrame=(ushort)(payload[13]*256+payload[14]); encodedSize = payload[21] * 256 + payload[22]; crc = (ushort)(payload[27] * 256 + payload[28]); frameRgb=payload[16]==15 ? payload[29..32] : null; }
            if (op == 7) { chunks.AddRange(payload[17..]); if (chunks.Count == encodedSize) { byte[] pixels = codec == 0 ? chunks.ToArray() : Protocol.Unrle(chunks.ToArray()); if (codec == 2) for (int i = 0; i < 1024; i++) pixels[i] ^= Committed[i]; if (Protocol.Crc(pixels) != crc) throw new Exception("CRC mismatch"); Committed = pixels; if(frameRgb!=null) Rgb=frameRgb; return [0, 5]; } }
            return [0, 3, 255, 255];
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
