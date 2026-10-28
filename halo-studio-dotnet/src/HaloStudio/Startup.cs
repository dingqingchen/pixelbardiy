using Microsoft.Win32;
using System.Diagnostics;

namespace HaloStudio;

public static class Autostart
{
    const string Run = @"Software\Microsoft\Windows\CurrentVersion\Run"; const string Name = "HaloStudio";
    public static string Command => "\"" + Environment.ProcessPath + "\" --background";
    public static bool Enabled { get { using var k = Registry.CurrentUser.OpenSubKey(Run); return string.Equals(k?.GetValue(Name)?.ToString(), Command, StringComparison.OrdinalIgnoreCase); } }
    public static void Set(bool enabled) { using var k = Registry.CurrentUser.CreateSubKey(Run); if (enabled) k.SetValue(Name, Command, RegistryValueKind.String); else if (Enabled) k.DeleteValue(Name, false); }
}
