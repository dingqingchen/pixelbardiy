param([string]$Dotnet='dotnet')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$destination=Join-Path $projectRoot 'dist\HaloStudioNet'
& $Dotnet publish (Join-Path $projectRoot 'src\HaloStudio\HaloStudio.csproj') -c Release -r win-x64 --self-contained true -o $destination
if($LASTEXITCODE -ne 0){throw 'Build failed'}
Write-Output (Join-Path $destination 'HaloStudioNet.exe')
