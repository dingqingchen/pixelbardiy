param(
    [ValidateSet('Preflight','OfflineCheck','Flash','VerifyDisplay')][string]$Action = 'Preflight',
    [string]$AppDirectory,
    [string]$Serial,
    [string]$FactoryPackage,
    [string]$BackupDirectory
)
$ErrorActionPreference = 'Stop'
$taskPackage = Split-Path -Parent $PSScriptRoot
$taskUpdater = Join-Path $taskPackage 'HaloFirmware.exe'
if (-not (Test-Path -LiteralPath $taskUpdater -PathType Leaf)) { throw 'Run this script from the extracted MCU update package.' }
$taskArguments = @()
if ($Action -eq 'OfflineCheck') { $taskArguments += '--offline-check' }
if ($Action -eq 'Flash') { $taskArguments += '--flash' }
if ($Action -eq 'VerifyDisplay') { $taskArguments += '--verify-display' }
if ($AppDirectory) { $taskArguments += @('--app-dir',(Resolve-Path -LiteralPath $AppDirectory).Path) }
if ($Serial) { $taskArguments += @('--serial',$Serial) }
if ($FactoryPackage) { $taskArguments += @('--backup-file',(Resolve-Path -LiteralPath $FactoryPackage).Path) }
if ($BackupDirectory) { $taskArguments += @('--backup-dir',$BackupDirectory) }
& $taskUpdater @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'MCU tool stopped. Keep speaker power on and inspect the message/trace; do not automatically retry.' }
