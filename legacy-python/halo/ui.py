from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QTimer,QEvent
from PySide6.QtGui import QColor,QFont,QIcon,QPainter,QPen,QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QFrame,QLabel,QPushButton,
    QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,QCheckBox,QDoubleSpinBox,QSlider,QSpinBox,
    QProgressBar,QFileDialog,QColorDialog,QListWidget,QSystemTrayIcon,QMenu,QScrollArea,QTabWidget,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from .engine import Engine
from .themes import THEMES
from .pixels import preview_image

STYLE="""
QWidget { background:#0c111c;color:#e8eef9;font-family:'Microsoft YaHei UI';font-size:13px; }
QFrame#card {background:#141e2e;border:1px solid #29384d;border-radius:13px;}
QLabel {background:transparent;}
QLabel#eyebrow {color:#88a0bd;font-size:11px;font-weight:600;}
QLabel#title {font-size:25px;font-weight:700;}
QLabel#muted {color:#9aaac0;font-size:12px;}
QLabel#badge {color:#a0eed9;background:#193a3c;border-radius:9px;padding:7px 12px;}
QLabel#section {font-size:16px;font-weight:600;}
QPushButton {background:#223249;border:1px solid #394e6b;border-radius:8px;padding:9px 14px;}
QPushButton:hover {background:#314663;border-color:#79a7c3;}
QPushButton:checked {background:#284e57;border:2px solid #94e5d0;}
QPushButton#primary {background:#96e1ce;color:#112c2b;border:0;font-weight:600;}
QPushButton:disabled {color:#63748c;background:#192333;border-color:#253248;}
QComboBox,QDoubleSpinBox,QSpinBox {background:#0e1726;border:1px solid #3b4e69;border-radius:7px;padding:7px;min-height:20px;}
QComboBox QAbstractItemView {background:#172638;selection-background-color:#315469;}
QCheckBox {spacing:9px;background:transparent;}
QCheckBox::indicator {width:17px;height:17px;border:1px solid #526883;border-radius:4px;background:#101928;}
QCheckBox::indicator:checked {background:#91dfcb;border:2px solid #d5fff2;}
QSlider::groove:horizontal {height:5px;background:#2e3e55;border-radius:2px;}
QSlider::sub-page:horizontal {background:#91dfcb;}
QSlider::handle:horizontal {background:#d3fff1;width:14px;margin:-5px 0;border-radius:7px;}
QProgressBar {border:0;background:#29374e;border-radius:3px;height:6px;max-height:6px;}
QProgressBar::chunk {background:#86d8f6;border-radius:3px;}
QListWidget,QTableWidget {background:#101827;border:0;outline:0;gridline-color:#233247;selection-background-color:#244650;}
QListWidget::item {padding:8px;color:#9aadc8;}
QListWidget::item:selected {background:#244650;color:#c1ffeb;border-radius:5px;}
QHeaderView::section {background:#1d2c40;color:#adbed4;padding:6px;border:0;}
QTabWidget::pane {border:0;}
QTabBar::tab {background:#0d1421;color:#8fa2bd;padding:12px 22px;border-bottom:2px solid #263449;}
QTabBar::tab:selected {color:#b9f8e3;border-bottom:2px solid #9be7ce;background:#172636;}
QScrollArea {border:0;background:transparent;}
QToolTip {background:#223149;color:#e8eef9;border:1px solid #52637b;}
"""

def label(text,name=None,wrap=False):
    w=QLabel(text);w.setWordWrap(wrap)
    if name:w.setObjectName(name)
    return w
def button(text,callback,primary=False):
    w=QPushButton(text);w.clicked.connect(callback)
    if primary:w.setObjectName("primary")
    return w
def card():
    w=QFrame();w.setObjectName("card");l=QVBoxLayout(w);l.setContentsMargins(19,16,19,16);l.setSpacing(12);return w,l
def combo(items,current,callback):
    w=QComboBox()
    for text,key in items:w.addItem(text,key)
    w.setCurrentIndex(max(0,w.findData(current)));w.currentIndexChanged.connect(lambda:callback(w.currentData()));return w
def check(text,value,callback):
    w=QCheckBox(text);w.setChecked(value);w.toggled.connect(callback);return w

