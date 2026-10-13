using System.Text.Json;

namespace HaloStudio;

// Appearance metadata only. Never use Preview() to form a USB command: these
// swatches are qualitative visual estimates, not measured sRGB coordinates.
public sealed record ScreenSwatch(string Input, string Preview, string Name, string Observation, bool Quick);
public static class ScreenPalette
{
    public static IReadOnlyDictionary<string, ScreenSwatch> All { get; private set; } = new Dictionary<string, ScreenSwatch>(StringComparer.OrdinalIgnoreCase);
    public static string FilePath { get; private set; } = "";
    public static string? Reload(string path)
    {
        FilePath = path;
        try
        {
            if (new FileInfo(path).Length > 32768) throw new InvalidDataException("色表超过 32 KB");
            using var doc = JsonDocument.Parse(File.ReadAllText(path), new JsonDocumentOptions { MaxDepth = 8 });
            var root = doc.RootElement;
            if (root.GetProperty("version").GetInt32() != 1) throw new InvalidDataException("色表版本不支持");
            var next = new Dictionary<string, ScreenSwatch>(StringComparer.OrdinalIgnoreCase);
            var entries = root.GetProperty("colors");
            if (entries.GetArrayLength() is 0 or > 64) throw new InvalidDataException("色表需包含 1–64 个颜色");
            foreach (var e in entries.EnumerateArray())
            {
                string input = e.GetProperty("input").GetString()!, preview = e.GetProperty("preview").GetString()!;
                if (!Settings.IsColor(input) || !Settings.IsColor(preview)) throw new InvalidDataException("色值需为 #RRGGBB");
                string name = e.GetProperty("name").GetString()!, observation = e.GetProperty("observation").GetString()!;
                if (string.IsNullOrWhiteSpace(name) || name.Length > 12 || string.IsNullOrWhiteSpace(observation) || observation.Length > 100) throw new InvalidDataException("颜色说明无效");
                if (!next.TryAdd(input, new(input.ToUpperInvariant(), preview.ToUpperInvariant(), name, observation, e.GetProperty("quick").GetBoolean()))) throw new InvalidDataException("色表设备值重复");
            }
            All = next;
            return null;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException or InvalidDataException or KeyNotFoundException or InvalidOperationException or ArgumentException)
        { return "色表未加载，保留现有预览：" + e.Message; }
    }
    public static string Preview(string input) => All.GetValueOrDefault(input)?.Preview ?? input;
    public static string Description(string input) => All.TryGetValue(input, out var entry)
        ? entry.Name + " · " + entry.Observation : "未校准 · 色块仅为电脑 RGB 参考";
}
