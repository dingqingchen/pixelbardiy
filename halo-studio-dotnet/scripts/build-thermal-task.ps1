param([Parameter(Mandatory=$true)][string]$Zig)
$ErrorActionPreference='Stop'
$project=Split-Path $PSScriptRoot -Parent
& $Zig cc -target x86_64-windows-gnu -O2 -s (Join-Path $project 'thermal-native/halo_thermal.c') -lbcrypt -ladvapi32 '-Wl,--subsystem,windows' '-Wl,--entry,mainCRTStartup' -o (Join-Path $project 'native/HaloThermalTask.exe')
if($LASTEXITCODE -ne 0){throw 'Thermal task native build failed'}
Get-FileHash (Join-Path $project 'native/HaloThermalTask.exe') -Algorithm SHA256
# Runtime verifies a pinned SHA256 in CpuTemperature.cs. A changed binary must be
# reviewed and repinned; building it never installs a task or touches hardware.
