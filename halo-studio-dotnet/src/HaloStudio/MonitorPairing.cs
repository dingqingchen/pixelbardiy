using System.Text.RegularExpressions;
namespace HaloStudio;

public static class MonitorPairing
{
    public static Metric[][] Pages(IEnumerable<Metric> selected)
    {
        // Complete same-family pairs first; use only the metrics the user selected.
        var pages = new List<Metric[]>(); var singles = new List<Metric>();
        foreach (var group in selected.DistinctBy(m => m.Key).GroupBy(Family))
            foreach (var pair in group.OrderBy(Priority).ThenBy(m => m.Key, StringComparer.Ordinal).Chunk(2))
                if (pair.Length == 2) pages.Add(pair); else singles.Add(pair[0]);

        // Fixed category positions: CPU -> memory -> GPU -> disk -> network -> fan -> other.
        // Distances never depend on current readings or the selected subset. Equal
        // distances prefer the earlier category, then the ordinal sensor key.
        var remaining = singles.Select(m => (Metric: m, Rank: DistanceRank(m)))
            .OrderBy(m => m.Rank).ThenBy(m => m.Metric.Key, StringComparer.Ordinal).ToList();
        while (remaining.Count >= 2)
        {
            int nearest = 0, distance = int.MaxValue;
            // A closest pair in one dimension is always adjacent in sorted order.
            for (int i = 0; i < remaining.Count - 1; i++)
            {
                int gap = remaining[i + 1].Rank - remaining[i].Rank;
                if (gap < distance) { nearest = i; distance = gap; }
            }
            pages.Add([remaining[nearest].Metric, remaining[nearest + 1].Metric]);
            remaining.RemoveRange(nearest, 2);
        }
        if (remaining.Count == 1) pages.Add([remaining[0].Metric]);
        return pages.ToArray();
    }
    static int DistanceRank(Metric m)
    {
        string family = Family(m);
        if (family == "cpu") return 0;
        if (family == "ram") return 1;
        if (family.StartsWith("gpu")) return 2; // GPU fan readings stay near their GPU.
        if (family == "disk") return 3;
        if (family == "network") return 4;
        if (m.Unit == "RPM" || m.Key.EndsWith("_rated")) return 5;
        return 6;
    }
    static string Family(Metric m)
    {
        string key = m.Key;
        if (key is "cpu" or "cpu_temp" or "frequency" || m.Short == "CPU") return "cpu";
        if (key is "ram" or "ram_gb") return "ram";
        if (key is "upload" or "download") return "network";
        if (key is "disk_read" or "disk_write") return "disk";
        var fan = Regex.Match(key, @"^gpu\d+_fan\d+"); if (fan.Success) return fan.Value;
        var gpu = Regex.Match(key, @"^gpu\d+(?:_|$)"); if (gpu.Success) return gpu.Value.TrimEnd('_');
        if (key.StartsWith("lhm:") && (m.Unit == "RPM" || key.EndsWith("_rated"))) return key.EndsWith("_rated") ? key[..^6] : key;
        return "single:" + key;
    }
    static int Priority(Metric m) => m.Key switch
    {
        "cpu" or "ram_gb" or "upload" or "disk_read" => 0,
        "cpu_temp" or "ram" or "download" or "disk_write" => 1,
        "frequency" => 3,
        _ => m.Unit == "RPM" || Regex.IsMatch(m.Key, @"^gpu\d+$") ? 0 : m.Unit == "C" || m.Key.EndsWith("_rated") ? 1 : 2
    };
}
