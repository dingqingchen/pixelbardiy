param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $Python -m PyInstaller --noconfirm --distpath dist --workpath build/app HaloStudio.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    & $Python -m PyInstaller --noconfirm --distpath dist --workpath build/updater HaloFirmware.spec
    if ($LASTEXITCODE -ne 0) { throw 'Updater build failed.' }
    Copy-Item -LiteralPath (Join-Path $taskRoot 'firmware') -Destination (Join-Path $taskRoot 'dist/HaloFirmware') -Recurse -Force
    & (Join-Path $taskRoot 'dist/HaloFirmware/HaloFirmware.exe') --offline-check
    if ($LASTEXITCODE -ne 0) { throw 'Packaged firmware offline check failed.' }
} finally { Pop-Location }
