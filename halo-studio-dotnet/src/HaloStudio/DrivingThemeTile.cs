using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Text.Json;
namespace HaloStudio;

// Photos are local references. They are decoded only when a card becomes visible.
internal sealed record CarPhoto(string File, string Caption, string Source, string Credit, string License);
internal sealed record CarPhotoPair(CarPhoto Exterior, CarPhoto Interior);
internal static class CarPhotos
{
    internal static readonly string DirectoryPath = Path.Combine(AppContext.BaseDirectory, "telemetry-photos");
    static readonly Dictionary<string, CarPhotoPair> All = Read();
    static Dictionary<string, CarPhotoPair> Read()
    {
        try { return JsonSerializer.Deserialize<Dictionary<string, CarPhotoPair>>(File.ReadAllText(Path.Combine(DirectoryPath,"manifest.json")), new JsonSerializerOptions { PropertyNameCaseInsensitive=true }) ?? []; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException) { return []; }
    }
    internal static CarPhotoPair? Get(string key) => All.GetValueOrDefault(key);
    internal static Bitmap? Load(CarPhoto? photo, int maxWidth)
    {
        if(photo is null || Path.GetFileName(photo.File)!=photo.File) return null;
        try
        {
            using var original=Image.FromFile(Path.Combine(DirectoryPath,photo.File));
            int w=Math.Min(maxWidth,original.Width), h=Math.Max(1,(int)((long)original.Height*w/original.Width));
            var copy=new Bitmap(w,h); using var g=Graphics.FromImage(copy);
            g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(original,0,0,w,h);return copy;
        }
        catch(Exception e) when(e is IOException or UnauthorizedAccessException or ArgumentException or OutOfMemoryException) { return null; }
    }
    internal static void Show(Control owner, string model, CarPhoto? photo)
    {
        if(photo is null) return;
        using var image=Load(photo,1600);
        using var dialog=new Form { Text=model+" · "+photo.Caption, StartPosition=FormStartPosition.CenterParent, Size=new(1000,730), MinimumSize=new(640,440), BackColor=Palette.Background, ShowInTaskbar=false, AutoScaleMode=AutoScaleMode.Dpi };
        var picture=new PictureBox { Dock=DockStyle.Fill,SizeMode=PictureBoxSizeMode.Zoom,Image=image,BackColor=Color.FromArgb(20,26,39), Padding=new(12) };
        var footer=new Panel { Dock=DockStyle.Bottom, Height=108,Padding=new(18,10,18,10),BackColor=Palette.Card };
        var credit=new Label { Dock=DockStyle.Fill,Text=photo.Caption+"\n"+photo.Credit+" · "+photo.License,Font=Palette.Font(9),ForeColor=Palette.Muted };
        var source=new LinkLabel { Dock=DockStyle.Bottom,Height=28,Text="查看照片来源",Font=Palette.Font(9),LinkColor=Palette.Accent };
        source.LinkClicked+=(_,_)=> { if(Uri.TryCreate(photo.Source,UriKind.Absolute,out var uri) && uri.Scheme is "http" or "https") try { Process.Start(new ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute=true }); } catch(Exception e) when(e is System.ComponentModel.Win32Exception or InvalidOperationException) { MessageBox.Show(dialog,"无法打开浏览器。照片来源："+photo.Source); } };
        footer.Controls.Add(credit);footer.Controls.Add(source);dialog.Controls.Add(picture);dialog.Controls.Add(footer);dialog.ShowDialog(owner.FindForm());
    }
}

internal sealed class CarPhotoButton : Button
{
    readonly CarPhoto? photo; Bitmap? cached; bool attempted;
    internal CarPhotoButton(string model,string label,CarPhoto? photo)
    {
        this.photo=photo;Text="";AccessibleName=model+" · "+label+"，查看大图";Cursor=Cursors.Hand;
        SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.ResizeRedraw,true);
        Click+=(_,_)=>CarPhotos.Show(this,model,photo);
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g=e.Graphics;g.Clear(Parent?.BackColor??Palette.Card);g.SmoothingMode=SmoothingMode.AntiAlias;
        var r=new Rectangle(1,1,Width-3,Math.Max(1,Height-3));
        using var font=Palette.Font(8);
        using var path=Palette.Rounded(r,Palette.Px(this,7));using var bg=new SolidBrush(Color.FromArgb(20,26,39));g.FillPath(bg,path);
        if(!attempted) { cached=CarPhotos.Load(photo,480);attempted=true; }
        if(cached is not null)
        {
            double scale=Math.Max((double)r.Width/cached.Width,(double)r.Height/cached.Height);
            var target=new RectangleF(r.X+(r.Width-(float)(cached.Width*scale))/2,r.Y+(r.Height-(float)(cached.Height*scale))/2,(float)(cached.Width*scale),(float)(cached.Height*scale));
            var state=g.Save();g.SetClip(path);g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(cached,target);g.Restore(state);
        }
        else TextRenderer.DrawText(g,"暂无参考照片",font,r,Color.LightGray,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter);
        if(Focused) ControlPaint.DrawFocusRectangle(g,Rectangle.Inflate(r,-4,-4));
    }
    protected override void Dispose(bool disposing) { if(disposing) cached?.Dispose();base.Dispose(disposing); }
}

