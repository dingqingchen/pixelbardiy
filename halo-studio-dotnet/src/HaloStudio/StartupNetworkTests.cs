namespace HaloStudio;

internal static class StartupNetworkTests
{
    public static void Run(Action<bool, string> assert)
    {
        assert(NetworkSampler.RowSize == 1352, "Windows MIB_IF_ROW2 ABI size is 1352 bytes");
        Guid wifi = Guid.NewGuid(), vpn = Guid.NewGuid(), eth = Guid.NewGuid(); var n = new NetworkSampler();
        AdapterCounter A(Guid id, bool hardware, ulong tx, ulong rx, bool up = true, uint index = 1) => new(id, id.ToString(), index, hardware, up, 6, tx, rx);
        assert(n.Sample([A(wifi,true,8000,16000),A(vpn,false,8000,16000)],1000).Upload == null, "First network sample has no fabricated rate");
        var rate = n.Sample([A(wifi,true,16000,32000),A(vpn,false,16000,32000)],2000);
        assert(rate.Upload == 8000 && rate.Download == 16000, "Physical byte counters are neither VPN-doubled nor divided by eight");
        assert(n.Sample([A(wifi,true,24000,48000)],3000).Download == 16000, "Removing a virtual adapter does not reset physical rates");
        assert(n.Sample([A(wifi,true,1,1)],4000).Upload == null, "Counter reset warms up instead of producing a spike");
        assert(n.Sample([A(wifi,true,1025,2049)],5000).Upload == 1024, "Byte-per-second scale resumes after a counter reset");
        assert(n.Sample([A(eth,true,99999999,99999999)],6000).Download == null, "New adapter lifetime counters cannot become current speed");
        assert(n.Sample([A(eth,true,100000999,100002999)],7000).Download == 3000, "Replacement adapter starts from its own baseline");
        assert(n.Sample([A(eth,true,100000999,100002999,up:false)],8000).Download == null, "Disconnected physical interfaces are not counted");
        var onlyVirtual = new NetworkSampler(); onlyVirtual.Sample([A(vpn,false,100,100,index:2),A(wifi,false,100,100,index:3)],1000);
        assert(onlyVirtual.Sample([A(vpn,false,200,300,index:2),A(wifi,false,200,300,index:3)],2000).Download == 200, "Virtual-only fallback chooses one interface rather than summing layers");
        assert(new Metric("download","","",1048576,"B/s","").Text() == "1.00MiB/s", "Full network units explicitly mean binary bytes per second");
        assert(ThermalTask.ValidRequest(12,new string('a',32)) && !ThermalTask.ValidRequest(0,new string('a',32)) && !ThermalTask.ValidRequest(12,"bad & argument"), "Privileged thermal task accepts only PID and 32 lowercase hex nonce");
        assert(ThermalTask.Matches(ThermalTask.ProtectedExe,"$(Arg0) $(Arg1)",ThermalTask.ProtectedDirectory,System.Security.Principal.WindowsIdentity.GetCurrent().Name,3,1,1,0), "Task Scheduler account-name normalization resolves to the current user SID");
        assert(!ThermalTask.Matches(Path.Combine(Path.GetTempPath(),"HaloThermalTask.exe"),"$(Arg0) $(Arg1)",ThermalTask.ProtectedDirectory,"wrong",3,1,1,0), "A user-writable thermal task action is rejected");
    }
}
