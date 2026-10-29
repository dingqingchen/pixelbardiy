using System.Diagnostics;
using System.Runtime.InteropServices;

namespace HaloStudio;

public sealed class Hardware : IDisposable
{
    public CpuTemperature Temperature { get; } = new();
    public FrameStats Frames { get; } = new();
    ulong priorIdle, priorKernel, priorUser; readonly NetworkSampler network = new();
    readonly Dictionary<string, Queue<double>> history = [];
    IntPtr nv; IntPtr gpu; bool nvTried; object? wmi; long nextWmi; readonly CounterSet counters = new();
    public async Task<Snapshot> SampleAsync(Dictionary<string, double> limits, bool temperatureEnabled = false, bool temperatureElevation = false)
    {
        var rows = new List<Metric>(); void Add(string key, string name, string shortName, double? value, string unit, string source, double? scale = null) => rows.Add(new(key, name, shortName, value, unit, source, scale));
        Native.GetSystemTimes(out ulong idle, out ulong kernel, out ulong user); ulong total = kernel - priorKernel + user - priorUser; double? cpu = priorKernel == 0 || total == 0 ? null : 100.0 * (total - (idle - priorIdle)) / total; priorIdle = idle; priorKernel = kernel; priorUser = user;
        Add("cpu", "CPU 使用率", "CPU", cpu, "%", "Windows GetSystemTimes", 100);
        var mem = new Native.MemoryStatus { Length = (uint)Marshal.SizeOf<Native.MemoryStatus>() }; Native.GlobalMemoryStatusEx(ref mem);
        Add("ram", "内存使用率", "RAM", 100.0 * (mem.TotalPhys - mem.AvailPhys) / mem.TotalPhys, "%", "Windows", 100);
        Add("ram_gb", "已用物理内存", "RAM", (mem.TotalPhys - mem.AvailPhys) / Math.Pow(1024, 3), "GB", "Windows");
        var countersNow = counters.Read(); Add("disk_read", "磁盘读取", "READ", countersNow.GetValueOrDefault("disk_read"), "B/s", "Windows PDH"); Add("disk_write", "磁盘写入", "WRITE", countersNow.GetValueOrDefault("disk_write"), "B/s", "Windows PDH");
        Add("frequency", "CPU 报告频率", "CPU", countersNow.GetValueOrDefault("frequency") / 1000, "GHz", "Windows Processor Information（非精确核心时钟）");
        var rate = network.Read();
        Add("upload", "网络上传", "UP", rate.Upload, "B/s", rate.Source);
        Add("download", "网络下载", "DN", rate.Download, "B/s", rate.Source);
        InitNv(); if (gpu != IntPtr.Zero)
        {
            var util = Get<NvUtil>("nvmlDeviceGetUtilizationRates"); NvUtilization utilization = default; double? usage = util != null && util(gpu, out utilization) == 0 ? utilization.Gpu : null;
            Add("gpu0", "显卡使用率", "GPU", usage, "%", "NVIDIA NVML", 100); Add("gpu0_temp", "显卡温度", "GPU", NvNumber("nvmlDeviceGetTemperature", true), "C", "NVIDIA NVML", 100);
            var power = NvNumber("nvmlDeviceGetPowerUsage"); Add("gpu0_power", "显卡功耗", "GPU", power / 1000, "W", "NVIDIA NVML");
            var memoryGet = Get<NvMemory>("nvmlDeviceGetMemoryInfo"); NvMemoryInfo memory;
            if (memoryGet != null && memoryGet(gpu, out memory) == 0 && memory.Total > 0)
            {
                Add("gpu0_vram", "显存使用率", "VRAM", 100.0 * memory.Used / memory.Total, "%", "NVIDIA NVML", 100);
                Add("gpu0_vram_gb", "显存占用", "VRAM", memory.Used / Math.Pow(1024, 3), "GB", "NVIDIA NVML");
            }
            var clockGet = Get<NvClock>("nvmlDeviceGetClockInfo"); uint coreClock = 0, memoryClock = 0;
            if (clockGet != null && clockGet(gpu, 0, out coreClock) == 0) Add("gpu0_clock", "显卡核心频率", "GPU", coreClock / 1000.0, "GHz", "NVIDIA NVML");
            if (clockGet != null && clockGet(gpu, 2, out memoryClock) == 0) Add("gpu0_mem_clock", "显存频率", "VRAM", memoryClock / 1000.0, "GHz", "NVIDIA NVML");
            var fans = NvNumber("nvmlDeviceGetNumFans"); for (uint i = 0; i < (fans ?? 0); i++)
            {
                var speed = Get<NvFan>("nvmlDeviceGetFanSpeed_v2"); uint percent = 0; double? driver = speed != null && speed(gpu, i, out percent) == 0 ? percent : null;
                var rpmGet = Get<NvRpm>("nvmlDeviceGetFanSpeedRPM"); var data = new FanInfo { Version = (uint)Marshal.SizeOf<FanInfo>() | (1u << 24), Fan = i }; double? rpm = rpmGet != null && rpmGet(gpu, ref data) == 0 ? data.Speed : null;
                string key = $"gpu0_fan{i}"; Add(key, $"GPU 风扇 {i + 1}", $"FAN{i + 1}", rpm, "RPM", "NVML 实测 RPM"); Add(key + "_percent", "驱动目标转速比例", $"F{i + 1}DRV", driver, "%", "NVML 驱动目标比例，非 RPM/最大值", 100);
                if (limits.TryGetValue(key, out double max) && max > 0 && rpm != null) Add(key + "_rated", "风扇/额定最大转速", $"F{i + 1}MAX", 100 * rpm / max, "%", "RPM / 用户额定最大转速", 100);
            }
        }
        ReadWmi(rows, limits, Environment.TickCount64);
        var existingCpu = rows.FirstOrDefault(m => m.Unit == "C" && m.Short == "CPU" && m.Value is > 0 and <= 150);
        // Keep the stable key consumed by every theme, even when WMI supplies the value.
        double? cpuTemperature = existingCpu?.Value ?? await Temperature.ReadAsync(temperatureEnabled, temperatureElevation);
        Add("cpu_temp", "CPU 温度 Tctl/Tdie", "CPU", cpuTemperature, "C", existingCpu?.Source ?? Temperature.Detail, 100);
        Add("fps", "游戏帧率", "FPS", Frames.Fps, "", "RTSS 实时帧率");
        Add("frametime", "帧生成时间", "FT", Frames.FrameTimeMs, "ms", "RTSS 帧时间");
        for (int i = 0; i < rows.Count; i++) { var m = rows[i]; if (m.Key is "fps" or "frametime") continue; if (m.Value is double value) { if (!history.TryGetValue(m.Key, out var q)) history[m.Key] = q = new(); q.Enqueue(value); while (q.Count > 24) q.Dequeue(); rows[i] = m with { History = q.ToArray() }; } }
        for (int i = 0; i < rows.Count; i++) rows[i] = rows[i].Key switch
        {
            "fps" => rows[i] with { History = Frames.FpsHistory.TakeLast(24).ToArray() },
            "frametime" => rows[i] with { History = Frames.FrameHistory.TakeLast(24).ToArray() },
            _ => rows[i]
        };
        return new(rows.ToArray(), "Windows CPU / 内存 / 网络；GPU / 显存 / 风扇 NVML；帧率：" + Frames.Detail + "；温度：" + Temperature.Detail);
    }
    void InitNv()
    {
        if (nvTried) return; nvTried = true; string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "nvml.dll"); if (!NativeLibrary.TryLoad(path, out nv)) return;
        if (Get<NvInit>("nvmlInit_v2")?.Invoke() != 0) return; Get<NvHandle>("nvmlDeviceGetHandleByIndex_v2")?.Invoke(0, out gpu);
    }
    T? Get<T>(string symbol) where T : Delegate => nv != IntPtr.Zero && NativeLibrary.TryGetExport(nv, symbol, out var p) ? Marshal.GetDelegateForFunctionPointer<T>(p) : null;
    double? NvNumber(string symbol, bool temperature = false) { uint value = 0; int? result = temperature ? Get<NvTemperature>(symbol)?.Invoke(gpu, 0, out value) : Get<NvNumberFn>(symbol)?.Invoke(gpu, out value); return result == 0 ? value : null; }
    void ReadWmi(List<Metric> rows, Dictionary<string, double> limits, long now)
    {
        if (wmi == null && now >= nextWmi) { nextWmi = now + 30000; try { var type = Type.GetTypeFromProgID("WbemScripting.SWbemLocator"); if (type != null) { dynamic locator = Activator.CreateInstance(type)!; foreach (string space in new[] { @"root\LibreHardwareMonitor", @"root\OpenHardwareMonitor" }) try { wmi = locator.ConnectServer(".", space); break; } catch { } Marshal.FinalReleaseComObject(locator); } } catch { } }
        if (wmi == null) return; try
        {
            dynamic service = wmi; dynamic sensors = service.ExecQuery("SELECT Identifier,Name,SensorType,Value FROM Sensor WHERE SensorType='Temperature' OR SensorType='Fan'", "WQL", 0x30);
            foreach (dynamic sensor in sensors)
            {
                try
                {
                    if (sensor.Value == null) continue; string id = sensor.Identifier, key = "lhm:" + id, kind = sensor.SensorType, name = sensor.Name; double value = Convert.ToDouble(sensor.Value);
                    if (kind == "Temperature") rows.Add(new(key, name, id.Contains("cpu", StringComparison.OrdinalIgnoreCase) ? "CPU" : "TEMP", value, "C", "现有硬件监控 WMI", 100));
                    else { rows.Add(new(key, name, "FAN", value, "RPM", "现有硬件监控 WMI")); if (limits.TryGetValue(key, out double max) && max > 0) rows.Add(new(key + "_rated", name + " / 额定", "FANMAX", 100 * value / max, "%", "RPM / 用户额定最大转速", 100)); }
                }
                finally { Marshal.FinalReleaseComObject(sensor); }
            }
            Marshal.FinalReleaseComObject(sensors);
        }
        catch { try { Marshal.FinalReleaseComObject(wmi); } catch { } wmi = null; }
    }
    public void Dispose() { Temperature.Dispose(); Frames.Dispose(); counters.Dispose(); if (wmi != null) Marshal.FinalReleaseComObject(wmi); if (nv != IntPtr.Zero) { Get<NvInit>("nvmlShutdown")?.Invoke(); NativeLibrary.Free(nv); nv = IntPtr.Zero; } }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvInit(); [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvHandle(uint i, out IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvNumberFn(IntPtr h, out uint v); [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvTemperature(IntPtr h, uint sensor, out uint v);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvUtil(IntPtr h, out NvUtilization v); [StructLayout(LayoutKind.Sequential)] struct NvUtilization { public uint Gpu, Memory; }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvFan(IntPtr h, uint fan, out uint v); [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvRpm(IntPtr h, ref FanInfo v); [StructLayout(LayoutKind.Sequential)] struct FanInfo { public uint Version, Fan, Speed; }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvMemory(IntPtr h, out NvMemoryInfo v); [StructLayout(LayoutKind.Sequential)] struct NvMemoryInfo { public ulong Total, Free, Used; }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int NvClock(IntPtr h, uint type, out uint v);
    static class Native
    {
        [StructLayout(LayoutKind.Sequential)] internal struct MemoryStatus { public uint Length, Load; public ulong TotalPhys, AvailPhys, TotalPage, AvailPage, TotalVirtual, AvailVirtual, AvailExtended; }
        [DllImport("kernel32.dll")] internal static extern bool GlobalMemoryStatusEx(ref MemoryStatus s); [DllImport("kernel32.dll")] internal static extern bool GetSystemTimes(out ulong idle, out ulong kernel, out ulong user);
    }
}