internal sealed class DrivingThemeTile : Control
{
    readonly string caption,description; readonly Bitmap preview; readonly CarPhotoButton exterior,interior;bool selected;
    public string Key { get; }
    [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
    public bool Selected { get=>selected;set { if(selected==value)return;selected=value;Invalidate(); } }
    public DrivingThemeTile(string key,TelemetryDesign design)
    {
        Key=key;caption=design.Name;description=(design.ReferenceYear>0?design.ReferenceYear+" · ":"")+design.Description;DoubleBuffered=true;ResizeRedraw=true;TabStop=true;Cursor=Cursors.Hand;BackColor=Palette.Card;AccessibleName=caption;AccessibleRole=AccessibleRole.RadioButton;
        var canvas=new PixelCanvas();TelemetryDesigns.Render(key,TelemetrySprint.At(9),true).Pixels.CopyTo(canvas.Data,0);preview=canvas.Bitmap(ColorTranslator.FromHtml(ScreenPalette.Preview(design.Color)),1);
        var photos=CarPhotos.Get(key);exterior=new(caption,"外观",photos?.Exterior);interior=new(caption,"内饰 / 仪表",photos?.Interior);
        Controls.Add(exterior);Controls.Add(interior);
        KeyDown+=(_,e)=> { if(e.KeyCode is Keys.Enter or Keys.Space) { OnClick(EventArgs.Empty);e.Handled=true;e.SuppressKeyPress=true; } };
    }
    protected override void OnLayout(LayoutEventArgs e)
    {
        base.OnLayout(e);if(exterior is null)return;int p=Palette.Px(this,16),gap=Palette.Px(this,12),w=Math.Max(1,(Width-p*2-gap)/2);
        exterior.SetBounds(p,Palette.Px(this,176),w,Palette.Px(this,123));interior.SetBounds(p+w+gap,exterior.Top,w,exterior.Height);
    }
    protected override void OnPaint(PaintEventArgs e)
    {
        var g=e.Graphics;g.Clear(Parent?.BackColor??Palette.Background);g.SmoothingMode=SmoothingMode.AntiAlias;int p=Palette.Px(this,16);
        using var path=Palette.Rounded(new RectangleF(1,1,Width-3,Height-3),Palette.Px(this,12));using var bg=new SolidBrush(Palette.Card);g.FillPath(bg,path);using var edge=new Pen(selected?Palette.Accent:Palette.Border,selected?2:1);g.DrawPath(edge,path);
        using var title=Palette.Font(10,FontStyle.Bold);TextRenderer.DrawText(g,(selected?"✓  ":"")+caption,title,new Rectangle(p,p,Width-p*2,Palette.Px(this,29)),Palette.Text,TextFormatFlags.EndEllipsis|TextFormatFlags.VerticalCenter);
        var box=new Rectangle(p,Palette.Px(this,54),Width-p*2,Palette.Px(this,58));using var strip=new SolidBrush(Color.FromArgb(20,26,39));using var sp=Palette.Rounded(box,Palette.Px(this,6));g.FillPath(strip,sp);
        int w=Math.Min(box.Width-Palette.Px(this,12),(box.Height-Palette.Px(this,8))*8);w-=w%8;g.InterpolationMode=InterpolationMode.NearestNeighbor;g.PixelOffsetMode=PixelOffsetMode.Half;g.DrawImage(preview,new Rectangle(box.X+(box.Width-w)/2,box.Y+(box.Height-w/8)/2,w,w/8),0,0,256,32,GraphicsUnit.Pixel);g.PixelOffsetMode=PixelOffsetMode.Default;
        using var small=Palette.Font(8);TextRenderer.DrawText(g,description,small,new Rectangle(p,Palette.Px(this,124),Width-p*2,Palette.Px(this,44)),Palette.Muted,TextFormatFlags.WordBreak|TextFormatFlags.EndEllipsis);
        if(Focused)ControlPaint.DrawFocusRectangle(g,new Rectangle(5,5,Width-10,Height-10));
    }
    protected override void Dispose(bool disposing) { if(disposing)preview.Dispose();base.Dispose(disposing); }
}
