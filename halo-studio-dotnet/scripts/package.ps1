param([string]$Version='2.6.2')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$source=Join-Path $projectRoot 'dist\HaloStudioNet'
$packages=Join-Path $projectRoot 'packages'
$stage=Join-Path $packages ('stage-'+$Version+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $stage | Out-Null
$appStage=Join-Path $stage 'HaloStudioNet'
New-Item -ItemType Directory -Force $appStage | Out-Null
# Explicitly skip private runtime records, sensor data, settings and logs.
Get-ChildItem -LiteralPath $source | Where-Object Name -ne 'runtime' | Copy-Item -Destination $appStage -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md'),(Join-Path $projectRoot 'LICENSE'),(Join-Path $projectRoot 'THIRD_PARTY_LICENSE.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs'),(Join-Path $projectRoot 'thermal-native') -Destination $stage -Recurse
foreach($name in @('firmware-fullscreen','firmware-matrix','firmware-color')) {
    $firmwareStage=Join-Path $stage $name
    New-Item -ItemType Directory -Force $firmwareStage | Out-Null
    # Only public top-level sources, images and offline reports; no local evidence.
    Get-ChildItem -LiteralPath (Join-Path $projectRoot $name) -File | Where-Object Extension -in @('.md','.s','.py','.bin','.json','.sha256') | Copy-Item -Destination $firmwareStage
}
$manifest=Get-ChildItem -LiteralPath $stage -File -Recurse | ForEach-Object {
    [pscustomobject]@{path=$_.FullName.Substring($stage.Length+1).Replace('\','/');size=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $stage 'MANIFEST.json') -Encoding UTF8
$zip=Join-Path $packages ('HaloStudio-CSharp-'+$Version+'-win64.zip')
Compress-Archive -LiteralPath (Join-Path $stage 'HaloStudioNet'),(Join-Path $stage 'README.md'),(Join-Path $stage 'LICENSE'),(Join-Path $stage 'THIRD_PARTY_LICENSE.txt'),(Join-Path $stage 'docs'),(Join-Path $stage 'thermal-native'),(Join-Path $stage 'firmware-fullscreen'),(Join-Path $stage 'firmware-matrix'),(Join-Path $stage 'firmware-color'),(Join-Path $stage 'MANIFEST.json') -DestinationPath $zip -Force
Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-List
Write-Output $zip
