# 实现文档

本文档对应 HaloStudio 2.6.0 和 HPL2 换色固件。先阅读显示链路，再看 MCU 动画；协议字段以链接到的源码为准。

| 文档 | 内容 |
| --- | --- |
| [USB 实时像素协议](USB_PIXEL_PROTOCOL.md) | 点阵布局、HID 分包、压缩与差分、ACK、CRC、帧提交和调度 |
| [MCU 本地动画](MCU_ANIMATION.md) | RAM 缓冲、代码空间、整屏上推/揭幕/溶解/字符雨、独占和恢复 |
| [固件完整命令流程](FIRMWARE_USAGE.md) | 功能、依赖、原厂材料、备份、预检、升级、实屏确认与回退限制 |
| [歌词时间轴与分页](../halo-studio-dotnet/docs/LYRICS.md) | YRC 逐字分页、无逐字时首尾两页、0.8 秒补偿和最小化同步 |
| [固件与恢复](FIRMWARE.md) | 镜像、哈希、离线重建、更新前提、已验证范围与未解决边界 |
| [颜色与校准](../halo-studio-dotnet/docs/COLORS.md) | 设备 RGB 与电脑预览的区别，浅绿/粉色/白色校准 |
| [外部主题格式](../halo-studio-dotnet/docs/THEMES.md) | 运行时 JSON 布局、绘图指令与主题入口动画 |
| [客户端调度](../halo-studio-dotnet/docs/ARCHITECTURE.md) | 采集线程、传输任务、歌词优先级和后台开销 |
| [实测与离线验证](../halo-studio-dotnet/docs/VALIDATION.md) | 测试内容及证据的适用范围 |
| [Python 旧版](../legacy-python/README.md) | 保留版应用、原更新工具和历史实现 |

主链路：**主题/时钟/硬件/歌词 → PC 绘制目标点阵 → 压缩分包 → USB 主控转发 → 显示 MCU 校验暂存 → 本地显示或过场**。PC 提交目标画面，MCU 负责生成支持的过场中间帧。屏幕是单色掩码加整屏 RGB，并非每个像素独立 RGB。
