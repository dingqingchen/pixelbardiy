using Microsoft.Win32;
using System.Diagnostics;

namespace HaloStudio;

public sealed class DeviceOwner : IDisposable
{
    readonly string path = Path.Combine(Path.GetTempPath(), "halo-studio-2d99-a106.lock"); bool acquired;
    public void Acquire()
    {
        for (int attempt = 0; attempt < 2; attempt++) try
            {
                using var f = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read); using var writer = new StreamWriter(f);
                using var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Cryptography"); string machine = key?.GetValue("MachineGuid")?.ToString() ?? "";
                writer.Write($"{Environment.ProcessId}\nHaloStudioNet\n{Environment.MachineName}\n{machine}\n"); acquired = true; return;
            }
            catch (IOException)
            {
                string[] lines; try { lines = File.ReadAllLines(path); } catch { throw new IOException("另一个 HaloStudio 实例正在启动"); }
                if (lines.Length < 3 || lines[2] != Environment.MachineName || !int.TryParse(lines[0], out int pid)) throw new IOException("显示锁来自未知程序，请先退出旧版");
                try { using var p = Process.GetProcessById(pid); if (!p.HasExited) throw new IOException($"HaloStudio 已运行（PID {pid}）；请从托盘正常退出后切换版本"); } catch (ArgumentException) { File.Delete(path); }
            }
        throw new IOException("无法取得显示独占锁");
    }
    public void Dispose() { if (!acquired) return; try { var text = File.ReadAllLines(path); if (text.Length > 0 && text[0] == Environment.ProcessId.ToString()) File.Delete(path); } catch { } acquired = false; }
}
public static class Autostart
{
    const string Run = @"Software\Microsoft\Windows\CurrentVersion\Run"; const string Name = "HaloStudio";
    public static string Command => "\"" + Environment.ProcessPath + "\" --background";
    public static bool Enabled { get { using var k = Registry.CurrentUser.OpenSubKey(Run); return string.Equals(k?.GetValue(Name)?.ToString(), Command, StringComparison.OrdinalIgnoreCase); } }
    public static void Set(bool enabled) { using var k = Registry.CurrentUser.CreateSubKey(Run); if (enabled) k.SetValue(Name, Command, RegistryValueKind.String); else if (Enabled) k.DeleteValue(Name, false); }
}
