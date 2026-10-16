using System.Runtime.InteropServices;

namespace HaloStudio;

internal sealed record AdapterCounter(Guid Id, string Name, uint Index, bool Hardware, bool Up, uint Type, ulong Sent, ulong Received);
internal sealed record NetworkRate(double? Upload, double? Download, string Source);

internal sealed class NetworkSampler
{
    readonly Dictionary<Guid, (ulong Tx, ulong Rx, long At)> previous = [];
    public NetworkRate Read() => Sample(Enumerate(), Environment.TickCount64);

    internal NetworkRate Sample(AdapterCounter[] adapters, long now)
    {
        var active = adapters.Where(a => a.Up && a.Type is not (24 or 131)).ToArray();
        var physical = active.Where(a => a.Hardware).ToArray();
        // Count an outer physical link once, never add the VPN's inner traffic.
        // Virtual-only machines conservatively select one stable interface.
        var chosen = physical.Length > 0 ? physical : active.OrderBy(a => a.Index).Take(1).ToArray();
        double tx = 0, rx = 0; int valid = 0;
        foreach (var a in chosen)
        {
            if (previous.TryGetValue(a.Id, out var old) && now > old.At && a.Sent >= old.Tx && a.Received >= old.Rx)
            {
                double seconds = (now - old.At) / 1000.0;
                tx += (a.Sent - old.Tx) / seconds; rx += (a.Received - old.Rx) / seconds; valid++;
            }
        }
        previous.Clear();
        foreach (var a in chosen) previous[a.Id] = (a.Sent, a.Received, now);
        string source = chosen.Length == 0 ? "Windows IP Helper · 没有活动网卡" :
            "Windows IP Helper · " + (physical.Length > 0 ? "物理网卡 " : "单虚拟网卡回退 ") + string.Join(" / ", chosen.Select(a => a.Name));
        return new(valid > 0 ? tx : null, valid > 0 ? rx : null, source);
    }

    internal static unsafe AdapterCounter[] Enumerate()
    {
        if (GetIfTable2(out var table) != 0) return [];
        try
        {
            int count = Marshal.ReadInt32(table); if (count is < 0 or > 4096) return [];
            int stride = sizeof(IfRow); var result = new List<AdapterCounter>();
            for (int i = 0; i < count; i++)
            {
                var row = *(IfRow*)((byte*)table + 8 + i * stride);
                string name = new(row.Alias, 0, 257); name = name.TrimEnd('\0');
                result.Add(new(row.Id, name, row.Index, (row.Flags & 1) != 0, row.OperStatus == 1, row.Type, row.OutOctets, row.InOctets));
            }
            return result.ToArray();
        }
        finally { FreeMibTable(table); }
    }
    internal static int RowSize => Marshal.SizeOf<IfRow>();
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    unsafe struct IfRow
    {
        public ulong Luid; public uint Index; public Guid Id;
        public fixed char Alias[257]; public fixed char Description[257];
        public uint AddressLength; public fixed byte Address[32]; public fixed byte PermanentAddress[32];
        public uint Mtu, Type, TunnelType, MediaType, PhysicalMedium, AccessType, Direction;
        public byte Flags; public uint OperStatus, AdminStatus, MediaConnectState; public Guid NetworkGuid; public uint ConnectionType;
        public ulong TxSpeed, RxSpeed, InOctets, InUnicast, InNonUnicast, InDiscards, InErrors, InUnknown, InUnicastOctets, InMulticastOctets, InBroadcastOctets;
        public ulong OutOctets, OutUnicast, OutNonUnicast, OutDiscards, OutErrors, OutUnicastOctets, OutMulticastOctets, OutBroadcastOctets, OutQueue;
    }
    [DllImport("iphlpapi.dll")] static extern uint GetIfTable2(out IntPtr table);
    [DllImport("iphlpapi.dll")] static extern void FreeMibTable(IntPtr table);
}
