param(
    [ValidateSet('enable','disable','status')][string]$Action = 'enable',
    [string]$AppDirectory = (Join-Path $PSScriptRoot '..')
)
$ErrorActionPreference = 'Stop'
$taskExe = Join-Path (Resolve-Path -LiteralPath $AppDirectory).Path 'HaloStudio.exe'
if (-not (Test-Path -LiteralPath $taskExe -PathType Leaf)) { throw 'HaloStudio.exe not found. Pass -AppDirectory.' }
$taskProcess = Start-Process -FilePath $taskExe -ArgumentList @('--autostart',$Action) -WindowStyle Hidden -Wait -PassThru
if ($taskProcess.ExitCode -ne 0) { throw 'Autostart action failed or startup is disabled.' }
Write-Host ('HaloStudio logon startup: ' + $Action)
