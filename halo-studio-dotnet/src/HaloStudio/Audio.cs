using System.Diagnostics;
using System.Runtime.InteropServices;

namespace HaloStudio;

public sealed class MusicPeak : IDisposable
{
    readonly List<IAudioMeter> meters = []; readonly List<IAudioSessionControl> controls = []; long nextFind; public bool Playing { get; private set; }
    public string Detail { get; private set; } = "等待音频会话"; readonly List<string> failures = [];
    public double Read()
    {
        long now = Environment.TickCount64; if (now >= nextFind) { Clear(); failures.Clear(); nextFind = now + 3000; Find(); Detail = $"网易云会话 {controls.Count}" + (failures.Count > 0 ? " · " + string.Join(" | ", failures.Take(3)) : ""); }
        try { Playing=false;foreach(var control in controls){control.GetState(out int state);Playing|=state==1;}float peak = 0; foreach (var meter in meters) { meter.GetPeakValue(out float value); peak = Math.Max(peak, value); } return peak; } catch (Exception e) { Detail = e.Message; Clear(); nextFind = 0; return 0; }
    }
    void Find()
    {
        object? enumerator = null; IMMDeviceCollection? endpoints = null;
        try
        {
            enumerator = Activator.CreateInstance(Type.GetTypeFromCLSID(new("BCDE0395-E52F-467C-8E3D-C4579291692E"))!); var deviceEnumerator = (IMMDeviceEnumerator)enumerator!; deviceEnumerator.EnumAudioEndpoints(0, 1, out endpoints); endpoints.GetCount(out uint count); Playing = false;
            for (uint i = 0; i < count; i++)
            {
                IMMDevice? endpoint = null; object? manager = null; IAudioSessionEnumerator? sessions = null;
                try
                {
                    endpoints.Item(i, out endpoint); Guid iid = typeof(IAudioSessionManager).GUID; endpoint.Activate(ref iid, 23, IntPtr.Zero, out manager); ((IAudioSessionManager)manager).GetSessionEnumerator(out sessions); sessions.GetCount(out int n);
                    for (int j = 0; j < n; j++)
                    {
                        IAudioSessionControl? ctl = null; try
                        {
                            sessions.GetSession(j, out ctl); var ctl2 = (IAudioSessionControl2)ctl; ctl2.GetProcessId(out uint pid);
                            if (pid == 0) continue; using var p = Process.GetProcessById((int)pid); if (p.ProcessName.Equals("cloudmusic", StringComparison.OrdinalIgnoreCase)) { ctl.GetState(out int state); Playing |= state == 1; meters.Add((IAudioMeter)ctl); controls.Add(ctl); ctl = null; }
                        }
                        catch (Exception e) { failures.Add(e.GetType().Name + ": " + e.Message); }
                        finally { if (ctl != null) Marshal.ReleaseComObject(ctl); }
                    }
                }
                catch (Exception e) { failures.Add(e.GetType().Name + ": " + e.Message); }
                finally { if (sessions != null) Marshal.ReleaseComObject(sessions); if (manager != null) Marshal.ReleaseComObject(manager); if (endpoint != null) Marshal.ReleaseComObject(endpoint); }
            }
        }
        catch (Exception e) { failures.Add(e.GetType().Name + ": " + e.Message); }
        finally { if (endpoints != null) Marshal.ReleaseComObject(endpoints); if (enumerator != null) Marshal.ReleaseComObject(enumerator); }
    }
    void Clear() { foreach (var control in controls) try { Marshal.ReleaseComObject(control); } catch (Exception e) { failures.Add(e.GetType().Name + ": " + e.Message); } controls.Clear();meters.Clear(); }
    public void Dispose() => Clear();
    [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IMMDeviceEnumerator { void EnumAudioEndpoints(int flow, uint mask, out IMMDeviceCollection devices); void GetDefaultAudioEndpoint(int flow, int role, out IMMDevice device); void GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IMMDevice device); void RegisterEndpointNotificationCallback(IntPtr callback); void UnregisterEndpointNotificationCallback(IntPtr callback); }
    [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IMMDeviceCollection { void GetCount(out uint count); void Item(uint index, out IMMDevice device); }
    [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IMMDevice { void Activate(ref Guid iid, uint context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object value); void OpenPropertyStore(uint access, out IntPtr store); void GetId([MarshalAs(UnmanagedType.LPWStr)] out string id); void GetState(out uint state); }
    [ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IAudioSessionManager { void GetAudioSessionControl(IntPtr guid, uint flags, out IntPtr control); void GetSimpleAudioVolume(IntPtr guid, uint flags, out IntPtr volume); void GetSessionEnumerator(out IAudioSessionEnumerator enumerator); void RegisterSessionNotification(IntPtr callback); void UnregisterSessionNotification(IntPtr callback); void RegisterDuckNotification(IntPtr id, IntPtr callback); void UnregisterDuckNotification(IntPtr callback); }
    [ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IAudioSessionEnumerator { void GetCount(out int count); void GetSession(int index, out IAudioSessionControl session); }
    [ComImport, Guid("F4B1A599-7266-4319-A8CA-E70ACB11E8CD"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IAudioSessionControl { void GetState(out int state); void GetDisplayName(out IntPtr name); void SetDisplayName(IntPtr name, IntPtr context); void GetIconPath(out IntPtr path); void SetIconPath(IntPtr path, IntPtr context); void GetGroupingParam(out Guid guid); void SetGroupingParam(ref Guid guid, IntPtr context); void RegisterAudioSessionNotification(IntPtr callback); void UnregisterAudioSessionNotification(IntPtr callback); }
    [ComImport, Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IAudioSessionControl2 { void GetState(out int state); void GetDisplayName(out IntPtr name); void SetDisplayName(IntPtr name, IntPtr context); void GetIconPath(out IntPtr path); void SetIconPath(IntPtr path, IntPtr context); void GetGroupingParam(out Guid guid); void SetGroupingParam(ref Guid guid, IntPtr context); void RegisterAudioSessionNotification(IntPtr callback); void UnregisterAudioSessionNotification(IntPtr callback); void GetSessionIdentifier(out IntPtr id); void GetSessionInstanceIdentifier(out IntPtr id); void GetProcessId(out uint pid); [PreserveSig] int IsSystemSoundsSession(); void SetDuckingPreference(bool optOut); }
    [ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] interface IAudioMeter { void GetPeakValue(out float value); void GetMeteringChannelCount(out uint count); void GetChannelsPeakValues(uint count, IntPtr values); void QueryHardwareSupport(out uint mask); }
}
public sealed class Envelope
{
    readonly Queue<(double Time, double Peak)> history = new(); double level, last;
    public double Update(double peak, double time, double gain = 2.5)
    {
        peak = Math.Clamp(peak, 0, 1); if (history.Count == 0 || time - history.Last().Time >= .04) history.Enqueue((time, peak)); while (history.Count > 0 && time - history.Peek().Time > 4) history.Dequeue();
        var values = history.Select(p => p.Peak).Order().ToArray(); double low = values[(int)((values.Length - 1) * .15)], high = values[(int)((values.Length - 1) * .9)]; double target;
        if (peak < .002) target = 0; else if (values.Length < 8) target = Math.Min(.8, peak / (Math.Max(.1, high) * 1.3)); else target = Math.Clamp((Math.Clamp((peak - low) / Math.Max(.025, high - low), 0, 1) - .5) * Math.Max(.4, gain / 2.5) + .5, 0, 1);
        double dt = last == 0 ? .2 : Math.Max(0, time - last), weight = 1 - Math.Exp(-dt / (target > level ? .035 : .12)); level += (target - level) * weight; last = time; return level;
    }
    public static string ColorFor(string baseColor, string accent, double value, string style)
    {
        value = Math.Round(Math.Clamp(value, 0, 1) * 64) / 64; if (style == "beat") value = value > .55 ? 1 : .12; Color b = ColorTranslator.FromHtml(baseColor), a = ColorTranslator.FromHtml(accent);
        double blend = style == "color" ? value : 0, bright = .06 + .94 * value; return $"#{(int)Math.Round((b.R * (1 - blend) + a.R * blend) * bright):X2}{(int)Math.Round((b.G * (1 - blend) + a.G * blend) * bright):X2}{(int)Math.Round((b.B * (1 - blend) + a.B * blend) * bright):X2}";
    }
}
