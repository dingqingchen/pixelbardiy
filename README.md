# HaloStudio · PixelBar DIY

让 Edifier Halo PixelBar 的 **256 × 32 点阵屏**成为可编程显示屏：图形时钟、硬件监控、网易云逐句歌词和音乐氛围灯，统一在 Windows 控制台里设置。

新版使用定制显示 MCU 的 **RAM 直绘**。画面在内存里更新，支持无损压缩、差分帧和 MCU 本地字幕动画，没有逐句“图片上传中”的提示。日常显示路径不调用固件更新或资源 Flash 写入。

> 本项目为非官方实验性改造。目前实测对象是 USB `VID 2D99 / PID A106`、控制接口 `MI04`、主控报告版本 `1.3.7` 的 Halo PixelBar。相同产品名或版本号不能证明内部硬件一致。**显示 MCU 完全失效后的独立 USB 救砖方法尚未验证。**

## 下载与启动

| 包 | 用途 |
| --- | --- |
| [HaloStudio v1.0.0 · Windows x64](packages/HaloStudio-v1.0.0-win64.zip) | 已打包电脑应用，不需要安装 Python |
| [MCU 更新工具与固件 v1.0.0](packages/HaloFirmware-v1.0.0-win64.zip) | 独立控制台更新器、已验证镜像和 PowerShell 脚本 |
| [SHA256 校验](packages/SHA256SUMS.txt) | 校验下载的两个 ZIP |

