using System.Diagnostics;

namespace HaloStudio;

public sealed class Engine : IAsyncDisposable
{
    readonly string runtime; Settings settings; int revision; readonly CancellationTokenSource stop = new(); CancellationTokenSource? session;
    readonly Hardware hardware = new(); readonly MediaMonitor media = new(); readonly MusicPeak peak = new(); readonly Envelope envelope = new(); readonly LyricsStore lyrics;
    readonly TelemetryReceiver telemetry = new(); TelemetrySprint? sprint;
    public bool TelemetryDemoRunning => Volatile.Read(ref sprint) != null;
    public void StartTelemetryDemo() { StopShowcase(); Volatile.Write(ref sprint,new TelemetrySprint()); Interlocked.Increment(ref revision); }
    public void StopTelemetryDemo() { Volatile.Write(ref sprint,null); Interlocked.Increment(ref revision); }
    Showcase? showcase; bool frameOfficial; string frameColor = "#86D8F6";
    public bool DemoRunning => Volatile.Read(ref showcase) != null;
    public void StartShowcase() { StopTelemetryDemo(); Volatile.Write(ref showcase, new Showcase(Path.Combine(AppContext.BaseDirectory, "demos", "showcase.json"))); Interlocked.Increment(ref revision); }
    public void StopShowcase() { Volatile.Write(ref showcase, null); Interlocked.Increment(ref revision); }
    RamController? controller; IHaloTransport? link; Task? runner; Track track = new(); Snapshot snapshot = Snapshot.Empty;
    PixelFrame? frame; double signal; string? rhythmColor; volatile bool rhythmActive; string status = "离线预览"; List<LyricLine> lines = []; string lyricSource = "等待网易云播放";
    readonly object logGate = new(); public event Action<StudioState>? Changed;
    readonly LyricPlayback lyricPlayback = new(); int lyricImportRevision;
    public Settings Config => Volatile.Read(ref settings);
    public bool Visible { get; set; } = true; public bool MonitorVisible { get; set; }
    public Track CurrentTrack => track; public string LastError { get; private set; } = "";
    public Engine(string directory) { runtime = directory; Directory.CreateDirectory(directory); settings = (Files.Load<Settings>(Path.Combine(runtime, "settings.json")) ?? new()).Validated(); lyrics = new(Path.Combine(runtime, "lyrics-cache")); }
    public void Configure(Settings value) { Volatile.Write(ref settings, value.Validated()); Interlocked.Increment(ref revision); Files.Save(Path.Combine(runtime, "settings.json"), Config); }
    public void RefreshThemes() => Interlocked.Increment(ref revision);
    public void Start(bool preview = false) => runner = Task.Run(() => RunAsync(preview));
    public void EnableTemperature() { Configure(Config.WithTemperatureChoice(true)); hardware.Temperature.RequestRetry(); }
    public void ImportLrc(string path) { lyrics.Save(track, File.ReadAllText(path), "本地 LRC"); Interlocked.Increment(ref lyricImportRevision); Interlocked.Increment(ref revision); }
    void Log(string message) { lock (logGate) { string path = Path.Combine(runtime, "studio-net.log"); if (File.Exists(path) && new FileInfo(path).Length > 2_000_000) File.Move(path, path + ".previous", true); File.AppendAllText(path, $"{DateTimeOffset.Now:O} {message}\n"); } }
    static bool TempoHubRunning() { var processes = Process.GetProcessesByName("Edifier TempoHub"); bool running = processes.Length > 0; foreach (var process in processes) process.Dispose(); return running; }
    async Task SessionAsync()
    {
        var devices = HidTransport.Enumerate(); if (devices.Count != 1) throw new IOException("请仅连接一台已验证的 Halo PixelBar");
        string record = Path.Combine(runtime, "mcu-installation.json"); if (!File.Exists(record)) throw new IOException("缺少 MCU 直绘验证记录，请在设备页导入");
        var capabilities = RamController.ValidateInstallation(record, devices[0]);
        if (TempoHubRunning()) throw new IOException("请先退出 Edifier TempoHub，避免同时控制音响");
        link = new HidTransport(devices[0]); controller = new(link, capabilities.Codec, Config.DeviceScreenColor(), capabilities.FullAnimation, capabilities.LocalRain, capabilities.LiveColor);
        try { status = "正在同步独占显示状态…"; await controller.ConnectAsync(stop.Token); await controller.ApplyAmbientAsync(Config); status = "USB RAM 直绘已连接"; Log("Connected " + devices[0].Serial); }
        catch { await CloseSessionAsync(); throw; }
        session = new(); var local = controller; _pump = local.PumpAsync(() => Config, () => (rhythmColor, rhythmActive), session.Token);
    }
    Task? _pump;
    async Task CloseSessionAsync()
    {
        if (session != null) { session.Cancel(); try { if (_pump != null) await _pump; } catch (OperationCanceledException) { } catch (Exception e) { Log("Pump stopped: " + e.Message); } session.Dispose(); session = null; _pump = null; }
        if (controller != null) { try { await controller.ShutdownAsync(); await controller.ApplyAmbientAsync(Config); Log("Release and stable stock clock confirmed"); } catch (Exception e) { LastError = "退出恢复：" + e.Message; Log(LastError); } finally { if (link != null) await link.DisposeAsync(); link = null; controller = null; } }
    }
    public static string ScreenColor(Settings s) => s.ScreenColor();
    async Task RunAsync(bool preview)
    {
        long started = Environment.TickCount64, nextMedia = 0, nextMonitor = 0, nextEmit = 0, nextConnect = 0, nextPerf = Environment.TickCount64 + 5000, nextPeak = 0, nextOwner = 0; int oldRevision = -1; string renderKey = "", trackKey = "", renderedTheme = "";
        Task<Track>? mediaTask = null; Task<Snapshot>? sensorTask = null; Task<(List<LyricLine> Lines, string Source)>? lyricTask = null; CancellationTokenSource? lyricCancel = null; string fetchKey = ""; bool fetchOnline = Config.Online;
        long nextTelemetry = 0; bool wasTelemetry = false;
        int importRevision = -1; string cueKey = "";
        using var process = Process.GetCurrentProcess(); TimeSpan priorCpu = process.TotalProcessorTime; long perfAt = started; double cpu = 0, memory = process.WorkingSet64 / 1048576.0; bool mediaPlaying = false; int metricRevision = 0;
        try
        {
            while (!stop.IsCancellationRequested)
            {
                long now = Environment.TickCount64; var s = Config; int rev = Volatile.Read(ref revision); bool changed = rev != oldRevision; var demo = Volatile.Read(ref showcase); bool enabled = s.Enabled || demo != null; double elapsed = (now - started) / 1000.0;
                await telemetry.ConfigureAsync(s.TelemetryEnabled,s.TelemetryPort,now);
                var driveDemo = Volatile.Read(ref sprint);
                if(driveDemo?.Elapsed >= TelemetrySprint.Duration) { Interlocked.CompareExchange(ref sprint,null,driveDemo); driveDemo=null; }
                var car = driveDemo != null ? TelemetrySprint.At(driveDemo.Elapsed,now) : telemetry.Latest;
                bool carActive = TelemetryPriority.Takeover(s.TelemetryEnabled,driveDemo != null,car,now);
                enabled |= carActive;
                string telemetryStatus = driveDemo != null ? "零百加速演示 · 模拟数据 · 16 秒后自动结束" : telemetry.Detail;
                if(s.TelemetryEnabled && car != null && !carActive) telemetryStatus += " · 游戏暂停或数据已停止，继续日常显示";
                if(wasTelemetry && !carActive) renderKey = "";
                if (changed) { nextMedia = nextMonitor = 0; oldRevision = rev; }
                if (!preview && enabled && controller == null && now >= nextConnect) { try { await SessionAsync(); renderKey = ""; } catch (Exception e) { status = e.Message; Log("Connect: " + e.Message); } nextConnect = Environment.TickCount64 + 5000; }
                if (preview || controller?.Owned == true) driveDemo?.Begin();
                if (!enabled && controller != null) { status = "正在释放音响显示权…"; await CloseSessionAsync(); status = "已暂停，原厂显示已恢复"; renderKey = ""; }
                if (!preview && controller != null && now >= nextOwner) { nextOwner = now + 3000; if (TempoHubRunning()) { await CloseSessionAsync(); status = "TempoHub 正在运行，已释放音响"; nextConnect = now + 5000; } }
                if (_pump is { IsCompleted: true }) { if (_pump.Exception != null) { status = _pump.Exception.GetBaseException().Message; Log("USB: " + status); } await CloseSessionAsync(); nextConnect = now + 5000; }
                if (now >= nextPeak)
                {
                    bool want = enabled && s.Rhythm && s.AmbientEnabled && track.Playing && demo == null;
                    signal = peak.Read(); mediaPlaying = peak.Playing;
                    rhythmActive = want || demo != null; if (demo != null) rhythmColor = frameColor; else if (want) { double level = envelope.Update(signal, elapsed, s.RhythmGain); var d = Designs.All.GetValueOrDefault(s.Theme) ?? Designs.All.Values.First(); rhythmColor = Envelope.ColorFor(s.ScreenColor(), d.Accent, level, s.RhythmStyle); } else rhythmColor = null;
                    nextPeak = now + (want ? (s.PowerProfile == "balanced" ? 33 : 50) : 600);
                }
                if (mediaTask?.IsCompleted == true) { try { track = await mediaTask; } catch (Exception e) { Log("Media: " + e.Message); } mediaTask = null; }
                if (mediaTask == null && now >= nextMedia) { mediaTask = media.PollAsync(mediaPlaying); nextMedia = now + (track.Playing ? (s.PowerProfile == "balanced" ? 100 : 200) : 1500); }
                if (sensorTask?.IsCompleted == true) { try { snapshot = await sensorTask; metricRevision++; } catch (Exception e) { Log("Sensors: " + e.Message); } sensorTask = null; }
                if (sensorTask == null && now >= nextMonitor && (MonitorVisible || (!carActive && s.WantsMonitor))) { sensorTask = hardware.SampleAsync(s.FanLimits, s.CpuTemperatureEnabled, s.CpuTemperatureElevation); nextMonitor = now + (s.PowerProfile == "balanced" ? 2000 : 3000); }
                if (track.Key != trackKey || fetchOnline != s.Online || importRevision != Volatile.Read(ref lyricImportRevision))
                {
                    trackKey = track.Key; fetchOnline = s.Online; importRevision = Volatile.Read(ref lyricImportRevision); lines = []; lyricCancel?.Cancel(); lyricCancel?.Dispose(); lyricCancel = CancellationTokenSource.CreateLinkedTokenSource(stop.Token);
                    fetchKey = track.Key; lyricTask = track.Title.Length > 0 ? lyrics.FetchAsync(track, s.Online, lyricCancel.Token) : null;
                }
                if (lyricTask?.IsCompleted == true) { try { var result = await lyricTask; if (fetchKey == track.Key) { lines = result.Lines; lyricSource = result.Source; } } catch (OperationCanceledException) { } catch (Exception e) { Log("Lyrics: " + e.Message); } lyricTask = null; }
                string mode = "时钟", text = DateTime.Now.ToString(s.Seconds ? "HH:mm:ss" : "HH:mm");
                var cue = lyricPlayback.Select(track, lines, s, elapsed, LyricsStore.CanUseTimeline(track, lyricSource), Math.Max(.5, controller?.FrameSeconds ?? .5) + (s.Transitions ? .55 : 0));
                if (s.Mode == "auto" && track.Playing && track.Title.Length > 0)
                {
                    if (cue != null) { text = cue.Text; mode = "歌词"; }
                }
                cueKey = mode == "歌词" ? cue!.Key + ":" + s.Theme : "";
                if (mode == "时钟" && s.WantsMonitor) { mode = "系统监控"; text = ""; }
                var clock = DateTime.Now; string key = $"{mode}|{text}|{cueKey}|{s.Theme}|{s.MonitorView}|{rev}|{(mode == "系统监控" ? metricRevision : 0)}|{(mode == "系统监控" && s.MonitorRotate ? (int)(elapsed / s.RotationSeconds) : 0)}|{(s.Animations ? (int)(elapsed / 2) : 0)}|{clock:yyyyMMdd}";
                if (carActive && car != null)
                {
                    if(!wasTelemetry || changed || now >= nextTelemetry)
                    {
                        try
                        {
                            var next = TelemetryDesigns.Render(s.TelemetryTheme,car,driveDemo != null);
                            var design = TelemetryDesigns.All.GetValueOrDefault(s.TelemetryTheme) ?? TelemetryDesigns.All.Values.First();
                            // A changing value must never interrupt an in-flight USB frame or start a whole-screen slide.
                            // The pump coalesces pending frames and only diffs against its acknowledged basis.
                            bool urgent = !wasTelemetry || renderedTheme != "telemetry:"+s.TelemetryTheme;
                            frame=next; frameColor=design.Color; frameOfficial=false; renderedTheme="telemetry:"+s.TelemetryTheme;
                            controller?.Offer(next,s.DeviceScreenColor(frameColor,false),0,urgent);
                        }
                        catch(Exception e) when(e is InvalidDataException or ArgumentException or InvalidOperationException or KeyNotFoundException) { status="遥测主题绘制失败："+e.Message; Log(status); }
                        nextTelemetry=now+(s.PowerProfile=="balanced"?125:200);
                    }
                }
                else if (demo != null)
                {
                    var sample = demo.Poll(s);
                    if (sample != null) { frame = sample.Frame; frameColor = sample.Color; frameOfficial = sample.OfficialColor; renderedTheme = ""; controller?.Offer(frame, s.DeviceScreenColor(sample.Color, sample.OfficialColor), sample.Animation, sample.Urgent, sample.Interval); }
                    if (demo.Finished) { Interlocked.CompareExchange(ref showcase, null, demo); renderKey = ""; }
                }
                else if (s.Enabled && key != renderKey)
                {
                    try
                    {
                        var next = Designs.Render(text, mode, s, elapsed, snapshot, clock, lyricCue: cue);
                        if (mode == "歌词") next = next with { Identity = next.Identity + ":" + cueKey };
                        bool urgent = changed || mode == "歌词" && next.Identity != frame?.Identity;
                        byte animation = s.Transitions && frame != null && next.Identity != frame.Identity ? (renderedTheme != s.Theme ? Transitions.ThemeStyle(s.Theme) : Transitions.Style(s.PixelTransition)) : (byte)0;
                        frame = next; frameColor = ScreenColor(s); frameOfficial = s.OfficialScreenColor(); renderedTheme = s.Theme; controller?.Offer(next, s.DeviceScreenColor(frameColor), animation, urgent);
                    }
                    catch (Exception e) when (e is InvalidDataException or ArgumentException or InvalidOperationException or KeyNotFoundException) { status = "主题绘制失败，保留上一画面：" + e.Message; Log(status); }
                    renderKey = key;
                }
                wasTelemetry=carActive;
                if (now >= nextPerf)
                {
                    process.Refresh(); TimeSpan current = process.TotalProcessorTime; cpu = 100 * (current - priorCpu).TotalMilliseconds / Math.Max(1, now - perfAt) / Environment.ProcessorCount; priorCpu = current; perfAt = now; memory = process.WorkingSet64 / 1048576.0; nextPerf = now + 5000;
                    Log($"perf cpu={cpu:F3}% rss={memory:F1}MB frames={controller?.Frames ?? 0} writes={link?.Writes ?? 0} codec={controller?.Codec} bytes={controller?.EncodedBytes} theme={s.Theme} playing={track.Playing} peak={signal:F3} demo={demo?.StageName} text={frame?.Text} cpu_temp={snapshot.Get("cpu_temp").Text()} thermal={hardware.Temperature.Detail}");
                }
                if (now >= nextEmit) { Changed?.Invoke(new(status + " · " + lyricSource + (mode == "歌词" && cue?.Timed == false ? " · 当前句回退，等待可用时间轴（无法提前）" : ""), track, snapshot, frame, controller?.Frames ?? 0, controller?.Dropped ?? 0, link?.Writes ?? 0, controller?.Codec ?? "预览", controller?.EncodedBytes ?? 0, controller?.FrameSeconds ?? 0, cpu, memory, signal, hardware.Temperature.Detail, controller?.Owned ?? false, demo?.StageName ?? "", demo?.Progress ?? 0, frameColor, peak.Detail, frameOfficial, telemetryStatus, carActive, driveDemo != null)); nextEmit = now + (Visible ? (demo != null || carActive ? 125 : 500) : 3000); }
                await Task.Delay(rhythmActive ? 25 : demo != null || carActive || track.Playing ? 50 : 200, stop.Token);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception e) { LastError = e.ToString(); status = e.Message; Log("Engine: " + e); Changed?.Invoke(new(status, track, snapshot, frame, 0, 0, 0, "", 0, 0, cpu, memory, signal, hardware.Temperature.Detail, false)); }
        finally { lyricCancel?.Cancel(); await telemetry.DisposeAsync(); await CloseSessionAsync(); if (mediaTask != null) try { await mediaTask; } catch { } if (sensorTask != null) try { await sensorTask; } catch { } if (lyricTask != null) try { await lyricTask; } catch { } lyricCancel?.Dispose(); }
    }
    public async ValueTask DisposeAsync() { stop.Cancel(); if (runner != null) await runner; hardware.Dispose(); media.Dispose(); peak.Dispose(); lyrics.Dispose(); stop.Dispose(); }
}
