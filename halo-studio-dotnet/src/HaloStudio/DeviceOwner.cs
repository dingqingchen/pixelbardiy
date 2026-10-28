using Microsoft.Win32;
using System.Diagnostics;
using System.Text;

namespace HaloStudio;

public sealed class DeviceOwner : IDisposable
{
    readonly string path;
    FileStream? lease;
    public DeviceOwner() : this(Path.Combine(Path.GetTempPath(), "halo-studio-2d99-a106.lock")) { }
    internal DeviceOwner(string lockPath) { path = lockPath; }

    public void Acquire()
    {
        if (lease != null) throw new InvalidOperationException("显示锁已经取得");
        for (int attempt = 0; attempt < 4; attempt++)
        {
            FileStream file;
            try { file = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.Read); }
            catch (IOException)
            {
                if (!File.Exists(path)) continue;
                string[] lines;
                DateTime modified;
                try
                {
                    modified = File.GetLastWriteTimeUtc(path);
                    using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                    using var reader = new StreamReader(input);
                    lines = reader.ReadToEnd().Split('\n').Select(x => x.TrimEnd('\r')).ToArray();
                }
                catch (FileNotFoundException) { continue; }
                catch (IOException) { throw new IOException("另一个 HaloStudio 实例正在启动或使用音响"); }
                if (lines.Length < 3 || lines[2] != Environment.MachineName || !int.TryParse(lines[0], out int pid) || pid <= 0)
                    throw new IOException("显示锁无法识别，请先退出其他音响控制程序");
                bool stale;
                try
                {
                    using var process = Process.GetProcessById(pid);
                    stale = lines[1] == "HaloStudioNet" && !string.Equals(process.ProcessName, "HaloStudioNet", StringComparison.OrdinalIgnoreCase);
                    if (!stale && lines[1] == "HaloStudioNet")
                    {
                        // Old four-line records must not confuse a recycled PID with this app.
                        stale = !string.Equals(process.ProcessName, "HaloStudioNet", StringComparison.OrdinalIgnoreCase);
                        if (!stale)
                        {
                            long start = process.StartTime.ToUniversalTime().Ticks;
                            stale = DifferentStart(lines, start) || modified.AddSeconds(2).Ticks < start;
                        }
                    }
                }
                catch (ArgumentException) { stale = true; }
                catch (InvalidOperationException) { stale = true; }
                catch (System.ComponentModel.Win32Exception) { throw new IOException($"无法核对显示锁所属进程（PID {pid}），请先退出其他音响控制程序"); }
                if (!stale) throw new IOException($"HaloStudio 已运行（PID {pid}）；请从托盘打开，或正常退出后切换版本");
                // A live new owner retains a handle which denies deletion; never force it closed.
                try { File.Delete(path); }
                catch (IOException) { throw new IOException("显示锁仍被其他进程占用，请先退出其他音响控制程序"); }
                continue;
            }
            try
            {
                using var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Cryptography");
                string machine = key?.GetValue("MachineGuid")?.ToString() ?? "";
                using var process = Process.GetCurrentProcess();
                // Keep Qt's first five fields compatible; our process birth time is an extra field.
                string record = $"{Environment.ProcessId}\nHaloStudioNet\n{Environment.MachineName}\n{machine}\n\nstartUtcTicks={process.StartTime.ToUniversalTime().Ticks}\n";
                file.Write(Encoding.UTF8.GetBytes(record)); file.Flush(true);
                lease = file; return;
            }
            catch { file.Dispose(); File.Delete(path); throw; }
        }
        throw new IOException("无法取得显示独占锁，请稍后重试");
    }

    internal static bool DifferentStart(string[] lines, long actual)
    {
        const string prefix = "startUtcTicks=";
        return lines.Length > 5 && lines[5].StartsWith(prefix, StringComparison.Ordinal) &&
            long.TryParse(lines[5][prefix.Length..], out long expected) && expected != actual;
    }

    public void Dispose()
    {
        var file = lease; if (file == null) return;
        lease = null;
        // Until this point Windows prevents replacement/deletion of our record.
        file.Dispose();
        try { File.Delete(path); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }
}
