using System.Text.Json;
namespace HaloStudio;

public static class MonitorRegressionTests
{
    public static void Run(Action<bool,string> check, string directory)
    {
        Settings Read(string json) => JsonSerializer.Deserialize<Settings>(json,Files.Json)!.Validated();
        var oldMonitor=Read("""{"idle_content":"monitor","theme":"kitty","monitor_view":"compact","monitor_metrics":["ram","cpu"],"rotation_seconds":12}""");
        check(oldMonitor.MonitorEnabled && oldMonitor.WantsMonitor,"Old monitor choice migrates");
        check(!Read("""{"idle_content":"clock"}""").MonitorEnabled,"Old clock choice remains clock");
        check(!Read("{}").MonitorEnabled,"Fresh settings preserve clock default");
        check(!Read("""{"idle_content":"monitor","monitor_enabled":false}""").MonitorEnabled,"Explicit new off overrides old monitor");
        check(Read("""{"idle_content":"clock","monitor_enabled":true}""").MonitorEnabled,"Explicit new on overrides old clock");
        check(oldMonitor.MonitorView=="compact" && oldMonitor.RotationSeconds==12 && oldMonitor.MonitorMetrics.SequenceEqual(new[]{"ram","cpu"}),"Migration retains metric order, layout and interval");
        var roundtrip=Read(JsonSerializer.Serialize(oldMonitor,Files.Json));
        check(roundtrip.MonitorEnabled && !(roundtrip with {MonitorEnabled=false}).Validated().MonitorEnabled,"Migrated choice persists and can be disabled");
        foreach(var theme in new[]{"amber","ion","kitty","matrix","paper","peach"})
            check((oldMonitor with {Theme=theme}).WantsMonitor,"Legacy theme retains monitoring: "+theme);
        foreach(var theme in new[]{"mochi","bunny","bear"})
            check(!(oldMonitor with {Theme=theme}).WantsMonitor,"Explicit clock-only theme: "+theme);
        check(!(oldMonitor with {Enabled=false}).WantsMonitor,"Disabled screen does not request monitor sampling");
        Task.Run(()=>EngineCheck(check,directory)).GetAwaiter().GetResult();
    }
    static async Task EngineCheck(Action<bool,string> check,string directory)
    {
        await using var engine=new Engine(Path.Combine(directory,"monitor-regression-"+Guid.NewGuid().ToString("N")));
        engine.Configure(new Settings{Theme="perf",MonitorEnabled=true,IdleContent="clock",Mode="idle",Online=false,Rhythm=false,AmbientEnabled=false,PowerProfile="balanced"});
        StudioState? latest=null;
        engine.Changed+=s=>Volatile.Write(ref latest,s);
        engine.MonitorVisible=false;
        engine.Start(true);
        async Task Until(Func<StudioState,bool> ready)
        {
            long deadline=Environment.TickCount64+15000;
            while(Volatile.Read(ref latest) is not {} s || !ready(s))
            {if(Environment.TickCount64>deadline)throw new Exception("Monitor engine regression: "+engine.LastError);await Task.Delay(50);}
        }
        await Until(s=>s.Snapshot.Get("cpu").History.Length>=2 && s.Frame?.Identity.StartsWith("系统监控:")==true);
        check(true,"New monitor theme continuously samples outside hardware page");
        engine.MonitorVisible=true;
        await Until(s=>s.Snapshot.Get("cpu").History.Length>=3);
        engine.MonitorVisible=false; engine.Visible=false;
        await Until(s=>s.Snapshot.Get("cpu").History.Length>=4);
        check(true,"Leaving hardware page and hiding to tray keeps sampling");
        engine.Configure(engine.Config with {MonitorEnabled=false});
        await Until(s=>s.Frame?.Identity.StartsWith("时钟:")==true);
        check(engine.LastError.Length==0,"Disabling monitoring restores clock without engine error");
    }
}
