namespace HaloStudio;
// Compact labels only. Vehicle speed uses larger seven-segment digits.
public static class TelemetryFont
{
    static readonly Dictionary<char,string> glyphs = new()
    {
        ['A'] = "010101111101101",
        ['B'] = "110101110101110",
        ['C'] = "011100100100011",
        ['D'] = "110101101101110",
        ['E'] = "111100110100111",
        ['F'] = "111100110100100",
        ['G'] = "011100101101011",
        ['H'] = "101101111101101",
        ['I'] = "111010010010111",
        ['J'] = "001001001101010",
        ['K'] = "101101110101101",
        ['L'] = "100100100100111",
        ['M'] = "101111111101101",
        ['N'] = "101111111111101",
        ['O'] = "111101101101111",
        ['P'] = "110101110100100",
        ['Q'] = "111101101111001",
        ['R'] = "110101110101101",
        ['S'] = "011100111001110",
        ['T'] = "111010010010010",
        ['U'] = "101101101101111",
        ['V'] = "101101101101010",
        ['W'] = "101101111111101",
        ['X'] = "101101010101101",
        ['Y'] = "101101010010010",
        ['Z'] = "111001010100111",
        ['0'] = "111101101101111",
        ['1'] = "010110010010111",
        ['2'] = "110001111100111",
        ['3'] = "110001111001110",
        ['4'] = "101101111001001",
        ['5'] = "111100111001110",
        ['6'] = "011100111101111",
        ['7'] = "111001010010010",
        ['8'] = "111101111101111",
        ['9'] = "111101111001110",
        [' '] = "000000000000000",
        ['.'] = "000000000000010",
        [':'] = "000010000010000",
        ['/'] = "001001010100100",
        ['-'] = "000000111000000",
        ['+'] = "000010111010000",
        ['='] = "000111000111000",
        ['%'] = "101001010100101",
        ['!'] = "010010010000010",
        ['_'] = "000000000000111",
        ['|'] = "010010010010010",
        ['<'] = "001010100010001",
        ['>'] = "100010001010100",
    };
    public static void Micro(PixelCanvas c,string text,int x,int y)
    {
        foreach(char ch in text.ToUpperInvariant()) { string bits=glyphs.GetValueOrDefault(ch,glyphs[' ']); for(int i=0;i<15;i++) if(bits[i]=='1') c.Dot(x+i%3,y+i/3); x+=4; }
    }
    static readonly string[] sevenSegments = "abcdef bc abged abgcd fgbc afgcd afgecd abc abcdefg abfgcd".Split(' ');
    public static void Seven(PixelCanvas c,string text,int x,int y,int width,int height,int thick,int gap,int slots)
    {
        width=Math.Clamp(width,5,24);height=Math.Clamp(height,7,30);thick=Math.Clamp(thick,1,3);gap=Math.Clamp(gap,1,6);slots=Math.Clamp(slots,1,6);
        text=text.Length>slots?text[^slots..]:text.PadLeft(slots);
        var parts=sevenSegments;int mid=height/2;
        foreach(char ch in text)
        {
            if(ch is >= '0' and <= '9') foreach(char p in parts[ch-'0'])
            {
                if(p is 'a' or 'g' or 'd') c.Rect(x+thick,y+(p=='a'?0:p=='g'?mid-thick/2:height-thick),width-2*thick,thick,true);
                else c.Rect(x+(p is 'f' or 'e'?0:width-thick),y+(p is 'f' or 'b'?thick:mid),thick, p is 'f' or 'b'?mid-thick:height-thick-mid,true);
            }
            else if(ch!=' ') c.Raster(ch.ToString(),x,y+(height-7)/2);
            x+=width+gap;
        }
    }
}