1. 完整解压 HaloStudio 包到一个可写、长期保留的位置，例如 `D:\Apps\HaloStudio`。保留 `_internal`，不要只复制 EXE。
2. 退出 TempoHub，双击 `HaloStudio.exe`。控制台与固件更新器共享单实例显示锁。
3. 已改造且完成本机验证的音响可以直接直绘。新安装需要先完成下述固件与屏幕验证；缺少验证记录时只显示本地预览，不会尝试原厂图片上传。
4. 在“后台与资源”开启“开机登录后自动启动到系统托盘”。它写入当前用户 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\HaloStudio`，启动参数为 `--background`，无需管理员权限。

关闭窗口会收起到托盘。托盘“退出”会停止同步、释放显示权，并恢复原厂时钟。退出不取消下一次登录的自启动；关闭自启动请取消对应开关。移动应用目录后重新开启开关以更新路径。程序路径过长时请放到更短的目录。

也可运行：

```powershell
.\scripts\Set-Autostart.ps1 -Action enable
.\scripts\Set-Autostart.ps1 -Action disable
.\HaloStudio.exe --background
```

Windows 启动应用列表里如果手动禁用了该项，需要在 Windows 设置中重新启用。软件显示的是自身注册的 Run 项。

## 显示与主题

- **时钟**：默认内容可选时钟或系统监控；时钟可选择显示秒、主题、颜色和动效。
- **监控**：单指标、双指标卡片、紧凑双行概览、轮流显示。支持 CPU/GPU 使用率、内存、网络速度、可用温度与风扇传感器。没有读数的传感器显示未知；风扇百分比需填写对应最大转速。
- **网易云歌词**：从支持版本的本地播放器读取实时歌词，并支持本地 LRC 和可关闭的在线补充。直接将中文字形绘制成像素。支持向上推入、横向揭幕等本地切换动画；播放器升级导致内存结构变化时可能需要更新适配。
- **氛围灯**：使用播放音频的动态峰值，而非固定音量滑块，驱动两侧音乐律动；可独立开关并调节增益。
- **新版 / 旧版**：左上角的小“旧版”入口保留原厂文字、图片等功能。切换前等待当前后台完全退出并恢复原厂显示，两套引擎串行交接。

六套主题贯穿时钟、监控和歌词，分别使用不同布局、图案与像素字形：

| 主题 | 设计语言 |
| --- | --- |
| 离子仪表 | 切角数字、航空刻度、信号舷窗 |
| 雷达终端 | 等宽数据、扫描栅格、终端字幕 |
| 桃兔甜点 | 圆润字形、奶油卡片、兔兔气泡 |
| 猫咪乐谱 | 跳跃像素、钢琴键盘、五线谱 |
| 月白书页 | 衬线数字、编辑排版、山形留白 |
| 琥珀音响 | 点阵数字、磁带双盘、模拟电平 |

主题动画、页面切换动画和音乐律动均可关闭。整个点阵是单色像素，显示颜色由屏幕灯色设置控制。

## CPU 温度与后台资源

CPU 温度采集可以独立运行。当前直接寄存器采集支持 **AMD Zen family 17h / 19h / 1Ah**；本次实测 CPU 为 Ryzen 5 9600X。Intel 和其他不支持的 CPU 不应套用此温度算法。

在监控页点击“启用 CPU 温度 · 管理员确认”：只提升小型 `HaloThermal.exe` 采集进程，主 UI 保持普通权限。先复用已加载的 WinRing0 兼容驱动；其次复用官方签名 PawnIO。两者都不存在时才校验并运行随包附带的官方 PawnIO 2.2.0 安装器。不会重复安装 TrafficMonitor 已加载的驱动，也不需要启动 TrafficMonitor。

每次启动 HaloStudio 后，温度采集仍需明确开启并通过 UAC；登录自启动不会绕过此权限确认。共享驱动不会随软件退出卸载。实现、上游出处和硬件支持范围见 [温度采集说明](docs/THERMAL.md)。

节能模式监控约 3 秒采样、律动目标 20 Hz；均衡模式约 2 秒和 30 Hz。隐藏窗口停止预览绘制；相同帧不重发；传输队列只保留最新目标；传感器按需唤醒，采集器空闲时阻塞等待。静止屏幕维持约 500 ms 心跳。

一次本机后台测试中，六十秒整机归一化 CPU 平均约 **0.07%**，主程序内存约 **204 MB**，温度采集器约 **5.4 MB**。这是具体配置的观测值，不能换算为功率或保证其他机器相同。Qt/Python 应用内存仍有进一步优化空间。

## MCU 固件更新

**这台已经实测成功的音响无需再次刷写相同固件。** 平时换主题、歌词、监控只写 RAM。

更新包包括 57,252 字节的显示 MCU 应用镜像，不包括 USB/音频主控和启动加载器。SHA256：

```text
f7b8ee274ba2439b3211c5eea80206599acff6e80d73dc0c898ba143e2e32f62
```

请先阅读 [完整更新步骤与恢复限制](docs/FIRMWARE.md)。基本流程如下：

```powershell
# 在完整解压的 HaloFirmware 目录中执行。默认仅查询，不能刷写。
.\scripts\Verify-Package.ps1
.\scripts\Update-MCU.ps1 -Action OfflineCheck
.\scripts\Update-MCU.ps1 -Action Preflight

# 完全退出 HaloStudio 和 TempoHub，保留原厂 PC_137 固件包并核对序列号。
# 以下命令会备份本机配置和原厂包，并要求再次输入 FLASH <序列号>。
.\scripts\Update-MCU.ps1 -Action Flash -AppDirectory 'D:\Apps\HaloStudio' `
  -Serial '<上一步查询的序列号>' -FactoryPackage 'D:\Firmware\Halo PixelBar-PC_137.bin'

# 等待设备重启恢复正常画面后，再执行；核对实物画面后输入 YES。
.\scripts\Update-MCU.ps1 -Action VerifyDisplay -AppDirectory 'D:\Apps\HaloStudio'
```

更新器只接受固定镜像、原厂包和已测试的协议状态。1057 个请求驱动的分包保持字节一致；不发送 USB 主控固件、不主动复位、不自动重试。中断会保留状态和原始包日志，默认阻止再次刷写。

