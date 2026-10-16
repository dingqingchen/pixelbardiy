using System.Buffers.Binary;
using System.Diagnostics;
using System.IO.MemoryMappedFiles;
using System.Security.Cryptography;
using System.Text.Json;

namespace HaloStudio;

public sealed class CpuTemperature : IDisposable
{
    readonly SemaphoreSlim gate = new(1, 1);
    Session? session;
    Task<Session>? starting;
    long nextAttempt;
    int retry;
    bool elevatedAttempted, disposed;
    public string Detail { get; private set; } = "等待按需采集 CPU 温度";
    static readonly Dictionary<string, string> hashes = new()
    {
        ["HaloThermalTask.exe"] = "57aedf7e11005125cc575539b0f3fb1f5f6b80d3ff80ca3735e0ed44bba69fad",
        ["HaloThermal.exe"] = "6a10ae1d93fead056e819967b661e7b89783bee6770c2bf0bd3ff9a4ee6d1066",
        ["PawnIO_setup.exe"] = "1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032",
        ["AMDFamily17.bin"] = "dae74615761b78bdf064dfb3e136252ddcc6fc727d88f14738d0e5800d427a91"
    };
    static readonly string[] messages = ["温度正常", "等待首个样本", "此 CPU 暂不支持独立直读", "驱动未就绪，请启用独立采集", "需要管理员授权，请点击「授权并重试」", "PCI 访问繁忙", "寄存器读取失败", "辅助进程已结束", "未启用", "已取消权限授权", "辅助文件缺失", "驱动需要重启", "准备驱动", "组件哈希不匹配"];
    public void RequestRetry() => Interlocked.Exchange(ref retry, 1);

