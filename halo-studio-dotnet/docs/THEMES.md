# 运行时主题格式 v1

将 UTF-8 JSON 放入 `themes/`。文件监视器在文件保存后重新加载；读取失败的文件会显示诊断，不执行任何文件内代码。若全部文件读取失败，会保留上一次主题列表。

顶层字段：`version: 1`、唯一 `id`（小写英文、数字、下划线或连字符）、`name`、`color`、`accent`、`description`、`sprites` 和 `scenes`。

2.5 可选 `transition` 指定进入本主题时的过场：`center` 中心展开（默认）、`dissolve` 像素溶解、`up` 上推、`wipe` 揭幕。新主题不需要修改程序中的 ID 列表。关闭 UI 的切换动画后日常主题直接更新；演示遵循其编排。前两种需要经过验证的换色固件，旧固件自动采用支持的揭幕方式。

```json
{
  "version": 1,
  "id": "my_theme",
  "name": "我的主题",
  "color": "#64DFFF",
  "accent": "#677FFF",
  "description": "清晰数字与自定义图案",
  "sprites": {"spark": [".X.", "XXX", ".X."]},
  "scenes": {
    "clock": [
      {"op":"digits","text":"${time}","x":8,"y":3,"w":180,"h":26,"style":"ion"},
      {"op":"sprite","name":"spark","x":220,"y":"=10+phase%2","scale":2}
    ],
    "lyric": [{"op":"text","text":"${text}","x":39,"y":4,"w":197,"h":24,"size":18}],
    "single": [{"op":"text","text":"${label} ${value}","x":0,"y":0,"w":256,"h":32,"size":20}],
    "pair": [{"op":"metrics","count":2,"commands":[{"op":"text","text":"${label} ${value}","x":"=x+2","y":0,"w":124,"h":32}]}],
    "dense": [{"op":"small","text":"CUSTOM MONITOR","x":3,"y":12}]
  }
}
```

坐标为设备原生像素，原点左上角，X 0…255、Y 0…31。设备是单色点阵，主题 `color` 指定整屏 RGB；不是逐像素 RGB 屏。

`color` 保持历史设备输入语义，不直接等于电脑预览 sRGB。2.4.2 的 `palettes/pixelbar.json` 按输入值提供近似观感 `preview`，不改变主题发送值。比如琥珀的 `color: "#FF6000"` 保留实屏土黄效果，色表的 `preview: "#C7A34A"` 只用于 UI。任意新值未校准时会标注提示；不要把 `preview` 填回 `color`，否则会改变实屏效果。详见 [颜色说明](COLORS.md)。

## 绘图命令

| op | 主要参数 |
|---|---|
| line | x, y, x2, y2 |
| rect / round | x, y, w, h；rect 的 fill；round 的 r |
| circle / star | x, y, r；circle 的 start / end 为角度 |
| sprite | name, x, y, scale；`.` 为空，其他字符为亮点 |
| small / raster | text, x, y；raster 的 scale / dotted；small 的 right |
| digits | text, x, y, w, h, style：ion / pixel / dots / round / serif |
| text | text, x, y, w, h, font, size, bold, align |
| tag | text, x, y, w；反白标签 |
| erase / invert | x, y, w, h |
| segments | x, y, w, h, ratio, count, slant |
| history | x, y, w, h, area；使用当前指标历史 |
| dial | x, y, r, ratio, start, end |
| repeat | count, var, start, step, commands |
| metrics | count 与 commands，或 items 与 commands |

`text` 的字体可写 Windows 已安装字体名称，也支持 body（微软雅黑）、round（Segoe UI）、serif（Georgia）、song（宋体）。不抗锯齿；自动缩小并在空间允许时换行。温度末尾 `°C` 用独立紧凑圆环拼接，避免字号或字体导致圆圈缺失。

数值可写数字或 `=表达式`。支持 `+ - * / %`、括号、`sin`、`cos`、`round`、`min`、`max`、`clamp`、`pi`。`when` 结果为 0 时跳过命令。仅支持算术，不支持 C#、Python、文件路径执行或调用系统 API。

`phase` 在装饰动画启用时每 2 秒更新，0…7；关闭后固定为 0。`seconds`、`graph`、`instrument` 是 0/1 开关。时钟文本占位符：`${time}`、`${hour}`、`${minute}`、`${second}`、`${date}`、`${day}`、`${daynum}`；歌词为 `${text}`。指标为 `${label}`、`${value}`、`${compact}`、`${short}`、`${maxlabel}`，数值表达式提供 `ratio` 和 `valid`。

`metrics.count` 依次选择轮换指标；上下文有 `column`、`x`。`metrics.items` 自定义固定排版，每个条目指定 `key`、`label`、`short`、`unit`、`x`、`w`，上下文增加 `row`、`y`。参考各现有主题的 `dense` 场景。

所有布局始终可以使用 256×32 全部像素。2.1 全屏动画固件提供全幅上推和揭幕；旧 codec 固件的原生动画只作用于 X 38…237、Y 4…27。客户端会检查实际变化区域：旧固件上涉及外部像素变化时改用整屏 PC 中间帧，避免部分像素停住。新固件上安全的中央歌词切换仍保留外围装饰，其余场景使用全幅动画，无需主题作者指定像素裁剪区域。

最大文件 256 KB、JSON 深度 32、单个命令列表 512 项、每帧执行 4096 条、repeat 最多 256 次、表达式最多 160 字符，防止主题导致无界资源占用。
