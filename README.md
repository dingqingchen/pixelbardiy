# HaloStudio · PixelBar DIY

将 Edifier Halo PixelBar 的 **256 × 32 点阵屏**用作图形时钟、系统监控、网易云逐句歌词和音乐氛围灯。当前桌面版为 **C# / .NET 10 的 HaloStudio 2.5.1**，Python 旧版源码继续保留。

画面通过 USB HID 写入显示 MCU 的 RAM，支持压缩、差分更新和 MCU 本地动画。日常换图、换主题和歌词更新不擦写 Flash，也不会出现原厂图片上传提示。

> 非官方实验性项目。已测试的是 USB `VID 2D99 / PID A106`、控制接口 `MI04`、主控报告版本 `1.3.7` 的设备，产品名或版本号相同不代表内部硬件相同。显示 MCU 完全失效后的独立 USB 恢复仍未验证。备份的镜像是已知文件，不是整机 Flash 读回。

## 下载与启动

| 内容 | 下载 / 说明 |
| --- | --- |
| 最新 Windows x64 应用与固件资料 | [HaloStudio C# 2.5.1](packages/HaloStudio-CSharp-2.5.1-win64.zip) |
| MCU 固件与工程工具包 | [HPL2 2.5.1 固件包](packages/HaloPixelBar-MCU-2.5.1.zip) |
| 下载校验 | [全部包的 SHA256](packages/SHA256SUMS.txt) |
| C# 使用、配置与构建 | [新版说明](halo-studio-dotnet/README.md) |
| Python 旧版 | [旧版说明和下载](legacy-python/README.md) |

1. 完整解压 ZIP，运行其中 `HaloStudioNet/HaloStudioNet.exe`。包含 .NET 运行时，无需安装 Python 或 .NET；保留所有资源和依赖文件。
2. 正常退出 TempoHub 或其他显示控制程序。导入**本机已完成实屏验证**的 MCU 安装记录，客户端按固件哈希启用对应能力；分发包不含个人设备记录。首次使用可先运行 `HaloStudioNet.exe --preview` 离线查看。
3. 在“主题与屏幕”选择默认时钟或监控，播放网易云音乐时可自动显示歌词。在“设置”开启登录 Windows 后后台启动。
4. 关闭窗口会隐藏到托盘；“设置 → 退出并恢复原厂显示”才会停止显示控制。旧版本入口在“设置 → HaloStudio”内，切换前先释放显示权；未自动找到旧版时可手动选择 EXE。

本机设置、歌词缓存、安装身份、运行日志都保存在 `runtime/`，不纳入 Git 或分发包。不要复制其他人的安装记录来绕过设备验证。

## 实现文档

从 [文档索引](docs/README.md) 开始：涵盖 [实时 USB 像素协议](docs/USB_PIXEL_PROTOCOL.md)、[MCU 本地动画](docs/MCU_ANIMATION.md)及 [固件与恢复边界](docs/FIRMWARE.md)。

## 当前功能

- 六套运行时加载的外部 JSON 主题，统一覆盖时钟、系统监控和歌词，各自有布局、图案、字形及过场设计。
- 单指标仪表、历史曲线、紧凑两行、双指标卡片；双指标优先同类配对，余项就近匹配，只有总数为奇数时末项单独显示；横向轮换可选每次一个或一对。
- 网易云实时歌词、本地 LRC，以及按实际播放能量变化的两侧灯光。播放器版本变化可能需要更新适配。
- 独立 CPU 温度采集，优先复用已有驱动。驱动需要权限时仅采集器请求 UAC；支持范围见[温度说明](legacy-python/docs/THERMAL.md)。
- MCU 本地整屏上推、横向揭幕、中心展开、像素溶解与字符雨；新版换色与画面在同一显示租约中提交，主题和演示换幕不再插入原厂时钟。
- 独占显示、心跳超时恢复、正常退出恢复原厂时钟；后台暂停 UI 绘制、按需采样、合并待传帧，避免积压。
- 响应式卡片布局、统一控件、可滚动指标列表；高 DPI 下重载调色板仍保持正确尺寸。

快捷色按观感色相排列为 **柔红 → 土黄 → 浅绿 → 离子蓝 → 猫咪蓝 → 淡粉 → 白色**，包含六套主题原色。浅绿、淡粉、土黄和白色使用本机目视校准结果；柔红是待实屏核对的候选。预览是近似示意，不能保证任意 RGB 与实屏一致。[颜色原理和校准记录](halo-studio-dotnet/docs/COLORS.md)。

## 固件与恢复边界

当前换色与过场镜像为 [mcu-hpl2-color.bin](halo-studio-dotnet/firmware-color/mcu-hpl2-color.bin)，57,252 字节：

```text
9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e
```

它只修改显示 MCU 的应用区域，不包含 USB/音频主控或引导区。已经安装并验证相同固件的设备无需再刷。客户端不会自动升级固件。

[换色固件说明](halo-studio-dotnet/firmware-color/README.md)包含协议、源码、离线报告、升级脚本及限制。`stage_color.py` 是保留的工程工具，需要完整的本机备份、原厂包和身份记录；默认仅预检，显式参数才允许发送，不自动重试。它不是解压即可用于任意设备的通用刷机工具。旧 `HaloFirmware v1.0.0` 更新器仍固定旧 codec 镜像，不能用它刷新的换色镜像。

全屏动画和字符雨的历史源码、镜像及报告也保留在新版目录。回退依赖显示 MCU 应用仍可响应；不能将这些文件当作已经验证的独立救砖方案。

## 源码与验证

```text
halo-studio-dotnet/   C# 2.5.1 客户端、外部主题/色表、MCU 扩展源码与报告
legacy-python/       Python 旧版、依赖、测试与固件实验基线
docs/                MCU 动画、USB 协议与显示链路的实现原理
firmware/            当前与历史显示 MCU 镜像、校验值
packages/            可下载的应用包、历史包与哈希
```

在 Windows 上安装 .NET 10 SDK，然后：

```powershell
cd halo-studio-dotnet
./scripts/build.ps1
./scripts/verify.ps1
```

GitHub Actions 分别验证 Python 与 C#。本机 2.5.1 已完成协议/主题自检、30 组布局状态和连续三次高 DPI 色表重载检查；新 MCU 的实屏、退出、停心跳恢复已单独验证。[验证范围与记录](halo-studio-dotnet/docs/VALIDATION.md)。离线检查不替代刷机后的实物确认。

固件离线重建需要自行取得并核对原厂显示 MCU 镜像。先依照 [旧固件构建说明](legacy-python/docs/FIRMWARE.md)准备 `legacy-python/firmware-analysis/v137/mcu.bin`，安装 `legacy-python/requirements-dev.txt` 中的开发依赖，再运行 `python halo-studio-dotnet/firmware-color/validate_color.py`。`legacy-python/` 中的 Python/实验工具同时为新版验证提供基线；仿真不访问 USB，也不在 CI 中自动刷写设备。

## 许可

项目原创代码采用 [MIT](LICENSE)。温度组件、PawnIO 和参考实现遵循各自许可，详见 [第三方声明](THIRD_PARTY_LICENSE.txt)及[新版声明](halo-studio-dotnet/THIRD_PARTY_LICENSE.txt)。固件 BIN 含原厂专有代码，不因本项目的 MIT 许可而变成 MIT 软件。
