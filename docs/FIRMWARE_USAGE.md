# 固件工具完整使用流程（2.6.0 资料版）

> [!WARNING]
> 非官方实验固件，主要代码由 GPT-6 Astra 完成，未经过完整全面测试。版本不匹配、断电或未知缺陷可能使音响无法启动、变砖或损坏。备份是已知文件，不是整机 Flash 读回；**独立 USB 救砖尚未验证**。下面的命令是有前提的工程流程，不是适用于任意新音响的一键安装器。不要用 `python -O` 或 `PYTHONOPTIMIZE`，脚本依赖断言执行校验。

## 功能、版本与适配前提

| 内容 | 支持情况 |
| --- | --- |
| 当前显示镜像 | `mcu-hpl2-color.bin`，57,252 字节；2.6.0 资料包和 2.5.1 使用同一个 BIN |
| 实时显示 | 256×32 单色点阵掩码 + 整屏 RGB；USB HID 转发至显示 MCU，日常画面只写 RAM |
| 压缩与差分 | raw、RLE、XOR-RLE，帧序号/CRC，整帧提交与确认 |
| MCU 动画 | 整屏上推、横向揭幕、中心展开、像素溶解、字符雨；PC 提交目标帧，MCU 生成中间帧 |
| 所有权 | 独占、心跳超时回收、退出恢复原厂时钟；换色和换主题可保持同一租约 |
| 原厂资源 | 压缩保存原背景资源，字体保留；离线验证 30 个主题场景与 16 个字形用例一致，不等同于所有官方功能均实测通过 |
| 更新范围 | 只发送显示 MCU 应用镜像，不发送 USB/音频主控代码，不包含引导区；升级仍会写 OTA 暂存与升级标记 |
| 已核对设备 | USB VID `2D99` / PID `A106`、控制接口 `MI04`，主控查询 `1.3.7`；这些字段相同也不能证明硬件批次完全相同 |
| 脚本升级起点 | **已经安装并实屏验证字符雨版** `ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884` 的同一设备 |
| 不支持直接套用 | 原厂全新设备、其他固件起点、其他硬件、无真实安装记录、显示 MCU 已失效。请反馈适配需求，不要伪造记录或删校验 |

已安装当前 SHA 的设备只更新电脑应用，不要重复刷写：

```text
9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e
```

## 脚本入口

| 脚本 | 用途 / 是否写音响 |
| --- | --- |
| `legacy-python/scripts/build_firmware.py --original-mcu PATH` | 审计原厂显示镜像、准备基线和离线验证；不访问 USB |
| `halo-studio-dotnet/firmware-color/validate_color.py` | 重建当前镜像并运行真实 ARM 指令回归；不访问 USB |
| `halo-studio-dotnet/firmware-color/stage_color.py` | 默认只读预检：校验本机文件、设备身份、独占和主控版本；创建本地预检日志 |
| 同上 `--flash-authorized` | 明确开始一次 MCU 更新，不自动重试 |
| 同上 `--rollback --flash-authorized` | 从备份选择固定字符雨镜像回退；仍需显示 MCU 能响应，不是救砖工具 |
| C# `--color-commission --after-observed-reboot` | 完整传输并确认重启后播放 RAM 测试；不刷固件，不自动写入目视确认 |
| 同上 `--timeout-release` | 播放一幕后停止心跳，检查自动恢复；不发退出命令 |

以下在 **PowerShell** 中运行，工作目录为仓库或完整 MCU 工程 ZIP 的根目录，保留 `legacy-python` 与 `halo-studio-dotnet` 的相邻布局。可直接复制命令，但先将 `D:\PixelBarPrivate\...` 替换成你自己的真实文件位置；文件缺失时停止，不能下载他人设备记录补齐。

## 1. 环境与文件核对（不访问 USB）

Windows x64 + Python 3.12 x64。日常 C# 应用不需要 Python；本节仅供工程工具使用。

```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'D:\pixelbardiy'  # 改为实际解压/克隆位置
py -3.12 -m venv .venv
$py = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $py -m pip install -r .\legacy-python\requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
& $py -c 'import sys,unicorn,capstone,keystone; assert sys.flags.optimize == 0; assert unicorn.__version__ == "2.1.3"; print(sys.version,unicorn.__version__,capstone.__version__,keystone.__version__)'
if ($LASTEXITCODE -ne 0) { throw '环境不匹配' }

$candidate = '.\halo-studio-dotnet\firmware-color\mcu-hpl2-color.bin'
$expected = '9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e'
if ((Get-FileHash $candidate -Algorithm SHA256).Hash -ne $expected) { throw '发布镜像校验失败' }
```

依赖版本由 requirements 文件固定，包含 Unicorn 2.1.3、Keystone 0.9.2、Capstone 5.0.9，USB/锁与枚举使用 hidapi、PySide6、psutil。不要在不明版本上跳过验证。

## 2. 原厂材料与离线重建

必须自行保存并核对以下原厂材料，发布包不包含原厂完整更新容器：

