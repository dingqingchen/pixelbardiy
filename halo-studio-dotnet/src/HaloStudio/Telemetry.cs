using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;

namespace HaloStudio;

// FH6 Data Out, fixed 324-byte little-endian packet. Bytes 232..243 are
// CarGroup / SmashableVelDiff / SmashableMass, NOT position or speed.
public sealed record CarTelemetry(uint Timestamp, bool Driving, float MaxRpm, float IdleRpm,
    float Rpm, float Speed, float Power, float Torque, float Boost, float Fuel,
    float Distance, float RaceTime, byte Throttle, byte Brake, byte Clutch,
    byte Handbrake, byte Gear, sbyte Steer, float SlipFL, float SlipFR, float SlipRL,
    float SlipRR, int Drivetrain, long ReceivedAt)
{
    public double Kmh => Math.Abs(Speed) * 3.6;
    public double RpmRatio => Math.Clamp(Rpm / Math.Max(1, MaxRpm), 0, 1);
    public bool Fresh(long now) => Driving && MaxRpm > 0 && now >= ReceivedAt && now - ReceivedAt < 1500;
    public static bool TryParse(ReadOnlySpan<byte> p, long now, out CarTelemetry? value)
    {
        value = null;
        if (p.Length != 324) return false;
        int driving = BinaryPrimitives.ReadInt32LittleEndian(p);
        if (driving is not (0 or 1)) return false;
        // Only validate consumed fields; unknown/trailing fields are not interpreted.
        foreach (int offset in (ReadOnlySpan<int>)[8,12,16,180,184,188,192,256,260,264,284,288,292,308])
            if (!float.IsFinite(F(p, offset))) return false;
        if (F(p,8) < 0 || F(p,8) > 100000 || F(p,16) < 0 || F(p,16) > 100000 || Math.Abs(F(p,256)) > 1000 || F(p,288) < 0 || F(p,288) > 1.01f || p[319] > 20) return false;
        value = new(BinaryPrimitives.ReadUInt32LittleEndian(p[4..]), driving == 1,
            F(p,8), F(p,12), F(p,16), F(p,256), F(p,260), F(p,264), F(p,284), F(p,288),
            F(p,292), F(p,308), p[315], p[316], p[317], p[318], p[319], unchecked((sbyte)p[320]),
            F(p,180), F(p,184), F(p,188), F(p,192), BinaryPrimitives.ReadInt32LittleEndian(p[224..]), now);
        return true;
    }
    static float F(ReadOnlySpan<byte> p, int offset) => BinaryPrimitives.ReadSingleLittleEndian(p[offset..]);
}

// One latest immutable sample, no packet queue, and no polling while disabled.
// Loopback-only: this feature neither opens a LAN listener nor sends to the game.
public sealed class TelemetryReceiver : IAsyncDisposable
{
    UdpClient? socket; Task? readTask; CancellationTokenSource? stop;
    CarTelemetry? latest; string detail = "遥测接收已关闭";
    long accepted, rejected, retryAt; int port;
    public CarTelemetry? Latest => Volatile.Read(ref latest);
    public string Detail => Volatile.Read(ref detail);
    public long Accepted => Interlocked.Read(ref accepted);
    public long Rejected => Interlocked.Read(ref rejected);
    public static bool ValidPort(int p) => p is >= 1024 and <= 65535 && p is not (>= 5200 and <= 5300);
    public async Task ConfigureAsync(bool enabled, int requestedPort, long now)
    {
        if (!enabled) { if (socket != null) await CloseAsync(); detail = "遥测接收已关闭"; retryAt = 0; return; }
        if (socket != null && port == requestedPort && readTask is { IsCompleted: false }) return;
        if (port != requestedPort) retryAt = 0;
        if (now < retryAt) return;
        await CloseAsync(); port = requestedPort;
        if (!ValidPort(port)) { detail = "端口须为 1024–65535，避开 5200–5300"; retryAt = now + 5000; return; }
        try
        {
            socket = new UdpClient(AddressFamily.InterNetwork);
            socket.ExclusiveAddressUse = true;
            socket.Client.ReceiveBufferSize = 16384;
            socket.Client.Bind(new IPEndPoint(IPAddress.Loopback, port));
            stop = new(); detail = $"等待游戏数据 · 127.0.0.1:{port}";
            readTask = ReceiveAsync(socket, stop.Token);
        }
        catch (SocketException e) { socket?.Dispose(); socket = null; detail = $"无法监听 {port}：{e.SocketErrorCode}（检查端口占用）"; retryAt = now + 5000; }
    }
    async Task ReceiveAsync(UdpClient client, CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                var packet = await client.ReceiveAsync(token); long now = Environment.TickCount64;
                if (!CarTelemetry.TryParse(packet.Buffer, now, out var sample)) { Interlocked.Increment(ref rejected); continue; }
                var previous = Latest;
                // Signed modular subtraction handles the game's uint timestamp wrap.
                // After silence accept a restarted game's new timestamp baseline.
                if (previous != null && now - previous.ReceivedAt < 1500 && unchecked((int)(sample!.Timestamp - previous.Timestamp)) <= 0) continue;
                Volatile.Write(ref latest, sample); Interlocked.Increment(ref accepted);
                detail = $"已收到 {Accepted:N0} 包 · 127.0.0.1:{port}";
            }
        }
        catch (OperationCanceledException) { }
        catch (ObjectDisposedException) { }
        catch (SocketException e) { detail = "遥测接收中断：" + e.SocketErrorCode; }
    }
    async Task CloseAsync()
    {
        stop?.Cancel(); socket?.Dispose(); if (readTask != null) await readTask;
        stop?.Dispose(); stop = null; socket = null; readTask = null; Volatile.Write(ref latest, null);
    }
    public async ValueTask DisposeAsync() => await CloseAsync();
}

public sealed class TelemetrySprint
{
    public const double Duration = 16;
    long start = -1;
    public void Begin() => Interlocked.CompareExchange(ref start, Environment.TickCount64, -1);
    public double Elapsed => Volatile.Read(ref start) is long t && t >= 0 ? (Environment.TickCount64 - t) / 1000.0 : 0;
    public static CarTelemetry At(double seconds, long now = 0)
    {
        double t = Math.Clamp((seconds - 2) / 10, 0, 1), kmh = 100 * Math.Pow(t, .8);
        byte gear = kmh < 38 ? (byte)1 : kmh < 73 ? (byte)2 : (byte)3;
        double rpm = gear switch { 1 => 950 + kmh / 38 * 5600, 2 => 3800 + (kmh - 38) / 35 * 2600, _ => 4100 + (kmh - 73) / 27 * 1900 };
        return new((uint)Math.Max(0, seconds * 1000), true, 7000, 950, (float)rpm, (float)(kmh / 3.6),
            (float)(rpm * 42), 380, seconds is > 2 and < 12 ? 12 : 0, .68f, (float)(seconds * kmh / 7.2),
            (float)Math.Max(0,seconds-2), seconds is > 2 and < 12 ? (byte)255 : (byte)40, 0, 0,
            seconds < 1 ? (byte)255 : (byte)0, gear, 0, .05f,.05f,.15f,.15f, 2, now);
    }
}

public static class TelemetryPriority
{
    public static bool Takeover(bool enabled, bool demo, CarTelemetry? sample, long now) => demo || enabled && sample?.Fresh(now) == true;
}
