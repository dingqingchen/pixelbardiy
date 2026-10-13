# 固件文件、更新工具与验证

完整操作手册：[功能、前提与逐步命令](FIRMWARE_USAGE.md)。2.6.0 更新的是工程资料和说明，显示 BIN 与 2.5.1 完全相同；本次不要求已验证设备重刷。

## 文件入口

- [当前换色与过场镜像](../firmware/hpl2-color/mcu-hpl2-color.bin) / [SHA256](../firmware/hpl2-color/mcu-hpl2-color.bin.sha256)。
- [字符雨历史镜像](../firmware/hpl2-matrix/mcu-hpl2-matrix.bin)。
- [全屏动画历史镜像](../firmware/hpl2-fullscreen/mcu-hpl2-fullscreen.bin)。
- [固件与工程工具 ZIP](../packages/HaloPixelBar-MCU-2.6.0.zip) / [校验清单](../packages/SHA256SUMS.txt)。
- [当前补丁源码、报告与脚本](../halo-studio-dotnet/firmware-color/README.md)。

三个镜像均为 57,252 字节的显示 MCU 应用镜像。最新 SHA256 为 `9a1b6d1425e980ca1bf9753e0dc1c7ef5ffefde95c741c9a6cf797ace5da237e`。ZIP 保留源码和依赖目录结构，包含原始 codec 基线和工程脚本；不包含个人身份记录、刷机日志、备份、温度驱动安装器或原厂完整更新包。

## 离线重建

在 Windows 的独立 Python 3.12 环境安装 `legacy-python/requirements-dev.txt`。Unicorn 必须为 2.1.3。准备自行保存的原厂 1.3.7 显示 MCU 镜像；原镜像审计会核对身份，不接受任意同尺寸文件。

```powershell
# 仓库或完整固件工程包根目录；两个步骤都不访问 USB。
python legacy-python/scripts/build_firmware.py --original-mcu '<原厂显示MCU镜像路径>'
python halo-studio-dotnet/firmware-color/validate_color.py
```

第一个步骤准备 `legacy-python/firmware-analysis/v137/mcu.bin` 并验证旧 codec 基线；第二个步骤重建当前扩展、运行 ARM 像素/生命周期/OTA 暂存回归。最后核对输出镜像 SHA 与发布文件一致，不能只看脚本退出码。

## 更新与回退前提

`stage_color.py` 复用经过验证的按设备请求发送流程。默认仅预检；`--flash-authorized` 才允许更新；`--rollback` 选择固定的字符雨回退镜像。它要求本机备份清单、镜像哈希、旧安装记录、设备身份、一台音响及独占控制全部满足，不自动补造安装记录、不自动重试。

这套脚本保留了研究工程的准备约束：例如 `validation/color-backup-path.txt`、备份中的旧镜像和记录，以及旧 `images()` 路径要求的原厂完整包和审计镜像。**下载文件不代表这些准备已完成**；在新设备上不能直接套用已成功设备的记录。旧版 `HaloFirmware v1.0.0` 工具固定旧 codec 镜像，不是新版固件的通用入口。

一次实际升级传输了 1,041 包显示 MCU 数据，USB/音频主控发送 0 字节；传完必须等设备启动、再核对图形、动画与退出恢复。主控回读 `1.3.7` 或传输 ACK 均不能证明显示 MCU 已正确启动。

## ROM / Flash 和恢复边界

日常显示走 RAM，没有资源 Flash 擦写。固件更新是不同路径：先写外部 SPI 的 OTA 暂存区，再设置升级标记。已知原厂流程会写包外的升级标记区，不能推断“不含 bootloader 的包就绝不会破坏启动”。

目前备份是已知固件文件和本机客户端，未完成整机 Flash 读回。历史镜像回退要求显示 MCU 应用还能响应；**显示 MCU 完全失效后的独立 USB 救砖仍未验证**。离线仿真验证分包与暂存一致性，不验证引导加载器安装、断电或硬件损坏后的恢复。

用户实机已经确认当前固件重启正常、颜色/过场正常、没有图片上传提示、退出恢复时钟、停止心跳自动恢复且保持稳定。上述结论只适用于已测试设备和固定镜像，不能外推到所有 PixelBar 硬件批次。
