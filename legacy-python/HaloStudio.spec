# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import copy_metadata
from pathlib import Path
import sys

# Match the SSL DLLs to the Python runtime instead of unrelated conda DLLs on PATH.
python_dlls = Path(sys.base_prefix) / 'DLLs'
ssl_binaries = [(str(python_dlls / name), '.') for name in ('libssl-3-x64.dll', 'libcrypto-3-x64.dll')]

datas = [('THIRD_PARTY_LICENSE.txt', '.'), ('references/LICENSE-HaloPixelToolBox.txt', 'licenses'), ('references/LICENSE-halo-pixelbar-mcp.txt','licenses')]
datas += [('native/HaloThermal.exe','native'),('thermal-native/references/LHM/LICENSE','licenses/LibreHardwareMonitor')]
datas += [('references/licenses','licenses/Qt'),(str(Path(sys.base_prefix)/'LICENSE.txt'),'licenses/Python')]
datas += [('native/PawnIO_setup.exe','native'),('native/AMDFamily17.bin','native')]
datas += [('thermal-native/references/PawnIO-LGPL-2.1.txt','licenses/PawnIO'),
          ('thermal-native/references/AMDFamily17.p','licenses/PawnIO'),
          ('thermal-native/references/PawnIO-source.json','licenses/PawnIO')]
hiddenimports = ['winrt.windows.foundation', 'winrt.windows.foundation.collections', 'winrt.windows.media', 'winrt.windows.storage.streams']
datas += copy_metadata('PySide6-Essentials')
datas += copy_metadata('shiboken6')
datas += copy_metadata('hidapi')
datas += copy_metadata('pycaw')
datas += copy_metadata('winrt-runtime')
datas += copy_metadata('nvidia-ml-py')
for distribution in ('requests','psutil','comtypes','certifi','urllib3','charset-normalizer','idna'):
    datas += copy_metadata(distribution)
hiddenimports += collect_submodules('winrt')
hiddenimports += collect_submodules('pycaw')
hiddenimports += collect_submodules('comtypes.gen')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ssl_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HaloStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HaloStudio',
)
