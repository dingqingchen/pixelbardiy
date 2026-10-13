# 自适应布局（2.4.1）

参考官方 [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev) 固定提交 `5b10331022940dfbd049adfa6f714d3da2d5a6ef` 的布局方式，以现有 C# / WinForms 控件实现，没有引入其 React/MUI 代码或运行时：

- [settings.tsx](https://github.com/clash-verge-rev/clash-verge-rev/blob/5b10331022940dfbd049adfa6f714d3da2d5a6ef/src/pages/settings.tsx)：网格在 xs/sm 使用 6 列、md 使用 12 列，卡片组占 6 列，实现一列与两列切换。
- [home.tsx](https://github.com/clash-verge-rev/clash-verge-rev/blob/5b10331022940dfbd049adfa6f714d3da2d5a6ef/src/pages/home.tsx)：主页也使用相同断点网格及统一间隔。
- [layout-item.tsx](https://github.com/clash-verge-rev/clash-verge-rev/blob/5b10331022940dfbd049adfa6f714d3da2d5a6ef/src/components/layout/layout-item.tsx) 与 [layout.scss](https://github.com/clash-verge-rev/clash-verge-rev/blob/5b10331022940dfbd049adfa6f714d3da2d5a6ef/src/assets/styles/layout.scss)：导航项留左右边距，容器将内边距纳入宽度计算。

## HaloStudio 的实现

`PagePanel` 使用扣除侧栏、内边距和滚动条后的真实内容宽度，每卡最小约 400 逻辑像素，间隔 18 像素，允许 1–3 列。画廊、正在聆听和底部硬件表使用通栏。2.4.1 采用紧凑的瀑布流：下一张卡片放在当前最短列末尾，等高优先左列，无须等待同排最高卡片。通栏卡片位于全部前序卡片下方，之后各列重新对齐。单列保持原有阅读顺序。

`SettingRow` 根据文字与输入控件所需宽度，在左右排列与上下排列之间自动切换；开关保持在文字旁边。侧栏去掉 TableLayoutPanel 默认外边距，按钮按父容器可用宽度计算，避免固定按钮宽度超出容器。侧栏底部状态区改为内容自适应高度并贴底，去掉旧固定高度留下的空白，使文字与托盘按钮一同下移。

预览高度根据可用宽度计算；`PixelPreview.Viewport` 始终保持 256:32 比例，缓存位图以最近邻采样绘制到视口，避免此前整倍数缩放使预览只占中间一小块。

圆角卡片、主题预览、指标选框、输入框和按钮启用 `ResizeRedraw` 与双缓冲。宽度变化时整个控件失效重绘，不仅绘制新增的右侧条带，因此旧位置的圆角边框不会残留。该逻辑只影响桌面 UI，不增加音响帧刷新率或改变显示驱动。

## 验证入口

`--preview --ui-audit <目录>` 在同一窗口执行 1280 → 1020 → 1520 → 1920 → 1020 → 1280 逻辑宽度的往返检查，覆盖五个页面。验证卡片、设置字段和侧栏无裁切，卡片不重叠，同列连续卡片无超出标准间距的空洞，侧栏底部无多余内部空白，预览比例与占宽正确，硬件表始终在最后；输出截图及 JSON。该诊断不连接 USB。
