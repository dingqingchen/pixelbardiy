"""Current-user Windows logon startup; no task scheduler or elevation."""
from pathlib import Path
import subprocess
import sys

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'HaloStudio'


def startup_command(executable=None, *, frozen=None, script=None):
    executable = Path(executable or sys.executable).resolve()
    frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    if frozen:
        args = [str(executable), '--background']
    else:
        pythonw = executable.with_name('pythonw.exe')
        if pythonw.exists():
            executable = pythonw
        args = [str(executable), str(Path(script or Path(__file__).parents[1] / 'main.py').resolve()), '--background']
    return subprocess.list2cmdline(args)


def read_command():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, kind = winreg.QueryValueEx(key, VALUE_NAME)
            return value if kind == winreg.REG_SZ else ''
    except FileNotFoundError:
        return ''


def is_enabled():
    return read_command() == startup_command()


def set_enabled(enabled):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = startup_command()
            if len(command) > 260:
                raise ValueError('自启动路径超过 Windows Run 的 260 字符限制，请把程序移到更短的路径。')
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    return is_enabled()
