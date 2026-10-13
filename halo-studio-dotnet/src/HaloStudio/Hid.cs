using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using System.Threading.Channels;

namespace HaloStudio;

public sealed record DeviceInfo(string Path, string Serial, ushort UsagePage, ushort Usage, ushort InputLength, ushort OutputLength);
public interface IHaloTransport : IAsyncDisposable
{
    long Writes { get; }
    Task<byte[]> QueryAsync(byte command, byte[] payload, CancellationToken cancellation = default);
    Task WriteAsync(byte command, byte[] payload, CancellationToken cancellation = default);
}
public sealed class HidTransport : IHaloTransport
{
    static readonly Guid HidGuid = new("4D1E55B2-F16F-11CF-88CB-001111000030");
    readonly FileStream input, output;
    readonly CancellationTokenSource close = new();
    readonly Channel<byte[]> reports = Channel.CreateBounded<byte[]>(new BoundedChannelOptions(64) { FullMode = BoundedChannelFullMode.DropOldest, SingleReader = true, SingleWriter = true });
    readonly SemaphoreSlim writer = new(1, 1), query = new(1, 1);
    readonly Task reader;
    long lastWrite; byte lastCommand;
    public long Writes { get; private set; }
    public bool Owned { get; set; }
    public bool Authorized { get; set; }
    public bool CodecEnabled { get; set; }
    public bool LiveColorEnabled { get; set; }
    public HidTransport(DeviceInfo info)
    {
        var h = Native.CreateFile(info.Path, 0x80000000, 3, IntPtr.Zero, 3, 0x40000000, IntPtr.Zero);
        if (h.IsInvalid) throw new IOException("无法打开 HID", Marshal.GetExceptionForHR(Marshal.GetHRForLastWin32Error()));
        var writeHandle = Native.CreateFile(info.Path, 0x40000000, 3, IntPtr.Zero, 3, 0x40000000, IntPtr.Zero);
        if (writeHandle.IsInvalid) { h.Dispose(); throw new IOException("无法打开 HID 输出", Marshal.GetExceptionForHR(Marshal.GetHRForLastWin32Error())); }
        // Separate unbuffered handles: a pending HID read must never hold the FileStream
        // buffer lock needed by the request that will produce its response.
        input = new FileStream(h, FileAccess.Read, 1, true);
        output = new FileStream(writeHandle, FileAccess.Write, 1, true);
        Native.HidD_FlushQueue(h); reader = ReadLoop(info.InputLength);
    }
    async Task ReadLoop(int length)
    {
        try
        {
            while (!close.IsCancellationRequested)
            {
                byte[] buffer = new byte[length]; int n = await input.ReadAsync(buffer, close.Token);
                if (n == 0) throw new IOException("音响 USB 已断开"); if (n != buffer.Length) Array.Resize(ref buffer, n); await reports.Writer.WriteAsync(buffer, close.Token);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception e) { reports.Writer.TryComplete(e); return; }
        reports.Writer.TryComplete();
    }
    void Guard(byte cmd, byte[] data)
    {
        if (cmd is not (0x17 or 0x66 or 0x6A or 0x6B or 0xEE or 0xEF or 0xC6)) throw new InvalidOperationException("禁止非 RAM 显示/灯光指令");
        if (cmd == 0xEF && Owned) throw new InvalidOperationException("必须先释放 MCU 显示权");
        if (cmd == 0x17 && data.Length >= 17 && data[8] == 6 && data[16] != 12 && !(LiveColorEnabled && data[16] == 15)) throw new InvalidOperationException("MCU 未验证帧内换色能力");
        if (cmd == 0x17 && (!Authorized || data.Length < 17 || !data.AsSpan(0, 8).SequenceEqual(new byte[] { 0, 2, 255, 255, 72, 80, 76, 50 }) || data[8] < 1 || data[8] > (CodecEnabled ? 7 : 5) || data.Length != 17 + data[16]))
            throw new InvalidOperationException("已阻止资源上传或非 HPL2 写入");
    }
    public async Task WriteAsync(byte command, byte[] payload, CancellationToken cancellation = default)
    {
        Guard(command, payload);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation, close.Token); timeout.CancelAfter(1500);
        await writer.WaitAsync(timeout.Token);
        try
        {
            if (command == 0x6B || lastCommand == 0x6B) { int gap = 7 - (int)(Environment.TickCount64 - lastWrite); if (gap > 0) await Task.Delay(gap, cancellation); }
            byte[] p = Protocol.Packet(command, payload); for (int i = 0; ; i++)
            {
                try { await output.WriteAsync(p, timeout.Token); break; }
                catch (IOException) when (command == 0x6B && i < 2) { await Task.Delay(8 * (i + 1), cancellation); }
            }
            lastWrite = Environment.TickCount64; lastCommand = command; Writes++;
        }
        finally { writer.Release(); }
    }
    public async Task<byte[]> QueryAsync(byte command, byte[] payload, CancellationToken cancellation = default)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation, close.Token); timeout.CancelAfter(1500);
        await query.WaitAsync(timeout.Token);
        try
        {
            while (reports.Reader.TryRead(out _)) { } // one query owns the input queue
            try { await WriteAsync(command, payload, timeout.Token); while (true) { var p = await reports.Reader.ReadAsync(timeout.Token); if (p.Length >= 4 && p[0] == 0x2F && p[3] == command) return Protocol.Response(p, command); } }
            catch (OperationCanceledException) when (!cancellation.IsCancellationRequested && !close.IsCancellationRequested) { throw new TimeoutException($"音响响应超时 0x{command:X2}"); }
        }
        finally { query.Release(); }
    }
    public async ValueTask DisposeAsync()
    {
        close.Cancel(); input.Dispose(); output.Dispose(); try { await reader; } catch { }
        close.Dispose(); writer.Dispose(); query.Dispose();
    }
    public static List<DeviceInfo> Enumerate()
    {
        var result = new List<DeviceInfo>(); Guid guid = HidGuid; IntPtr set = Native.SetupDiGetClassDevs(ref guid, null, IntPtr.Zero, 0x12);
        if (set == new IntPtr(-1)) return result;
        try
        {
            for (uint index = 0; ; index++)
            {
                var iface = new Native.InterfaceData { Size = Marshal.SizeOf<Native.InterfaceData>() };
                if (!Native.SetupDiEnumDeviceInterfaces(set, IntPtr.Zero, ref guid, index, ref iface)) break;
                Native.SetupDiGetDeviceInterfaceDetail(set, ref iface, IntPtr.Zero, 0, out uint required, IntPtr.Zero);
                IntPtr detail = Marshal.AllocHGlobal((int)required);
                try
                {
                    Marshal.WriteInt32(detail, IntPtr.Size == 8 ? 8 : 6);
                    if (!Native.SetupDiGetDeviceInterfaceDetail(set, ref iface, detail, required, out _, IntPtr.Zero)) continue;
                    string path = Marshal.PtrToStringUni(detail + 4) ?? "";
                    if (!path.Contains("vid_2d99&pid_a106", StringComparison.OrdinalIgnoreCase) || !path.Contains("mi_04", StringComparison.OrdinalIgnoreCase)) continue;
                    using var h = Native.CreateFile(path, 0, 3, IntPtr.Zero, 3, 0, IntPtr.Zero); if (h.IsInvalid) continue;
                    var attributes = new Native.Attributes { Size = Marshal.SizeOf<Native.Attributes>() };
                    if (!Native.HidD_GetAttributes(h, ref attributes) || attributes.Vid != 0x2D99 || attributes.Pid != 0xA106) continue;
                    if (!Native.HidD_GetPreparsedData(h, out IntPtr preparsed)) continue;
                    try
                    {
                        if (Native.HidP_GetCaps(preparsed, out var caps) != 0x110000 || caps.UsagePage != 0xFF14 || caps.Usage != 1 || caps.OutputReportByteLength != 64 || caps.InputReportByteLength != 64) continue;
                        byte[] serial = new byte[256]; Native.HidD_GetSerialNumberString(h, serial, serial.Length);
                        result.Add(new(path, System.Text.Encoding.Unicode.GetString(serial).TrimEnd('\0'), caps.UsagePage, caps.Usage, caps.InputReportByteLength, caps.OutputReportByteLength));
                    }
                    finally { Native.HidD_FreePreparsedData(preparsed); }
                }
                finally { Marshal.FreeHGlobal(detail); }
            }
        }
        finally { Native.SetupDiDestroyDeviceInfoList(set); }
        return result;
    }
    static class Native
    {
        [StructLayout(LayoutKind.Sequential)] internal struct InterfaceData { public int Size; public Guid Guid; public int Flags; public IntPtr Reserved; }
        [StructLayout(LayoutKind.Sequential)] internal struct Attributes { public int Size; public ushort Vid, Pid, Version; }
        [StructLayout(LayoutKind.Sequential)] internal struct Caps { public ushort Usage, UsagePage, InputReportByteLength, OutputReportByteLength, FeatureReportByteLength; [MarshalAs(UnmanagedType.ByValArray, SizeConst = 17)] public ushort[] Reserved; public ushort LinkNodes, InputButtons, InputValues, InputIndices, OutputButtons, OutputValues, OutputIndices, FeatureButtons, FeatureValues, FeatureIndices; }
        [DllImport("kernel32.dll", EntryPoint = "CreateFileW", CharSet = CharSet.Unicode, SetLastError = true)] internal static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("setupapi.dll", EntryPoint = "SetupDiGetClassDevsW", CharSet = CharSet.Unicode)] internal static extern IntPtr SetupDiGetClassDevs(ref Guid guid, string? enumerator, IntPtr parent, uint flags);
        [DllImport("setupapi.dll")] internal static extern bool SetupDiEnumDeviceInterfaces(IntPtr set, IntPtr device, ref Guid guid, uint index, ref InterfaceData data);
        [DllImport("setupapi.dll", EntryPoint = "SetupDiGetDeviceInterfaceDetailW", SetLastError = true)] internal static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr set, ref InterfaceData data, IntPtr detail, uint size, out uint needed, IntPtr device);
        [DllImport("setupapi.dll")] internal static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
        [DllImport("hid.dll")] internal static extern bool HidD_GetAttributes(SafeFileHandle h, ref Attributes attributes);
        [DllImport("hid.dll")] internal static extern bool HidD_GetSerialNumberString(SafeFileHandle h, byte[] serial, int size);
        [DllImport("hid.dll")] internal static extern bool HidD_GetPreparsedData(SafeFileHandle h, out IntPtr data);
        [DllImport("hid.dll")] internal static extern bool HidD_FreePreparsedData(IntPtr data);
        [DllImport("hid.dll")] internal static extern int HidP_GetCaps(IntPtr data, out Caps caps);
        [DllImport("hid.dll")] internal static extern bool HidD_FlushQueue(SafeFileHandle h);
    }
}
