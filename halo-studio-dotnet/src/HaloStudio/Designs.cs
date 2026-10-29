using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Globalization;
namespace HaloStudio;

public sealed record Design(string Name, string Color, string Accent, string Description, JsonElement Scenes, Dictionary<string, string[]> Sprites, string Transition = "center", bool Monitor = false);
public static class Designs
{
    public static IReadOnlyDictionary<string, Design> All { get; private set; } = new Dictionary<string, Design>();
    public static string DirectoryPath { get; private set; } = "";
    public static string[] Reload(string directory)
    {
        var next = new Dictionary<string, Design>(); var errors = new List<string>();
        foreach (string path in Directory.EnumerateFiles(directory, "*.json").Order())
        {
            try
            {
                if (new FileInfo(path).Length > 262144) throw new InvalidDataException("主题超过 256 KB"); using var doc = JsonDocument.Parse(File.ReadAllText(path), new JsonDocumentOptions { MaxDepth = 32 }); var r = doc.RootElement;
                if (r.GetProperty("version").GetInt32() != 1) throw new InvalidDataException("主题版本不支持"); string id = r.GetProperty("id").GetString()!;
                if (!Regex.IsMatch(id, @"^[a-z][a-z0-9_-]{0,47}$")) throw new InvalidDataException("id 无效"); string color = r.GetProperty("color").GetString()!, accent = r.GetProperty("accent").GetString()!; Protocol.Rgb(color); Protocol.Rgb(accent);
                var scenes = r.GetProperty("scenes").Clone(); foreach (string scene in new[] { "clock", "lyric", "single", "pair", "dense" }) Validate(scenes.GetProperty(scene));
                var sprites = new Dictionary<string, string[]>(); if (r.TryGetProperty("sprites", out var sj)) foreach (var p in sj.EnumerateObject()) sprites[p.Name] = p.Value.EnumerateArray().Select(s => s.GetString()!).ToArray();
                string transition=r.TryGetProperty("transition",out var tj) ? tj.GetString() ?? "center" : "center";
                if(transition is not ("up" or "wipe" or "center" or "dissolve")) throw new InvalidDataException("主题过场无效");
                bool monitor = r.TryGetProperty("monitor", out var mj) ? mj.ValueKind == JsonValueKind.True : new[] { "single", "pair", "dense" }.All(s => scenes.GetProperty(s).GetArrayLength() > 0);
                if (!next.TryAdd(id, new(r.GetProperty("name").GetString()!, color, accent, r.GetProperty("description").GetString()!, scenes, sprites, transition, monitor))) throw new InvalidDataException("重复 id");
            }
            catch (Exception e) when (e is JsonException or InvalidDataException or KeyNotFoundException or FormatException or ArgumentException or InvalidOperationException) { errors.Add(Path.GetFileName(path) + ": " + e.Message); }
        }
        if (next.Count == 0) throw new InvalidDataException("无可用主题: " + string.Join("；", errors)); All = next; DirectoryPath = directory; return errors.ToArray();
    }
    static readonly HashSet<string> operations = ["line", "rect", "round", "circle", "star", "sprite", "small", "raster", "digits", "text", "tag", "erase", "invert", "segments", "history", "dial", "repeat", "metrics", "micro", "seven", "spark"];
    internal static void Validate(JsonElement a) { if (a.ValueKind != JsonValueKind.Array || a.GetArrayLength() > 512) throw new InvalidDataException("命令列表无效"); foreach (var e in a.EnumerateArray()) { string op = e.GetProperty("op").GetString()!; if (!operations.Contains(op)) throw new InvalidDataException("未知操作: " + op); if (op is "repeat" or "metrics") Validate(e.GetProperty("commands")); } }
    public static LyricViewport LyricViewport(Settings s)
    {
        var d = All.GetValueOrDefault(s.Themes ? s.Theme : "paper") ?? All.Values.First();
        var ctx = new Context(new(), d, s, Snapshot.Empty); var views = new List<LyricViewport>();
        void Read(JsonElement commands)
        {
            foreach (var e in commands.EnumerateArray())
            {
                if (e.GetProperty("op").GetString() == "text" && e.GetProperty("text").GetString() == "${text}")
                    views.Add(new(Math.Max(1, I(e, "w", ctx)), Math.Max(1, I(e, "h", ctx)), S(e, "font", ctx, "body"), I(e, "size", ctx, 17), B(e, "bold")));
                if (e.TryGetProperty("commands", out var nested)) Read(nested);
            }
        }
        Read(d.Scenes.GetProperty("lyric"));
        return views.OrderBy(v => v.Width / (double)Math.Max(1, v.Size)).FirstOrDefault() ?? new(240, 32, "body", 17, false);
    }
    public static PixelFrame Render(string text, string mode, Settings s, double elapsed, Snapshot snap, DateTime now, LyricScroll? lyricScroll = null, LyricCue? lyricCue = null)
    {
        var d = All.GetValueOrDefault(s.Themes ? s.Theme : "paper") ?? All.Values.First(); var c = new PixelCanvas(); var ctx = new Context(c, d, s, snap);
        ctx.LyricScroll = mode == "歌词" ? lyricScroll ?? new(0, 8) : null;
        ctx.LyricCue = mode == "歌词" ? lyricCue : null;
        foreach (var p in new Dictionary<string, string> { { "text", text }, { "time", now.ToString("HH:mm") }, { "hour", now.ToString("HH") }, { "minute", now.ToString("mm") }, { "second", s.Seconds ? now.ToString("ss") : "" }, { "date", now.ToString("MM/dd") }, { "day", now.ToString("ddd", CultureInfo.InvariantCulture).ToUpperInvariant() }, { "daynum", now.ToString("dd") } }) ctx.Text[p.Key] = p.Value;
        ctx.Numbers["phase"] = s.Animations && s.Themes ? (int)(elapsed / 2) % 8 : 0; ctx.Numbers["seconds"] = s.Seconds ? 1 : 0; ctx.Numbers["graph"] = s.MonitorView == "graph" ? 1 : 0; ctx.Numbers["instrument"] = s.MonitorView == "value" ? 1 : 0;
        string scene = mode == "时钟" ? "clock" : mode == "歌词" ? "lyric" : s.MonitorView == "dense" ? "dense" : s.MonitorView == "compact" ? "pair" : "single", identity = mode + ":" + s.Theme + ":" + scene;
        // A temporarily missing sensor keeps its card as --, so sampling cannot
        // turn an even selection into an odd one or reshuffle the paired pages.
        var chosen = scene == "pair" ? s.MonitorMetrics.Distinct().Select(k => snap.Get(k, k)).ToArray()
            : s.MonitorMetrics.Select(k => snap.Metrics.FirstOrDefault(m => m.Key == k)).Where(m => m != null).Cast<Metric>().ToArray();
        int index = chosen.Length > 0 && s.MonitorRotate ? (int)(elapsed / Math.Max(2, s.RotationSeconds)) % chosen.Length : 0;
        ctx.Selected = chosen.Skip(index).Concat(chosen.Take(index)).ToArray();
        if (scene == "pair" && chosen.Length > 0)
        {
            var pairs = MonitorPairing.Pages(chosen); long step = s.MonitorRotate ? (long)(Math.Max(0, elapsed) / Math.Max(2, s.RotationSeconds)) : 0;
            if (s.PixelTransition == "wipe" && s.PairAdvance == "single")
            {
                var ordered = pairs.SelectMany(p => p).ToArray(); int start = (int)(step % ordered.Length);
                ctx.Selected = ordered.Skip(start).Concat(ordered.Take(start)).Take(2).ToArray();
            }
            else ctx.Selected = pairs[step % pairs.Length];
        }
        if (mode == "系统监控" && scene != "dense") { if (ctx.Selected.Length == 0) { c.Typeset("等待监控数据", 0, 0, 256, 32, size: 18); return new(c.Data, "等待监控数据", identity); } ctx.Metric = ctx.Selected[0]; ctx.Bind(); text = ctx.Metric.Label + " " + ctx.Metric.Text(); identity += ":" + ctx.Metric.Key; }
        if (scene == "pair") { identity += ":" + string.Join("+", ctx.Selected.Select(m => m.Key)); text = string.Join(" / ", ctx.Selected.Select(m => m.Label + " " + m.Text())); }
        if (mode == "歌词") identity += ":" + text; if (scene == "dense") identity += ":dense";
        if (scene == "dense" && s.MonitorMetricsCustom && s.MonitorMetrics.Length > 0)
        {
            // Keep the theme's dense slot geometry and decorations but fill the
            // slots with the metrics the user applied in the hardware page.
            using var dense = JsonDocument.Parse(DenseWithSelected(d, s));
            Execute(dense.RootElement, ctx);
        }
        else Execute(d.Scenes.GetProperty(scene), ctx);
        return new(c.Data, text, identity, ctx.LyricPart == 1, ctx.LyricPart);
    }
    static string DenseWithSelected(Design d, Settings s)
    {
        var root = JsonNode.Parse(d.Scenes.GetProperty("dense").GetRawText())!.AsArray();
        foreach (var node in root)
        {
            if (node is not JsonObject op || op["op"]?.GetValue<string>() != "metrics") continue;
            if (op["items"] is not JsonArray items) continue;
            int keep = Math.Min(items.Count, s.MonitorMetrics.Length);
            for (int i = items.Count - 1; i >= keep; i--) items.RemoveAt(i);
            for (int i = 0; i < keep; i++)
            {
                string key = s.MonitorMetrics[i];
                if (items[i] is not JsonObject item) continue;
                item["key"] = key;
                item["label"] = ShortLabel(key);
                item["short"] = ShortLabel(key);
                item["unit"] = "";
            }
            break;
        }
        return root.ToJsonString();
    }
    static string ShortLabel(string key) => key switch
    {
        "cpu" => "CPU", "gpu0" => "GPU", "ram" => "RAM", "ram_gb" => "GB",
        "gpu0_vram" => "VRAM", "gpu0_vram_gb" => "VRAM", "cpu_temp" => "CPU", "gpu0_temp" => "GPU",
        "frequency" => "FREQ", "gpu0_clock" => "GCLK", "gpu0_mem_clock" => "MCLK",
        "fps" => "FPS", "frametime" => "FT", "upload" => "UP", "download" => "DN",
        "disk_read" => "READ", "disk_write" => "WRITE",
        _ => key.Length > 5 ? key[..5].ToUpperInvariant() : key.ToUpperInvariant()
    };
    internal static byte[] RenderCommands(JsonElement commands, Dictionary<string,string[]> sprites, Dictionary<string,double> numbers, Dictionary<string,string> text)
    {
        var c = new PixelCanvas(); var d = new Design("", "#FFFFFF", "#FFFFFF", "", default, sprites);
        var ctx = new Context(c,d,new Settings(),Snapshot.Empty) { Numbers = numbers, Text = text };
        Execute(commands,ctx); return c.Data;
    }
    sealed class Context(PixelCanvas canvas, Design design, Settings settings, Snapshot snapshot)
    {
        public LyricScroll? LyricScroll; public int LyricPart; public LyricCue? LyricCue;
        public PixelCanvas Canvas = canvas; public Design Design = design; public Settings Settings = settings; public Snapshot Snapshot = snapshot; public Metric? Metric; public Metric[] Selected = []; public Dictionary<string, double> Numbers = []; public Dictionary<string, string> Text = []; public int Budget = 4096;
        public void Bind() { if (Metric == null) return; Text["label"] = Metric.Label; Text["value"] = Metric.Text(); Text["compact"] = Metric.Text(true); Text["short"] = Metric.Short; Text["maxlabel"] = Metric.Scale == 100 ? "100" : "AUTO"; Numbers["ratio"] = Metric.Ratio; Numbers["valid"] = Metric.Value != null ? 1 : 0; }
    }
    static string Template(string value, Context c) => Regex.Replace(value, @"\$\{([a-zA-Z_][a-zA-Z_0-9]*)\}", m => c.Text.GetValueOrDefault(m.Groups[1].Value, c.Numbers.GetValueOrDefault(m.Groups[1].Value).ToString(CultureInfo.InvariantCulture)));
    static double Number(JsonElement v, Context c) => v.ValueKind == JsonValueKind.Number ? v.GetDouble() : Expression.Evaluate((v.GetString() ?? "0").TrimStart('='), c.Numbers);
    static int I(JsonElement e, string key, Context c, int fallback = 0) => e.TryGetProperty(key, out var v) ? Math.Clamp((int)Math.Round(Number(v, c)), -2048, 2048) : fallback;
    static double N(JsonElement e, string key, Context c, double fallback = 0) => e.TryGetProperty(key, out var v) ? Number(v, c) : fallback;
    static string S(JsonElement e, string key, Context c, string fallback = "") => e.TryGetProperty(key, out var v) ? Template(v.GetString() ?? "", c) : fallback;
    static bool B(JsonElement e, string key, bool fallback = false) => e.TryGetProperty(key, out var v) ? v.GetBoolean() : fallback;
    static void Execute(JsonElement commands, Context ctx)
    {
        var c = ctx.Canvas; foreach (var e in commands.EnumerateArray())
        {
            if (--ctx.Budget < 0) throw new InvalidDataException("绘图指令超过上限"); if (e.TryGetProperty("when", out var when) && Number(when, ctx) == 0) continue;
            string op = e.GetProperty("op").GetString()!; int x = I(e, "x", ctx), y = I(e, "y", ctx), w = I(e, "w", ctx), h = I(e, "h", ctx);
            switch (op)
            {
                case "micro": TelemetryFont.Micro(c, S(e,"text",ctx),x,y); break;
                case "seven": TelemetryFont.Seven(c,S(e,"text",ctx),x,y,I(e,"dw",ctx,10),h,I(e,"thick",ctx,2),I(e,"gap",ctx,3),I(e,"slots",ctx,3)); break;
                case "line": c.Line(x, y, I(e, "x2", ctx), I(e, "y2", ctx)); break;
                case "rect": c.Rect(x, y, w, h, B(e, "fill")); break;
                case "round": c.Round(x, y, w, h, I(e, "r", ctx, 3)); break;
                case "circle": c.Circle(x, y, I(e, "r", ctx), I(e, "start", ctx), I(e, "end", ctx, 360)); break;
                case "star": c.Star(x, y, I(e, "r", ctx, 2)); break;
                case "sprite": if (ctx.Design.Sprites.TryGetValue(S(e, "name", ctx), out var rows)) c.Sprite(rows, x, y, I(e, "scale", ctx, 1)); break;
                case "small": c.Small(S(e, "text", ctx), x, y, e.TryGetProperty("right", out _) ? I(e, "right", ctx) : null); break;
                case "raster": c.Raster(S(e, "text", ctx), x, y, I(e, "scale", ctx, 1), B(e, "dotted")); break;
                case "digits": c.Digits(S(e, "text", ctx), x, y, w, h, S(e, "style", ctx, "pixel")); break;
                case "text":
                    if (ctx.LyricCue is { } cue && e.GetProperty("text").GetString() == "${text}")
                        c.LyricPage(cue.Text, x, y, w, h, S(e, "font", ctx, "body"), I(e, "size", ctx, 17), B(e, "bold"), cue.Part == 1 ? "left" : cue.Part == 2 ? "right" : S(e, "align", ctx, "center"));
                    else if (ctx.LyricScroll is { } scroll && e.GetProperty("text").GetString()!.Contains("${text}"))
                        ctx.LyricPart = Math.Max(ctx.LyricPart, c.Lyric(S(e, "text", ctx), x, y, w, h, scroll, S(e, "font", ctx, "body"), I(e, "size", ctx, 17), B(e, "bold"), S(e, "align", ctx, "center")));
                    else c.Typeset(S(e, "text", ctx), x, y, w, h, S(e, "font", ctx, "body"), I(e, "size", ctx, 17), B(e, "bold"), S(e, "align", ctx, "center"));
                    break;
                case "tag": c.Tag(S(e, "text", ctx), x, y, w); break;
                case "erase": c.Erase(x, y, w, h); break;
                case "invert": c.Invert(x, y, w, h); break;
                case "segments": Segments(c, x, y, w, h, N(e, "ratio", ctx, ctx.Metric?.Ratio ?? 0), I(e, "count", ctx, 14), B(e, "slant")); break;
                case "history": if (ctx.Metric != null) History(c, ctx.Metric, x, y, w, h, B(e, "area")); break;
                case "spark":
                    {
                        var sparkMetric = ctx.Snapshot.Metrics.FirstOrDefault(m => m.Key == S(e, "key", ctx));
                        if (sparkMetric != null && sparkMetric.History.Length > 1) History(c, sparkMetric, x, y, w, h, B(e, "area"));
                        break;
                    }
                case "dial": Dial(c, x, y, I(e, "r", ctx, 14), N(e, "ratio", ctx), I(e, "start", ctx, 190), I(e, "end", ctx, 350)); break;
                case "repeat": { string variable = S(e, "var", ctx, "i"); double old = ctx.Numbers.GetValueOrDefault(variable); int count = Math.Clamp(I(e, "count", ctx), 0, 256); double start = N(e, "start", ctx), step = N(e, "step", ctx, 1); for (int i = 0; i < count; i++) { ctx.Numbers[variable] = start + i * step; Execute(e.GetProperty("commands"), ctx); } ctx.Numbers[variable] = old; break; }
                case "metrics":
                    {
                        var saved = ctx.Metric; int i = 0; if (e.TryGetProperty("items", out var items)) { foreach (var item in items.EnumerateArray()) { string key = item.GetProperty("key").GetString()!; ctx.Metric = ctx.Snapshot.Get(key, S(item, "short", ctx, key), S(item, "unit", ctx)); ctx.Bind(); ctx.Numbers["column"] = i / 2; ctx.Numbers["row"] = i % 2; ctx.Numbers["x"] = I(item, "x", ctx); ctx.Numbers["w"] = I(item, "w", ctx); ctx.Numbers["y"] = item.TryGetProperty("y", out _) ? I(item, "y", ctx) : 3 + i % 2 * 16; ctx.Text["label"] = S(item, "label", ctx); Execute(e.GetProperty("commands"), ctx); i++; } }
                        else foreach (var m in ctx.Selected.Take(I(e, "count", ctx, 2))) { ctx.Metric = m; ctx.Bind(); ctx.Numbers["column"] = i; ctx.Numbers["x"] = i * 128; Execute(e.GetProperty("commands"), ctx); i++; }
                        ctx.Metric = saved; ctx.Bind(); break;
                    }
            }
        }
    }
    static void Segments(PixelCanvas c, int x, int y, int w, int h, double ratio, int count, bool slant) { count = Math.Clamp(count, 1, 128); int on = (int)Math.Round(Math.Clamp(ratio, 0, 1) * count); double step = w / (double)count; for (int i = 0; i < count; i++) { int xx = x + (int)Math.Round(i * step), ww = Math.Max(1, (int)Math.Round(step) - 2); if (i < on) { if (slant) for (int k = 0; k < ww; k++) c.Line(xx + k, y + h - 1, xx + k + 3, y); else c.Rect(xx, y, ww, h, true); } else c.Line(xx, y + h - 1, xx + ww - 1, y + h - 1); } }
    static void History(PixelCanvas c, Metric m, int x, int y, int w, int h, bool area) { var values = m.History.TakeLast(24).ToArray(); double max = m.Scale ?? Math.Max(1, values.DefaultIfEmpty(1).Max()); Point? prior = null; for (int i = 0; i < values.Length; i++) { int xx = x + (int)Math.Round(i * (w - 1) / (double)Math.Max(1, values.Length - 1)), yy = y + h - 1 - (int)Math.Round(Math.Clamp(values[i] / max, 0, 1) * (h - 1)); if (area) c.Line(xx, yy, xx, y + h - 1); if (prior is Point p) c.Line(p.X, p.Y, xx, yy); else c.Dot(xx, yy); prior = new(xx, yy); } }
    static void Dial(PixelCanvas c, int x, int y, int r, double ratio, int start, int end) { c.Circle(x, y, r, start, end); double a = (start + (end - start) * Math.Clamp(ratio, 0, 1)) * Math.PI / 180; c.Line(x, y, x + (int)Math.Round(Math.Cos(a) * (r - 3)), y + (int)Math.Round(Math.Sin(a) * (r - 3))); c.Circle(x, y, 1); for (int deg = start; deg <= end; deg += 40) { a = deg * Math.PI / 180; c.Line(x + (int)Math.Round(Math.Cos(a) * r), y + (int)Math.Round(Math.Sin(a) * r), x + (int)Math.Round(Math.Cos(a) * (r - 3)), y + (int)Math.Round(Math.Sin(a) * (r - 3))); } }
}
// Arithmetic only. Theme files cannot execute scripts, access files or write USB commands.
public sealed class Expression
{
    readonly string source; readonly IReadOnlyDictionary<string, double> variables; int pos;
    Expression(string text, IReadOnlyDictionary<string, double> vars) { source = text; variables = vars; }
    public static double Evaluate(string text, IReadOnlyDictionary<string, double> vars) { if (text.Length > 160) throw new InvalidDataException("表达式过长"); var p = new Expression(text, vars); double n = p.Add(); p.Skip(); if (p.pos != text.Length || !double.IsFinite(n)) throw new InvalidDataException("表达式无效: " + text); return n; }
    void Skip() { while (pos < source.Length && char.IsWhiteSpace(source[pos])) pos++; }
    bool Take(char c) { Skip(); if (pos < source.Length && source[pos] == c) { pos++; return true; } return false; }
    double Add() { double n = Mul(); while (true) { if (Take('+')) n += Mul(); else if (Take('-')) n -= Mul(); else return n; } }
    double Mul() { double n = Atom(); while (true) { if (Take('*')) n *= Atom(); else if (Take('/')) n /= Atom(); else if (Take('%')) n %= Atom(); else return n; } }
    double Atom()
    {
        Skip(); if (Take('-')) return -Atom(); if (Take('+')) return Atom(); if (Take('(')) { double n = Add(); if (!Take(')')) throw new InvalidDataException("缺少括号"); return n; }
        int begin = pos; while (pos < source.Length && (char.IsLetterOrDigit(source[pos]) || source[pos] is '_' or '.')) pos++; string token = source[begin..pos]; if (token.Length == 0) throw new InvalidDataException("表达式不完整"); if (double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out double value)) return value;
        if (Take('(')) { double a = Add(), b = Take(',') ? Add() : 0, c = Take(',') ? Add() : 0; if (!Take(')')) throw new InvalidDataException("缺少括号"); return token switch { "sin" => Math.Sin(a), "cos" => Math.Cos(a), "round" => Math.Round(a), "min" => Math.Min(a, b), "max" => Math.Max(a, b), "clamp" => Math.Clamp(a, b, c), _ => throw new InvalidDataException("未知函数") }; }
        return token == "pi" ? Math.PI : variables.GetValueOrDefault(token);
    }
}