主控回报的 `1.3.7` 版本以及 HID 回复都不能证明 MCU 已启动。只有传输记录匹配、实际看到猫咪/边框/`RAM LIVE 01 → 02`、没有上传提示，并且退出后恢复稳定原厂时钟，才生成本机 `runtime/mcu-installation.json`。该记录绑定当前 USB 路径与音响序列号，**不能从别人的电脑复制**；换 USB 口可能需要重新验证。

## 源码与构建

建议 Windows x64、Python 3.12。运行时和开发依赖均锁定版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
.\scripts\Build-App.ps1 -Python '.\.venv\Scripts\python.exe'
.\.venv\Scripts\python.exe scripts\package_release.py --version v1.0.0
```

打包脚本会运行测试、分别构建 GUI 与控制台更新器，并离线校验固件。发布脚本生成两个 ZIP、逐文件清单及 `SHA256SUMS.txt`，排除运行目录、配置和歌词缓存。首次发布的二进制由仓库内源代码构建，打包目录是 `dist/`。

如需重新编译采集器，安装 Zig 0.13.0 后运行 `scripts\Build-Thermal.ps1 -Zig '<zig.exe>'`。仓库同时保留已编译的采集器、未修改的官方 PawnIO 安装器与模块，以及来源和许可证。

MCU 补丁源码位于 `firmware-lab/`。提供**精确原厂 1.3.7 MCU 分段**即可离线重建：

```powershell
.\.venv\Scripts\python.exe scripts\build_firmware.py --original-mcu '<原厂 mcu.bin>'
```

输入段 SHA256 必须为 `8fb58ded25d23b5148dc9a37ec57b380e03d65681c13c7f445eff62102010e3b`。工具重建并运行 ARM 仿真，要求输出与发布镜像一致；它不会连接音响。Unicorn 必须为 2.1.3，2.1.4 不通过本项目的 Thumb IT 回归。原厂完整包需从自己的 TempoHub 下载保存，仓库不提供第三方全量固件归档。

```text
halo/                    应用、界面、监控、歌词、USB 与 RAM 传输
main.py                  Windows GUI 入口
firmware_update.py       独立更新器入口
firmware/hpl2-codec/     已验证 MCU 镜像、校验与审核摘要
firmware-lab/            补丁汇编、压缩及离线 ARM 验证
thermal-native/         小型原生温度采集器源码和上游资料
native/                 采集器及固定版本官方驱动资产
scripts/                构建、打包、自启动、更新和校验
tests/                  可离线运行的回归测试
docs/                   更新、采集与验证说明
packages/               本次发布的可用应用和 MCU 更新 ZIP
PROTOCOL.md              实测协议研究笔记
```

## 协议、恢复与许可

普通显示通过保留的 HID 命令封装 HPL2 租约和像素数据。完整帧为 1024 字节；压缩与 XOR 差分经过 CRC 和基帧校验后原子提交。MCU 负责字幕局部动画；心跳超时约 2 秒释放显示权，显式退出后还核对原厂时钟是否稳定，防止旧监控文字反弹。实现与时序见 [PROTOCOL.md](PROTOCOL.md)。

USB 主控与显示 MCU 是不同的固件部分。仅 USB 还能枚举，不能证明损坏的显示应用仍可接收更新。仍能正常响应时，可通过官方 TempoHub 和已保存原厂包恢复；完全失效情形可能需要硬件调试接口，当前未确认。备份的是本地原厂文件与配置，**不是音响 Flash 的完整读回**。

本项目原创应用代码使用 MIT；移植的温度采集文件使用 MPL-2.0；第三方库、PawnIO 与厂商 MCU 代码保留各自权利。详见 [LICENSE](LICENSE) 与 [第三方声明](THIRD_PARTY_LICENSE.txt)。此项目与 Edifier、网易云、TrafficMonitor、LibreHardwareMonitor 的官方产品没有隶属关系。