class BarPreview(QWidget):
    def __init__(self):
        super().__init__();self.text="--:--:--";self.color="#86D8F6";self.level=0;self.setMinimumHeight(134);self.pixels=None;self.bitmap=None;self.bitmap_key=None
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);w,h=self.width(),self.height()
        p.setPen(QPen(QColor("#384b62"),1));p.setBrush(QColor("#050a12"));p.drawRoundedRect(QRectF(5,10,w-10,h-20),28,28)
        color=QColor(self.color)
        for side in (58,w-58):
            for radius in (34,27,20,13):
                ring=QColor(color);ring.setAlpha(min(230,45+int((34-radius)*5)+int(self.level*80)))
                p.setPen(QPen(ring,2));p.setBrush(Qt.NoBrush);p.drawEllipse(QRectF(side-radius,h/2-radius,2*radius,2*radius))
        if self.pixels:
            key=(self.pixels,self.color)
            if key!=self.bitmap_key:self.bitmap=preview_image(self.pixels,self.color);self.bitmap_key=key
            scale=min((w-234)/256,(h-24)/32);rect=QRectF((w-256*scale)/2,(h-32*scale)/2,256*scale,32*scale)
            p.setRenderHint(QPainter.SmoothPixmapTransform,False);p.drawImage(rect,self.bitmap);p.end();return
        p.setPen(QColor("#152332"))
        for x in range(125,int(w-120),7):
            for y in range(27,int(h-23),7):p.drawPoint(x,y)
        font=QFont("Consolas" if self.text.isascii() else "Microsoft YaHei UI");font.setPixelSize(40 if len(self.text)<=10 else 31 if len(self.text)<=13 else 25);font.setBold(True)
        p.setFont(font);p.setPen(color);p.drawText(QRectF(117,21,w-234,h-42),Qt.AlignCenter,self.text);p.end()

