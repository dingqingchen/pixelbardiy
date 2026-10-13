# README 效果图

`images/halostudio-overview.png` 展示 HaloStudio 2.6.2 的三页客户端界面、六套时钟主题、三段原创歌词及监控编排。客户端控件由 WinForms 实际绘制，点阵来自应用使用的 `Designs.Render`，没有另外重画一套产品界面。

为避免 `DrawToBitmap` 把系统标题栏导出成经典 GDI / Win7 风格，导出只保留真实客户端区域；拼图脚本添加 Win11 风格的平面标题栏、圆角细边框和柔和阴影。该外框是展示排版，并非 DWM 截屏。点阵是电脑端近似预览，不是音响实拍，也不证明物理色彩或动画帧率。

截图模式必须使用 `--preview`，不接管 USB；使用固定日期、`Showcase.Sample` 模拟指标及原创歌词，不使用个人歌曲信息。应在单独的应用副本／运行目录中执行，避免污染日常设置。Pillow 仅是生成图片的开发依赖，日常应用不依赖 Python。

在仓库根目录的 PowerShell 中执行：

```powershell
# 先构建独立的文档预览副本
dotnet publish ./halo-studio-dotnet/src/HaloStudio/HaloStudio.csproj `
  -c Release -r win-x64 --self-contained true `
  -o ./halo-studio-dotnet/validation/readme/app

$shots = Join-Path (Get-Location) 'halo-studio-dotnet/validation/readme/shots'
$runtime = Join-Path (Get-Location) 'halo-studio-dotnet/validation/readme/runtime'
Start-Process ./halo-studio-dotnet/validation/readme/app/HaloStudioNet.exe `
  -ArgumentList @('--preview', '--runtime', ('"' + $runtime + '"'), `
    '--readme-shots', ('"' + $shots + '"'), '--quit-after', '15') -Wait

# Pillow 12.3.0 为本次生成版本；仅安装在开发环境
python -m pip install Pillow==12.3.0
python ./scripts/compose-readme.py $shots ./docs/images/halostudio-overview.png
```

拼图脚本使用 Windows 自带的微软雅黑。源截图只保存在忽略的 `validation/` 目录；公开提交的是最终拼图和可复现的生成代码。
