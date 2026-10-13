from pathlib import Path
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import sys
import tempfile

def main():
    # comtypes owns an atexit CoUninitialize on the main thread. Import it here,
    # before the worker is created, so its implicit initialization is balanced.
    parser=argparse.ArgumentParser()
    parser.add_argument("--diagnose",action="store_true")
    parser.add_argument("--screenshot")
    parser.add_argument("--quit-after",type=int,default=0)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--background",action="store_true",help="Start in the system tray")
    parser.add_argument("--autostart",choices=("enable","disable","status"),help="Manage current-user logon startup")
    args=parser.parse_args()
    if args.autostart:
        from halo.autostart import is_enabled, set_enabled
        enabled = is_enabled() if args.autostart == 'status' else set_enabled(args.autostart == 'enable')
        return 0 if enabled == (args.autostart != 'disable') else 1
    import comtypes
    base=Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent
    data=base/"runtime"
    data.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,handlers=[RotatingFileHandler(data/"studio.log",maxBytes=500000,backupCount=2,encoding="utf-8")])
    if args.self_test:
        import ssl
        import asyncio
        import requests
        from halo.device import HaloLink
        from halo.media import MediaMonitor
        from halo.lyrics import LyricsStore
        monitor=MediaMonitor(); track=asyncio.run(monitor.poll()); monitor.close()
        link=HaloLink(); link.connect(); volume=list(link.query(0x66)); link.close()
        result={"ssl":ssl.OPENSSL_VERSION,"device_volume":volume,"media_provider":track.provider,
                "track_detected":bool(track.title),"playing":track.playing,"live_lyric_detected":bool(track.realtime_lyric)}
        if track.title:
            lines,source=LyricsStore(data/"lyrics").fetch(track.title,track.artist,track.album,track.duration)
            result.update(lyric_count=len(lines),lyrics_source=source)
        (data/"self-test.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        return
    if args.diagnose:
        import asyncio
        from dataclasses import asdict
        from halo.device import HaloLink
        from halo.media import MediaMonitor
        link=HaloLink(); link.connect()
        result={"hardware":link.status(),"media":asdict(asyncio.run(MediaMonitor().poll()))}
        link.close(); print(json.dumps(result,ensure_ascii=False,indent=2)); return
    from PySide6.QtCore import QLockFile,QTimer
    from PySide6.QtWidgets import QApplication,QMessageBox
    from halo.studio_host import StudioHost
    from halo.ui import STYLE
    from halo.pixels import init_fonts
    app=QApplication(sys.argv); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    app.setApplicationName("Halo Studio"); app.setQuitOnLastWindowClosed(False)
    init_fonts()
    lock=QLockFile(str(Path(tempfile.gettempdir())/"halo-studio-2d99-a106.lock"))
    lock.setStaleLockTime(0)
    if not args.screenshot and not lock.tryLock(50):
        if args.background: return
        QMessageBox.information(None,"Halo Studio","控制台已经在运行，请从系统托盘打开。"); return
    host=StudioHost(data,preview=bool(args.screenshot),background=args.background)
    window=host.window
    if args.screenshot:
        def capture():
            window.preview.update(); app.processEvents()
            window.grab().save(args.screenshot)
            window.real_quit=True; app.quit()
        QTimer.singleShot(500,capture)
    if args.quit_after:QTimer.singleShot(args.quit_after*1000,host.quit)
    app.aboutToQuit.connect(host.emergency_stop)
    app.exec()

if __name__=="__main__":
    sys.exit(main() or 0)
