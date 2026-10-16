using System.Text.Json;

namespace HaloStudio;

internal static class Program
{
    static DeviceOwner? owner;
    public static void ReleaseOwner() { owner?.Dispose(); owner = null; }
    [STAThread]
    static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize(); string Arg(string name, string fallback) { int i = Array.IndexOf(args, name); return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback; }
        string runtime = Path.GetFullPath(Arg("--runtime", Path.Combine(AppContext.BaseDirectory, "runtime"))); Directory.CreateDirectory(runtime);
        try
        {
            if (args.Contains("--install-thermal-task")) { ThermalTask.Install(); return 0; }
            if (args.Contains("--network-probe")) { Task.Run(async () => { var network = new NetworkSampler(); var rows = new List<object>(); for (int i = 0; i < 6; i++) { rows.Add(new { At = i, Rate = network.Read(), Adapters = NetworkSampler.Enumerate() }); await Task.Delay(1000); } Files.Save(Arg("--output", Path.Combine(runtime, "network-probe.json")), rows); }).GetAwaiter().GetResult(); return 0; }
            if (args.Contains("--temperature-probe")) { Task.Run(() => TemperatureDiagnostic.Run(Arg("--output", Path.Combine(runtime, "temperature-probe.json")))).GetAwaiter().GetResult(); return 0; }
            Designs.Reload(Path.GetFullPath(Arg("--themes", Path.Combine(AppContext.BaseDirectory, "themes"))));
            if (ScreenPalette.Reload(Path.Combine(AppContext.BaseDirectory, "palettes", "pixelbar.json")) is string paletteError) File.WriteAllText(Path.Combine(runtime, "palette-warning.txt"), paletteError);
            if (args.Contains("--self-test")) { SelfTests.Run(Arg("--output", Path.Combine(runtime, "self-test.json")), Arg("--fixtures", "")); return 0; }
            if (args.Contains("--lyrics-probe")) { Task.Run(() => LyricDiagnostic.Run(runtime, Arg("--output", Path.Combine(runtime, "lyric-probe.json")), int.Parse(Arg("--seconds", "30")))).GetAwaiter().GetResult(); return 0; }
            if (args.Contains("--probe")) { Files.Save(Arg("--output", Path.Combine(runtime, "probe.json")), HidTransport.Enumerate()); return 0; }
            if (args.Contains("--color-commission")) { if(!args.Contains("--after-observed-reboot")) throw new InvalidOperationException("需先确认音响已重启"); ColorCommissioning.Run(runtime,Arg("--live-folder",""),args.Contains("--timeout-release")).GetAwaiter().GetResult(); return 0; }
            if (args.Contains("--color-test")) { ScreenColorDiagnostic.Run(runtime, Arg("--output", Path.Combine(runtime,"screen-colors.json")), hues: args.Contains("--hues")).GetAwaiter().GetResult(); return 0; }
            if (args.Contains("--white-test")) { ScreenColorDiagnostic.Run(runtime, Arg("--output", Path.Combine(runtime,"white-calibration.json")), true, args.Contains("--warmer"), args.Contains("--compare"), args.Contains("--calibrated")).GetAwaiter().GetResult(); return 0; }
            if (args.Contains("--transport-probe")) { using var probeOwner = new DeviceOwner(); probeOwner.Acquire(); var devices = HidTransport.Enumerate(); if (devices.Count != 1) throw new IOException("请仅连接一台 PixelBar"); var hid = new HidTransport(devices[0]); try { var version = hid.QueryAsync(0xC6, []).GetAwaiter().GetResult(); Files.Save(Arg("--output", Path.Combine(runtime, "transport-probe.json")), new { Version = Convert.ToHexString(version), Writes = hid.Writes, Command = "C6 read-only version", DisplayAcquired = false }); } finally { hid.DisposeAsync().AsTask().GetAwaiter().GetResult(); } return 0; }
            if (args.Contains("--owner-probe")) { bool available = false; string message = ""; using var test = new DeviceOwner(); try { test.Acquire(); available = true; } catch (IOException e) { message = e.Message; } Files.Save(Arg("--output", Path.Combine(runtime, "owner-probe.json")), new { Available = available, Message = message }); return 0; }
            if (args.Contains("--diagnostics")) { using var hardware = new Hardware(); using var peaks = new MusicPeak(); using var media = new MediaMonitor(); peaks.Read(); var track = media.PollAsync(peaks.Playing).GetAwaiter().GetResult(); var sensors = hardware.SampleAsync([]).GetAwaiter().GetResult(); Files.Save(Arg("--output", Path.Combine(runtime, "diagnostics.json")), new { Track = track, Snapshot = sensors, Peak = peaks.Read(), AudioDetail = peaks.Detail, AudioPlaying = peaks.Playing, Devices = HidTransport.Enumerate() }); return 0; }
            bool preview = args.Contains("--preview"); if (!preview) { owner = new(); owner.Acquire(); }
            var engine = new Engine(runtime); if (args.Contains("--demo")) engine.StartShowcase(); if (args.Contains("--enable-temperature") && !preview) engine.EnableTemperature(); var form = new StudioForm(engine, runtime, preview, args.Contains("--background"));
            if (int.TryParse(Arg("--ui-page", "0"), out int page)) form.ShowPage(page);
            if (int.TryParse(Arg("--ui-width", "0"), out int width) && width > 0) form.ClientSize = new(width, form.ClientSize.Height);
            System.Windows.Forms.Timer? closeTimer = null, screenshotTimer = null, sequenceTimer = null;
            Settings? savedSettings = null;
            if (args.Contains("--test-sequence"))
            {
                savedSettings = engine.Config; int step = 0; var keys = Designs.All.Keys.ToArray(); sequenceTimer = new() { Interval = 6000 };
                sequenceTimer.Tick += (_, _) =>
                {
                    if (step >= keys.Length + 2) { sequenceTimer.Stop(); return; }
                    var baseline = savedSettings;
                    form.ApplyTestSettings(baseline with { Theme = keys[Math.Min(step, keys.Length - 1)], Mode = step >= keys.Length ? "auto" : "idle", IdleContent = step % 2 == 0 ? "clock" : "monitor", MonitorView = step % 3 == 0 ? "dense" : "compact", Animations = true, Transitions = true }); step++;
                }; sequenceTimer.Start();
            }
            if (int.TryParse(Arg("--quit-after", "0"), out int seconds) && seconds > 0) { closeTimer = new() { Interval = seconds * 1000 }; closeTimer.Tick += async (_, _) => { closeTimer.Stop(); await form.QuitAsync(); }; closeTimer.Start(); }
            string screenshot = Arg("--ui-snapshot", ""); if (screenshot.Length > 0) { screenshotTimer = new() { Interval = 3000 }; screenshotTimer.Tick += (_, _) => { screenshotTimer.Stop(); form.SaveScreenshot(screenshot); }; screenshotTimer.Start(); }
            string audit = Arg("--ui-audit", ""); if (preview && audit.Length > 0) { screenshotTimer = new() { Interval = 3500 }; screenshotTimer.Tick += (_, _) => { screenshotTimer.Stop(); form.AuditLayout(audit); }; screenshotTimer.Start(); }
            string inputs = Arg("--input-audit", ""); if (preview && inputs.Length > 0) { screenshotTimer = new() { Interval = 1500 }; screenshotTimer.Tick += (_, _) => { screenshotTimer.Stop(); form.AuditInputs(inputs); }; screenshotTimer.Start(); }
            string readme = Arg("--readme-shots", ""); if (preview && readme.Length > 0) { screenshotTimer = new() { Interval = 2000 }; screenshotTimer.Tick += (_, _) => { screenshotTimer.Stop(); form.CaptureReadme(readme); }; screenshotTimer.Start(); }
            if (preview && args.Contains("--background-audit"))
            {
                bool everVisible = false, shown = false; form.VisibleChanged += (_, _) => everVisible |= form.Visible; form.Shown += (_, _) => shown = true;
                screenshotTimer = new() { Interval = 2000 };
                screenshotTimer.Tick += async (_, _) => { screenshotTimer.Stop(); Files.Save(Arg("--output", Path.Combine(runtime, "background-audit.json")), new { Passed = !everVisible && !shown && !form.Visible && !form.ShowInTaskbar && form.WorkerStarted, EverVisible = everVisible, Shown = shown, form.Visible, form.ShowInTaskbar, form.WorkerStarted }); await form.QuitAsync(); }; screenshotTimer.Start();
            }
            Application.Run(form); closeTimer?.Dispose(); screenshotTimer?.Dispose(); sequenceTimer?.Dispose(); if (savedSettings != null) engine.Configure(savedSettings); ReleaseOwner(); return 0;
        }
        catch (Exception e) { File.WriteAllText(Path.Combine(runtime, "last-error.txt"), e.ToString()); ReleaseOwner(); if (!args.Any(a => a is "--install-thermal-task" or "--temperature-probe" or "--self-test" or "--lyrics-probe" or "--probe" or "--diagnostics" or "--transport-probe" or "--color-test" or "--white-test" or "--color-commission" or "--owner-probe")) MessageBox.Show(e.Message, "HaloStudio C#"); return 1; }
    }
}
