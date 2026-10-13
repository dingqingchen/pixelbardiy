using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Buffers.Binary;
using System.Text;
using Windows.Media.Control;
namespace HaloStudio;

public sealed class MediaMonitor : IDisposable
{
    GlobalSystemMediaTransportControlsSessionManager? manager;
    readonly NetEaseNative native = new();
    readonly NetEaseLibrary library = new();
    long propertiesAt; string lastApp = "", title = "", artist = "", album = "";
    public async Task<Track> PollAsync(bool nativePlaying)
    {
        var local = native.Poll(nativePlaying);
        if (local != null) local = library.Enrich(local);
        try
        {
            manager ??= await GlobalSystemMediaTransportControlsSessionManager.RequestAsync();
            var relevant = manager.GetSessions().Where(s => new[] { "cloudmusic", "netease", "网易", "music163" }.Any(x => s.SourceAppUserModelId.Contains(x, StringComparison.OrdinalIgnoreCase))).ToArray();
            var current = manager.GetCurrentSession();
            var session = relevant.FirstOrDefault(s => s.SourceAppUserModelId == current?.SourceAppUserModelId) ?? relevant.FirstOrDefault();
            if (session == null) { lastApp = ""; return local ?? new(); }
            string app = session.SourceAppUserModelId; long now = Environment.TickCount64;
            if (app != lastApp || now - propertiesAt >= 700)
            {
                var properties = await session.TryGetMediaPropertiesAsync(); title = properties.Title ?? ""; artist = properties.Artist ?? ""; album = properties.AlbumTitle ?? ""; propertiesAt = now; lastApp = app;
            }
            var playback = session.GetPlaybackInfo(); var timeline = session.GetTimelineProperties();
            bool playing = playback.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;
            double duration = Math.Max(0, (timeline.EndTime - timeline.StartTime).TotalSeconds), position = Math.Max(0, (timeline.Position - timeline.StartTime).TotalSeconds);
            // Some NetEase builds publish SMTC metadata/play state but no timeline.
            // Prefer the verified native playback clock, independent of lyric UI.
            if (local?.NativeTimeline == true && LyricsStore.Normalize(title) == LyricsStore.Normalize(local.Title) && LyricsStore.Normalize(artist) == LyricsStore.Normalize(local.Artist))
                return local with { Playing = playing };
            if (playing) { double elapsed = (DateTimeOffset.UtcNow - timeline.LastUpdatedTime).TotalSeconds; if (elapsed is >= 0 and < 86400) position += elapsed * (playback.PlaybackRate ?? 1); }
            var track = new Track(title, artist, album, duration, duration > 0 ? Math.Min(position, duration) : position, playing, app);
            if (local != null && LyricsStore.Normalize(track.Title) == LyricsStore.Normalize(local.Title) && LyricsStore.Normalize(track.Artist) == LyricsStore.Normalize(local.Artist)) track = track with { RealtimeLyric = local.RealtimeLyric, LineElapsed = local.LineElapsed, SongId = local.SongId };
            return track;
        }
        catch { return local ?? new(); }
    }
    public void Dispose() { native.Dispose(); manager = null; }
}
public sealed class NetEaseNative : IDisposable
{
    IntPtr handle; int pid, fallbackPid; long baseAddress, lyricRva, positionRva, durationRva, nextFind, lineSince; string lastLine = "", version = "未适配的模块版本";
    readonly Dictionary<int, IntPtr> titleWindows = []; long nextWindows;
    Dictionary<int, string> Captions(long now)
    {
        if (now >= nextWindows)
        {
            nextWindows = now + 3000;
            var processes = Process.GetProcessesByName("cloudmusic");
            var ids = processes.Select(p => p.Id).ToHashSet(); foreach (var p in processes) p.Dispose();
            titleWindows.Clear();
            Native.EnumWindows((hwnd, _) =>
            {
                Native.GetWindowThreadProcessId(hwnd, out int p); if (!ids.Contains(p)) return true;
                var text = new StringBuilder(1024); Native.GetWindowText(hwnd, text, text.Capacity);
                if (IsSongCaption(text.ToString())) titleWindows.TryAdd(p, hwnd);
                return true;
            }, IntPtr.Zero);
        }
        var captions = new Dictionary<int, string>();
        foreach (var (p, hwnd) in titleWindows)
        {
            Native.GetWindowThreadProcessId(hwnd, out int actualPid); if (p != actualPid) continue;
            var text = new StringBuilder(1024); Native.GetWindowText(hwnd, text, text.Capacity);
            string caption = text.ToString(); if (IsSongCaption(caption)) captions.Add(p, caption);
        }
        return captions;
    }
    public static bool IsSongCaption(string title) => title.Contains(" - ") && !title.StartsWith("MediaPlayer SMTC window", StringComparison.OrdinalIgnoreCase);
    public static (long Rva, string Version) Profile(uint stamp, uint size) => (stamp, size) switch
    {
        (1787745734, 40951808) => (35641104, "3.1.39"),
        (1791636812, 41054208) => (35736240, "3.1.41"),
        _ => (0, "未适配的模块版本")
    };
    public static (long Position, long Duration) TimelineProfile(uint stamp, uint size) => (stamp, size) switch
    {
        (1791636812, 41054208) => (0x21A74D8, 0x2214778),
        _ => (0, 0)
    };
    public static bool ValidTimeline(double position, double duration) => double.IsFinite(position) && double.IsFinite(duration) && duration is > 0 and < 86400 && position >= 0 && position <= duration + .5;
    public Track? Poll(bool playing)
    {
        long now = Environment.TickCount64; var titles = Captions(now);
        if (handle == IntPtr.Zero || !titles.ContainsKey(pid))
        {
            if (now < nextFind) return Caption(titles.GetValueOrDefault(fallbackPid), playing, "网易云本地 · " + version);
            Dispose(); nextFind = now + 3000;
            foreach (var process in Process.GetProcessesByName("cloudmusic"))
            {
                using (process) try
                    {
                        if (!titles.ContainsKey(process.Id)) continue; fallbackPid = process.Id;
                        foreach (ProcessModule module in process.Modules)
                        {
                            if (!module.ModuleName.Equals("cloudmusic.dll", StringComparison.OrdinalIgnoreCase)) continue;
                            using var f = File.OpenRead(module.FileName); byte[] head = new byte[64]; f.ReadExactly(head);
                            if (head[0] != 77 || head[1] != 90) continue;
                            int pe = BinaryPrimitives.ReadInt32LittleEndian(head.AsSpan(60)); if (pe < 64 || pe > f.Length - 84) continue;
                            f.Position = pe; head = new byte[84]; f.ReadExactly(head);
                            if (!head.AsSpan(0, 4).SequenceEqual(new byte[] { 80, 69, 0, 0 })) continue;
                            (lyricRva, version) = Profile(BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(8)), BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(80)));
                            (positionRva, durationRva) = TimelineProfile(BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(8)), BinaryPrimitives.ReadUInt32LittleEndian(head.AsSpan(80)));
                            if (lyricRva == 0) continue;
                            handle = Native.OpenProcess(0x1010, false, process.Id); if (handle != IntPtr.Zero) { pid = process.Id; baseAddress = module.BaseAddress.ToInt64(); }
                            else version += " · 读取权限不足";
                            break;
                        }
                    }
                    catch { }
                if (handle != IntPtr.Zero) break;
            }
        }
        if (handle == IntPtr.Zero) return Caption(titles.GetValueOrDefault(fallbackPid), playing, "网易云本地 · " + version);
        var track = Caption(titles.GetValueOrDefault(pid), playing, "网易云本地 · " + version); if (track == null) return null;
        if (positionRva != 0)
        {
            byte[] p = Read(baseAddress + positionRva, 8), d = Read(baseAddress + durationRva, 8);
            if (p.Length == 8 && d.Length == 8)
            {
                double position = BitConverter.ToDouble(p), duration = BitConverter.ToDouble(d);
                if (ValidTimeline(position, duration)) return track with { Position = Math.Min(position, duration), Duration = duration, NativeTimeline = true, Provider = "网易云本地进度 · " + version };
            }
        }
        long root = Ptr(baseAddress + lyricRva), second = root == 0 ? 0 : Ptr(root + 0x120), final = second == 0 ? 0 : Ptr(second + 8); byte[] raw = final == 0 ? [] : Read(final, 200); int end = raw.Length & ~1;
        for (int i = 0; i + 1 < raw.Length; i += 2) if (raw[i] == 0 && raw[i + 1] == 0) { end = i; break; }
        string line = Encoding.Unicode.GetString(raw, 0, end); line = string.Join(" ", line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries)).Replace("\uFEFF", "").Replace("\u200B", ""); if (line.Length > 100 || line.Any(char.IsControl)) line = "";
        if (lastLine != line) { lastLine = line; lineSince = now; }
        return track with { RealtimeLyric = line, LineElapsed = (now - lineSince) / 1000.0 };
    }
    static Track? Caption(string? title, bool playing, string provider) { if (title == null) return null; int split = title.LastIndexOf(" - ", StringComparison.Ordinal); return split < 0 ? null : new(title[..split].Trim(), title[(split + 3)..].Trim(), Playing: playing, App: "cloudmusic.exe", Provider: provider); }
    byte[] Read(long address, int count) { if (address <= 0x10000 || address >= 0x7FFFFFFFFFFF || handle == IntPtr.Zero) return []; byte[] bytes = new byte[count]; if (!Native.ReadProcessMemory(handle, new(address), bytes, (nuint)count, out nuint n)) return []; if (n < (nuint)count) Array.Resize(ref bytes, (int)n); return bytes; }
    long Ptr(long address) { var p = Read(address, 8); return p.Length == 8 ? BinaryPrimitives.ReadInt64LittleEndian(p) : 0; }
    public void Dispose() { if (handle != IntPtr.Zero) Native.CloseHandle(handle); handle = IntPtr.Zero; }
    static class Native
    {
        internal delegate bool Visitor(IntPtr hwnd, IntPtr arg);
        [DllImport("user32.dll")] internal static extern bool EnumWindows(Visitor visitor, IntPtr arg);
        [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out int pid);
        [DllImport("user32.dll", EntryPoint = "GetWindowTextW", CharSet = CharSet.Unicode)] internal static extern int GetWindowText(IntPtr hwnd, StringBuilder value, int count);
        [DllImport("kernel32.dll")] internal static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
        [DllImport("kernel32.dll")] internal static extern bool ReadProcessMemory(IntPtr process, IntPtr address, byte[] data, nuint size, out nuint read);
        [DllImport("kernel32.dll")] internal static extern bool CloseHandle(IntPtr handle);
    }
}
