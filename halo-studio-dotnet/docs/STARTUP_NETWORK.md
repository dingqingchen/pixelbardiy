# 后台启动、温度授权与网速（2.6.4）

## 无窗口后台启动

开机 Run 项使用 `HaloStudioNet.exe --background`，仍以普通用户权限运行。程序在首次 `SetVisibleCore` 之前抑制显示，先创建隐藏窗口句柄／托盘，再启动后台引擎，不再先显示白窗后隐藏。托盘打开时恢复任务栏入口，后台引擎只启动一次。

`--preview --background --background-audit --runtime <独立目录> --output <报告>` 是不接管音响的验证模式：检查启动期间无 `Shown`、无可见状态转换、无任务栏窗口，且工作引擎已启动。不要求注销或重启电脑。

## 温度只授权一次

首次仍默认关闭。主动启用温度采集后，通过一次 UAC 注册当前用户的 `\HaloStudio\Thermal-<SID>` 按需任务；不把主界面改成管理员程序。建立任务后，正常手动启动和开机启动均复用授权，采集器仍按监控请求采样、等待时阻塞，主程序退出或崩溃后随之退出。没有常驻后台服务或登录时独立运行的温度进程。

任务只允许执行 `Program Files\HaloStudio\Thermal\HaloThermalTask.exe`，固定参数模板仅接受父 PID 和随机 32 位十六进制会话 nonce，不接受任意命令或文件路径。采集器和固定驱动材料复制到继承系统 ACL 的 Program Files 目录，普通用户只读；任务所有者为 Administrators，当前用户只获读取／执行权。客户端同时核对路径、参数、运行身份、权限级别、触发器及文件 SHA256。未降低 UAC、未改驱动设备权限，也未给普通主界面管理员令牌。

后台采集器与原 `HaloThermal.exe` 使用同一份 `thermal-native/halo_thermal.c`，仅按 Windows 子系统构建，不创建控制台。沿用原有受限 AMD SMN 温度读取、PCI 全局互斥、固定签名 PawnIO 和已有驱动复用逻辑。

参考 [TrafficMonitor 的计划任务自启动实现](https://github.com/zhongyang219/TrafficMonitor/blob/master/TrafficMonitor/auto_start_helper.cpp) 及 [微软任务安全上下文](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks)。我们的按需任务只提升采集器；与 TrafficMonitor 提升整个应用的方式不同。

授权建立后应用目录移动通常无需重建任务，因为动作指向受保护副本；辅助二进制变更、任务被删除或策略阻止时需要重新授权。标准用户使用另一个管理员账户完成 UAC 的情形尚未验证；当前用户必须能建立本账户的高权限任务。关闭温度开关即停止调用任务。完全清理时，可在管理员 PowerShell 中删除对应的 `\HaloStudio` 温度任务及 Program Files 下的固定辅助目录，**不要删除共享的 WinRing0／PawnIO 驱动**。

开发构建（Zig 0.13.0）：

```powershell
./scripts/build-thermal-task.ps1 -Zig C:/path/to/zig.exe
```

本次辅助二进制 SHA256 为 `57aedf7e11005125cc575539b0f3fb1f5f6b80d3ff80ca3735e0ed44bba69fad`。代码中的固定哈希必须经审查后同步更新。

只读采集验证，不连接音响，不自动弹 UAC：

```powershell
./HaloStudioNet.exe --temperature-probe --output temperature.json
```

## 网速按字节统计，避免 VPN 叠加

Windows `MIB_IF_ROW2.InOctets/OutOctets` 本来就是字节，不是位；直接对差值除以真实采样秒数，**不能再除以 8**。原实现把所有非回环接口相加，物理网卡和 VPN／TUN 上的同一流量可能重复计数，数值看起来异常偏大。

现在按活动物理网卡汇总，使用 Windows 的 `HardwareInterface` 标志，不靠网卡名称猜测；有 WLAN 时不再加 Meta、VPN 或其他虚拟层。无物理接口的虚拟机保守选择一个活动非回环／非隧道接口，不累计多层。计数器按接口 GUID 独立记录，新接口、断连重连或计数器复位先建立基线，防止终身累计值突然变成当前速率。

完整单位写为 B/s、KiB/s、MiB/s（1024 进制）；狭窄点阵仍使用 K/M 等缩写，UI 旁明确其代表字节／秒，与宽带标称 Mbps 不同。例：100 Mbps 理论上约为 12.5 MB/s，约 11.92 MiB/s，且实际速度还受协议与链路开销影响。

多物理网卡桥接／路由转发、虚拟机和特殊硬件仍需更多实测；当前默认统计物理接口总流量，不等于某个应用的文件下载速度。