class StudioWindow(QMainWindow):
    def __init__(self,engine:Engine,start=True):
        super().__init__();self.engine=engine;self.real_quit=False;self.last_state={};self.lyric_signature=None;self.metric_keys=[];self.table_updating=False
        self.color=engine.config["color"];self.ambient_color=engine.config["ambient_color"]
        self.setWindowTitle("Halo Studio · 主题 / 音乐 / 硬件监控");available=QApplication.primaryScreen().availableGeometry()
        self.resize(min(1130,available.width()-40),min(900,available.height()-60));self.setMinimumSize(920,660)
        pix=QPixmap(64,64);pix.fill(QColor("#101725"));p=QPainter(pix);p.setPen(QColor("#91dfcb"));p.setFont(QFont("Segoe UI",32,QFont.Bold));p.drawText(pix.rect(),Qt.AlignCenter,"H");p.end();self.setWindowIcon(QIcon(pix))
        root=QWidget();self.setCentralWidget(root);main=QVBoxLayout(root);main.setContentsMargins(26,20,26,16);main.setSpacing(13)
        header=QHBoxLayout();titles=QVBoxLayout();titles.addWidget(label("HALO  /  PIXEL STUDIO","eyebrow"));titles.addWidget(label("让桌面，有自己的节奏","title"));header.addLayout(titles);header.addStretch()
        self.connection=label("正在连接…","badge");header.addWidget(self.connection);header.addWidget(button("重新连接",lambda:engine.submit("reconnect")));main.addLayout(header)
        frame,pl=card();ph=QHBoxLayout();ph.addWidget(label("音响屏幕","section"));self.theme_badge=label("","muted");ph.addWidget(self.theme_badge);ph.addStretch();self.display_mode=label("时钟","badge");ph.addWidget(self.display_mode);pl.addLayout(ph)
        self.preview=BarPreview();pl.addWidget(self.preview);foot=QHBoxLayout();self.write_status=label("等待设备连接","muted");foot.addWidget(self.write_status);foot.addStretch();self.rhythm_badge=label("律动已关闭","muted");foot.addWidget(self.rhythm_badge);pl.addLayout(foot);main.addWidget(frame)
        self.tabs=QTabWidget();main.addWidget(self.tabs,1);self.build_display();self.build_monitor();self.build_music();self.build_lights();self.build_power();self.tabs.currentChanged.connect(self.visibility)
        bottom=QHBoxLayout();self.message=label("保持程序或托盘运行，时钟与歌词才会同步。","muted",True);bottom.addWidget(self.message,1);self.toggle=button("暂停同步",self.toggle_service,True);bottom.addWidget(self.toggle);main.addLayout(bottom)
        self.tray=QSystemTrayIcon(self.windowIcon(),self);menu=QMenu();menu.addAction("打开控制台",self.show_from_tray);menu.addAction("退出 Halo Studio",self.quit);self.tray.setContextMenu(menu);self.tray.setToolTip("Halo Studio · 时钟 / 监控 / 歌词");self.tray.activated.connect(lambda reason:self.show_from_tray() if reason==QSystemTrayIcon.DoubleClick else None)
        self.ui_timer=QTimer(self);self.ui_timer.setInterval(500);self.ui_timer.timeout.connect(self.render_latest);self.ui_timer.start();engine.changed.connect(self.receive_state);engine.notice.connect(self.message.setText)
        if start:self.tray.show();engine.start()
    def page(self,title):
        scroll=QScrollArea();scroll.setWidgetResizable(True);w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(0,14,0,4);l.setSpacing(13);scroll.setWidget(w);self.tabs.addTab(scroll,title);return l
    def build_display(self):
        c=self.engine.config;l=self.page("屏幕与主题");top,tl=card();grid=QGridLayout()
        self.idle=combo([("时钟","clock"),("系统运行监控","monitor")],c["idle_content"],lambda v:self.config(idle_content=v))
        self.auto=check("音乐播放时优先显示歌词",c["mode"]=="auto",lambda v:self.config(mode="auto" if v else "idle"));self.seconds=check("时钟显示秒数",c["seconds"],lambda v:self.config(seconds=v))
        grid.addWidget(label("默认显示","section"),0,0);grid.addWidget(self.idle,0,1);grid.addWidget(self.auto,0,2);grid.addWidget(self.seconds,1,2)
        self.themes=check("启用主题",c["themes"],lambda v:self.config(themes=v));grid.addWidget(self.themes,1,0);self.color_button=button("自定义颜色  "+self.color,self.pick_color);grid.addWidget(self.color_button,1,1);tl.addLayout(grid);l.addWidget(top)
        gallery,gl=card();gl.addWidget(label("实时显示 · 六套主题配色","section"));choices=QGridLayout();self.theme_buttons={}
        for index,(key,theme) in enumerate(THEMES.items()):
            w=QPushButton();w.setMinimumHeight(92);w.setCheckable(True);w.setChecked(c["theme"]==key)
            tile=QVBoxLayout(w);tile.setContentsMargins(11,9,11,9)
            title=label(theme.name);pic=label(theme.left+'20:26:08'+theme.right);pic.setStyleSheet(f'color:{theme.color};font-size:20px;font-family:Consolas;')
            desc=label('主题配色 / 时钟文字装饰','muted')
            for child in (title,pic,desc):child.setAttribute(Qt.WA_TransparentForMouseEvents);tile.addWidget(child)
            w.setStyleSheet(f"QPushButton{{color:{theme.color};text-align:left;padding:13px;}} QPushButton:checked{{border:2px solid {theme.color};background:#20323f;}}")
            w.clicked.connect(lambda checked=False,k=key:self.select_theme(k));self.theme_buttons[key]=w;choices.addWidget(w,index//3,index%3)
        gl.addLayout(choices);motion=QHBoxLayout();self.animations=check("启用屏幕动画",c["animations"],lambda v:self.config(animations=v));motion.addWidget(self.animations)
        self.transition=check("歌词 / 监控启用文字动效",c['transitions'],lambda v:self.config(transitions=v));motion.addWidget(self.transition,1);gl.addLayout(motion)
        self.text_motion=combo([('歌词原生上滑 · 监控淡出换页','native_up'),('横向滚动 · 由设备连续播放','scroll'),('淡出换行 · 约 0.24 秒','fade')],c['text_motion'],lambda v:self.config(text_motion=v));gl.addWidget(self.text_motion)
        gl.addWidget(label("上滑和横向滚动由音响播放，无需连续上传图片。关闭屏幕动画或文字动效后，内容直接切换。预览显示文字与配色，动画以实机为准。\n\n原生歌词上滑已通过本机视觉验证。任意图形流播仍在研究，实时模式暂不显示猫咪、边框或曲线图；原图案素材保留在工程中。","muted",True));l.addWidget(gallery);l.addStretch()
    def build_monitor(self):
        c=self.engine.config;l=self.page("系统监控");frame,fl=card();r=QHBoxLayout();r.addWidget(label("监控编排","section"))
        self.monitor_view=combo([("名称 + 数值","value"),("字符负载条","bar"),("双项数值","compact")],c["monitor_view"],lambda v:self.config(monitor_view=v));r.addWidget(self.monitor_view)
        self.rotate=check("轮流显示已勾选项目",c["monitor_rotate"],lambda v:self.config(monitor_rotate=v));r.addWidget(self.rotate);self.rotation=QSpinBox();self.rotation.setRange(2,30);self.rotation.setSuffix(" 秒 / 项");self.rotation.setValue(c["rotation_seconds"]);self.rotation.valueChanged.connect(lambda v:self.config(rotation_seconds=v));r.addWidget(self.rotation);fl.addLayout(r)
        fl.addWidget(label("实时文字通道支持数值、字符负载条和双项显示，轮流展示已勾选的指标。此模式不上传图形素材；文字动效在“屏幕与主题”中设置。","muted",True))
        self.monitor_table=QTableWidget(0,4);self.monitor_table.setHorizontalHeaderLabels(["显示 / 指标","当前数值","单位","数据来源"]);self.monitor_table.verticalHeader().hide();self.monitor_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.monitor_table.setMinimumHeight(200);self.monitor_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);self.monitor_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch);self.monitor_table.setColumnWidth(1,110);self.monitor_table.setColumnWidth(2,70);self.monitor_table.itemChanged.connect(self.metrics_changed);fl.addWidget(self.monitor_table)
        self.monitor_detail=label("正在读取可用传感器…","muted",True);fl.addWidget(self.monitor_detail);l.addWidget(frame)
        fan,fanl=card();fanl.addWidget(label("风扇 · 转速读数与相对转速","section"));fr=QHBoxLayout();self.fan_choice=QComboBox();self.fan_choice.currentIndexChanged.connect(self.fan_selected);fr.addWidget(self.fan_choice,1);self.fan_max=QSpinBox();self.fan_max.setRange(0,30000);self.fan_max.setSpecialValueText("额定最大 RPM 未知");self.fan_max.setSuffix(" RPM 最大值");self.fan_max.setSingleStep(100);self.fan_max.valueChanged.connect(self.set_fan_limit);fr.addWidget(self.fan_max);fanl.addLayout(fr);self.fan_reading=label("等待传感器","muted",True);fanl.addWidget(self.fan_reading)
        fanl.addWidget(label("填写风扇规格中的最大 RPM 后，计算“当前 RPM / 额定最大 RPM”。驱动百分比单独标注；软件不调节风扇。","muted",True));l.addWidget(fan);l.addStretch()
    def build_music(self):
        c=self.engine.config;l=self.page("网易云歌词");frame,ml=card();r=QHBoxLayout();self.song=label("等待网易云播放","section");r.addWidget(self.song,1);self.play_status=label("已暂停","badge");r.addWidget(self.play_status);ml.addLayout(r);self.artist=label("","muted");ml.addWidget(self.artist)
        self.progress=QProgressBar();self.progress.setRange(0,1000);self.progress.setTextVisible(False);ml.addWidget(self.progress);self.elapsed=label("","muted");ml.addWidget(self.elapsed);self.lyric_list=QListWidget();self.lyric_list.setMinimumHeight(180);ml.addWidget(self.lyric_list);self.source=label("","muted");ml.addWidget(self.source)
        r=QHBoxLayout();self.import_button=button("导入 LRC",self.import_lrc);r.addWidget(self.import_button);r.addWidget(button("重新匹配",lambda:self.engine.submit("retry_lyrics")));self.online=check("自动获取歌词上下文",c["online"],lambda v:self.config(online=v));r.addWidget(self.online);r.addStretch();ml.addLayout(r)
        r=QHBoxLayout();r.addWidget(label("时间校准","muted"));self.offset=QDoubleSpinBox();self.offset.setRange(-15,15);self.offset.setSingleStep(.2);self.offset.setSuffix(" 秒");self.offset.setValue(c["offset"]);self.offset.valueChanged.connect(lambda v:self.config(offset=v));r.addWidget(self.offset);self.sync_hint=label("","muted",True);r.addWidget(self.sync_hint,1);ml.addLayout(r);l.addWidget(frame);l.addStretch()
    def build_lights(self):
        c=self.engine.config;l=self.page("氛围灯与律动");frame,ll=card();r=QHBoxLayout();r.addWidget(label("日常氛围灯","section"));r.addStretch();self.ambient_enabled=check("开启氛围灯",c["ambient_enabled"],lambda v:None);r.addWidget(self.ambient_enabled);ll.addLayout(r)
        grid=QGridLayout();self.effect=combo([("呼吸","breathing"),("色彩潮汐","color_tide"),("静态单色","static"),("彩色波纹","ripple"),("流光","flow"),("动态","dynamic")],c["effect"],lambda _:self.update_effect());self.ambient_button=button("颜色  "+self.ambient_color,self.pick_ambient);self.brightness=combo([("低亮度","low"),("中亮度","medium"),("高亮度","high")],c["brightness"],lambda _:None);self.speed=QSlider(Qt.Horizontal);self.speed.setRange(1,10);self.speed.setValue(c["speed"])
        for i,(title,w) in enumerate((("灯效",self.effect),("颜色",self.ambient_button),("亮度",self.brightness),("呼吸速度",self.speed))):grid.addWidget(label(title,"muted"),0,i);grid.addWidget(w,1,i)
        ll.addLayout(grid);ll.addWidget(button("应用日常灯光",self.apply_lights,True));self.update_effect();l.addWidget(frame)
        rhythm,rl=card();rl.addWidget(label("让音乐点亮桌面","section"));self.rhythm=check("播放网易云时启用音乐律动",c["rhythm"],lambda v:self.config(rhythm=v));rl.addWidget(self.rhythm);r=QHBoxLayout();self.rhythm_style=combo([("连续能量起伏","pulse"),("双色能量渐变","color"),("亮暗两档（跳变）","beat")],c["rhythm_style"],lambda v:self.config(rhythm_style=v));r.addWidget(self.rhythm_style,1);r.addWidget(label("灵敏度","muted"));self.gain=QDoubleSpinBox();self.gain.setRange(.5,8);self.gain.setSingleStep(.25);self.gain.setValue(c["rhythm_gain"]);self.gain.valueChanged.connect(lambda v:self.config(rhythm_gain=v));r.addWidget(self.gain);rl.addLayout(r)
        self.level=QProgressBar();self.level.setRange(0,100);self.level.setTextVisible(False);rl.addWidget(self.level);self.rhythm_status=label("等待开启","muted");rl.addWidget(self.rhythm_status);rl.addWidget(label("读取网易云实际输出的瞬时声音强弱，自动适应每首歌的响度；系统音量固定也会律动。扫描所有活动输出设备，无需麦克风、不保存音频。暂停后恢复日常灯光。","muted",True));l.addWidget(rhythm);l.addStretch()
    def build_power(self):
        c=self.engine.config;l=self.page("后台与资源");frame,fl=card();fl.addWidget(label("按需要刷新，让后台保持轻量","section"));self.power=combo([("节能 · 监控 3 秒 / 灯光最高 20 Hz","eco"),("均衡 · 监控 2 秒 / 灯光最高 30 Hz","balanced")],c["power_profile"],lambda v:self.config(power_profile=v));fl.addWidget(self.power);self.performance=label("正在采样应用资源…","section",True);fl.addWidget(self.performance)
        fl.addWidget(label("• 仅选择系统监控或打开监控页时读取硬件\n• 重复文字和灯光不重复写入 USB\n• 收起窗口后停用预览重绘，后台继续同步\n• 关闭律动后不轮询音量峰值\n• 复用现有 GPU 驱动，不额外安装内核驱动\n• CPU 占用不是瓦数；真实功耗需要外部测量","muted",True));fl.addWidget(button("关闭屏幕动画与音乐律动",self.disable_effects));l.addWidget(frame)
        info,il=card();il.addWidget(label("不启动程序，会发生什么？","section"));il.addWidget(label("正常听歌不受影响。完全退出后，歌词、监控、主题动画与电脑时钟更新都会停止，屏幕可能保留最后一帧；音乐律动在正常退出时恢复日常灯光。\n\n点击关闭按钮会收起到托盘，继续同步。右击托盘选择“退出 Halo Studio”才是完全退出。","muted",True));l.addWidget(info);l.addStretch()
    def config(self,**kwargs):self.engine.submit("config",kwargs)
    def select_theme(self,key):
        for k,w in self.theme_buttons.items():w.setChecked(k==key)
        self.themes.setChecked(True);self.config(theme=key,themes=True)
    def disable_effects(self):self.animations.setChecked(False);self.rhythm.setChecked(False)
    def toggle_service(self):self.config(enabled=not self.last_state.get("enabled",True))
    def update_effect(self):self.speed.setEnabled(self.effect.currentData()=="breathing")
    def pick_color(self):
        color=QColorDialog.getColor(QColor(self.color),self,"自定义屏幕颜色")
        if color.isValid():self.color=color.name();self.color_button.setText("自定义颜色  "+self.color);self.themes.setChecked(False);self.config(color=self.color)
    def pick_ambient(self):
        color=QColorDialog.getColor(QColor(self.ambient_color),self,"氛围灯颜色")
        if color.isValid():self.ambient_color=color.name();self.ambient_button.setText("颜色  "+self.ambient_color)
    def apply_lights(self):self.engine.submit("ambient",{"effect":self.effect.currentData(),"ambient_color":self.ambient_color,"brightness":self.brightness.currentData(),"speed":self.speed.value(),"ambient_enabled":self.ambient_enabled.isChecked()})
    def metrics_changed(self,item):
        if self.table_updating or item.column()!=0:return
        self.config(monitor_metrics=[self.metric_keys[r] for r in range(self.monitor_table.rowCount()) if self.monitor_table.item(r,0).checkState()==Qt.Checked])
    def fan_selected(self):
        key=self.fan_choice.currentData();self.fan_max.blockSignals(True);self.fan_max.setValue(self.engine.config["fan_limits"].get(key,0));self.fan_max.blockSignals(False);self.render_fan()
    def set_fan_limit(self,value):
        key=self.fan_choice.currentData()
        if key:
            limits=dict(self.engine.config["fan_limits"]);limits[key]=value;self.config(fan_limits=limits)
    def render_fan(self):
        fan=next((f for f in self.last_state.get("monitor",{}).get("fans",[]) if f["key"]==self.fan_choice.currentData()),None)
        if not fan:self.fan_reading.setText("没有可读取的风扇传感器");return
        def value(v,suffix):return "未知" if v is None else f"{v:.0f}{suffix}"
        self.fan_reading.setText("转速读数 "+value(fan["rpm"]," RPM")+"   ·   驱动报告比例 "+value(fan["driver_percent"],"%")+"   ·   相对额定最大值 "+value(fan["rated_percent"],"%"))
    def import_lrc(self):
        t=self.last_state.get("track",{})
        if not t.get("title"):self.message.setText("请先在网易云播放需要关联歌词的歌曲。");return
        key=(t["title"],t["artist"],t["album"]);filename,_=QFileDialog.getOpenFileName(self,"为当前歌曲导入 LRC","","LRC 歌词 (*.lrc);;文本文件 (*.txt)")
        if filename:
            try:
                data=Path(filename).read_bytes()
                try:text=data.decode("utf-8-sig")
                except UnicodeDecodeError:text=data.decode("gb18030")
                self.engine.submit("lrc",{"key":key,"text":text})
            except Exception as exc:self.message.setText("读取歌词失败："+str(exc))
    def receive_state(self,state):self.last_state=state
    def render_latest(self):
        if not self.isVisible() or self.isMinimized() or not self.last_state:return
        s=self.last_state;t=s["track"];c=self.engine.config
        self.connection.setText("● USB 已连接" if s["connected"] else "○ 等待音响");self.preview.text=s["display"];self.preview.color=s["color"];self.preview.pixels=s.get('pixels');self.preview.level=s.get("rhythm_level",0);self.preview.update();self.theme_badge.setText(THEMES.get(c["theme"],THEMES["ion"]).name if c["themes"] else "自定义颜色")
        self.display_mode.setText(s["display_mode"] if s["enabled"] else "同步已暂停");self.write_status.setText(("原生上滑歌词已发送 · USB 已连接" if s.get('layout')=='native_lyric_up' else "实时文字已回读 · 图片上传已禁用") if s["connected"] and s["verified"] and s["enabled"] else s["device_message"] if s["enabled"] else "同步已暂停");self.rhythm_badge.setText("音乐律动中" if s.get("rhythm_active") else "律动待命" if c["rhythm"] else "律动已关闭");self.toggle.setText("暂停同步" if s["enabled"] else "恢复同步")
        tab=self.tabs.currentIndex()
        if tab==1:self.render_monitor(s.get("monitor",{}))
        if tab==2:
            self.play_status.setText(s["media_message"]);self.song.setText(t["title"] or "等待网易云播放");self.artist.setText(t["artist"]);native=t.get("provider","").startswith("网易云本地");self.offset.setEnabled(not native);self.elapsed.setText(t["provider"]);self.sync_hint.setText("实时跟随播放器；LRC 导入用于上下文。" if native else "正值提前；本地 LRC 优先。")
            self.progress.setValue(round(1000*t["position"]/t["duration"]) if t["duration"] else 0);self.source.setText(s["source"]);signature=tuple((v["time"],v["text"]) for v in s["lines"])
            if signature!=self.lyric_signature:
                self.lyric_signature=signature;self.lyric_list.clear()
                for v in s["lines"]:self.lyric_list.addItem(f"{int(v['time'])//60:02d}:{int(v['time'])%60:02d}   {v['text']}")
            row=s["active"]["index"] if s["active"] else -1
            if row!=self.lyric_list.currentRow():
                self.lyric_list.setCurrentRow(row)
                if row>=0:self.lyric_list.scrollToItem(self.lyric_list.item(row),QListWidget.PositionAtCenter)
            self.import_button.setEnabled(bool(t["title"]))
        if tab==3:self.level.setValue(round(s.get("rhythm_level",0)*100));self.rhythm_status.setText((s.get("rhythm_message","")+f" · 原始峰值 {s.get('rhythm_raw',0):.3f} / 动态能量 {s.get('rhythm_level',0):.0%}") if s.get("rhythm_active") else "暂停后恢复日常灯光" if c["rhythm"] else "音乐律动已关闭")
        if tab==4:
            p=s.get("performance",{});self.performance.setText(f"CPU {p.get('cpu_percent',0):.2f}%   ·   内存 {p.get('memory_mb',0):.1f} MB   ·   USB {p.get('hid_per_second',0):.1f} 包/秒")
        if not s["connected"]:self.message.setText(s["device_message"])
    def render_monitor(self,snapshot):
        metrics=snapshot.get("metrics",[]);keys=[m["key"] for m in metrics];self.table_updating=True
        if keys!=self.metric_keys:
            self.metric_keys=keys;self.monitor_table.setRowCount(len(metrics))
            for row,m in enumerate(metrics):
                for col in range(4):self.monitor_table.setItem(row,col,QTableWidgetItem())
                item=self.monitor_table.item(row,0);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if m["key"] in self.engine.config["monitor_metrics"] else Qt.Unchecked)
        for row,m in enumerate(metrics):
            for col,text in enumerate((m["name"],m["text"],m["unit"],m["source"])):
                item=self.monitor_table.item(row,col)
                if item.text()!=text:item.setText(text)
        self.table_updating=False;self.monitor_detail.setText(snapshot.get("detail",""));fans=snapshot.get("fans",[])
        if [self.fan_choice.itemData(i) for i in range(self.fan_choice.count())]!=[f["key"] for f in fans]:
            self.fan_choice.blockSignals(True);self.fan_choice.clear()
            for f in fans:self.fan_choice.addItem(f["name"],f["key"])
            self.fan_choice.blockSignals(False);self.fan_selected()
        self.render_fan()
    def visibility(self,*_):
        if not hasattr(self,"ui_timer"):return
        visible=self.isVisible() and not self.isMinimized();self.engine.submit("visibility",{"visible":visible,"monitor":visible and self.tabs.currentIndex()==1})
        if visible:self.ui_timer.start();self.render_latest()
        else:self.ui_timer.stop()
    def showEvent(self,event):super().showEvent(event);self.visibility()
    def hideEvent(self,event):super().hideEvent(event);self.visibility()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.WindowStateChange:self.visibility()
    def show_from_tray(self):self.showNormal();self.raise_();self.activateWindow()
    def closeEvent(self,event):
        if not self.real_quit and QSystemTrayIcon.isSystemTrayAvailable():self.hide();event.ignore()
        else:self.engine.stop();event.accept()
    def quit(self):self.real_quit=True;self.tray.hide();self.engine.stop();QApplication.instance().quit()
