namespace HaloStudio;

public sealed record LyricCue(string Text, string Key, double Remaining, bool Timed, int Part = 0, bool WordTimed = false, int Page = 1, int Pages = 1);

// Native NetEase exposes the current sentence, but not a media timeline on all
// versions. Observed sentence boundaries anchor the cached LRC to a monotonic clock.
// Do not assume the first sentence read at app startup has just begun.
public sealed class LyricPlayback
{
    string key = "", native = ""; bool playing, observedBoundary;
    double boundaryAt, anchorAt; double? attemptedBoundary; double[] anchorPositions = []; bool anchored;
    readonly List<(double At, string Text)> history = [];
    List<LyricLine>? priorLines;
    readonly LyricPager pager = new();
    public LyricCue? Select(Track track, List<LyricLine> lines, Settings settings, double now, bool versionMatched = true, double transferSeconds = .5)
    {
        if (track.Key != key) { key = track.Key; native = ""; anchored = observedBoundary = false; attemptedBoundary = null; history.Clear(); playing = false; }
        if (!ReferenceEquals(lines, priorLines)) { anchored = false; attemptedBoundary = null; priorLines = lines; pager.Clear(); }
        if (!track.Playing) { playing = false; anchored = observedBoundary = false; return null; }
        if (!playing) { native = track.RealtimeLyric; playing = true; history.Clear(); if (native.Length > 0) history.Add((now, native)); }
        if (native != track.RealtimeLyric)
        {
            native = track.RealtimeLyric; observedBoundary = true; boundaryAt = now - Math.Clamp(track.LineElapsed, 0, 1);
            history.Add((boundaryAt, native)); while (history.Count > 128) history.RemoveAt(0);
            if (lines.Count > 0) Anchor(lines);
        }
        if (!anchored && observedBoundary && lines.Count > 0) Anchor(lines);
        double shift = settings.LyricLeadSeconds + settings.Offset;
        bool timeline = track.NativeTimeline || !track.Provider.StartsWith("网易云本地") && track.Duration > 0;
        if (versionMatched && lines.Count > 0 && (timeline || anchored))
        {
            var positions = timeline ? [track.Position + shift] : anchorPositions.Select(p => p + now - anchorAt + shift).ToArray();
            var candidates = positions.Select(At).ToArray();
            // Repeated verses can have several valid positions. Predict only when
            // every remaining position agrees on the sentence; otherwise fall back.
            if (candidates.All(c => c?.Text == candidates[0]?.Text)) return candidates[0];
        }
        LyricCue? At(double position)
        {
            int i = lines.FindLastIndex(l => l.Time <= position);
            // NetEase LRC often inserts sub-second empty cues between sentences.
            // Keep the preceding line through these gaps rather than flashing a clock.
            if (i > 0 && string.IsNullOrWhiteSpace(lines[i].Text) && i + 1 < lines.Count && lines[i + 1].Time - lines[i].Time <= 2) i--;
            if (i < 0 || string.IsNullOrWhiteSpace(lines[i].Text)) return null;
            double end = i + 1 < lines.Count ? lines[i + 1].Time : Math.Max(track.Duration, lines[i].Time + 8);
            if (i + 2 < lines.Count && string.IsNullOrWhiteSpace(lines[i + 1].Text) && lines[i + 2].Time - end <= 2) end = lines[i + 2].Time;
            return pager.Select(lines[i], end, Designs.LyricViewport(settings), transferSeconds, position, key + ":" + i, true);
        }
        // No future timestamps: only already observed text can be delayed. Never
        // pretend a positive offset can predict an unavailable future sentence.
        int h = history.FindLastIndex(l => l.At <= now + Math.Min(0, shift));
        // Without a clock/next timestamp a short provisional window shows the tail
        // promptly. Its real remaining duration is unknown, not a fabricated time.
        return h >= 0 && history[h].Text.Length > 0 ? pager.Select(new(history[h].At, history[h].Text), history[h].At + 2, Designs.LyricViewport(settings), transferSeconds, now + Math.Min(0, shift), key + ":native:" + history[h].At, false) : null;
    }
    void Anchor(List<LyricLine> lines)
    {
        if (attemptedBoundary == boundaryAt) return; attemptedBoundary = boundaryAt;
        string normalized = LyricsStore.Normalize(native); if (normalized.Length == 0) return;
        var matches = lines.Where(l => LyricsStore.Normalize(l.Text) == normalized).ToArray();
        if (matches.Length == 0) { anchored = false; return; }
        // Retain all plausible occurrences until later boundaries disambiguate.
        if (anchored)
        {
            var continued = matches.Where(l => anchorPositions.Any(p => Math.Abs(l.Time - (p + boundaryAt - anchorAt)) < 2.5)).ToArray();
            if (continued.Length > 0) matches = continued;
        }
        anchorPositions = matches.Select(l => l.Time).ToArray(); anchorAt = boundaryAt; anchored = true;
    }
}

public sealed record LyricScroll(double Elapsed, double Duration, double TransferSeconds = .5, double? HeadShownSeconds = 0)
{
    // Submit the tail before the midpoint of the actual head-to-next-cue window,
    // subtracting measured transfer time plus margin. Wait for the head's ACK.
    public double SwitchAt => HeadShownSeconds is double head ? Math.Max(head, (head + Duration) / 2 - TransferSeconds - .15) : double.PositiveInfinity;
    public double Progress => Elapsed >= SwitchAt ? 1 : 0;
    public int Offset(int overflow) => (int)Math.Round(Math.Max(0, overflow) * Progress);
}
