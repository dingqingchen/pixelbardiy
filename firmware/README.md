# 显示 MCU 固件

| 目录 | 能力 | 用途 |
| --- | --- | --- |
| `hpl2-color/` | 压缩、差分、全屏动画、字符雨、帧内 RGB、中心展开、像素溶解 | 当前版本 |
| `hpl2-matrix/` | 压缩、差分、全屏动画、字符雨 | 固定历史回退版本 |
| `hpl2-fullscreen/` | 压缩、差分、全屏上推和横向揭幕 | 历史版本 |

各目录包含 `.bin` 和 `.sha256`。源代码、检查报告和更新脚本在 [新版工程](../halo-studio-dotnet/firmware-color/README.md)，另提供 [完整固件工程包](../packages/HaloPixelBar-MCU-2.5.1.zip)。

请先读 [更新前提与恢复限制](../docs/FIRMWARE.md)。已有相同已验证固件无需再次刷写；这不是 USB 主控或 bootloader 镜像，不是已经验证的独立救砖包。