    public async Task<double?> ReadAsync(bool enabled = false, bool elevate = false)
    {
        if (disposed || !await gate.WaitAsync(0)) return null;
        try
        {
            if (!enabled)
            {
                session?.Dispose(); session = null;
                if (starting?.IsCompleted == true) { try { (await starting).Dispose(); } catch { } starting = null; }
                Detail = "CPU 温度采集已关闭"; return null;
            }
            if (Interlocked.Exchange(ref retry, 0) != 0)
            {
                session?.Dispose(); session = null; nextAttempt = 0; elevatedAttempted = false;
            }
            if (starting != null)
            {
                if (!starting.IsCompleted) return null;
                try { session = await starting; }
                catch (Exception e) { Detail = e is System.ComponentModel.Win32Exception { NativeErrorCode: 1223 } ? "已取消权限授权，可点击重试" : e.Message; nextAttempt = Environment.TickCount64 + 60000; }
                starting = null;
            }
            if (session?.Process.HasExited == true)
            {
                uint status = session.View.ReadUInt32(36);
                Detail = Status(status == 0 ? 7u : status);
                session.Dispose(); session = null; nextAttempt = Environment.TickCount64 + 60000;
            }
            if (session == null)
            {
                if (Environment.TickCount64 < nextAttempt) return null;
                // Automatic restart tries existing drivers without elevating repeatedly.
                bool requestElevation = elevate && !elevatedAttempted;
                elevatedAttempted |= requestElevation;
                Detail = requestElevation ? "正在准备温度采集（首次可能需要授权）…" : "检查已授权任务或现有温度驱动…";
                starting = Task.Run(() => StartSession(requestElevation));
                return null;
            }
            var s = session;
            s.View.Write(16, (ulong)Environment.TickCount64); s.Request.Set();
            // A previous request may finish late. Accept a coherent, fresh sample
            // instead of requiring it to arrive in the old 15 ms time window.
            byte[] bytes = new byte[80];
            for (int i = 0; i < 20; i++)
            {
                uint before = s.View.ReadUInt32(32);
                s.View.ReadArray(0, bytes, 0, bytes.Length);
                if (before == s.View.ReadUInt32(32) && (before & 1) == 0)
                {
                    uint status = BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(36));
                    Detail = Status(status);
                    if (Decode(bytes, Environment.ProcessId, s.Process.Id, (ulong)Environment.TickCount64) is double value)
                    {
                        Detail = "独立采集正常 · " + (bytes[64] == 1 ? "WinRing0" : "PawnIO") + (bytes[68] == 1 ? "（复用现有驱动）" : "") + (s.Scheduled ? " · 已授权后台任务" : "");
                        return value;
                    }
                    if (status is not (0 or 1 or 12)) return null;
                }
                await Task.Delay(5);
            }
            if (Detail == "温度正常") Detail = "样本已过期，等待下次采集";
            return null;
        }
        finally { gate.Release(); }
    }

    static string Status(uint code) => code < messages.Length ? messages[code] : "未知温度状态 " + code;
    internal static double? Decode(ReadOnlySpan<byte> b, int parent, int helper, ulong now)
    {
        if (b.Length != 80 || !b[..8].SequenceEqual("HALOTC02"u8)) return null;
        // Span cannot be captured by lambdas; the fields below are read explicitly.
        return DecodeFields(b, parent, helper, now);
    }
    static double? DecodeFields(ReadOnlySpan<byte> b, int parent, int helper, ulong now)
    {
        uint version = BinaryPrimitives.ReadUInt32LittleEndian(b[8..]), owner = BinaryPrimitives.ReadUInt32LittleEndian(b[12..]);
        ulong stamp = BinaryPrimitives.ReadUInt64LittleEndian(b[24..]);
        uint seq = BinaryPrimitives.ReadUInt32LittleEndian(b[32..]), status = BinaryPrimitives.ReadUInt32LittleEndian(b[36..]);
        uint raw = BinaryPrimitives.ReadUInt32LittleEndian(b[40..]), family = BinaryPrimitives.ReadUInt32LittleEndian(b[44..]);
        float value = BinaryPrimitives.ReadSingleLittleEndian(b[52..]);
        uint pid = BinaryPrimitives.ReadUInt32LittleEndian(b[56..]), stop = BinaryPrimitives.ReadUInt32LittleEndian(b[60..]);
        uint backend = BinaryPrimitives.ReadUInt32LittleEndian(b[64..]), reused = BinaryPrimitives.ReadUInt32LittleEndian(b[68..]), samples = BinaryPrimitives.ReadUInt32LittleEndian(b[72..]);
        return version == 2 && owner == parent && pid == helper && seq > 0 && (seq & 1) == 0 && status == 0 && stop == 0 &&
            family is 0x17 or 0x19 or 0x1a && raw is not (0 or uint.MaxValue) && backend is 1 or 2 && reused <= 1 && samples > 0 &&
            stamp <= now && now - stamp <= 10000 && float.IsFinite(value) && value is > 0 and <= 150 ? value : null;
    }
    internal static void ValidateNative(string native, bool taskOnly = false)
    {
        foreach (var (name, hash) in hashes)
        {
            if (taskOnly && name == "HaloThermal.exe") continue;
            string path = Path.Combine(native, name);
            if (!File.Exists(path) || Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant() != hash) throw new IOException("温度组件校验失败：" + name);
        }
    }
    static Session StartSession(bool elevate)
    {
        string native = Path.Combine(AppContext.BaseDirectory, "native"); ValidateNative(native);
        if (elevate) ThermalTask.EnsureInstalled();
        bool scheduled = ThermalTask.Ready();
        string exe = Path.Combine(native, "HaloThermal.exe");
        if (!scheduled)
        {
            using var probe = Process.Start(new ProcessStartInfo(exe, "--probe") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true })!;
            if (!probe.WaitForExit(3000)) throw new IOException("温度驱动探测超时");
            using var json = JsonDocument.Parse(probe.StandardOutput.ReadToEnd());
            if (!json.RootElement.GetProperty("supported").GetBoolean()) throw new IOException(Status(2));
            uint status = json.RootElement.GetProperty("status").GetUInt32();
            if (status != 0) throw new IOException(Status(status));
        }
        var result = new Session();
        try
        {
            int pid = Environment.ProcessId; string token = Guid.NewGuid().ToString("N"), prefix = $"Local\\HaloStudioCpu-{pid}-{token}";
            result.Map = MemoryMappedFile.CreateNew(prefix, 80); result.View = result.Map.CreateViewAccessor(0, 80);
            result.View.WriteArray(0, "HALOTC02"u8.ToArray(), 0, 8); result.View.Write(8, 2u); result.View.Write(12, (uint)pid); result.View.Write(36, 1u);
            result.Request = new EventWaitHandle(false, EventResetMode.AutoReset, prefix + "-request");
            if (scheduled)
            {
                if (!ThermalTask.TryRun(pid, token)) throw new IOException("温度后台授权失效，请重新授权");
                long until = Environment.TickCount64 + 8000; uint helper = 0;
                while (helper == 0 && Environment.TickCount64 < until) { helper = result.View.ReadUInt32(56); if (helper == 0) Thread.Sleep(25); }
                if (helper == 0) throw new IOException("温度后台任务启动超时");
                result.Process = Process.GetProcessById(checked((int)helper)); result.Scheduled = true;
            }
            else result.Process = Process.Start(new ProcessStartInfo(exe, $"{pid} {token}") { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden, WorkingDirectory = native }) ?? throw new IOException("无法启动温度采集器");
            result.Request.Set(); return result;
        }
        catch { result.Dispose(); throw; }
    }
    sealed class Session : IDisposable
    {
        public MemoryMappedFile Map = null!; public MemoryMappedViewAccessor View = null!;
        public EventWaitHandle Request = null!; public Process Process = null!; public bool Scheduled;
        public void Dispose()
        {
            try { View?.Write(60, 1u); Request?.Set(); } catch { }
            View?.Dispose(); Map?.Dispose(); Request?.Dispose(); Process?.Dispose();
        }
    }
    public void Dispose()
    {
        disposed = true; session?.Dispose(); session = null;
        if (starting != null) _ = starting.ContinueWith(t => { if (t.Status == TaskStatus.RanToCompletion) t.Result.Dispose(); else _ = t.Exception; }, TaskScheduler.Default);
    }
}
