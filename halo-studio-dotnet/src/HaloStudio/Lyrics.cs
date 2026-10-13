using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Security.Cryptography;

namespace HaloStudio;

public sealed record LyricLine(double Time, string Text);
public sealed class LyricsStore : IDisposable
{
    readonly string directory; readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(10) };
    static readonly Regex stamp = new(@"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]", RegexOptions.Compiled);
    public LyricsStore(string path) { directory = path; Directory.CreateDirectory(path); http.DefaultRequestHeaders.UserAgent.ParseAdd("HaloStudio/2.0"); http.DefaultRequestHeaders.Referrer = new("https://music.163.com/"); }
    public static List<LyricLine> Parse(string text)
    {
        var map = new SortedDictionary<double, string>(); var offset = Regex.Match(text, @"\[offset:([+-]?\d+)\]", RegexOptions.IgnoreCase); double shift = offset.Success ? int.Parse(offset.Groups[1].Value) / 1000.0 : 0;
        foreach (string raw in text.Split('\n')) { var tags = stamp.Matches(raw); string content = Regex.Replace(stamp.Replace(raw, ""), @"<\d+:\d+(?:\.\d+)?>", "").Trim(); foreach (Match tag in tags) { double t = int.Parse(tag.Groups[1].Value) * 60 + int.Parse(tag.Groups[2].Value) + int.Parse((tag.Groups[3].Success ? tag.Groups[3].Value : "0").PadRight(3, '0')) / 1000.0 + shift; if (!map.TryGetValue(t, out var v) || v.Length == 0) map[t] = content; } }
        return map.Select(p => new LyricLine(p.Key, p.Value)).ToList();
    }
    public static string Normalize(string text) => string.Concat(text.Normalize(NormalizationForm.FormKC).ToLowerInvariant().Where(char.IsLetterOrDigit));
    public static string[] Pages(string text) { var result = new List<string>(); string part = ""; foreach (var rune in text.EnumerateRunes()) { if (Rune.GetUnicodeCategory(rune) == UnicodeCategory.Control) continue; string next = rune.ToString(); if (part.Length > 0 && (part.EnumerateRunes().Count() + 1 > 16 || Encoding.UTF8.GetByteCount(part + next) > 48)) { result.Add(part); part = ""; } part += next; } if (!string.IsNullOrWhiteSpace(part)) result.Add(part.Trim()); return result.Count > 0 ? result.ToArray() : ["♪"]; }
    public static string? At(List<LyricLine> lines, double position, double duration) { int i = lines.FindLastIndex(l => l.Time <= position); if (i < 0 || string.IsNullOrWhiteSpace(lines[i].Text)) return null; var l = lines[i]; double end = i + 1 < lines.Count ? lines[i + 1].Time : Math.Max(duration, l.Time + 6); var pages = Pages(l.Text); int page = Math.Min(pages.Length - 1, (int)(Math.Max(0, position - l.Time) / Math.Max(.7, (end - l.Time) / pages.Length))); return pages[page]; }
    string Key(Track t) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Normalize(t.Title) + "|" + Normalize(t.Artist)))).ToLowerInvariant();
    public List<LyricLine> Save(Track t, string text, string source) { var lines = Parse(text); if (lines.Count == 0) throw new InvalidDataException("LRC 没有有效时间标签"); Files.Save(Path.Combine(directory, Key(t) + (source == "本地 LRC" ? ".manual.json" : ".json")), new { Lrc = text, Source = source }); return lines; }
    public async Task<(List<LyricLine> Lines, string Source)> FetchAsync(Track t, bool online, CancellationToken stop)
    {
        foreach (string suffix in new[] { ".manual.json", ".json" }) try { using var doc = JsonDocument.Parse(await File.ReadAllTextAsync(Path.Combine(directory, Key(t) + suffix), stop)); var lines = Parse(doc.RootElement.GetProperty("lrc").GetString() ?? ""); if (lines.Count > 0) return (lines, doc.RootElement.GetProperty("source").GetString() + " · 缓存"); } catch (Exception e) when (e is IOException or JsonException or KeyNotFoundException) { }
        if (!online) return ([], "联网获取已关闭，可导入 LRC");
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
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException) { if (stop.IsCancellationRequested) throw; }
        try
        {
            var query = new Dictionary<string, string> { { "track_name", t.Title }, { "artist_name", t.Artist } }; if (t.Duration > 0) query["duration"] = Math.Round(t.Duration).ToString(CultureInfo.InvariantCulture); if (t.Album.Length > 0) query["album_name"] = t.Album;
            string url = "https://lrclib.net/api/get?" + string.Join("&", query.Select(p => Uri.EscapeDataString(p.Key) + "=" + Uri.EscapeDataString(p.Value))); using var lyric = JsonDocument.Parse(await http.GetStringAsync(url, stop));
            string lrc = lyric.RootElement.GetProperty("syncedLyrics").GetString() ?? ""; if (Parse(lrc).Count > 0) return (Save(t, lrc, "LRCLIB"), "LRCLIB");
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException) { if (stop.IsCancellationRequested) throw; }
        return ([], "暂无匹配同步歌词，可导入本地 LRC");
    }
    public void Dispose() => http.Dispose();
}
