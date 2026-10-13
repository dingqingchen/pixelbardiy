# 显示 MCU 更新与恢复

## 已验证范围

- Halo PixelBar 的 USB 控制接口：VID `2D99`，PID `A106`，MI `04`，usage page `FF14` / usage `01`。
- 主控回报版本 `1.3.7`。仅版本号相同不足以证明 MCU 或 PCB 相同。
- 镜像 `mcu-hpl2-codec.bin`，57,252 字节，SHA256 `f7b8ee274ba2439b3211c5eea80206599acff6e80d73dc0c898ba143e2e32f62`。
- 原厂完整包 `Halo PixelBar-PC_137.bin`，805,084 字节，SHA256 `71c6274c982715c56c99ef61fa568dd88a92c883d97ea7784721fba9de96fd60`。
- MCU 应用基址 `0x08002000`；补丁压缩十幅背景资产，保留原厂解码显示，复用腾出的程序空间。日常像素写 RAM，不反复刷固件。

## 操作步骤

1. 完整解压两个发布包。运行更新包的 `scripts/Verify-Package.ps1` 和 `Update-MCU.ps1 -Action OfflineCheck`。
2. 保存 TempoHub 下载的原厂包，复制到自己的长期备份目录。不要将 BLE/USB 主控分段或其他机型镜像当成 MCU 输入。
3. 从托盘“退出” HaloStudio 和 TempoHub，等待显示回到原厂时钟。不要同时运行另一个 Python 源码控制台。
4. `Update-MCU.ps1 -Action Preflight` 只查询版本与接口，打印实际序列号，不取得 RAM 显示权、不写固件。
5. 显式传入 `-Action Flash`、`-Serial`、`-AppDirectory` 和 `-FactoryPackage`。工具先复制并校验原厂包、当前 EXE、配置与旧验证记录。备份目录默认位于应用的 `backups/`。它不声称读回音响 Flash，也不包含当前应用全部 DLL；更新电脑应用前应另外保存整个应用目录。
6. 输入 `FLASH <实际序列号>` 后才发送 START。工具仅响应 MCU 请求，固定 1057 包、57,252 字节；USB 主控请求出现时立即结束，不发送下一段、空包结束或复位指令。请维持音响供电。
7. 传输完成只表示 staging 完成。等待音响自行重启并显示正常时钟，再运行 `-Action VerifyDisplay -AppDirectory '<应用目录>'`。
8. 确认猫咪、边框、`RAM LIVE 01 → 02` 完整出现，全程无“图片上传中”，随后恢复稳定时钟。只有全部正确才输入 `YES`。验证记录生成在应用的 `runtime/mcu-installation.json`。

已安装相同且确认过的镜像时，更新器拒绝再次刷写。复制旧验证记录到新电脑不能替代真实屏幕验证。现有已确认记录可以运行 VerifyDisplay 重新绑定同一音响的当前 USB 路径。

## 中断与恢复限制

超时、短写、未知状态、包偏移不匹配都立即停止；没有自动重试或续传。一次尝试创建 `runtime/firmware-update/pending.json`，失败时保留它和 JSONL 传输日志；后续刷写默认被阻止。日志可能包含设备序列号和本机路径，请勿直接上传公开仓库。

中断后先保持供电，核对屏幕与 USB 状态。已观察过一次早期中断后设备恢复原厂时钟；不能据此保证所有阶段都可恢复。不要反复强行刷写或随意断电。仍正常响应的设备可尝试官方 TempoHub 恢复原厂；若工具或官方软件不能识别、屏幕持续升级或黑屏，应停下来检查当前状态。

启动加载器未包含在此镜像里，USB/音频主控未修改。然而 MCU 应用失效可能导致 USB 桥无法完成更新交互。**独立于显示应用的 USB 恢复入口和硬件恢复步骤尚未验证。** 未获得可实际执行的救砖证据前，不应称其为无风险升级。恢复工具只做文件校验/接口检查，不会自动擦除任何未知区域。

## 校验与源码

补丁汇编与离线构建源码见 `firmware-lab/`；输入原厂 MCU SHA 必须匹配。ARM 测试覆盖原始 parser、租约、超时、退出、CRC、越界拒绝、压缩/差分、动画、OTA 边界问题及原厂图片解码。仿真不能代替真实启动、USB 桥时序或物理 Flash 读回。

`firmware/hpl2-codec/candidate-review.json` 是移除本机路径的审核摘要。`docs/VALIDATION.md` 区分仿真、真实设备和本次发布测试。
