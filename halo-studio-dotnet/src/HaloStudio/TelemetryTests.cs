using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;

namespace HaloStudio;

public static class TelemetryTests
{
    public static byte[] Packet(uint timestamp=1000,bool driving=true)
    {
        var p=new byte[324]; BinaryPrimitives.WriteInt32LittleEndian(p,driving?1:0);
        BinaryPrimitives.WriteUInt32LittleEndian(p.AsSpan(4),timestamp);
        void F(int offset,float value)=>BinaryPrimitives.WriteSingleLittleEndian(p.AsSpan(offset),value);
        F(8,8000);F(12,900);F(16,5800); F(256,35.555557f);F(260,240000);F(264,330);F(284,12);F(288,.68f);F(292,1840);F(308,120);
        F(180,1.2f);F(184,.3f);F(188,1.5f);F(192,.4f);
        BinaryPrimitives.WriteInt32LittleEndian(p.AsSpan(224),2);
        // Distinct sentinels catch accidental use of the Motorsport / FH4 offsets.
        BinaryPrimitives.WriteUInt32LittleEndian(p.AsSpan(232),0x11223344);F(236,4.5f);F(240,950);
        F(244,100);F(248,200);F(252,300);
        p[315]=210;p[316]=12;p[317]=25;p[318]=255;p[319]=4;p[320]=unchecked((byte)-64);
        return p;
    }
    public static void Run(Action<bool,string> assert,string directory)
    {
        var viewTime=new DateTime(2026,10,29,12,34,0);
        var p=Packet();assert(CarTelemetry.TryParse(p,100,out var t),"FH6 324-byte packet accepted");
        assert(Math.Abs(t!.Kmh-128)<.001 && t.Rpm==5800 && t.MaxRpm==8000 && t.Gear==4,"FH6 fields after 12-byte extra block have correct offsets");
        assert(Math.Abs((t with {Rpm=4000,MaxRpm=8000}).RpmRatio-.5)<.0001 && Math.Abs((t with {Rpm=4000,MaxRpm=5000}).RpmRatio-.8)<.0001,"Same RPM scales to the current vehicle limit");
        assert((t with {Rpm=9000,MaxRpm=8000}).RpmRatio==1 && !(t with {MaxRpm=0}).Fresh(101),"Over-rev clamps and zero engine limit cannot take over");
        var highLimit=(byte[])p.Clone(); BinaryPrimitives.WriteSingleLittleEndian(highLimit.AsSpan(8),12000);
        assert(CarTelemetry.TryParse(highLimit,101,out var high) && high!.MaxRpm==12000 && high.RpmRatio<t.RpmRatio,"EngineMaxRpm is refreshed by each packet");
        assert(t.Throttle==210 && t.Brake==12 && t.Clutch==25 && t.Handbrake==255 && t.Steer==-64,"Packed tail bytes / signed steer");
        assert(t.Power==240000 && t.Boost==12 && t.SlipFL==1.2f && t.Drivetrain==2,"Power, boost, wheel-slip and drivetrain parsed");
        assert(!CarTelemetry.TryParse(p[..323],100,out _) && !CarTelemetry.TryParse(new byte[331],100,out _),"Other packet sizes rejected");
        var bad=(byte[])p.Clone();BinaryPrimitives.WriteSingleLittleEndian(bad.AsSpan(256),float.NaN);
        assert(!CarTelemetry.TryParse(bad,100,out _),"Non-finite speed rejected");
        bad=(byte[])p.Clone();bad[319]=255;assert(!CarTelemetry.TryParse(bad,100,out _),"Invalid gear rejected");
        assert(t.Fresh(1599) && !t.Fresh(1600),"Stale telemetry releases priority at 1.5 seconds");
        assert(!TelemetryPriority.Takeover(true,false,null,100),"Enabled without data leaves existing lyrics/clock untouched");
        assert(TelemetryPriority.Takeover(true,false,t,101),"Active telemetry takes priority over music");
        assert(!TelemetryPriority.Takeover(false,false,t,101),"Disabled telemetry never takes over");
        assert(!TelemetryPriority.Takeover(true,false,t with {Driving=false},101),"Menu packet restores existing display");
        assert(TelemetryPriority.Takeover(false,true,null,101),"Manual demo overrides display even with receiver off");
        assert(TelemetrySprint.At(0).Kmh==0 && Math.Abs(TelemetrySprint.At(12).Kmh-100)<.001 && Math.Abs(TelemetrySprint.At(15).Kmh-100)<.001,"Sprint starts at zero, reaches 100 and holds");
        assert(TelemetrySprint.At(8).Gear>TelemetrySprint.At(2).Gear,"Sprint demonstrates shifts");
        assert(!TelemetryReceiver.ValidPort(5200)&&!TelemetryReceiver.ValidPort(5300)&&TelemetryReceiver.ValidPort(20777),"Reserved game ports excluded");
        assert(TelemetryDesigns.All.Count==15,"All 15 vehicle themes load from external JSON");
        Directory.CreateDirectory(directory);using var sheet=new Bitmap(1048,TelemetryDesigns.All.Count*175);
        using var g=Graphics.FromImage(sheet);g.Clear(Color.FromArgb(14,19,28));using var font=new Font("Segoe UI",12);int row=0;var hashes=new HashSet<string>();
        foreach(var (key,d) in TelemetryDesigns.All)
        {
            assert(!d.Commands.GetRawText().Contains("${year}"),key+" keeps model years off the pixel screen");
            assert(d.ReferenceYear is >= 1980 and <= 1999,key+" has a reference model year");
            assert(!d.Commands.GetRawText().Contains("${mode}"),key+" has no DEMO/LIVE screen label");
            var lowRange=TelemetryDesigns.Render(key,t with {Rpm=4000,MaxRpm=5000},false,viewTime);
            var highRange=TelemetryDesigns.Render(key,t with {Rpm=4000,MaxRpm=10000},false,viewTime);
            assert(!lowRange.Pixels.AsSpan().SequenceEqual(highRange.Pixels),key+" gauge adapts when only max RPM changes");
            assert(TelemetryDesigns.Render(key,t,true,viewTime).Pixels.AsSpan().SequenceEqual(TelemetryDesigns.Render(key,t,false,viewTime).Pixels),key+" live and demo use the same uncluttered layout");
            var stopped=TelemetryDesigns.Render(key,TelemetrySprint.At(0),true,viewTime);var moving=TelemetryDesigns.Render(key,t,true,viewTime);
            assert(stopped.Pixels.Length==1024 && !stopped.Pixels.AsSpan().SequenceEqual(moving.Pixels),key+" dynamically changes speed and gauges");
            hashes.Add(Convert.ToHexString(SHA256.HashData(moving.Pixels)));
            foreach(float kmh in new[]{0f,9f,99f,128f,300f,999f})
            { var frame=TelemetryDesigns.Render(key,t with{Speed=kmh/3.6f,Rpm=kmh*8,Gear=kmh==0?(byte)0:(byte)10},false,viewTime);assert(frame.Pixels.Any(b=>b!=0),key+" edge speed / gear "+kmh); }
            var c=new PixelCanvas();moving.Pixels.CopyTo(c.Data,0);using var bitmap=c.Bitmap(ColorTranslator.FromHtml(ScreenPalette.Preview(d.Color)),4);
            g.DrawString(d.Name,font,Brushes.White,12,row*175+4);g.DrawImageUnscaled(bitmap,12,row*175+32);row++;
        }
        assert(hashes.Count==15,"15 distinct dashboard layouts");sheet.Save(Path.Combine(directory,"telemetry-atlas.png"));
        static bool Dot(PixelFrame f,int x,int y)=>(f.Pixels[y/8*256+x]&(1<<(y%8)))!=0;
        foreach(byte gear in new byte[]{0,1,4,7,10})
        {
            var frame=TelemetryDesigns.Render("15_vector_w8",t with{Gear=gear},false,viewTime);
            for(int cell=0;cell<8;cell++) assert(Dot(frame,3+cell%4*16,3+cell/4*16)==(cell==Math.Min(7,(int)gear)),$"Vector highlights only selected gear {gear}/{cell}");
        }
        var clockA=TelemetryDesigns.Render("03_nissan_300zx_z31",t,false,viewTime);
        var clockB=TelemetryDesigns.Render("03_nissan_300zx_z31",t,false,viewTime.AddMinutes(1));
        assert(!clockA.Pixels.AsSpan().SequenceEqual(clockB.Pixels),"Local HH:mm changes at the next minute");
        var fullArc=TelemetryDesigns.Render("14_vauxhall_astra_gte",t with{Rpm=8001,MaxRpm=8000},false,viewTime);
        var halfArc=TelemetryDesigns.Render("14_vauxhall_astra_gte",t with{Rpm=4000,MaxRpm=8000},false,viewTime);
        for(int dx=-36;dx<=36;dx++)
        {
            int top=(int)Math.Ceiling(27-23*Math.Sqrt(Math.Max(0,1-dx*dx/1296.0)));
            int bottom=Math.Abs(dx)<32?(int)Math.Floor(27-19*Math.Sqrt(1-dx*dx/1024.0)):27;
            for(int y=top;y<=bottom;y++) assert(Dot(fullArc,213+dx,y),$"Full Vauxhall arc has no hole at {dx}/{y}");
        }
        assert(Dot(halfArc,190,12) && !Dot(halfArc,236,12),"Half RPM fills the left arc without lighting the right interior");
        var alfaOff=TelemetryDesigns.Render("10_alfa_romeo_90",t with{Rpm=0,Throttle=0},false,viewTime);
        var alfaOn=TelemetryDesigns.Render("10_alfa_romeo_90",t with{Rpm=8000,Throttle=255},false,viewTime);
        assert(!Dot(alfaOff,160,11) && Dot(alfaOn,160,11),"Alfa positive RPM bar lights its progress");
        assert(Dot(alfaOff,160,26) && !Dot(alfaOn,160,26),"Alfa inverse throttle bar darkens its progress");
        Task.Run(()=>NetworkAsync(assert)).GetAwaiter().GetResult();
    }
    static async Task WaitFor(Func<bool> test)
    { long until=Environment.TickCount64+2500;while(!test()){if(Environment.TickCount64>until)throw new TimeoutException("UDP test timeout");await Task.Delay(10);} }
    static async Task NetworkAsync(Action<bool,string> assert)
    {
        using var reserver=new UdpClient(new IPEndPoint(IPAddress.Loopback,0));int port=((IPEndPoint)reserver.Client.LocalEndPoint!).Port;
        await using var receiver=new TelemetryReceiver();await receiver.ConfigureAsync(true,port,Environment.TickCount64);
        assert(receiver.Detail.Contains("无法监听"),"Busy port is reported without crashing");reserver.Close();
        await receiver.ConfigureAsync(false,port,Environment.TickCount64);await receiver.ConfigureAsync(true,port,Environment.TickCount64);
        using var sender=new UdpClient();await sender.SendAsync(Packet(1),new IPEndPoint(IPAddress.Loopback,port));await WaitFor(()=>receiver.Accepted==1);
        await sender.SendAsync(new byte[2],new IPEndPoint(IPAddress.Loopback,port));await WaitFor(()=>receiver.Rejected==1);
        for(uint i=2;i<=121;i++) { await sender.SendAsync(Packet(i),new IPEndPoint(IPAddress.Loopback,port)); if(i%10==0)await Task.Delay(1); }
        await WaitFor(()=>receiver.Latest?.Timestamp==121);
        assert(receiver.Latest!.Fresh(Environment.TickCount64),"Async UDP receiver keeps latest frame from a 120-packet burst");
        await sender.SendAsync(Packet(120),new IPEndPoint(IPAddress.Loopback,port));await Task.Delay(60);assert(receiver.Latest.Timestamp==121,"Out-of-order packets do not move gauges backward");
        await sender.SendAsync(Packet(122,false),new IPEndPoint(IPAddress.Loopback,port));await WaitFor(()=>receiver.Latest?.Timestamp==122);
        assert(!receiver.Latest!.Fresh(Environment.TickCount64),"Pause packet immediately stops takeover");
        await receiver.ConfigureAsync(false,port,Environment.TickCount64);assert(receiver.Latest==null,"Disabling clears cached sample");
        using var reopened=new UdpClient(new IPEndPoint(IPAddress.Loopback,port));assert(true,"Disabling releases UDP port");
    }
}
