"""Single owner/tray and asynchronous new/legacy mode handoffs."""
import logging
import time
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QToolBar
from .device import HaloLink
from .engine import Engine
from .pixel_engine import PixelEngine
from .pixel_ui import PixelWindow
from .ram_display import restore_clock
from .ui import StudioWindow


class LegacyEngine(Engine):
    """Lifecycle adapter only; display, media and legacy settings stay intact."""
    stop_error = None

    async def _loop(self):
        try:
            await super()._loop()
        finally:
            # The old engine closes its handle before this wrapper runs.
            link = HaloLink()
            try:
                link.connect()
                restore_clock(link, self.config['color'])
                self.stop_error = None
            except Exception as exc:
                self.stop_error = str(exc)
                logging.exception('Legacy handoff clock restoration failed')
            finally:
                link.close()


class LegacyWindow(StudioWindow):
    def __init__(self, engine, host):
        self.host = host
        super().__init__(engine, start=False)
        self.setWindowTitle('HaloStudio · 旧版控制台')
        toolbar = QToolBar('版本切换', self); toolbar.setMovable(False)
        toolbar.addAction('← 返回新版像素工作室', lambda: host.switch('pixel'))
        toolbar.addSeparator(); toolbar.addAction('退出 HaloStudio', host.quit)
        self.addToolBar(toolbar)

    def quit(self): self.host.quit()
    def closeEvent(self, event):
        if self.real_quit: event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable(): self.hide(); event.ignore()
        else: event.ignore(); self.host.quit()


class StudioHost(QObject):
    mode_changed = Signal(str)
    finished = Signal()

    def __init__(self, directory, *, preview=False, background=False):
        super().__init__()
        self.directory = directory; self.preview = preview; self.background = background
        self.engine = self.window = None; self.mode = 'pixel'; self.pending = None
        self.timer = QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self._poll_stop)
        self.tray = QSystemTrayIcon(self)
        menu = QMenu(); menu.addAction('打开 HaloStudio', self.show); menu.addSeparator(); menu.addAction('退出 HaloStudio', self.quit)
        self.menu = menu; self.tray.setContextMenu(menu); self.tray.setToolTip('HaloStudio · 像素工作室')
        self.tray.activated.connect(lambda reason: self.show() if reason == QSystemTrayIcon.DoubleClick else None)
        self._activate('pixel')

    def _activate(self, mode):
        if self.engine and self.engine.thread and self.engine.thread.is_alive():
            raise RuntimeError('Cannot overlap USB control engines')
        if self.window:
            self.window.real_quit = True; self.window.ui_timer.stop(); self.window.close()
            self.window.deleteLater(); self.engine.deleteLater()
        self.mode = mode
        self.engine = PixelEngine(self.directory) if mode == 'pixel' else LegacyEngine(self.directory)
        self.window = PixelWindow(self.engine, self) if mode == 'pixel' else LegacyWindow(self.engine, self)
        self.tray.setIcon(self.window.windowIcon())
        if not self.preview:
            self.engine.start(); self.tray.show()
        if self.background:
            self.window.ui_timer.stop(); self.engine.submit('visibility', {'visible': False, 'monitor': False})
        else:
            self.window.show()
        logging.info('Studio mode activated: %s', mode)
        self.mode_changed.emit(mode)

    def show(self):
        self.background = False
        if self.window: self.window.show_from_tray()

    def switch(self, mode):
        if mode not in ('pixel', 'legacy') or self.pending is not None: return
        self.background = False; self._begin_stop(mode)

    def quit(self):
        if self.pending is not None:
            self.pending = 'quit'
        else:
            self._begin_stop('quit')

    def _begin_stop(self, destination):
        self.pending = destination; self.stop_started = time.monotonic()
        self.window.centralWidget().setEnabled(False)
        self.window.message.setText('正在停止后台并恢复原厂时钟，请稍候…')
        # Signal only. Never block the Qt event loop on HID/lyric network work.
        self.engine.exit_event.set()
        self.timer.start()

    def _poll_stop(self):
        thread = self.engine.thread
        if thread and thread.is_alive():
            if time.monotonic()-self.stop_started > 8:
                self.window.message.setText('仍在等待当前后台结束；完成前不会启动另一套控制程序。')
            return
        self.timer.stop(); destination = self.pending; self.pending = None
        error = getattr(self.engine, 'stop_error', None)
        if error:
            logging.error('Handoff restoration unconfirmed: %s', error)
            self.tray.showMessage('HaloStudio', '屏幕恢复未确认：'+error, QSystemTrayIcon.Warning, 8000)
        logging.info('Studio handoff completed: %s -> %s', self.mode, destination)
        if destination == 'quit':
            self.tray.hide(); self.window.real_quit = True; self.window.close()
            self.finished.emit(); QApplication.instance().quit()
        else:
            self._activate(destination)

    def emergency_stop(self):
        """Qt session shutdown fallback; normal UI quit uses the async barrier."""
        if self.engine:
            self.engine.exit_event.set()
            if self.engine.thread: self.engine.thread.join(timeout=12)
        self.tray.hide()
