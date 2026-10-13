using System.Runtime.InteropServices;
namespace HaloStudio;

public sealed class CounterSet : IDisposable
{
    IntPtr query; readonly Dictionary<string, IntPtr> counters = [];
    public CounterSet()
    {
        if (PdhOpenQuery(null, IntPtr.Zero, out query) != 0) return;
        foreach (var (key, path) in new Dictionary<string, string> { { "disk_read", @"\PhysicalDisk(_Total)\Disk Read Bytes/sec" }, { "disk_write", @"\PhysicalDisk(_Total)\Disk Write Bytes/sec" }, { "frequency", @"\Processor Information(_Total)\Processor Frequency" } })
            if (PdhAddEnglishCounter(query, path, IntPtr.Zero, out var counter) == 0) counters[key] = counter; PdhCollectQueryData(query);
    }
    public Dictionary<string, double?> Read()
    {
        var result = new Dictionary<string, double?>(); if (query == IntPtr.Zero || PdhCollectQueryData(query) != 0) return result;
        foreach (var (key, counter) in counters) { double? value = null; if (PdhGetFormattedCounterValue(counter, 0x200, out _, out var data) == 0 && data.Status <= 1 && double.IsFinite(data.Number)) value = data.Number; result[key] = value; }
        return result;
    }
    public void Dispose() { if (query != IntPtr.Zero) PdhCloseQuery(query); query = IntPtr.Zero; }
    [StructLayout(LayoutKind.Explicit, Size = 16)] struct Value { [FieldOffset(0)] public uint Status; [FieldOffset(8)] public double Number; }
    [DllImport("pdh.dll", EntryPoint = "PdhOpenQueryW", CharSet = CharSet.Unicode)] static extern uint PdhOpenQuery(string? source, IntPtr data, out IntPtr query);
    [DllImport("pdh.dll", EntryPoint = "PdhAddEnglishCounterW", CharSet = CharSet.Unicode)] static extern uint PdhAddEnglishCounter(IntPtr query, string path, IntPtr data, out IntPtr counter);
    [DllImport("pdh.dll")] static extern uint PdhCollectQueryData(IntPtr query); [DllImport("pdh.dll")] static extern uint PdhGetFormattedCounterValue(IntPtr counter, uint format, out uint type, out Value value); [DllImport("pdh.dll")] static extern uint PdhCloseQuery(IntPtr query);
}
