using System.IO.MemoryMappedFiles;
using System.Text;

namespace HaloStudio;

/// <summary>
/// Reads RivaTuner Statistics Server shared memory (RTSSSharedMemoryV2) for
/// per-game FPS / frame time. RTSS is the same source MSI Afterburner and
/// HWiNFO use; it needs no elevated helper here and degrades to "--" when RTSS
/// is not running or no 3D application is hooked.
/// </summary>
public sealed class FrameStats : IDisposable
{
    const string MapName = "RTSSSharedMemoryV2";
    const uint Signature = 0x53535452; // 'RTSS'
    const int HeaderSize = 36;
    readonly object gate = new();
    readonly List<double> fpsSamples = [];
    readonly List<double> frameSamples = [];
    readonly System.Threading.Timer timer;
    public double? Fps { get; private set; }
    public double? FrameTimeMs { get; private set; }
    public string Detail { get; private set; } = "RTSS 未运行";

    public FrameStats() { timer = new System.Threading.Timer(_ => Sample(), null, 250, 250); Sample(); }

    public double[] FpsHistory { get { lock (gate) return fpsSamples.ToArray(); } }
    public double[] FrameHistory { get { lock (gate) return frameSamples.ToArray(); } }

    void Sample()
    {
        try
        {
            using var map = MemoryMappedFile.OpenExisting(MapName, MemoryMappedFileRights.Read);
            using var view = map.CreateViewAccessor(0, 0, MemoryMappedFileAccess.Read);
            uint signature = view.ReadUInt32(0);
            if (signature != Signature) { Publish(null, null, "RTSS 共享内存签名无效"); return; }
            uint appEntrySize = view.ReadUInt32(8), appArrOffset = view.ReadUInt32(12), appArrSize = view.ReadUInt32(16);
            if (appEntrySize < 300 || appEntrySize > 65536 || appArrSize == 0 || appArrSize > 4096) { Publish(null, null, "RTSS 布局未知"); return; }
            int count = (int)Math.Min(appArrSize, 256); uint now = unchecked((uint)Environment.TickCount);
            double? bestFps = null, bestFrame = null; uint bestTime = 0; string bestName = "";
            for (int i = 0; i < count; i++)
            {
                long b = appArrOffset + (long)i * appEntrySize;
                uint pid = view.ReadUInt32(b);
                if (pid == 0) continue;
                uint time0 = view.ReadUInt32(b + 268), time1 = view.ReadUInt32(b + 272), frames = view.ReadUInt32(b + 276), frameTime = view.ReadUInt32(b + 280);
                if (time1 == 0 || frames == 0 || unchecked(now - time1) > 3000) continue;
                if (time1 < bestTime && bestTime != 0) continue;
                double? fps = frameTime > 0 ? 1_000_000.0 / frameTime : time1 > time0 ? 1000.0 * frames / (time1 - time0) : null;
                if (fps is not double value || !double.IsFinite(value) || value <= 0 || value > 2000) continue;
                bestTime = time1; bestFps = value; bestFrame = frameTime > 0 ? frameTime / 1000.0 : time1 > time0 ? (time1 - time0) / (double)frames : null;
                bestName = ReadName(view, b + 4);
            }
            Publish(bestFps, bestFrame, bestFps == null ? "RTSS 已运行，等待游戏帧" : "RTSS" + (bestName.Length > 0 ? " · " + bestName : ""));
        }
        catch (FileNotFoundException) { Publish(null, null, "RTSS 未运行"); }
        catch (Exception e) { Publish(null, null, "RTSS 读取失败: " + e.GetType().Name); }
    }

    static string ReadName(MemoryMappedViewAccessor view, long offset)
    {
        var bytes = new byte[260];
        for (int i = 0; i < bytes.Length; i++) bytes[i] = view.ReadByte(offset + i);
        int end = Array.IndexOf(bytes, (byte)0); if (end < 0) end = bytes.Length;
        return Encoding.UTF8.GetString(bytes, 0, end);
    }

    void Publish(double? fps, double? frame, string detail)
    {
        lock (gate)
        {
            Fps = fps; FrameTimeMs = frame; Detail = detail;
            if (fps is double f) { fpsSamples.Add(f); while (fpsSamples.Count > 120) fpsSamples.RemoveAt(0); }
            if (frame is double ms) { frameSamples.Add(Math.Clamp(ms, 0, 1000)); while (frameSamples.Count > 120) frameSamples.RemoveAt(0); }
        }
    }

    public void Dispose() => timer.Dispose();
}
