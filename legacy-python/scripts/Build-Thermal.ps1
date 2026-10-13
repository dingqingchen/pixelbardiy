param([string]$Zig = 'zig')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
& $Zig cc -target x86_64-windows-gnu -O2 -s (Join-Path $taskRoot 'thermal-native/halo_thermal.c') -lbcrypt -ladvapi32 -o (Join-Path $taskRoot 'native/HaloThermal.exe')
if ($LASTEXITCODE -ne 0) { throw 'Thermal helper compilation failed.' }
& (Join-Path $taskRoot 'native/HaloThermal.exe') --self-test
if ($LASTEXITCODE -ne 0) { throw 'Thermal helper self-test failed.' }
