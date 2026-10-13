namespace HaloStudio;

internal static class ScreenColorDiagnostic
{
    public static async Task Run(string runtime, string output, bool whiteBalance = false, bool warmer = false, bool compare = false, bool calibrated = false, bool hues = false)
    {
        using var owner = new DeviceOwner(); owner.Acquire();
        var devices = HidTransport.Enumerate(); if (devices.Count != 1) throw new IOException("请仅连接一台已验证的 PixelBar");
        var caps = RamController.ValidateInstallation(Path.Combine(runtime, "mcu-installation.json"), devices[0]);
        await using var display = new RamController(new HidTransport(devices[0]), caps.Codec, whiteBalance ? "#FFFFFF" : "#86D8F6", caps.FullAnimation, caps.LocalRain, caps.LiveColor);
        var log = new List<object>();
        await display.ConnectAsync(); using var stop = new CancellationTokenSource();
        var settings = (Files.Load<Settings>(Path.Combine(runtime,"settings.json")) ?? new()).Validated();
        var pump = display.PumpAsync(() => settings, () => (null,false), stop.Token);
        try
        {
            await Task.Delay(15000);
            var colors = hues
                ? new[] { ("G1", "#60FF30"), ("G2", "#90FF48"), ("G3", "#B0FF60"), ("P1", "#FF3040"), ("P2", "#FF6048"), ("P3", "#FF9060") }
                : calibrated
                ? new[] { ("WHITE 144", settings.DeviceScreenColor("#FFFFFF")) }
                : compare
                ? new[] { ("W4", "#FFFF80"), ("W5", "#FFFF60") }
                : warmer
                ? new[] { ("W4", "#FFFF80"), ("W5", "#FFFF60"), ("W6", "#FFFF40") }
                : whiteBalance
                ? new[] { ("W0", "#FFFFFF"), ("W1", "#FFFFE0"), ("W2", "#FFFFC0"), ("W3", "#FFFFA0") }
                : new[] { ("PINK", "#FF4080"), ("ORANGE", "#FF6000"), ("WHITE", "#FFFFFF"), ("RED", "#FF0000") };
            foreach (var (label, color) in colors)
            {
                var canvas = new PixelCanvas(); canvas.Raster(label, 12, 8, 2); canvas.Rect(1, 1, 254, 30); canvas.Rect(212, 6, 30, 20, true);
                long before = display.Frames, started = Environment.TickCount64;
                display.Offer(new(canvas.Data, label, "color-test:"+label), color, 0, true);
                while (display.Frames == before && Environment.TickCount64 - started < 10000) { if(pump.IsCompleted) await pump; await Task.Delay(25); }
                if(display.Frames == before) throw new TimeoutException("颜色测试画面未确认");
                log.Add(new { Label=label, Color=color, At=DateTimeOffset.Now, SettleMs=Environment.TickCount64-started, display.Frames }); Files.Save(output, log);
                await Task.Delay(hues ? 14000 : calibrated ? 30000 : compare ? 25000 : whiteBalance ? 18000 : label == "RED" ? 20000 : 12000);
            }
        }
        finally { stop.Cancel(); try { await pump; } catch(OperationCanceledException) {} }
    }
}
