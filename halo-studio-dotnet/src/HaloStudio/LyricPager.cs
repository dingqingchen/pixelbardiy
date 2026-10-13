using System.Globalization;

namespace HaloStudio;

public sealed record LyricViewport(int Width, int Height, string Font, int Size, bool Bold)
{
    public int Measure(string text) => PixelCanvas.LyricWidth(text, Height, Font, Size, Bold);
}
public sealed record LyricPage(double Time, string Text, int Part = 0, bool WordTimed = false);

// Pages are cached, including their fallback switch time: fluctuating USB timings
// must never make a displayed tail jump back to its head.
public sealed class LyricPager
{
    readonly Dictionary<(LyricLine, double, LyricViewport), LyricPage[]> cache = [];
    public void Clear() => cache.Clear();
    public LyricPage[] Pages(LyricLine line, double end, LyricViewport viewport, double transfer)
    {
        var key = (line, end, viewport);
        if (cache.TryGetValue(key, out var pages)) return pages;
        pages = Build(line, end, viewport, transfer);
        if (cache.Count >= 32) cache.Clear();
        cache[key] = pages; return pages;
    }
    public static LyricPage[] Build(LyricLine line, double end, LyricViewport view, double transfer)
    {
        if (view.Measure(line.Text) <= view.Width) return [new(line.Time, line.Text, WordTimed: line.Words?.Count > 0)];
        if (line.Words is { Count: > 0 } words)
        {
            var pages = new List<LyricPage>(); string text = ""; double at = line.Time;
            // Simultaneous tokens are inseparable: no invented intra-word timing.
            foreach (var group in words.GroupBy(w => w.Time))
            {
                string token = string.Concat(group.Select(w => w.Text));
                if (group.Key >= end || view.Measure(token.Trim()) > view.Width) return Fallback();
                if (text.Length > 0 && view.Measure((text + token).Trim()) > view.Width)
                { pages.Add(new(at, text.Trim(), WordTimed: true)); text = ""; at = group.Key; }
                text += token;
            }
            if (text.Trim().Length > 0) pages.Add(new(at, text.Trim(), WordTimed: true));
            if (pages.Count > 0) return pages.ToArray();
        }
        return Fallback();

        LyricPage[] Fallback()
        {
            var elements = new List<string>(); var enumerator = StringInfo.GetTextElementEnumerator(line.Text);
            while (enumerator.MoveNext()) elements.Add(enumerator.GetTextElement());
            string Fit(bool tail)
            {
                int lo = 0, hi = elements.Count;
                string Candidate(int n) => tail ? "..." + string.Concat(elements.TakeLast(n)).TrimStart() : string.Concat(elements.Take(n)).TrimEnd() + "...";
                while (lo < hi) { int n = (lo + hi + 1) / 2; if (view.Measure(Candidate(n)) <= view.Width) lo = n; else hi = n - 1; }
                return Candidate(lo);
            }
            double duration = Math.Max(.02, end - line.Time);
            double cost = double.IsFinite(transfer) ? Math.Clamp(transfer, 0, 5) : .5;
            // Arrival of tail is at/before the midpoint of head-arrival -> next
            // sentence. This estimate cannot guarantee visibility on a stalled USB.
            double split = Math.Clamp((duration - cost) / 2 - .15, .01, duration / 2);
            return [new(line.Time, Fit(false), 1), new(line.Time + split, Fit(true), 2)];
        }
    }
    public LyricCue Select(LyricLine line, double end, LyricViewport view, double transfer, double position, string key, bool timed)
    {
        var pages = Pages(line, end, view, transfer); int index = Math.Max(0, Array.FindLastIndex(pages, p => p.Time <= position));
        var page = pages[index]; double next = index + 1 < pages.Length ? pages[index + 1].Time : end;
        return new(page.Text, key + ":page:" + index, Math.Max(.01, next - position), timed, page.Part, page.WordTimed, index + 1, pages.Length);
    }
}
