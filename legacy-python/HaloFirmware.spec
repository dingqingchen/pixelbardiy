# Separate console updater; ordinary HaloStudio has no automatic flash path.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata

licenses=[('THIRD_PARTY_LICENSE.txt','.'),('references/licenses','licenses/Qt'),
          ('references/LICENSE-halo-pixelbar-mcp.txt','licenses'),
          (str(Path(sys.base_prefix)/'LICENSE.txt'),'licenses/Python')]
for distribution in ('PySide6-Essentials','shiboken6','hidapi','psutil'):
    licenses += copy_metadata(distribution)

a = Analysis(['firmware_update.py'], pathex=[], binaries=[],
    datas=licenses, hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWidgets','PySide6.QtGui'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='HaloFirmware',
    debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='HaloFirmware')
