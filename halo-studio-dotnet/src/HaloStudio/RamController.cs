using System.Security.Cryptography;

namespace HaloStudio;

public sealed class RamController : IAsyncDisposable
{
    readonly IHaloTransport link; readonly bool codec, fullAnimation, localRain, liveColor; readonly object gate = new();
    PixelFrame? target, committed; byte animation, interval = 16; bool urgent; string color; uint sid; long colorChanged;
    ushort frame, committedId; long heartbeat; string restoreColor = "#86D8F6"; bool touched;
    public bool Owned { get; private set; }
    public long Frames { get; private set; }
    public long Dropped { get; private set; }
    public string Codec { get; private set; } = "raw"; public int EncodedBytes { get; private set; } = 1024;
    public double FrameSeconds { get; private set; }
    public RamController(IHaloTransport transport, bool useCodec, string screenColor, bool useFullAnimation = false, bool useLocalRain = false, bool useLiveColor = false) { link = transport; codec = useCodec; fullAnimation = useCodec && useFullAnimation; localRain = fullAnimation && useLocalRain; liveColor = localRain && useLiveColor; color = screenColor; }
    public static (bool Codec, bool FullAnimation, bool LocalRain, bool LiveColor) Capabilities(string? sha) => sha switch
    {
        Protocol.ColorSha => (true, true, true, true),
        Protocol.MatrixSha => (true, true, true, false),
        Protocol.FullscreenSha => (true, true, false, false),
        Protocol.FirmwareSha => (true, false, false, false),
        Protocol.LegacySha => (false, false, false, false),
        _ => throw new InvalidOperationException("未识别的 MCU 固件验证记录")
    };
    public static (bool Codec, bool FullAnimation, bool LocalRain, bool LiveColor) ValidateInstallation(string path, DeviceInfo d)
    {
        using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(path)); var r = doc.RootElement;
        string? sha = r.GetProperty("candidate_sha256").GetString();
        var capabilities = Capabilities(sha);
        if (!r.GetProperty("graphics_visually_confirmed").GetBoolean() ||
            r.GetProperty("serial").GetString() != d.Serial || !string.Equals(r.GetProperty("hid_path").GetString(), d.Path, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("音响与本机 MCU 验证记录不一致，请导入已验证记录"); return capabilities;
    }
    static uint NewSid() { uint v = BitConverter.ToUInt32(RandomNumberGenerator.GetBytes(4)); return v == 0 ? 1 : v; }
    void MarkOwned(bool value) { Owned = value; if (link is HidTransport hid) hid.Owned = value; }
    async Task Control(byte op) { Check(await link.QueryAsync(0x17, Protocol.Body(op, sid)), op == 5); heartbeat = Environment.TickCount64 + 500; }
    static void Check(byte[] ack, bool final = false) { if (!ack.AsSpan().SequenceEqual(final ? new byte[] { 0, 5 } : new byte[] { 0, 3, 255, 255 })) throw new IOException("HPL2 响应异常: " + Convert.ToHexString(ack)); }
    public async Task ConnectAsync(CancellationToken cancellation = default)
    {
        if (!(await link.QueryAsync(0xC6, [], cancellation)).AsSpan().SequenceEqual(new byte[] { 1, 3, 7 })) throw new IOException("固件版本已改变，需要重新验证 MCU 协议");
        if (link is HidTransport hid) { hid.Authorized = true; hid.CodecEnabled = codec; hid.LiveColorEnabled = liveColor; }
        await Task.Delay(2200, cancellation); var screen = await link.QueryAsync(0xEE, [], cancellation);
        if (screen.Length < 8) throw new IOException("未知屏幕状态"); restoreColor = "#" + Convert.ToHexString(screen[1..4]); touched = true;
        await link.WriteAsync(0xEF, Protocol.ScreenColor(color), cancellation); await RestoreClockAsync(color);
        sid = NewSid(); MarkOwned(true); await Control(1);
    }
    public void Offer(PixelFrame pixels, string nextColor, byte nextAnimation, bool important, byte nextInterval = 16)
    {
        if(nextAnimation > 7 || nextInterval is < 8 or > 64) throw new ArgumentOutOfRangeException(nameof(nextAnimation));
        if(nextAnimation >= 6 && !liveColor) nextAnimation = fullAnimation ? (byte)4 : (byte)2;
        lock (gate) { if (target != null && target.Identity != pixels.Identity) Dropped++; target = pixels; if (color != nextColor) colorChanged = Environment.TickCount64; color = nextColor; animation = nextAnimation == 5 && !localRain ? (byte)2 : nextAnimation; interval = nextInterval; urgent |= important; }
    }
    public async Task PumpAsync(Func<Settings> settings, Func<(string? Color, bool Active)> light, CancellationToken stop)
    {
        string activeColor = color, currentColor = color; bool lighting = false; string? lastLight = null, lastAmbient = null; long lightDue = 0;
        PixelFrame? current = null; Queue<byte[]> packets = new(); Queue<PixelFrame> motion = new(); EncodingPlan? plan = null; long started = 0, nativeUntil = 0; byte currentAnimation = 0, currentInterval = 16;
        while (!stop.IsCancellationRequested)
        {
            if (Environment.TickCount64 >= heartbeat) await Control(2);
            var s = settings(); var l = light();
            if (s.AmbientEnabled && l.Active)
            {
                if (!lighting) { await link.WriteAsync(0x6B, Protocol.Ambient(s, l.Color, true)); await link.WriteAsync(0x6B, Protocol.AmbientPower(true)); lighting = true; }
                if (Environment.TickCount64 >= lightDue && l.Color != null && l.Color != lastLight) { await link.WriteAsync(0x6B, Protocol.Ambient(s, l.Color, true)); lastLight = l.Color; lightDue = Environment.TickCount64 + (s.PowerProfile == "balanced" ? 33 : 50); }
            }
            else { string signature = $"{s.Effect}|{s.AmbientColor}|{s.Brightness}|{s.Speed}|{s.AmbientEnabled}"; if (lighting || signature != lastAmbient) { await ApplyAmbientAsync(s); lighting = false; lastLight = null; lastAmbient = signature; } }
            string desired; bool supersede; lock (gate) { desired = color; supersede = urgent && target != null && (current != null ? !target.Pixels.AsSpan().SequenceEqual(current.Pixels) : motion.Count > 0 || currentAnimation == 5 && committed != null && !target.Pixels.AsSpan().SequenceEqual(committed.Pixels)); urgent = false; }
            if(supersede && currentAnimation == 5) nativeUntil = 0; // Stop demo can interrupt the long effect.
            if (!liveColor && (desired != activeColor || frame == ushort.MaxValue))
            {
                // Finish the in-flight ACK before this branch. Drop uncommitted data before releasing.
                if (Environment.TickCount64 - colorChanged < 180) { await Task.Delay(25, stop); continue; }
                packets.Clear(); motion.Clear(); current = null; committed = null; nativeUntil = 0; await Control(5); MarkOwned(false);
                // EE reads the USB controller's cached RGB, not completion of its
                // deferred BLT+LCD+SET forwarding. Reacquiring after 100 ms can
                // race with the display MCU's lease guard. Keep the lease released
                // through the settling window; cached RGB is not optical validation.
                while (true)
                {
                    await link.WriteAsync(0xEF, Protocol.ScreenColor(desired), stop); await Task.Delay(100, stop);
                    await RestoreClockAsync(desired, stop, verifyColor: true);
                    string newest; lock (gate) newest = color;
                    if (newest == desired) break; desired = newest;
                }
                sid = NewSid(); frame = committedId = 0; MarkOwned(true); await Control(1); activeColor = desired; continue;
            }
            if (supersede && (packets.Count > 0 || motion.Count > 0)) { packets.Clear(); motion.Clear(); current = null; Dropped++; }
            if (current == null && Environment.TickCount64 >= nativeUntil)
            {
                PixelFrame? next; byte anim = 0, tickInterval = 16; string nextColor = activeColor;
                if (motion.Count > 0) next = motion.Dequeue();
                else
                {
                    lock (gate) { next = target; nextColor = color; anim = animation; tickInterval = interval; target = null; }
                    if (next != null && committed != null && anim is 1 or 2 && fullAnimation && !Transitions.NativeCompatible(committed, next))
                        anim = (byte)(anim == 2 ? 4 : 3);
                    else if (next != null && committed != null && anim is 1 or 2 && (!codec || !Transitions.NativeCompatible(committed, next)))
                    {
                        // One whole-screen midpoint matches the established Python path.
                        // Keep only this transition's final target; never queue old scenes.
                        motion.Enqueue(next); next = Transitions.Compose(committed, next, anim, .5); anim = 0;
                    }
                }
                if (next != null && (committed == null || !next.Pixels.AsSpan().SequenceEqual(committed.Pixels) || liveColor && nextColor != activeColor))
                {
                    current = next; currentColor = nextColor; if(liveColor && frame == ushort.MaxValue) frame = 0; frame++; plan = Protocol.Choose(next.Pixels, frame % 64 == 0 ? null : committed?.Pixels, committedId);
                    if (!codec) plan = new(0, next.Pixels, 0, 0, Protocol.Crc(next.Pixels));
                    currentAnimation = anim; currentInterval = tickInterval; packets = Protocol.Fragments(sid, frame, next.Pixels, plan, codec, anim, tickInterval, liveColor ? currentColor : null); started = Environment.TickCount64;
                }
            }
            if (packets.Count > 0)
            {
                var p = packets.Dequeue(); Check(await link.QueryAsync(0x17, p), packets.Count == 0); heartbeat = Environment.TickCount64 + 500;
                // The device only commits after the final CRC check. Base never follows an abandoned frame.
                if (packets.Count == 0) { committed = current; committedId = frame; activeColor = currentColor; current = null; Frames++; Codec = plan!.Name; EncodedBytes = plan.Data.Length; FrameSeconds = (Environment.TickCount64 - started) / 1000.0; if (currentAnimation != 0) nativeUntil = Environment.TickCount64 + (currentAnimation == 5 ? 160 : currentAnimation >= 3 ? 32 : 24) * currentInterval + 20; }
                continue;
            }
            await Task.Delay(lighting ? 25 : 50, stop);
        }
    }
    public async Task ApplyAmbientAsync(Settings s) { await link.WriteAsync(0x6B, Protocol.Ambient(s)); await link.WriteAsync(0x6B, Protocol.AmbientPower(s.AmbientEnabled)); }
    static bool IsClock(byte[] p) => p.Length >= 8 && p[5] == 1 && p[6] == 0 && p[7] == 0;
    async Task RestoreClockAsync(string value, CancellationToken cancellation = default, bool verifyColor = false)
    {
        long deadline = Environment.TickCount64 + 7000;
        while (Environment.TickCount64 < deadline)
        {
            await link.WriteAsync(0xEF, Protocol.Clock(value), cancellation); bool stable = true;
            foreach (int delay in new[] { 350, 650, 1500 }) { await Task.Delay(delay, cancellation); var observed = await link.QueryAsync(0xEE, [], cancellation); if (!IsClock(observed) || verifyColor && !observed.AsSpan(1, 3).SequenceEqual(Protocol.Rgb(value))) { stable = false; break; } }
            if (stable) return;
        }
        throw new IOException("原厂时钟未稳定，请退出其他音响控制软件");
    }
    public async Task ShutdownAsync()
    {
        lock (gate) { target = null; }
        if (!Owned && !touched) return;
        if (Owned) try { await Control(5); } catch { await Task.Delay(2200); } finally { MarkOwned(false); }
        await link.WriteAsync(0xEF, Protocol.ScreenColor(restoreColor)); await RestoreClockAsync(restoreColor);
        touched = false;
    }
    public async ValueTask DisposeAsync() { try { await ShutdownAsync(); } finally { await link.DisposeAsync(); } }
}