| 文件 | 字节 / SHA256 |
| --- | --- |
| 原厂 1.3.7 显示 MCU | 57,252 / `8fb58ded25d23b5148dc9a37ec57b380e03d65681c13c7f445eff62102010e3b` |
| TempoHub 原厂完整更新包 | 805,084 / `71c6274c982715c56c99ef61fa568dd88a92c883d97ea7784721fba9de96fd60` |

```powershell
$originalMcu = 'D:\PixelBarPrivate\original-mcu-137.bin'
$originalPackage = 'D:\PixelBarPrivate\Halo PixelBar-PC_137.bin'
if ((Get-FileHash $originalPackage).Hash -ne '71c6274c982715c56c99ef61fa568dd88a92c883d97ea7784721fba9de96fd60') { throw '原厂容器不匹配' }
& $py .\legacy-python\scripts\build_firmware.py --original-mcu $originalMcu
if ($LASTEXITCODE -ne 0) { throw '原厂审计/基线验证失败' }
& $py .\halo-studio-dotnet\firmware-color\validate_color.py
if ($LASTEXITCODE -ne 0) { throw '当前固件离线验证失败' }
if ((Get-FileHash $candidate).Hash -ne $expected) { throw '重建结果与发布镜像不同' }

# 旧传输辅助函数还会核对原厂容器和历史审计镜像。
$archive = '.\legacy-python\firmware-archive\20261012'
New-Item -ItemType Directory -Force $archive | Out-Null
Copy-Item -LiteralPath $originalPackage -Destination (Join-Path $archive 'Halo PixelBar-PC_137.71c6274c982715c5.bin')
# 从已审计的原厂镜像离线重建历史参考文件；它不是本次刷入对象。
@'
import sys, hashlib
from pathlib import Path
sys.path[:0] = [str(Path('legacy-python/firmware-lab').resolve()), str(Path('legacy-python').resolve())]
import validate_session
_, image, *_ = validate_session.build()
if hashlib.sha256(image).hexdigest() != 'fe18bc92afd790cd2f2248b98091033f8d8d76cac674b60540cbf5c644f389ae':
    raise RuntimeError('Historical reference mismatch')
out = Path('legacy-python/firmware-candidates/hpl2-review')
out.mkdir(parents=True, exist_ok=True)
(out/'mcu-hpl2-review-only.bin').write_bytes(image)
'@ | & $py -
if ($LASTEXITCODE -ne 0) { throw '参考镜像重建失败' }
```

预期报告：19 组生命周期、8 组 codec、11 组全屏动画、至少 20 组颜色/过场检查；显示路径 Flash 调用为 0，30 个主题场景与 16 个字形一致，升级与回退 OTA 暂存逐字节相同。它们**不验证**引导区安装、断电恢复或不同实物批次。

## 3. 建立自己的备份（仅支持真实字符雨版起点）

先从 HaloStudio 设置页正常退出并等时钟恢复，再退出 TempoHub、旧 HaloStudio 及其他控制器。只连接一台目标音响。

以下备份自己的应用目录、原安装记录和已安装字符雨镜像。记录必须原本就属于这台音响、镜像与版本匹配，并已实屏确认，不能为通过脚本而将标记改成 true。

```powershell
$appDir = 'D:\HaloStudio\HaloStudioNet'  # 当前实际应用目录
$recordPath = (Resolve-Path (Join-Path $appDir 'runtime\mcu-installation.json')).Path
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$old = 'ccb55a58beb825e730175969d9388bdc94ef55d0ad8534947a3ec8c728473884'
if ($record.candidate_sha256 -ne $old -or $record.graphics_visually_confirmed -ne $true) { throw '不是已验证字符雨版起点；不要继续' }
if (-not $record.serial -or -not $record.hid_path) { throw '缺少自己的设备身份' }
$matrix = '.\halo-studio-dotnet\firmware-matrix\mcu-hpl2-matrix.bin'
if ((Get-FileHash $matrix).Hash -ne $old) { throw '回退镜像不匹配' }
$validation = Join-Path (Get-Location) 'halo-studio-dotnet\validation'
$backup = Join-Path $validation ('color-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath $appDir -Destination (Join-Path $backup 'app') -Recurse
Copy-Item -LiteralPath $recordPath -Destination (Join-Path $backup 'installation.json')
Copy-Item -LiteralPath $matrix -Destination (Join-Path $backup 'installed-matrix.bin')
Copy-Item -LiteralPath $originalPackage -Destination (Join-Path $backup 'original-package.bin')
Copy-Item -LiteralPath $originalMcu -Destination (Join-Path $backup 'original-mcu.bin')
ConvertTo-Json -InputObject @(@{ source=$recordPath; backup='installation.json' }) | Set-Content (Join-Path $backup 'records.json') -Encoding utf8
$files = @(Get-ChildItem -LiteralPath $backup -Recurse -File | ForEach-Object {
    @{ path=$_.FullName.Substring($backup.Length+1); sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
})
@{ files=$files } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $backup 'backup-manifest.json') -Encoding utf8
$backup | Set-Content (Join-Path $validation 'color-backup-path.txt') -Encoding utf8
```

