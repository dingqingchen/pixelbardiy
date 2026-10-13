import sys
from types import SimpleNamespace
from halo import autostart


def test_quoted_packaged_path_and_background():
    command = autostart.startup_command('C:/Program Files/HaloStudio/HaloStudio.exe', frozen=True)
    assert command.startswith('"') and 'HaloStudio.exe" --background' in command
    assert len(command) < 260


def test_source_startup_uses_entry_script():
    command = autostart.startup_command('C:/Python/python.exe', frozen=False, script='C:/My App/main.py')
    assert '"C:\\My App\\main.py" --background' in command


def test_enable_disable_are_idempotent_and_preserve_other_entries(monkeypatch):
    values = {'AnotherApp': 'untouched'}
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def query(key, name):
        if name not in values: raise FileNotFoundError
        return values[name], 1
    def delete(key, name):
        if name not in values: raise FileNotFoundError
        del values[name]
    registry = SimpleNamespace(HKEY_CURRENT_USER=1, REG_SZ=1, KEY_SET_VALUE=2,
        OpenKey=lambda *args: Key(), CreateKeyEx=lambda *args: Key(), QueryValueEx=query,
        SetValueEx=lambda key,name,reserved,kind,value: values.update({name:value}), DeleteValue=delete)
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    assert not autostart.is_enabled()
    assert autostart.set_enabled(True)
    assert autostart.set_enabled(True)
    assert values['HaloStudio'].endswith('--background')
    assert not autostart.set_enabled(False)
    assert not autostart.set_enabled(False)
    assert values == {'AnotherApp': 'untouched'}
