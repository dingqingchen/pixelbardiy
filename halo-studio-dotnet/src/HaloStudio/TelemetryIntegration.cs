using System.Net;
using System.Net.Sockets;

namespace HaloStudio;

public static class TelemetryIntegration
{
    // Runs the real Engine and UDP path in preview mode: no HID, no temperature
    // driver and no online lyric request. Uses a separate diagnostic settings dir.
    public static async Task RunAsync(string output)
    {
        var checks=new List<string>();void Check(bool ok,string name){if(!ok)throw new Exception(name);checks.Add(name);}
        string dir=Path.Combine(Path.GetDirectoryName(output)!,"integration-runtime");
        using var reserve=new UdpClient(new IPEndPoint(IPAddress.Loopback,0));int port=((IPEndPoint)reserve.Client.LocalEndPoint!).Port;reserve.Close();
        await using var engine=new Engine(dir);engine.Configure(new Settings { Theme="paper",Mode="idle",Online=false,Rhythm=false,AmbientEnabled=false,CpuTemperatureEnabled=false,TelemetryEnabled=true,TelemetryPort=port });
        StudioState? latest=null;var frames=new List<string>();
        engine.Changed+=s=> {Volatile.Write(ref latest,s);lock(frames)frames.Add(s.Frame?.Identity??"");};engine.Start(true);
        async Task Until(Func<StudioState,bool> ready,int timeout=3500)
        {long end=Environment.TickCount64+timeout;while(Volatile.Read(ref latest) is not {} s || !ready(s)){if(Environment.TickCount64>end)throw new TimeoutException("Engine: "+latest?.Status+" / "+latest?.TelemetryStatus);await Task.Delay(25);}}
        await Until(s=>s.Frame!=null);
        Check(!latest!.TelemetryActive && latest.Frame!.Identity.StartsWith("时钟:"),"Receiver enabled with no data keeps clock");
        using var sender=new UdpClient();var endpoint=new IPEndPoint(IPAddress.Loopback,port);
        for(uint i=1;i<=60;i++){await sender.SendAsync(TelemetryTests.Packet(i),endpoint);await Task.Delay(25);}
        await Until(s=>s.TelemetryActive);
        Check(latest!.Frame!.Identity=="遥测:01_lagonda_led84","Real UDP packet takes over Engine display");
        await Until(s=>!s.TelemetryActive && s.Frame!.Identity.StartsWith("时钟:"));
        Check(true,"Silence restores prior clock without an upload or app restart");
        engine.Configure(engine.Config with{TelemetryEnabled=false});engine.StartTelemetryDemo();
        await Until(s=>s.TelemetryDemo && s.TelemetryActive);
        Check(latest!.Frame!.Text.Contains("模拟数据"),"Demo independently overrides display and is labelled simulation");
        engine.Configure(engine.Config with{TelemetryTheme="15_vector_w8"});
        await Until(s=>s.TelemetryDemo && s.Frame!.Identity=="遥测:15_vector_w8");Check(true,"Changing dashboard during acceleration immediately updates theme");
        await Until(s=>!s.TelemetryDemo && !s.TelemetryActive && s.Frame!.Identity.StartsWith("时钟:"),18000);
        Check(true,"Demo automatically ends and restores prior display");
        engine.StartTelemetryDemo();await Until(s=>s.TelemetryDemo);engine.StopTelemetryDemo();
        await Until(s=>!s.TelemetryDemo && !s.TelemetryActive);Check(true,"Demo switch can cancel early");
        Check(engine.LastError.Length==0,"Engine completed without errors");
        Files.Save(output,new {Passed=true,Count=checks.Count,Checks=checks,Frames=frames.Distinct().ToArray()});
    }
}
