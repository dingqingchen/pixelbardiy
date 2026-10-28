using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace HaloStudio;

public sealed record TelemetryDesign(string Name, string Description, string Color, JsonElement Commands, Dictionary<string,string[]> Sprites, int ReferenceYear = 0);
public static class TelemetryDesigns
{
    public static IReadOnlyDictionary<string,TelemetryDesign> All { get; private set; } = new Dictionary<string,TelemetryDesign>();
    public static string DirectoryPath { get; private set; } = "";
    public static string[] Reload(string path)
    {
        var next = new Dictionary<string,TelemetryDesign>(); var errors = new List<string>();
        foreach (string file in Directory.EnumerateFiles(path,"*.json").Order())
        {
            try
            {
                if (new FileInfo(file).Length > 262144) throw new InvalidDataException("主题超过 256 KB");
                using var doc = JsonDocument.Parse(File.ReadAllText(file), new JsonDocumentOptions { MaxDepth = 32 }); var r = doc.RootElement;
                if (r.GetProperty("version").GetInt32() != 1) throw new InvalidDataException("主题版本不支持");
                string id = r.GetProperty("id").GetString()!;
                if (!Regex.IsMatch(id,@"^[a-z0-9][a-z0-9_-]{0,63}$")) throw new InvalidDataException("id 无效");
                string color = r.GetProperty("color").GetString()!; Protocol.Rgb(color);
                var commands = r.GetProperty("commands").Clone(); Designs.Validate(commands);
                var sprites = new Dictionary<string,string[]>();
                if (r.TryGetProperty("sprites",out var sj)) foreach(var p in sj.EnumerateObject()) sprites[p.Name] = p.Value.EnumerateArray().Select(v=>v.GetString()!).ToArray();
                int referenceYear=0;
                if(r.TryGetProperty("reference_year",out var year)) int.TryParse(Regex.Match(year.GetString() ?? "",@"\b(?:19|20)\d{2}\b").Value,out referenceYear);
                var design = new TelemetryDesign(r.GetProperty("name").GetString()!,r.GetProperty("description").GetString()!,color,commands,sprites,referenceYear);
                // Validate expressions/fields before publishing a new set.
                Render(id,design,TelemetrySprint.At(7),false,DateTime.Now);
                if(!next.TryAdd(id,design)) throw new InvalidDataException("重复 id");
            }
            catch(Exception e) when(e is JsonException or InvalidDataException or KeyNotFoundException or ArgumentException or InvalidOperationException or FormatException) { errors.Add(Path.GetFileName(file)+": "+e.Message); }
        }
        if(next.Count==0) throw new InvalidDataException("没有可用遥测主题："+string.Join("；",errors));
        All=next; DirectoryPath=path; return errors.ToArray();
    }
    public static PixelFrame Render(string key,CarTelemetry t,bool demo,DateTime? now = null) => Render(key, All.GetValueOrDefault(key) ?? All.Values.First(), t, demo,now ?? DateTime.Now);
    static PixelFrame Render(string key,TelemetryDesign d,CarTelemetry t,bool demo,DateTime now)
    {
        static string Num(double n,string format="0") => n.ToString(format,CultureInfo.InvariantCulture);
        var numbers = new Dictionary<string,double>
        {
            ["gear_raw"]=t.Gear, ["speed"]=Math.Min(999,t.Kmh), ["speed_ratio"]=Math.Clamp(t.Kmh/300,0,1),
            ["rpm"]=t.Rpm,["max_rpm"]=t.MaxRpm,["rpm_ratio"]=t.RpmRatio,["throttle"]=t.Throttle/255.0,
            ["brake"]=t.Brake/255.0,["fuel"]=Math.Clamp(t.Fuel,0,1),["boost"]=Math.Clamp(t.Boost/30,0,1),
            ["handbrake"]=t.Handbrake>0?1:0,["engine"]=t.Rpm>100?1:0,
            ["slip_fl"]=Math.Abs(t.SlipFL)>1?1:0,["slip_fr"]=Math.Abs(t.SlipFR)>1?1:0,
            ["slip_rl"]=Math.Abs(t.SlipRL)>1?1:0,["slip_rr"]=Math.Abs(t.SlipRR)>1?1:0,
            ["steer"]=t.Steer/127.0,["phase"]=(t.Distance%6)/6,["demo"]=demo?1:0
        };
        var text=new Dictionary<string,string>
        {
            ["clock"]=now.ToString("HH:mm",CultureInfo.InvariantCulture), ["gear_high"]=t.Gear>=7?Num(t.Gear):"7+",
            ["rpm_k"]=Num(t.Rpm/1000,t.Rpm<10000?"0.0":"0"),["boost_int"]=Num(Math.Clamp(t.Boost,-99,999)),["engine_state"]=t.Rpm>100?"ON":"--",
            ["year"]=d.ReferenceYear>0?d.ReferenceYear.ToString(CultureInfo.InvariantCulture):"", ["max_rpm"]=Num(t.MaxRpm),
            ["speed"]=Num(Math.Clamp(t.Kmh,0,999)), ["rpm"]=Num(t.Rpm),["rpm100"]=Num(t.Rpm/100),
            ["gear"]=t.Gear==0?"R":Num(t.Gear),["fuel"]=Num(Math.Clamp(t.Fuel,0,1)*100),
            ["power"]=Num(t.Power/1000),["torque"]=Num(t.Torque),["boost"]=Num(t.Boost,"0.0"),
            ["throttle"]=Num(t.Throttle/2.55),["brake"]=Num(t.Brake/2.55),
            ["trip"]=Num(Math.Clamp(t.Distance/1000,0,999.9),"0.0"),
            ["drive"]=t.Drivetrain switch {0=>"FWD",1=>"RWD",2=>"AWD",_=>"---"},
            ["mode"]=demo?"DEMO":"LIVE", ["time"]=Num(Math.Clamp(t.RaceTime,0,9999),"0.0")
        };
        for(int i=1;i<=8;i++) text["tick"+i]=Num(t.MaxRpm*i/8000,"0.#");
        var pixels=Designs.RenderCommands(d.Commands,d.Sprites,numbers,text);
        return new(pixels,$"{(demo?"零百加速演示（模拟数据）":"地平线 6")} · {d.Name} · {text["speed"]} km/h · {text["rpm"]} RPM · {text["gear"]} 挡","遥测:"+key);
    }
}
