using System.Text.Json;
namespace HaloStudio;

// One bounded diagnostic, bound to an exact completed update and device. This
// never writes a visual-validation record or offers any firmware write command.
internal static class ColorCommissioning
{
    public static async Task Run(string runtime, string liveFolder, bool timeout)
    {
        using var owner = new DeviceOwner(); owner.Acquire();
        using var latch = JsonDocument.Parse(File.ReadAllText(Path.Combine(liveFolder,"UPGRADE_STARTED.json")));
        if(latch.RootElement.GetProperty("candidate").GetString()!=Protocol.ColorSha) throw new IOException("升级记录不匹配");
        bool complete=File.ReadLines(latch.RootElement.GetProperty("trace").GetString()!).Any(line => {
            using var d=JsonDocument.Parse(line); var r=d.RootElement;
            return r.GetProperty("event").GetString()=="mcu_transfer_complete" && r.GetProperty("candidate").GetString()==Protocol.ColorSha && r.GetProperty("bytes").GetInt32()==57252 && r.GetProperty("main_controller_bytes").GetInt32()==0;
        });
        if(!complete) throw new IOException("MCU 传输未完整结束");
        using var record=JsonDocument.Parse(File.ReadAllText(Path.Combine(runtime,"mcu-installation.json")));
        var devices=HidTransport.Enumerate(); var rec=record.RootElement;
        bool matches=rec.TryGetProperty("pending_candidate_sha256",out var pending) ? pending.GetString()==Protocol.ColorSha : rec.GetProperty("candidate_sha256").GetString()==Protocol.ColorSha && rec.GetProperty("graphics_visually_confirmed").GetBoolean();
        if(devices.Count!=1 || devices[0].Serial!=rec.GetProperty("serial").GetString() || !devices[0].Path.Equals(rec.GetProperty("hid_path").GetString(),StringComparison.OrdinalIgnoreCase) || !matches) throw new IOException("测试设备与升级记录不一致");
        foreach(var process in System.Diagnostics.Process.GetProcessesByName("Edifier TempoHub")) { process.Dispose(); throw new IOException("请先退出 TempoHub"); }
        var settings=(Files.Load<Settings>(Path.Combine(runtime,"settings.json"))??new()).Validated();
        await using var link=new HidTransport(devices[0]) { Authorized=true, CodecEnabled=true, LiveColorEnabled=true };
        var trace=new TraceLink(link); var controller=new RamController(trace,true,"#60FF30",true,true,true);
        var log=new List<object>(); string output=Path.Combine(liveFolder,(timeout?"timeout-":"smoke-")+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".json");
        using var stop=new CancellationTokenSource(); Task? pump=null; bool expired=false;
        try
        {
            await controller.ConnectAsync(); pump=controller.PumpAsync(()=>settings,()=>(null,false),stop.Token);
            await Task.Delay(15000);
            string[] themes=timeout ? ["peach"] : ["matrix","peach","amber","paper","matrix","peach"];
            for(int i=0;i<themes.Length;i++)
            {
                string theme=themes[i]; var s=settings with { Theme=theme, Themes=true, MonitorView="compact", MonitorRotate=false, ThemeColors=[] };
                var pixels=Designs.Render(i%2==0 ? "" : "让星光落在你的肩",i%2==0?"系统监控":"歌词",s,0,Showcase.Sample(0),new DateTime(2026,10,14,12,34,56));
                long before=controller.Frames,at=Environment.TickCount64;
                controller.Offer(pixels,s.DeviceScreenColor(),i==0?(byte)0:Transitions.ThemeStyle(theme),true);
                while(controller.Frames==before && Environment.TickCount64-at<10000) { if(pump.IsCompleted) await pump; await Task.Delay(25); }
                if(controller.Frames==before) throw new TimeoutException("测试帧未提交");
                log.Add(new {Theme=theme,Color=s.DeviceScreenColor(),At=DateTimeOffset.Now,Milliseconds=Environment.TickCount64-at,controller.Frames});
                Files.Save(output,new { CandidateSha256=Protocol.ColorSha,Events=log,Commands=trace.Events });
                await Task.Delay(timeout?350:6500);
            }
            stop.Cancel(); try { await pump; } catch(OperationCanceledException) {}
            if(timeout)
            {
                expired=true; log.Add(new { HeartbeatStopped=DateTimeOffset.Now });
                Files.Save(output,new { CandidateSha256=Protocol.ColorSha,Events=log,Commands=trace.Events });
                await Task.Delay(10000); // No release, clock, color or heartbeat writes.
            }
        }
        finally
        {
            stop.Cancel(); if(pump!=null) try { await pump; } catch(OperationCanceledException) {}
            if(!expired) await controller.ShutdownAsync();
            Files.Save(output,new { CandidateSha256=Protocol.ColorSha,Events=log,Commands=trace.Events,CompletedAt=DateTimeOffset.Now,TimeoutRelease=expired,FirmwareWrites=0 });
        }
    }
    sealed class TraceLink(HidTransport inner) : IHaloTransport
    {
        public List<object> Events { get; }=[];
        public long Writes=>inner.Writes;
        void Record(byte command,byte[] payload) { if(command!=0x6B) Events.Add(new {At=DateTimeOffset.Now,Command=command,Op=command==0x17?payload[8]:0,Data=Convert.ToHexString(payload)}); }
        public async Task<byte[]> QueryAsync(byte command,byte[] payload,CancellationToken cancellation=default)
        {
            Record(command,payload); var result=await inner.QueryAsync(command,payload,cancellation);
            if(command==0x17 && payload[8] is 1 or 5) inner.Owned=payload[8]==1;
            return result;
        }
        public Task WriteAsync(byte command,byte[] payload,CancellationToken cancellation=default) { Record(command,payload); return inner.WriteAsync(command,payload,cancellation); }
        public ValueTask DisposeAsync()=>inner.DisposeAsync();
    }
}