上述备份文件含私人设备信息，不要提交 GitHub。文件数量不固定；脚本逐项核对 manifest，不能仅凭“备份文件夹存在”继续。

## 4. 只读预检，再单独决定刷写

```powershell
& $py .\halo-studio-dotnet\firmware-color\stage_color.py --help
& $py .\halo-studio-dotnet\firmware-color\stage_color.py
if ($LASTEXITCODE -ne 0) { throw '预检失败；停止，不加刷写参数' }
```

预检成功日志包含 `preflight`。它核对精确 HID 路径/序列号、单设备、控制器已退出、锁、主控 C6 回读 1.3.7、备份哈希和报告。版本回读不能替代硬件审计。

**以下是实际写入命令，不能作为“测试一下”的预检运行。** 确认供电稳定、没有其他控制器、备份完整且愿意承担风险后，才运行一次：

```powershell
& $py .\halo-studio-dotnet\firmware-color\stage_color.py --flash-authorized
if ($LASTEXITCODE -ne 0) { throw '传输已中止；保留供电和日志，不自动重试' }
```

正常传输日志应有 `mcu_transfer_complete`、57,252 字节、主控发送 0 字节；本机一次为 1,041 包（数量取决于请求分包）。**完成传输不代表已安装成功**，继续保持供电，等待设备自己重启。不要以主控 1.3.7、ACK 或脚本退出码代替屏幕启动确认。

`validation/color-live/UPGRADE_STARTED.json` 是一次性尝试锁，失败后也保留。不要删除它自动重试，不要复用别人的完整日志。遇到异常请保存该目录并反馈，先评估设备状态。

## 5. 重启后 RAM 功能与超时恢复

先亲眼确认设备自行重启且正常显示，再用单独解压的 C# 应用执行以下两轮。`$appDir` 必须仍指向第 3 步的本机运行目录，记录已由更新脚本标记 pending；不要同时启动普通客户端。

```powershell
$exe = Join-Path $appDir 'HaloStudioNet.exe'
$runtime = Join-Path $appDir 'runtime'
$live = Join-Path $validation 'color-live'
# 六幕主题、颜色、过场；正常退出恢复时钟。开头留 15 秒准备观察。
Start-Process -FilePath $exe -ArgumentList @('--color-commission','--after-observed-reboot','--live-folder',('"'+$live+'"'),'--runtime',('"'+$runtime+'"')) -Wait
# 单幕后停止心跳，不发退出指令；观察是否自行恢复且持续稳定。
Start-Process -FilePath $exe -ArgumentList @('--color-commission','--after-observed-reboot','--live-folder',('"'+$live+'"'),'--runtime',('"'+$runtime+'"'),'--timeout-release') -Wait
```

检查新生成的 `smoke-*.json`、`timeout-*.json` 有完成时间和 `firmware_writes: 0`，并核对自己的实屏：文字/图形完整、过场正常、没有图片上传提示、不闪回时钟，最后恢复且保持稳定。CLI 不自动将安装记录改为通过。只有全部实物检查完成后，才更新**自己的原记录**（保留身份字段，不能新造）：

```powershell
if ((Read-Host '仅在两轮实屏均正常后输入：已确认实屏和恢复正常') -ne '已确认实屏和恢复正常') { throw '未确认，不登记' }
$r = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
if ($r.pending_candidate_sha256 -ne $expected -or $r.serial -ne $record.serial -or $r.hid_path -ne $record.hid_path) { throw '记录状态/身份已变化' }
$r.candidate_sha256 = $expected
$r.graphics_visually_confirmed = $true
$r.PSObject.Properties.Remove('pending_candidate_sha256')
$r.PSObject.Properties.Remove('pending_trace')
$r | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $recordPath -Encoding utf8
Start-Process -FilePath $exe
```

正常客户端再次按精确 SHA 和设备身份启用能力。若使用另一应用目录，在设备页导入这份自己的验证记录。

## 6. 有条件的回退与故障反馈

仅在显示 MCU 仍可响应、备份及设备身份可核验且没有在途升级时考虑回退。先退出所有控制器：

```powershell
& $py .\halo-studio-dotnet\firmware-color\stage_color.py --rollback
if ($LASTEXITCODE -ne 0) { throw '回退预检失败，停止' }
# 明确决定回退后单独运行；会实际写入备份字符雨镜像。
& $py .\halo-studio-dotnet\firmware-color\stage_color.py --rollback --flash-authorized
```

回退也有 `ROLLBACK_STARTED.json` 一次性锁。之后同样等重启、进行相应字符雨版本的实屏/恢复验证，再登记该旧 SHA；不能运行只接受新色彩 SHA 的 `--color-commission` 来证明旧版通过，也不能复制旧记录宣称本次回退已验证。

遇到黑屏、无法启动、传输中断或身份/哈希不符，停止发送并保留日志。没有已验证的独立 USB 救砖命令可提供，不承诺能恢复；可能需要原厂维修或硬件调试。欢迎在 [Issues](https://github.com/woozyc/pixelbardiy/issues) 反馈 Windows/TempoHub/音响版本、失败阶段、错误文本与已脱敏日志，不上传私人备份、序列号或账户信息。
