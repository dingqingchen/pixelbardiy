namespace HaloStudio;

public sealed partial class StudioForm
{
    readonly ThemeGallery telemetryGallery = new(400, 315);
    readonly List<DrivingThemeTile> telemetryTiles = [];
    readonly Label telemetryStatusLabel = Hint("遥测接收已关闭");
    readonly ToggleSwitch telemetryDemoToggle = new() { AccessibleName = "零百加速演示" };
    void BuildTelemetry()
    {
        var p=pages[5];
        var receive=Card(p,"地平线 6 · 数据接入","仅在有效游戏数据到达后接管显示；音乐同时播放时优先显示仪表。");
        Setting(receive,"接收游戏遥测","没有数据、暂停或断流约 1.5 秒后，继续原来的歌词、时钟或监控。",Toggle("接收游戏遥测",()=>current.TelemetryEnabled,v=>Set(current with { TelemetryEnabled=v })));
        Setting(receive,"本机 UDP 端口","与游戏保持一致；避开 5200–5300。",Number("遥测 UDP 端口",1024,65535,()=>current.TelemetryPort,v=>{
            if(!TelemetryReceiver.ValidPort((int)v)) { MessageBox.Show(this,"请避开地平线占用的 5200–5300 端口。","遥测端口"); Sync(); return; }
            Set(current with { TelemetryPort=(int)v });
        }));
        receive.Controls.Add(telemetryStatusLabel);
        receive.Controls.Add(Hint("游戏 → 设置 → HUD 和游戏玩法 → Data Out：开启；IP：127.0.0.1；端口：20777（或填写上方修改后的端口）。开始驾驶后才会发送数据。"));
        var demo=Card(p,"零百加速演示","使用当前选择的仪表主题，无需启动游戏。");
        Setting(demo,"遥测演示","模拟起步、换挡与 0–100 km/h 加速，持续 16 秒；结束或关闭后自动恢复。",telemetryDemoToggle);
        telemetryDemoToggle.CheckedChanged+=(_,_)=> { if(!loading) { if(telemetryDemoToggle.Checked) engine.StartTelemetryDemo(); else engine.StopTelemetryDemo(); } };
        demo.Controls.Add(Hint("演示为模拟数据，并非车型的实测性能。仪表数值直接刷新，转速条随游戏车辆的最大转速自动调整。"));
        demo.Controls.Add(Row(Button("打开仪表主题文件夹",()=>OpenFolder(TelemetryDesigns.DirectoryPath)),Button("重新加载仪表",()=>Safe(()=>{
            var errors=TelemetryDesigns.Reload(TelemetryDesigns.DirectoryPath); LoadTelemetryThemes(); current=current.Validated(); engine.Configure(current); Sync();
            if(errors.Length>0) MessageBox.Show(this,string.Join("\n",errors),"部分仪表未加载");
        }))));
        p.Controls.Add(telemetryGallery); LoadTelemetryThemes();
    }
    void LoadTelemetryThemes()
    {
        telemetryGallery.SuspendLayout(); foreach(var tile in telemetryTiles) tile.Dispose();telemetryTiles.Clear();telemetryGallery.Controls.Clear();
        foreach(var (key,design) in TelemetryDesigns.All)
        {
            var tile=new DrivingThemeTile(key,design); if(AutoScaleMode==AutoScaleMode.Dpi) tile.Scale(new SizeF(DeviceDpi/96f,DeviceDpi/96f));
            tile.Click+=(_,_)=>Set(current with { TelemetryTheme=tile.Key }); telemetryTiles.Add(tile);telemetryGallery.Controls.Add(tile);
        }
        telemetryGallery.ResumeLayout(true);
    }
}
