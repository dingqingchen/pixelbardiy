namespace HaloStudio;

// Read-only player diagnostic: no HID connection, display lease or firmware writes.
static class LyricDiagnostic
{
    public static async Task Run(string runtime, string output, int seconds)
    {
        using var media = new MediaMonitor(); using var peak = new MusicPeak();
        using var store = new LyricsStore(Path.Combine(runtime, "lyrics-cache")); var player = new LyricPlayback();
        var settings = (Files.Load<Settings>(Path.Combine(runtime, "settings.json")) ?? new()).Validated();
        var events = new List<object>(); long start = Environment.TickCount64; string key = "", prior = ""; List<LyricLine> lines = []; string source = "";
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(Math.Clamp(seconds, 5, 120)));
        try
        {
            while (!stop.IsCancellationRequested)
            {
                peak.Read(); var track = await media.PollAsync(peak.Playing); double now = (Environment.TickCount64 - start) / 1000.0;
                if (track.Key != key) { key = track.Key; (lines, source) = await store.FetchAsync(track, settings.Online, stop.Token); }
                var cue = player.Select(track, lines, settings, now, LyricsStore.CanUseTimeline(track, source)); string signature = track.RealtimeLyric + "|" + cue?.Key;
                if (signature != prior) { events.Add(new { Seconds = now, Native = track.RealtimeLyric, Target = cue?.Text, cue?.Timed, cue?.Remaining, cue?.WordTimed, cue?.Page, cue?.Pages, Source = source, Lines = lines.Count, track.Provider, track.Position }); prior = signature; }
                await Task.Delay(100, stop.Token);
            }
        }
        catch (OperationCanceledException) { }
        finally { Files.Save(output, new { settings.LyricLeadSeconds, settings.Offset, FirmwareWrites = 0, Events = events }); }
    }
}
