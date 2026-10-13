using System.Buffers.Binary;

namespace HaloStudio;

public sealed record EncodingPlan(byte Codec, byte[] Data, ushort BaseId, ushort BaseCrc, ushort TargetCrc)
{
    public string Name => new[] { "raw", "rle", "xor-rle" }[Codec];
    public int PacketCount => 1 + (Data.Length + 36) / 37;
}
public static class Protocol
{
    public const string FirmwareSha = "f7b8ee274ba2439b3211c5eea80206599acff6e80d73dc0c898ba143e2e32f62";
    public const string FullscreenSha = "ab4698cf8e826a3c64472ea0af1125653f65f796cd7fcf9013667344e4c0fc50";
    public const string MatrixSha = "ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884";
    public const string ColorSha = "9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e";
    public const string LegacySha = "fe18bc92afd790cd2f2248b98091033f8d8d76cac674b60540cbf5c644f389ae";
    public static byte[] Packet(byte command, ReadOnlySpan<byte> payload, byte type = 0xED)
    {
        if (payload.Length > 57) throw new ArgumentOutOfRangeException(nameof(payload));
        byte[] p = new byte[64]; p[0] = 0x2E; p[1] = 0xAA; p[2] = type; p[3] = command;
        BinaryPrimitives.WriteUInt16BigEndian(p.AsSpan(4), (ushort)payload.Length); payload.CopyTo(p.AsSpan(6));
        p[6 + payload.Length] = (byte)p.AsSpan(1, 5 + payload.Length).ToArray().Sum(x => (int)x); return p;
    }
    public static byte[] Response(ReadOnlySpan<byte> p, byte command)
    {
        if (p.Length < 7 || p[0] != 0x2F || p[1] != 0xBB || p[2] != 0xEC || p[3] != command) throw new IOException("HID 响应帧不匹配");
        int length = BinaryPrimitives.ReadUInt16BigEndian(p[4..]);
        if (length > 57 || p.Length < length + 7) throw new IOException("HID 响应长度无效");
        int sum = 0; for (int i = 1; i < 6 + length; i++) sum += p[i];
        if (p[6 + length] != (byte)sum) throw new IOException("HID 校验失败"); return p.Slice(6, length).ToArray();
    }
    public static ushort Crc(ReadOnlySpan<byte> data)
    {
        ushort crc = 0; foreach (byte b in data) { crc ^= (ushort)(b << 8); for (int i = 0; i < 8; i++) crc = (ushort)((crc << 1) ^ ((crc & 0x8000) != 0 ? 0x1021 : 0)); }
        return crc;
    }
    public static byte[] Rle(ReadOnlySpan<byte> raw)
    {
        var output = new List<byte>(); int pos = 0;
        while (pos < raw.Length)
        {
            int run = 1; while (pos + run < raw.Length && raw[pos + run] == raw[pos] && run < 128) run++;
            if (run >= 3) { output.Add((byte)(0x80 | run - 1)); output.Add(raw[pos]); pos += run; continue; }
            int start = pos; pos += run;
            while (pos < raw.Length && pos - start < 128) { run = 1; while (pos + run < raw.Length && raw[pos + run] == raw[pos] && run < 128) run++; if (run >= 3) break; pos += Math.Min(run, 128 - (pos - start)); }
            output.Add((byte)(pos - start - 1)); for (int i = start; i < pos; i++) output.Add(raw[i]);
        }
        return output.ToArray();
    }
    public static byte[] Unrle(ReadOnlySpan<byte> encoded, int expected = 1024)
    {
        var raw = new List<byte>(); int i = 0; while (i < encoded.Length)
        {
            byte token = encoded[i++]; int n = (token & 127) + 1;
            if ((token & 128) != 0) { if (i >= encoded.Length) throw new InvalidDataException(); byte b = encoded[i++]; for (int j = 0; j < n; j++) raw.Add(b); }
            else { if (i + n > encoded.Length) throw new InvalidDataException(); for (int j = 0; j < n; j++) raw.Add(encoded[i++]); }
            if (raw.Count > expected) throw new InvalidDataException();
        }
        if (raw.Count != expected) throw new InvalidDataException(); return raw.ToArray();
    }
    public static EncodingPlan Choose(byte[] pixels, byte[]? basis, ushort basisId)
    {
        if (pixels.Length != 1024 || basis != null && basis.Length != 1024) throw new ArgumentException("需要 1024 字节点阵");
        var best = new EncodingPlan(0, pixels, 0, 0, Crc(pixels)); var rle = Rle(pixels);
        if (rle.Length < best.Data.Length) best = best with { Codec = 1, Data = rle };
        if (basis != null && basisId > 0)
        {
            var delta = new byte[1024]; for (int i = 0; i < 1024; i++) delta[i] = (byte)(pixels[i] ^ basis[i]); rle = Rle(delta);
            if (rle.Length < best.Data.Length) best = best with { Codec = 2, Data = rle, BaseId = basisId, BaseCrc = Crc(basis) };
        }
        return best;
    }
    public static byte[] Body(byte op, uint sid, ushort frame = 0, byte index = 0, ReadOnlySpan<byte> data = default)
    {
        if (sid == 0 || op is < 1 or > 7 || data.Length > 37) throw new ArgumentException("HPL2 参数无效");
        if (op is not (4 or 6 or 7) && data.Length != 0) throw new ArgumentException("控制指令不可附加数据");
        byte[] p = new byte[17 + data.Length]; p[0] = 0; p[1] = 2; p[2] = 255; p[3] = 255; "HPL2"u8.CopyTo(p.AsSpan(4)); p[8] = op;
        BinaryPrimitives.WriteUInt32BigEndian(p.AsSpan(9), sid); BinaryPrimitives.WriteUInt16BigEndian(p.AsSpan(13), frame);
        p[15] = index; p[16] = (byte)data.Length; data.CopyTo(p.AsSpan(17)); return p;
    }
    public static Queue<byte[]> Fragments(uint sid, ushort frame, byte[] pixels, EncodingPlan plan, bool codec, byte animation, byte interval = 16, string? color = null)
    {
        var q = new Queue<byte[]>(); byte[] data;
        if (codec)
        {
            if(animation > (color == null ? 5 : 7) || interval is < 8 or > 64) throw new ArgumentOutOfRangeException(nameof(animation));
            byte[] begin = new byte[color == null ? 12 : 15]; begin[0] = plan.Codec; begin[1] = animation; begin[2] = interval;
            if (color != null) Rgb(color).CopyTo(begin, 12);
            BinaryPrimitives.WriteUInt16BigEndian(begin.AsSpan(4), (ushort)plan.Data.Length);
            BinaryPrimitives.WriteUInt16BigEndian(begin.AsSpan(6), plan.BaseId); BinaryPrimitives.WriteUInt16BigEndian(begin.AsSpan(8), plan.BaseCrc);
            BinaryPrimitives.WriteUInt16BigEndian(begin.AsSpan(10), plan.TargetCrc); q.Enqueue(Body(6, sid, frame, 0, begin)); data = plan.Data;
        }
        else { q.Enqueue(Body(3, sid, frame)); data = new byte[1026]; pixels.CopyTo(data, 0); BinaryPrimitives.WriteUInt16BigEndian(data.AsSpan(1024), Crc(pixels)); }
        for (int i = 0, pos = 0; pos < data.Length; i++, pos += 37) q.Enqueue(Body(codec ? (byte)7 : (byte)4, sid, frame, (byte)i, data.AsSpan(pos, Math.Min(37, data.Length - pos)))); return q;
    }
    public static byte[] Rgb(string hex)
    {
        var c = ColorTranslator.FromHtml(hex); return [c.R, c.G, c.B];
    }
    public static byte[] Clock(string color) { var rgb = Rgb(color); return [1, .. rgb, 0, 1, 0, 0, 255]; }
    public static byte[] ScreenColor(string color) { var rgb = Rgb(color); return [3, .. rgb, 0, 0, 255, 255, 255]; }
    public static byte[] Ambient(Settings s, string? color = null, bool rhythm = false)
    {
        byte effect = (byte)(rhythm ? 3 : s.Effect switch { "breathing" => 1, "color_tide" => 2, "static" => 3, "ripple" => 4, "flow" => 5, "dynamic" => 6, _ => 3 });
        byte brightness = s.Brightness switch { "low" => 20, "medium" => 40, _ => 60 };
        return [0x13, effect, .. Rgb(color ?? s.AmbientColor), brightness, (byte)(s.Effect == "color_tide" && !rhythm ? 8 : Math.Clamp(s.Speed, 1, 10))];
    }
    public static byte[] AmbientPower(bool enabled) => [0, 0, 0, 0, (byte)(enabled ? 1 : 0), 255, 255];
}
