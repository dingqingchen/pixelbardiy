# HaloStudio · PixelBar DIY

> [!WARNING]
> **非官方实验项目 · 设备损坏与变砖风险**
> 本项目主要代码由 **GPT-6 Astra** 完成，结合作者在本机设备上的实验与反馈迭代。项目目前仅在我自己的音响上成功，**尚未经过全面的测试，不保证不会损坏设备**，也不保证适用于所有硬件批次、固件或播放器版本。固件/硬件版本不匹配、刷写中断及其他未知问题，可能导致音响无法启动、显示异常、变砖或其他设备损坏。已提供的备份与回退流程不是通用救砖保证。请先阅读并自行评估并承担使用风险。遇到问题欢迎通过 [GitHub Issues](https://github.com/woozyc/pixelbardiy/issues) 反馈，附版本和复现步骤。

**该项目需要刷入新的音响MCU固件，有变砖风险，若无法接受请勿使用**

HaloStudio 可以让 Edifier Halo PixelBar 显示网易云音乐歌词、电脑状态和自定义的像素画面。

## 主要功能

- **USB 像素直绘**：刷入提供的 MCU 固件后，电脑可通过 USB 直接在音响屏幕上绘制和更新像素画面，更多自定义潜力。
- **电脑性能监控**：显示 CPU、内存、网速、磁盘、显卡和可获取的温度、风扇转速。可以选择紧凑两行、双指标卡片、仪表或曲线等布局，也可以轮换显示。监控设计和硬件检测参考了 [TrafficMonitor](https://github.com/zhongyang219/TrafficMonitor)，感谢其开源项目；日常使用不需要先启动 TrafficMonitor。
- **自定义主题与颜色**：内置六套风格不同的主题，时钟、监控和歌词都能使用；可以换颜色、选择动画，也可以通过编辑主题文件添加新设计。
- **网易云音乐歌词**：播放时自动显示歌词，不必打开桌面歌词或让网易云停留在歌词页面。支持歌词时间调整和导入本地 LRC 文件。
- **退出后恢复官方显示**：正常退出时恢复原厂时钟；程序意外退出后，音响也会在心跳超时后自动恢复。本机已分别测试这两种情况。
- **便携、开源**：Windows 应用解压即可运行，主程序不需要管理员权限。项目原创代码开源。

## 效果展示

[![HaloStudio 界面、主题、歌词和系统监控](docs/images/halostudio-overview.png)](docs/images/halostudio-overview.png)

图中展示了软件界面和六套主题，监控数值及歌词为演示内容。画面由程序生成，实际屏幕颜色可能有所不同。

## 不足与限制

- 功能比官方 TempoHub 少，例如没有天气、资讯、官方在线内容库和完整的素材编辑功能。
- 音响内部传输速度有限，电脑无法像播放视频一样高帧率刷新整屏。目前流畅的切换动画需要安装本项目的显示固件。
- 部分主题、字体和排版还不够美观；屏幕尺寸也限制了长歌词和复杂画面的显示。
- 屏幕一次只能显示一种颜色，电脑预览和实屏可能有色差，不同设备也可能需要重新调整颜色。
- 网易云更新后歌词同步可能需要适配；部分歌曲没有逐字时间或可用歌词，没有网络且没有缓存时也无法获取新歌词。
- 温度、显卡和风扇信息取决于硬件及驱动支持，无法获取的项目会显示 `--`；独立 CPU 温度采集目前仅支持部分 AMD 平台。
- 目前只在文末列出的环境和一台音响上测试，其他硬件批次或软件版本的表现尚不确定。

## 下载与使用

### 1. 下载文件

- [下载 HaloStudio C# 2.6.4（Windows x64）](packages/HaloStudio-CSharp-2.6.4-win64.zip)：日常使用的软件，已包含 .NET 运行环境。
- [下载 MCU 固件与工程工具包 2.6.0](packages/HaloPixelBar-MCU-2.6.0.zip)：用于满足下述前提的固件更新和验证。
- [下载文件校验值](packages/SHA256SUMS.txt)；有需要时可用 PowerShell 的 `Get-FileHash 文件路径 -Algorithm SHA256` 对照。

### 2. 确认固件与刷机前提

当前固件 SHA256 为：

```text
9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e
```

刷机需要 Windows x64、Python 3.12、工程工具包和其中列出的依赖。完整的准备、备份、校验和命令请按[固件工具完整使用流程](docs/FIRMWARE_USAGE.md)操作。如果缺少前提文件或**设备不属于支持的固件版本，请不要继续。**

### 3. 刷入并验证固件

**刷入音响固件有变砖风险**
以下是操作顺序；具体路径和准备命令以[完整固件流程](docs/FIRMWARE_USAGE.md)为准。

1. 先保存并校验原厂文件、当前安装记录、已安装固件和应用备份，完成工具包中的离线验证。
2. 音响通过 USB 接入电脑，切换到**红灯的 USB 声卡模式**。正常退出 HaloStudio、TempoHub 和其他音响控制软件，只连接一台目标音响。
3. 在 PowerShell 中按完整流程设置好 `$py` 并切换到工程根目录，先运行预检：

   ```powershell
   & $py .\halo-studio-dotnet\firmware-color\stage_color.py
   ```

   预检失败就停止，查看错误和日志。预检通过后，确认供电稳定，再运行下面的命令进行一次实际刷写：

   ```powershell
   & $py .\halo-studio-dotnet\firmware-color\stage_color.py --flash-authorized
   ```

4. 传输完成后保持供电，等待音响自行重启，并亲眼确认屏幕显示正常。若传输中断或出现异常，保留供电和日志，不要反复重试；按[故障反馈与回退说明](docs/FIRMWARE_USAGE.md#6-有条件的回退与故障反馈)处理。
5. 按[刷后验证步骤](docs/FIRMWARE_USAGE.md#5-重启后-ram-功能与超时恢复)运行画面和心跳超时测试，确认图形、文字、动画、退出后时钟等恢复功能均正常。

### 4. 启动 HaloStudio

1. 完整解压应用 ZIP，运行 `HaloStudioNet/HaloStudioNet.exe`；不要把 EXE 单独移出文件夹。音响需连接电脑并处于**红灯 USB**模式。
2. 在「设置 → 音响连接」导入这台音响已完成实屏验证的 `mcu-installation.json`。下载包不含个人设备记录；更换应用目录时可导入自己的记录。
3. 在「主题与屏幕」选择主题、颜色，以及没有歌词时显示时钟还是系统监控；在「硬件监控」选择要显示的指标和布局。
4. 在「主题与屏幕」将「播放音乐时」设为「自动显示歌词」，然后播放网易云音乐。在「音乐与灯光」可以调整歌词时间轴偏移或导入 LRC 文件；歌词默认提前约 0.8 秒刷新。
5. 如需 CPU 温度，在「硬件监控」开启独立温度采集。此功能首次默认关闭；第一次开启需要确认一次 Windows 管理员授权，之后通常会复用授权。
6. 可在「设置」开启开机后台启动。关闭窗口会隐藏到托盘；需要停止控制并恢复官方显示时，请选择「退出并恢复原厂显示」。

本机设置、歌词缓存、设备验证记录和日志保存在应用的 `runtime/` 目录，请自行留存，不要将含设备信息的记录公开上传。需要详细设置或自行构建时，可查看 [C# 版说明](halo-studio-dotnet/README.md)；Python 旧版另见[旧版说明](legacy-python/README.md)（已弃用）。

## 官方 TempoHub 兼容性实测

2026-10-14 使用 **EDIFIER TempoHub 1.3.0**、Windows 11 26H2（26300.9457）、网易云 **3.1.41.205564** 测试当前换色 MCU（SHA `9a1b6d…237e`）。HaloStudio 2.6.0 正常退出后，官方软件识别设备并报告 1.3.7；用户已确认**原厂双箭头时钟走秒、中文“吉时 已到”主题、音乐播放、绿色静光、低亮度调节和自创文字显示正常**。

**官方情绪歌词尚未完成验证**：登录 TempoHub 后仍提示需绑定音乐账号，本轮未继续绑定，不能据此判定固件不兼容。自创文字由用户手动测试，尚未覆盖所有排列和动画组合。

这是单台设备上的有限功能测试，不表示官方全部功能、所有版本或恢复能力都已验证。完整操作、证据与未测范围见 [官方兼容性记录](docs/TEMPOHUB_COMPATIBILITY.md)。测试没有再次刷写固件，官方控制器与 HaloStudio 分开运行。

## 实现文档

从 [文档索引](docs/README.md) 开始：涵盖 [实时 USB 像素协议](docs/USB_PIXEL_PROTOCOL.md)、[MCU 本地动画](docs/MCU_ANIMATION.md)及 [固件与恢复边界](docs/FIRMWARE.md)。

## 固件与恢复边界

当前换色与过场镜像为 [mcu-hpl2-color.bin](halo-studio-dotnet/firmware-color/mcu-hpl2-color.bin)，57,252 字节：

```text
9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e
```

它只修改显示 MCU 的应用区域，不包含 USB/音频主控或引导区。已经安装并验证相同固件的设备无需再刷。客户端不会自动升级固件。

[换色固件说明](halo-studio-dotnet/firmware-color/README.md)包含协议、源码、离线报告、升级脚本及限制。`stage_color.py` 是保留的工程工具，需要完整的本机备份、原厂包和身份记录；默认仅预检，显式参数才允许发送，不自动重试。它不是解压即可用于任意设备的通用刷机工具。旧 `HaloFirmware v1.0.0` 更新器仍固定旧 codec 镜像，不能用它刷新的换色镜像。

全屏动画和字符雨的历史源码、镜像及报告也保留在新版目录。回退依赖显示 MCU 应用仍可响应；不能将这些文件当作已经验证的独立救砖方案。

## 已测试环境与必要依赖

| 项目 | 实际测试版本 / 前提 |
| --- | --- |
| Windows | **Windows 11 专业版，64 位，26H2，OS Build 26300.9457**；这是本机测试环境，不代表所有 Windows 版本已验证 |
| 网易云音乐 | **Windows 桌面版 3.1.41.205564**；独立播放进度只对已核对模块指纹启用，更新播放器后可能需要重新适配 |
| 音响 | Edifier Halo PixelBar，USB `VID 2D99 / PID A106`、`MI04`、主控报告 `1.3.7`；还需核对硬件及显示 MCU 镜像，不能只凭产品名判断兼容 |
| 日常运行 | Windows x64 应用包已含 **.NET 10** 运行时；无需 Python、.NET SDK 或 TrafficMonitor。USB HID 使用系统驱动；需自己的、实屏验证过的 MCU 安装记录 |
| 在线歌词 | 需能访问歌词接口；网易云歌曲 ID 与歌词版本应匹配。不要求开启桌面歌词。离线仅使用缓存或导入的 LRC，部分歌曲没有逐字数据 |
| CPU 温度（可选） | 随包 HaloThermal / AMD 采集模块；复用已有 WinRing0/PawnIO，否则通过已校验的 PawnIO 组件加载。首次需确认 UAC 建立固定采集器任务，之后复用；任务失效或采集器更新需重设。独立通道面向 AMD Family 17h / 19h / 1Ah，其他硬件可能没有温度 |
| GPU / 主板监控（可选） | NVIDIA 指标需厂商驱动提供 NVML；主板其他传感器需可用的 LHM/OHM WMI 提供程序。缺少传感器不影响时钟/歌词，显示 `--` |
| C# 源码编译 | Windows x64 + **.NET 10 SDK**（本机构建 10.0.401）；首次还原需网络。目标 API 版本为 Windows 10.0.19041，不能据此宣称旧系统已完整测试 |
| 固件工程工具 | **Python 3.12 x64**、`legacy-python/requirements-dev.txt` 固定依赖（含 Unicorn 2.1.3、Keystone 0.9.2、Capstone 5.0.9、hidapi、PySide6、psutil）；另需自己的原厂包、镜像和备份记录，详见[完整命令流程](docs/FIRMWARE_USAGE.md) |

应用包为 **2.6.4**，固件工具包仍为 **2.6.0** 发布资料；显示 MCU BIN 与 2.5.1 相同，已安装并验证相同 SHA 的设备**无需重新刷写**。本次后台启动、温度授权与网速修复只需更新电脑端。

## 源码与验证

```text
halo-studio-dotnet/   C# 2.6.4 客户端、外部主题/色表、MCU 扩展源码与报告
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

GitHub Actions 分别验证 Python 与 C#。2.6.4 本机通过 423 项离线检查及 30 组布局验证，覆盖温度首次关闭与持久化、后台隐藏启动、授权任务身份、网络接口复位及原有协议／歌词／配色回归；详细验证见[验证记录](halo-studio-dotnet/docs/VALIDATION.md)。新 MCU 的实屏、退出、停心跳恢复已在此前单独验证，本次没有刷写固件。离线检查不替代刷机后的实物确认。

固件离线重建需要自行取得并核对原厂显示 MCU 镜像。先依照 [旧固件构建说明](legacy-python/docs/FIRMWARE.md)准备 `legacy-python/firmware-analysis/v137/mcu.bin`，安装 `legacy-python/requirements-dev.txt` 中的开发依赖，再运行 `python halo-studio-dotnet/firmware-color/validate_color.py`。`legacy-python/` 中的 Python/实验工具同时为新版验证提供基线；仿真不访问 USB，也不在 CI 中自动刷写设备。

## 致谢与许可

项目原创代码采用 [MIT](LICENSE)。温度组件、PawnIO 和参考实现遵循各自许可，详见 [第三方声明](THIRD_PARTY_LICENSE.txt)及[新版声明](halo-studio-dotnet/THIRD_PARTY_LICENSE.txt)。固件 BIN 含原厂专有代码，不因本项目的 MIT 许可而变成 MIT 软件。

感谢 [TrafficMonitor](https://github.com/zhongyang219/TrafficMonitor)、[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)、[PawnIO](https://github.com/namazso/PawnIO) 的开源工作。
