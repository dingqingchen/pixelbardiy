"""New HaloStudio home. No changes to the retained legacy window."""
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QGridLayout, QPushButton, QListWidget, QStackedWidget,
    QScrollArea, QSpinBox, QComboBox, QTableWidget, QHeaderView,
    QAbstractItemView, QSystemTrayIcon)
from .ui import StudioWindow, BarPreview, label, button, card, combo, check
from .pixels import preview_image
from .pixel_design import render, THEMES


class PixelWindow(QMainWindow):
    # Shared controls are presentation-only. The new engine owns their commands.
    build_music = StudioWindow.build_music
    build_lights = StudioWindow.build_lights
    update_effect = StudioWindow.update_effect
    pick_ambient = StudioWindow.pick_ambient
    apply_lights = StudioWindow.apply_lights
    import_lrc = StudioWindow.import_lrc
    metrics_changed = StudioWindow.metrics_changed
    fan_selected = StudioWindow.fan_selected
    set_fan_limit = StudioWindow.set_fan_limit
    render_fan = StudioWindow.render_fan
    pick_color = StudioWindow.pick_color
    select_theme = StudioWindow.select_theme

    def __init__(self, engine, host):
        super().__init__()
        self.engine = engine; self.host = host; self.real_quit = False
        self.last_state = {}; self.lyric_signature = None; self.metric_keys = []; self.table_updating = False
        self.color = engine.config['color']; self.ambient_color = engine.config['ambient_color']
        self.setWindowTitle('HaloStudio · 像素工作室')
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1220, available.width()-40), min(900, available.height()-60))
        self.setMinimumSize(960, 650)
        icon = QPixmap(64, 64); icon.fill(QColor('#142731'))
        p = QPainter(icon); p.setPen(QColor('#9cebd8')); p.setFont(QFont('Segoe UI', 32, QFont.Bold))
        p.drawText(icon.rect(), Qt.AlignCenter, 'H'); p.end(); self.setWindowIcon(QIcon(icon))
        root = QWidget(); self.setCentralWidget(root)
        main = QVBoxLayout(root); main.setContentsMargins(22, 16, 22, 18); main.setSpacing(14)
        top = QHBoxLayout()
        self.legacy_button = button('↖ 旧版', lambda: host.switch('legacy'))
        self.legacy_button.setFixedWidth(86); self.legacy_button.setToolTip('停止像素后台、恢复原厂显示后打开旧版')
        top.addWidget(self.legacy_button); top.addSpacing(14)
        brand = QVBoxLayout(); brand.setSpacing(0)
        brand.addWidget(label('HaloStudio', 'title')); brand.addWidget(label('PIXEL STUDIO   /   桌面上的一小片光', 'eyebrow'))
        top.addLayout(brand); top.addStretch()
        self.connection = label('○ 正在准备', 'badge'); top.addWidget(self.connection)
        top.addWidget(button('重新连接', lambda: engine.submit('reconnect')))
        main.addLayout(top)
        preview_card, preview_layout = card()
        status = QHBoxLayout(); self.display_mode = label('图形时钟', 'section'); status.addWidget(self.display_mode)
        status.addStretch(); self.theme_badge = label(THEMES[engine.config['theme']].name, 'muted'); status.addWidget(self.theme_badge)
        preview_layout.addLayout(status)
        self.preview = BarPreview(); self.preview.setMinimumHeight(115); self.preview.setMaximumHeight(138)
        demo = render(datetime.now().strftime('%H:%M'), '时钟', engine.config, 0)
        self.preview.pixels = demo.pixels; self.preview.color = THEMES[engine.config['theme']].color
        preview_layout.addWidget(self.preview)
        row = QHBoxLayout(); self.write_status = label('本地预览 · 等待音响连接', 'muted'); row.addWidget(self.write_status, 1)
        self.rhythm_badge = label('音乐律动待命', 'muted'); row.addWidget(self.rhythm_badge); preview_layout.addLayout(row)
        main.addWidget(preview_card)
        middle = QHBoxLayout(); middle.setSpacing(18)
        self.nav = QListWidget(); self.nav.setFixedWidth(160); self.nav.setSpacing(5)
        self.nav.setStyleSheet('QListWidget{background:transparent;} QListWidget::item{padding:14px 10px;} QListWidget::item:selected{background:#233f48;color:#caffec;border-radius:9px;}')
        middle.addWidget(self.nav)
        self.tabs = QStackedWidget(); middle.addWidget(self.tabs, 1); main.addLayout(middle, 1)
        self.build_display(); self.build_monitor(); self.build_music(); self.build_lights(); self.build_power()
        self.nav.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.nav.currentRowChanged.connect(self.visibility); self.nav.setCurrentRow(0)
        bottom = QHBoxLayout(); self.message = label('256 × 32 全像素 · 图案在 RAM 中更新', 'muted', True); bottom.addWidget(self.message, 1)
        self.toggle = button('暂停同步', self.toggle_service, True); bottom.addWidget(self.toggle)
        bottom.addWidget(button('退出', host.quit)); main.addLayout(bottom)
        self.ui_timer = QTimer(self); self.ui_timer.setInterval(500); self.ui_timer.timeout.connect(self.render_latest)
        engine.changed.connect(self.receive_state); engine.notice.connect(self.message.setText)

    def page(self, title):
        self.nav.addItem(title)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(1, 1, 8, 8); layout.setSpacing(13)
        scroll.setWidget(widget); self.tabs.addWidget(scroll)
        return layout

    def build_display(self):
        c = self.engine.config; layout = self.page('时钟与主题')
        box, content = card(); grid = QGridLayout()
        grid.addWidget(label('默认画面', 'section'), 0, 0)
        self.idle = combo([('图形时钟', 'clock'), ('系统运行监控', 'monitor')], c['idle_content'], lambda v: self.config(idle_content=v))
        grid.addWidget(self.idle, 0, 1)
        self.auto = check('播放时优先显示网易云歌词', c['mode'] == 'auto', lambda v: self.config(mode='auto' if v else 'idle'))
        grid.addWidget(self.auto, 0, 2)
        self.themes = check('图案主题', c['themes'], lambda v: self.config(themes=v)); grid.addWidget(self.themes, 1, 0)
        self.color_button = button('自定义颜色  '+self.color, self.pick_color); grid.addWidget(self.color_button, 1, 1)
        self.seconds = check('显示秒数', c['seconds'], lambda v: self.config(seconds=v)); grid.addWidget(self.seconds, 1, 2)
        content.addLayout(grid); layout.addWidget(box)
        gallery, gl = card(); gallery_top = QHBoxLayout()
        gallery_top.addWidget(label('选择一种桌面心情', 'section'), 1)
        gallery_top.addWidget(label('设计预览 · 示例数据', 'muted'))
        self.gallery_mode = combo([('时钟', 'clock'), ('轮播监控', 'monitor'), ('双行概览', 'dense'), ('歌词', 'lyrics')], 'clock', self.update_theme_previews)
        gallery_top.addWidget(self.gallery_mode); gl.addLayout(gallery_top)
        choices = QGridLayout(); self.theme_buttons = {}; self.theme_previews = {}
        for i, (key, theme) in enumerate(THEMES.items()):
            tile = QPushButton(); tile.setCheckable(True); tile.setChecked(c['theme'] == key); tile.setMinimumHeight(109)
            inside = QVBoxLayout(tile); inside.setContentsMargins(12, 10, 12, 10); inside.setSpacing(6)
            title = label(theme.name); pic = label('')
            bitmap = render('20:26', '时钟', {**c, 'theme': key, 'themes': True}, 0, now=datetime(2026, 10, 12, 20, 26))
            pic.setPixmap(QPixmap.fromImage(preview_image(bitmap.pixels, theme.color)))
            self.theme_previews[key] = pic
            desc = label(theme.description, 'muted')
            for child in (title, pic, desc):
                child.setAttribute(Qt.WA_TransparentForMouseEvents); inside.addWidget(child)
            tile.clicked.connect(lambda checked=False, k=key: self.select_theme(k))
            self.theme_buttons[key] = tile; choices.addWidget(tile, i//2, i%2)
        gl.addLayout(choices)
        movement = QHBoxLayout()
        self.animations = check('主题小动画', c['animations'], lambda v: self.config(animations=v)); movement.addWidget(self.animations)
        self.transition = check('歌词 / 监控换页动效', c['transitions'], lambda v: self.config(transitions=v)); movement.addWidget(self.transition)
        self.motion = combo([('内容向上推入', 'up'), ('横向揭幕', 'wipe')], c['pixel_transition'], lambda v: self.config(pixel_transition=v))
        movement.addWidget(self.motion); gl.addLayout(movement)
        gl.addWidget(label('六套主题分别设计时钟、数据面板和歌词。主题小动画与换页可独立开关。歌词在中间字幕区播放音响本地动效；全宽监控面板完整换页。所有画面均在 RAM 中压缩、差分更新。', 'muted', True))
        layout.addWidget(gallery); layout.addStretch()

    def update_theme_previews(self, kind):
        if not hasattr(self, 'theme_previews'): return
        # Offline thumbnails: selecting this menu never changes the speaker.
        snapshot = {'metrics': [dict(key='cpu',short='CPU',text='37%',value=37,unit='%',scale=100,history=[12,20,42,37]),
            dict(key='ram',short='RAM',text='48%',value=48,unit='%',scale=100),
            dict(key='ram_gb',short='RAM',text='11.48GB',value=11.48,unit='GB'),
            dict(key='gpu0',short='GPU',text='64%',value=64,unit='%',scale=100),
            dict(key='gpu0_temp',short='GPU',text='51C',value=51,unit='C',scale=100),
            dict(key='upload',short='UP',text='1.25K/S',value=1280,unit='B/s'),
            dict(key='download',short='DN',text='1.12K/S',value=1147,unit='B/s')]}
        mode = '时钟' if kind=='clock' else '歌词' if kind=='lyrics' else '系统监控'
        text = '20:26' if kind=='clock' else '把每个明天写成一首歌'
        for key, pic in self.theme_previews.items():
            cfg = {**self.engine.config,'theme':key,'themes':True,'animations':False,'monitor_rotate':False,
                   'monitor_metrics':['cpu','ram'],'monitor_view':'dense' if kind=='dense' else 'bar'}
            frame = render(text,mode,cfg,0,snapshot,datetime(2026,10,13,20,26))
            pic.setPixmap(QPixmap.fromImage(preview_image(frame.pixels,THEMES[key].color)))

    def build_monitor(self):
        c = self.engine.config; layout = self.page('系统监控')
        box, content = card(); content.addWidget(label('让硬件状态变成像素图表', 'section'))
        row = QHBoxLayout()
        self.monitor_view = combo([('主题仪表', 'value'), ('图形负载条', 'bar'), ('双指标卡片', 'compact'), ('历史曲线', 'graph'), ('双行紧凑 · 全部概览', 'dense')], c['monitor_view'], self.monitor_view_changed)
        row.addWidget(self.monitor_view)
        self.rotate = check('轮流展示已选指标', c['monitor_rotate'], lambda v: self.config(monitor_rotate=v)); row.addWidget(self.rotate)
        self.rotation = QSpinBox(); self.rotation.setRange(4, 60); self.rotation.setValue(c['rotation_seconds']); self.rotation.setSuffix(' 秒 / 项')
        self.rotation.valueChanged.connect(lambda v: self.config(rotation_seconds=v)); row.addWidget(self.rotation); content.addLayout(row)
        content.addWidget(label('双行概览固定展示：上传 / 下载、CPU / GPU 使用率、CPU / GPU 温度、内存使用率 / 已用 GB；网速 K / M 表示 KB/s / MB/s。其它模式按下方勾选轮播。右侧图表跟随真实数据；AUTO 表示按近期峰值缩放，不代表额定上限。未知传感器显示 --。', 'muted', True))
        self.monitor_table = QTableWidget(0, 4); self.monitor_table.setHorizontalHeaderLabels(['显示 / 指标', '当前数值', '单位', '数据来源'])
        self.monitor_table.verticalHeader().hide(); self.monitor_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.monitor_table.setMinimumHeight(220); self.monitor_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.monitor_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.monitor_table.setColumnWidth(1, 95); self.monitor_table.setColumnWidth(2, 55)
        self.monitor_table.itemChanged.connect(self.metrics_changed); content.addWidget(self.monitor_table)
        self.monitor_detail = label('进入此页后开始读取传感器…', 'muted', True); content.addWidget(self.monitor_detail)
        self.cpu_temperature_button=button('启用 CPU 温度 · 管理员确认',lambda:self.engine.submit('cpu_temperature'))
        self.cpu_temperature_button.setToolTip('启动独立 AMD 温度采集器；已有驱动会复用，否则准备官方签名 PawnIO 驱动。退出本程序后采集器自动关闭。')
        content.addWidget(self.cpu_temperature_button);layout.addWidget(box)
        fan, fl = card(); fl.addWidget(label('风扇转速', 'section')); row = QHBoxLayout()
        self.fan_choice = QComboBox(); self.fan_choice.currentIndexChanged.connect(self.fan_selected); row.addWidget(self.fan_choice, 1)
        self.fan_max = QSpinBox(); self.fan_max.setRange(0, 30000); self.fan_max.setSpecialValueText('额定最大 RPM 未知')
        self.fan_max.setSuffix(' RPM 最大值'); self.fan_max.setSingleStep(100); self.fan_max.valueChanged.connect(self.set_fan_limit)
        row.addWidget(self.fan_max); fl.addLayout(row); self.fan_reading = label('等待传感器', 'muted', True); fl.addWidget(self.fan_reading)
        fl.addWidget(label('填写规格中的最大转速后，才计算相对最大转速。驱动比例单独标注；不可用的传感器显示未知。', 'muted', True))
        layout.addWidget(fan); layout.addStretch()
        self.update_monitor_controls(c['monitor_view'])

    def monitor_view_changed(self, value):
        self.config(monitor_view=value)
        self.update_monitor_controls(value)

    def render_monitor(self, snapshot):
        visible = {**snapshot, 'metrics': [{**m,'unit':'°C' if m['unit']=='C' else m['unit']} for m in snapshot.get('metrics',[])]}
        StudioWindow.render_monitor(self, visible)
        active=any(m.get('unit')=='C' and m.get('short')=='CPU' and m.get('value') is not None for m in snapshot.get('metrics',[]))
        self.cpu_temperature_button.setEnabled(not active and snapshot.get('cpu_temperature_status') not in (1,12))
        self.cpu_temperature_button.setText('CPU 温度已启用' if active else '启用 CPU 温度 · 管理员确认')
        if self.message.text() in ('请在 Windows 弹窗中确认独立温度采集器。','CPU 温度：正在准备独立硬件驱动'):
            if active:self.message.setText('CPU 温度已启用 · AMD Tctl/Tdie 寄存器直读')
            elif snapshot.get('cpu_temperature_status') not in (1,8):
                from .cpu_temperature import STATUS
                self.message.setText('CPU 温度：'+STATUS.get(snapshot.get('cpu_temperature_status'),'采集器暂不可用'))

    def update_monitor_controls(self, value):
        if not hasattr(self, 'monitor_table'): return
        overview = value == 'dense'
        self.rotate.setEnabled(not overview); self.rotation.setEnabled(not overview)
        self.monitor_table.setEnabled(not overview)
        self.monitor_table.setToolTip('双行概览使用固定八项读数；切换其它模式后恢复已选指标。' if overview else '')

    def build_power(self):
        c = self.engine.config; layout = self.page('后台与资源')
        from .autostart import is_enabled
        startup, sl = card(); sl.addWidget(label('Windows 登录自启动', 'section'))
        self.autostart = check('开机登录后自动启动到系统托盘', is_enabled(), self.change_autostart)
        self.autostart.setEnabled(not self.host.preview)
        sl.addWidget(self.autostart)
        sl.addWidget(label('使用当前用户的自启动项，不需要管理员权限。退出后本次停止，下次登录仍会启动；移动程序后请重新开启。CPU 温度采集仍需在监控页确认管理员权限。', 'muted', True))
        layout.addWidget(startup)
        box, content = card(); content.addWidget(label('按需采样，后台安静运行', 'section'))
        self.power = combo([('节能 · 监控 3 秒 / 灯光目标 20 Hz', 'eco'), ('均衡 · 监控 2 秒 / 灯光目标 30 Hz', 'balanced')], c['power_profile'], lambda v: self.config(power_profile=v))
        content.addWidget(self.power); self.performance = label('正在测量…', 'section', True); content.addWidget(self.performance)
        content.addWidget(label('相同画面不重发，只保留最新待发帧。仅在显示监控或打开监控页时读取硬件；窗口隐藏后停止预览重绘。静止画面只发送维持显示权的心跳。CPU 使用率不能直接换算为瓦数。', 'muted', True))
        content.addWidget(button('关闭主题动画和音乐律动', self.disable_effects)); layout.addWidget(box)
        helpbox, hl = card(); hl.addWidget(label('关闭、退出与切换旧版', 'section'))
        hl.addWidget(label('关闭窗口会收起到托盘，继续更新屏幕。点击“退出”会完全停止，并恢复音响自带时钟；未启动本程序时，正常听歌不受影响，自定义歌词和监控不会运行。\n\n左上角“旧版”会先停完像素后台，再打开原来的功能与设置。返回新版时执行同样的交接，两套后台不会同时发包。', 'muted', True))
        layout.addWidget(helpbox); layout.addStretch()

    def change_autostart(self, enabled):
        from .autostart import set_enabled, is_enabled
        try:
            set_enabled(enabled)
            self.message.setText('已启用登录自启动 · 启动到托盘' if enabled else '已关闭登录自启动')
        except (OSError, ValueError) as exc:
            self.autostart.blockSignals(True)
            self.autostart.setChecked(is_enabled())
            self.autostart.blockSignals(False)
            self.message.setText('自启动设置失败：'+str(exc))

    def config(self, **kwargs): self.engine.submit('config', kwargs)
    def disable_effects(self): self.animations.setChecked(False); self.rhythm.setChecked(False)
    def toggle_service(self): self.config(enabled=not self.last_state.get('enabled', self.engine.config['enabled']))
    def receive_state(self, state): self.last_state = state

    def render_latest(self):
        if not self.isVisible() or self.isMinimized() or not self.last_state: return
        s = self.last_state; c = self.engine.config; t = s['track']; tab = self.tabs.currentIndex()
        self.connection.setText('● RAM 已连接' if s['connected'] else '○ 未连接')
        self.display_mode.setText('图形'+s['display_mode'] if s['enabled'] else '同步已暂停')
        self.theme_badge.setText(THEMES.get(c['theme'], THEMES['ion']).name if c['themes'] else '自定义颜色')
        self.preview.pixels = s['pixels'] or s.get('preview_target'); self.preview.color = s['color']
        self.preview.level = s['rhythm_level']; self.preview.update()
        encoding = {'raw':'整帧', 'rle':'压缩帧', 'xor-rle':'差分帧'}.get(s.get('frame_codec'), '整帧')
        detail = f"{encoding}已发送 · {s['pixel_seconds']:.2f} 秒 · {s.get('frame_packets',29)} 包"
        if c['transitions'] and s['display_mode'] != '时钟':
            detail += ' · 本地字幕动效' if s.get('native_animation') and s['display_mode'] == '歌词' else ' · 整页过渡'
        self.write_status.setText((detail+(' · 正在更新' if s['pixel_busy'] else ' · 画面保持')) if s['verified'] else ('本地预览 · '+s['device_message'] if s['enabled'] else '已释放显示权 · 原厂时钟'))
        self.rhythm_badge.setText('音乐律动中' if s['rhythm_active'] else '音乐律动待命' if c['rhythm'] else '律动已关闭')
        self.toggle.setText('暂停同步' if s['enabled'] else '恢复同步')
        if tab == 1: self.render_monitor(s['monitor'])
        if tab == 2:
            self.song.setText(t['title'] or '等待网易云播放'); self.artist.setText(t['artist']); self.play_status.setText(s['media_message'])
            native = t.get('provider', '').startswith('网易云本地'); self.offset.setEnabled(not native)
            self.elapsed.setText(t['provider']); self.sync_hint.setText('实时歌词绘制为像素画面；LRC 提供上下文。' if native else '正值提前；本地 LRC 优先。')
            self.progress.setValue(round(1000*t['position']/t['duration']) if t['duration'] else 0); self.source.setText(s['source'])
            signature = tuple((v['time'], v['text']) for v in s['lines'])
            if signature != self.lyric_signature:
                self.lyric_signature = signature; self.lyric_list.clear()
                for v in s['lines']: self.lyric_list.addItem(f"{int(v['time'])//60:02d}:{int(v['time'])%60:02d}   {v['text']}")
            row = s['active']['index'] if s['active'] else -1
            if row != self.lyric_list.currentRow():
                self.lyric_list.setCurrentRow(row)
                if row >= 0: self.lyric_list.scrollToItem(self.lyric_list.item(row), QListWidget.PositionAtCenter)
            self.import_button.setEnabled(bool(t['title']))
        if tab == 3:
            self.level.setValue(round(s['rhythm_level']*100)); self.rhythm_status.setText(s['rhythm_message']+f" · 动态能量 {s['rhythm_level']:.0%}" if s['rhythm_active'] else '等待播放 / 律动未开启')
        if tab == 4:
            p = s['performance']; self.performance.setText(f"CPU {p.get('cpu_percent', 0):.2f}%   ·   内存 {p.get('memory_mb', 0):.1f} MB\nUSB {p.get('hid_per_second', 0):.1f} 包 / 秒   ·   已发送 {p.get('frames_sent', 0)} 帧")
        if not s['connected'] and s['enabled']: self.message.setText(s['device_message'])

    def visibility(self, *_):
        if not hasattr(self, 'ui_timer'): return
        visible = self.isVisible() and not self.isMinimized()
        self.engine.submit('visibility', {'visible': visible, 'monitor': visible and self.tabs.currentIndex() == 1})
        if visible: self.ui_timer.start(); self.render_latest()
        else: self.ui_timer.stop()

    def showEvent(self, event): super().showEvent(event); self.visibility()
    def hideEvent(self, event): super().hideEvent(event); self.visibility()
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange: self.visibility()
    def show_from_tray(self): self.showNormal(); self.raise_(); self.activateWindow()
    def closeEvent(self, event):
        if self.real_quit: event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable(): self.hide(); event.ignore()
        else: event.ignore(); self.host.quit()
    def quit(self): self.host.quit()
