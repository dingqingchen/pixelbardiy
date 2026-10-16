using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace HaloStudio;

// One user-approved setup installs only pinned native files into Program Files.
// The normal UI can execute this fixed task, but cannot replace its executable
// or edit its action. No logon trigger or always-running privileged service.
internal static class ThermalTask
{
    const string Arguments = "$(Arg0) $(Arg1)";
    internal static string ProtectedDirectory => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "HaloStudio", "Thermal");
    internal static string ProtectedExe => Path.Combine(ProtectedDirectory, "HaloThermalTask.exe");
    static string Sid { get { using var identity = WindowsIdentity.GetCurrent(); return identity.User!.Value; } }
    static string Name => "Thermal-" + Sid;
    static string Sddl => "O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;" + Sid + ")";

    internal static bool Matches(string path, string arguments, string working, string sid, int logon, int level, int actionCount, int triggerCount) =>
        Path.GetFullPath(path).Equals(ProtectedExe, StringComparison.OrdinalIgnoreCase) && arguments == Arguments &&
        Path.GetFullPath(working).Equals(ProtectedDirectory, StringComparison.OrdinalIgnoreCase) && SameUser(sid) && logon == 3 && level == 1 && actionCount == 1 && triggerCount == 0;

    static bool SameUser(string value) { if (value == Sid) return true; try { return ((SecurityIdentifier)new NTAccount(value).Translate(typeof(SecurityIdentifier))).Value == Sid; } catch (IdentityNotMappedException) { return false; } }
    static bool Valid(dynamic task, ComScope scope)
    {
        dynamic definition = scope.Keep(task.Definition), actions = scope.Keep(definition.Actions), triggers = scope.Keep(definition.Triggers);
        dynamic principal = scope.Keep(definition.Principal), settings = scope.Keep(definition.Settings);
        if ((int)actions.Count != 1 || !(bool)task.Enabled || !(bool)settings.AllowDemandStart) return false;
        dynamic action = scope.Keep(actions.Item(1));
        return (int)action.Type == 0 && Matches((string)action.Path, (string)action.Arguments, (string)action.WorkingDirectory,
            (string)principal.UserId, (int)principal.LogonType, (int)principal.RunLevel, (int)actions.Count, (int)triggers.Count);
    }
    internal static bool Ready()
    {
        try
        {
            CpuTemperature.ValidateNative(ProtectedDirectory, true);
            using var scope = new ComScope(); dynamic service = scope.Service(), folder = scope.Keep(service.GetFolder("\\HaloStudio")), task = scope.Keep(folder.GetTask(Name));
            return Valid(task, scope);
        }
        catch (Exception e) when (e is COMException or IOException or UnauthorizedAccessException or ArgumentException) { return false; }
    }
    internal static bool TryRun(int parent, string token)
    {
        if (!ValidRequest(parent, token)) throw new ArgumentException("Invalid thermal session");
        if (!Ready()) return false;
        using var scope = new ComScope(); dynamic service = scope.Service(), folder = scope.Keep(service.GetFolder("\\HaloStudio")), task = scope.Keep(folder.GetTask(Name));
        if (!Valid(task, scope)) throw new IOException("温度授权任务配置已改变，请重新授权");
        scope.Keep(task.Run(new string[] { parent.ToString(System.Globalization.CultureInfo.InvariantCulture), token }));
        return true;
    }
    internal static bool ValidRequest(int parent, string token) => parent > 0 && token.Length == 32 && token.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');

    internal static void EnsureInstalled()
    {
        if (Ready()) return;
        using var setup = Process.Start(new ProcessStartInfo(Environment.ProcessPath!, "--install-thermal-task")
        { UseShellExecute = true, Verb = "runas", WindowStyle = ProcessWindowStyle.Hidden, WorkingDirectory = AppContext.BaseDirectory }) ?? throw new IOException("无法启动温度授权设置");
        if (!setup.WaitForExit(120000)) throw new IOException("温度授权设置超时，请在系统授权完成后重试");
        if (setup.ExitCode != 0 || !Ready()) throw new IOException("温度后台授权未完成，请点击授权并重试");
    }
    internal static void Install()
    {
        if (!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator)) throw new UnauthorizedAccessException("首次设置需要管理员授权");
        string source = Path.Combine(AppContext.BaseDirectory, "native"); CpuTemperature.ValidateNative(source, true);
        Directory.CreateDirectory(ProtectedDirectory);
        foreach (string path in new[] { Path.GetDirectoryName(ProtectedDirectory)!, ProtectedDirectory })
            if (File.GetAttributes(path).HasFlag(FileAttributes.ReparsePoint)) throw new IOException("温度安装目录不能是链接");
        foreach (string name in new[] { "HaloThermalTask.exe", "PawnIO_setup.exe", "AMDFamily17.bin" })
        {
            string to = Path.Combine(ProtectedDirectory, name);
            if (File.Exists(to) && File.GetAttributes(to).HasFlag(FileAttributes.ReparsePoint)) throw new IOException("温度安装文件不能是链接");
            File.Copy(Path.Combine(source, name), to, true);
        }
        CpuTemperature.ValidateNative(ProtectedDirectory, true);
        using var scope = new ComScope(); dynamic service = scope.Service(), root = scope.Keep(service.GetFolder("\\")), folder;
        try { folder = scope.Keep(service.GetFolder("\\HaloStudio")); }
        catch (Exception e) when (e is COMException or FileNotFoundException or DirectoryNotFoundException) { folder = scope.Keep(root.CreateFolder("HaloStudio", "O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;BU)")); }
        dynamic task = scope.Keep(service.NewTask(0)), principal = scope.Keep(task.Principal), settings = scope.Keep(task.Settings);
        dynamic info = scope.Keep(task.RegistrationInfo), actions = scope.Keep(task.Actions), action = scope.Keep(actions.Create(0));
        info.Description = "HaloStudio 已授权的固定 AMD 温度采集器；按需启动，父进程结束即退出。";
        principal.UserId = Sid; principal.LogonType = 3; principal.RunLevel = 1;
        settings.Enabled = true; settings.Hidden = true; settings.AllowDemandStart = true; settings.ExecutionTimeLimit = "PT0S";
        settings.DisallowStartIfOnBatteries = false; settings.StopIfGoingOnBatteries = false; settings.MultipleInstances = 0;
        action.Path = ProtectedExe; action.WorkingDirectory = ProtectedDirectory; action.Arguments = Arguments;
        scope.Keep(folder.RegisterTaskDefinition(Name, task, 6, Sid, null, 3, Sddl));
    }
    sealed class ComScope : IDisposable
    {
        readonly List<object> objects = [];
        public dynamic Keep(object value) { if (Marshal.IsComObject(value)) objects.Add(value); return value; }
        public dynamic Service() { dynamic s = Keep(Activator.CreateInstance(Type.GetTypeFromProgID("Schedule.Service")!)!); s.Connect(); return s; }
        public void Dispose() { for (int i = objects.Count - 1; i >= 0; i--) try { Marshal.FinalReleaseComObject(objects[i]); } catch { } }
    }
}
