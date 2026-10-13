using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

namespace HaloStudio;

public sealed record LyricWord(double Time, double Duration, string Text);
public sealed record LyricLine(double Time, string Text, List<LyricWord>? Words = null, double Duration = 0);
public sealed class LyricsStore : IDisposable
{
    readonly string directory; readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(10) };
    static readonly Regex stamp = new(@"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]", RegexOptions.Compiled);
    static readonly Regex yrcLine = new(@"^\[(\d+),(\d+)\]", RegexOptions.Compiled);
    static readonly Regex yrcWord = new(@"\((\d+),(\d+),\d+\)", RegexOptions.Compiled);
    public LyricsStore(string path) { directory = path; Directory.CreateDirectory(path); http.DefaultRequestHeaders.UserAgent.ParseAdd("HaloStudio/2.0"); http.DefaultRequestHeaders.Referrer = new("https://music.163.com/"); }
    public static List<LyricLine> Parse(string text)
    {
        var map = new SortedDictionary<double, string>(); var offset = Regex.Match(text, @"\[offset:([+-]?\d+)\]", RegexOptions.IgnoreCase); double shift = offset.Success ? int.Parse(offset.Groups[1].Value) / 1000.0 : 0;
        foreach (string raw in text.Split('\n')) { var tags = stamp.Matches(raw); string content = Regex.Replace(stamp.Replace(raw, ""), @"<\d+:\d+(?:\.\d+)?>", "").Trim(); foreach (Match tag in tags) { double t = int.Parse(tag.Groups[1].Value) * 60 + int.Parse(tag.Groups[2].Value) + int.Parse((tag.Groups[3].Success ? tag.Groups[3].Value : "0").PadRight(3, '0')) / 1000.0 + shift; if (!map.TryGetValue(t, out var v) || v.Length == 0) map[t] = content; } }
        return map.Select(p => new LyricLine(p.Key, p.Value)).ToList();
    }
    public static string Normalize(string text) => string.Concat(text.Normalize(NormalizationForm.FormKC).ToLowerInvariant().Where(char.IsLetterOrDigit));
    public static List<LyricLine> ParseYrc(string text)
    {
        var result = new List<LyricLine>(); if (text.Length > 2_000_000) return result;
        foreach (string raw in text.Split('\n'))
        {
            string line = raw.Trim(); var head = yrcLine.Match(line); if (!head.Success) { if (line.StartsWith('[')) return []; continue; }
            if (!double.TryParse(head.Groups[1].Value, CultureInfo.InvariantCulture, out double start) || !double.TryParse(head.Groups[2].Value, CultureInfo.InvariantCulture, out double duration) || start < 0 || start > 86400000 || duration <= 0 || duration > 86400000 || result.Count > 0 && start / 1000 <= result[^1].Time) return [];
            var tags = yrcWord.Matches(line); if (tags.Count == 0 || tags[0].Index != head.Length) return []; var words = new List<LyricWord>();
            for (int i = 0; i < tags.Count; i++)
            {
                var tag = tags[i]; if (!double.TryParse(tag.Groups[1].Value, CultureInfo.InvariantCulture, out double at) || !double.TryParse(tag.Groups[2].Value, CultureInfo.InvariantCulture, out double length) || !double.IsFinite(at) || !double.IsFinite(length) || at < start || at > start + duration || length < 0 || at + length > start + duration + 1000 || words.Count > 0 && at / 1000 < words[^1].Time) return [];
                string part = line[(tag.Index + tag.Length)..(i + 1 < tags.Count ? tags[i + 1].Index : line.Length)];
                if (part.Any(char.IsControl)) return []; if (part.Length > 0) words.Add(new(at / 1000, length / 1000, part));
            }
            string joined = string.Concat(words.Select(w => w.Text)).Trim();
            if (joined.Length == 0 || joined.Length > 4096 || words.Count == 0) return [];
            result.Add(new(start / 1000, joined, words, duration / 1000));
        }
        return result;
    }
    public static string? At(List<LyricLine> lines, double position, double duration) { int i = lines.FindLastIndex(l => l.Time <= position); return i < 0 || string.IsNullOrWhiteSpace(lines[i].Text) ? null : lines[i].Text; }
    string Key(Track t) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Normalize(t.Title) + "|" + Normalize(t.Artist)))).ToLowerInvariant();
    static string CacheSuffix(Track t) => long.TryParse(t.SongId, out long id) && id > 0 ? "." + id + ".json" : ".json";
    public static bool CanUseTimeline(Track t, string source) => !t.Provider.StartsWith("网易云本地") || t.SongId.Length > 0 || source.StartsWith("本地 LRC");
    public List<LyricLine> Save(Track t, string text, string source, string yrc = "", bool wordsChecked = false) { var lines = ParseYrc(yrc); if (lines.Count == 0) lines = Parse(text); if (lines.Count == 0) throw new InvalidDataException("歌词没有有效时间标签"); Files.Save(Path.Combine(directory, Key(t) + (source == "本地 LRC" ? ".manual.json" : CacheSuffix(t))), new { Lrc = text, Yrc = yrc, WordsChecked = wordsChecked, Source = source }); return lines; }
    public async Task<(List<LyricLine> Lines, string Source)> FetchAsync(Track t, bool online, CancellationToken stop)
    {
        (List<LyricLine> Lines, string Source)? cached = null;
        foreach (string suffix in new[] { ".manual.json", CacheSuffix(t) }) try
        {
            using var doc = JsonDocument.Parse(await File.ReadAllTextAsync(Path.Combine(directory, Key(t) + suffix), stop)); var r = doc.RootElement;
            var lines = r.TryGetProperty("yrc", out var y) ? ParseYrc(y.GetString() ?? "") : []; bool hasWords = lines.Count > 0;
            if (!hasWords) lines = Parse(r.GetProperty("lrc").GetString() ?? "");
            if (lines.Count > 0)
            {
                cached = (lines, r.GetProperty("source").GetString() + (hasWords ? " · 逐字" : "") + " · 缓存");
                if (suffix == ".manual.json" || !online || t.SongId.Length == 0 || r.TryGetProperty("words_checked", out var checkedWords) && checkedWords.GetBoolean()) return cached.Value;
            }
        } catch (Exception e) when (e is IOException or JsonException or KeyNotFoundException or InvalidOperationException) { }
        if (!online) return ([], "联网获取已关闭，可导入 LRC");
        if (long.TryParse(t.SongId, out long exactId) && exactId > 0)
        {
            try
            {
                using var exact = JsonDocument.Parse(await http.GetStringAsync($"https://music.163.com/api/song/lyric/v1?id={exactId}&lv=-1&kv=-1&tv=-1&yv=-1&rv=-1&ytv=-1&yrv=-1", stop));
                string Field(string name) => exact.RootElement.TryGetProperty(name, out var p) && p.TryGetProperty("lyric", out var value) ? value.GetString() ?? "" : "";
                string lrc = Field("lrc"), yrc = Field("yrc"); bool hasWords = ParseYrc(yrc).Count > 0;
                if (hasWords || Parse(lrc).Count > 0) return (Save(t, lrc, "网易云当前版本", yrc, true), "网易云当前版本" + (hasWords ? " · 逐字" : ""));
            }
            catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException) { if (stop.IsCancellationRequested) throw; }
            if (cached != null) return cached.Value;
            try
            {
                using var fallback = JsonDocument.Parse(await http.GetStringAsync($"https://music.163.com/api/song/lyric?id={exactId}&lv=-1&kv=-1&tv=-1", stop));
                string lrc = fallback.RootElement.GetProperty("lrc").GetProperty("lyric").GetString() ?? "";
                if (Parse(lrc).Count > 0) return (Save(t, lrc, "网易云当前版本"), "网易云当前版本");
            }
            catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException) { if (stop.IsCancellationRequested) throw; }
            return ([], "当前歌曲版本暂无同步歌词，使用播放器当前句");
        }
        try
        {
            using var response = await http.PostAsync("https://music.163.com/api/search/get/web", new FormUrlEncodedContent(new Dictionary<string, string> { { "s", t.Title + " " + t.Artist }, { "type", "1" }, { "limit", "15" }, { "offset", "0" } }), stop); response.EnsureSuccessStatusCode(); using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(stop));
            foreach (var song in doc.RootElement.GetProperty("result").GetProperty("songs").EnumerateArray())
            {
                if (Normalize(song.GetProperty("name").GetString() ?? "") != Normalize(t.Title)) continue;
                string artist = Normalize(string.Join(" ", song.GetProperty("artists").EnumerateArray().Select(a => a.GetProperty("name").GetString()))), expected = Normalize(t.Artist);
                if (expected.Length > 0 && expected != artist && !artist.Contains(expected) && !(artist.Length > 0 && expected.Contains(artist))) continue;
                double duration = song.TryGetProperty("duration", out var d) ? d.GetDouble() / 1000 : 0; if (t.Duration > 0 && duration > 0 && Math.Abs(duration - t.Duration) > 5) continue;
                string id = song.GetProperty("id").ToString(); using var lyric = JsonDocument.Parse(await http.GetStringAsync($"https://music.163.com/api/song/lyric?id={id}&lv=-1&kv=-1&tv=-1", stop));
                string lrc = lyric.RootElement.GetProperty("lrc").GetProperty("lyric").GetString() ?? ""; if (Parse(lrc).Count > 0) return (Save(t, lrc, "网易云音乐"), "网易云音乐");
            }
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException) { if (stop.IsCancellationRequested) throw; }
        try
        {
            var query = new Dictionary<string, string> { { "track_name", t.Title }, { "artist_name", t.Artist } }; if (t.Duration > 0) query["duration"] = Math.Round(t.Duration).ToString(CultureInfo.InvariantCulture); if (t.Album.Length > 0) query["album_name"] = t.Album;
            string url = "https://lrclib.net/api/get?" + string.Join("&", query.Select(p => Uri.EscapeDataString(p.Key) + "=" + Uri.EscapeDataString(p.Value))); using var lyric = JsonDocument.Parse(await http.GetStringAsync(url, stop));
            string lrc = lyric.RootElement.GetProperty("syncedLyrics").GetString() ?? ""; if (Parse(lrc).Count > 0) return (Save(t, lrc, "LRCLIB"), "LRCLIB");
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException) { if (stop.IsCancellationRequested) throw; }
        return ([], "暂无匹配同步歌词，可导入本地 LRC");
    }
    public void Dispose() => http.Dispose();
}
