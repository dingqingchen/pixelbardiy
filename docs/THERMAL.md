# 独立温度采集

实现来自 TrafficMonitor V1.86 使用的 LibreHardwareMonitor 路径：

- TrafficMonitor：`02a817a069bac6bf4d263b5209d9c1b07fe2f950`，`OpenHardwareMonitorApi/OpenHardwareMonitorImp.cpp`。
- LibreHardwareMonitor v0.9.4：`b8077435b898d57539956388cddf49f7dacb86f7`，PCI 和全局互斥约定。
- LibreHardwareMonitor：`cd60f10f3290ff9b706e0f489b27ba9a50c1f9fa`，AMD Zen 5 与 Tctl/Tdie 解码。
- PawnIO 的固定版本、签名模块、SHA256 与源码出处见 `thermal-native/references/PawnIO-source.json`。

`thermal-native/halo_thermal.c` 是小型 Win64 用户态进程，不读取 TrafficMonitor 内存或插件。支持 AuthenticAMD family 17h/19h/1Ah，核对 PCI vendor，再通过固定 SMN `0x59800` 读取温度。`CUR_TEMP[31:21] × 0.125°C`；RANGE_SEL[19] 或 TJ_SEL[17:16]=3 时减 49°C，另保留旧型号偏置表。

主 UI 以普通权限运行。明确启用按钮经 UAC 启动 helper。先复用 WinRing0 兼容驱动，再复用 PawnIO；两者缺失时校验官方签名资产并运行固定安装参数 `-install -silent`。访问被拒绝/已有驱动忙时报告原因，不重复安装。无需关闭或重启 TrafficMonitor。

读数持有上游相同的 `Global\Access_PCI` 互斥，10 ms 内拿不到就跳过。本项目不调节时钟、电压、风扇、SMU 或 Flash。PawnIO 官方模块的 SMN 读取会设置地址选择器，按上游约定与其他读取者共享互斥。

80 字节本地共享内存报告温度、后端、复用状态和采样次数。按监控请求唤醒，空闲阻塞等待；父程序退出/崩溃都唤醒 helper 退出。超过十秒、未完成发布、错误或异常范围的读数显示不可用。驱动为共享系统组件，应用退出不卸载它。

重新编译：Zig 0.13.0，`scripts/Build-Thermal.ps1 -Zig '<zig.exe>'`。移植源文件使用 MPL-2.0；官方 PawnIO 模块使用 LGPL-2.1-or-later，源文件和许可证随发行包提供。
