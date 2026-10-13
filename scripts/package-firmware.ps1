param([string]$Version='2.6.0')
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$stage=Join-Path $repo ('release-staging/mcu-'+$Version+'-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
# Only Git-indexed public files. Stage new documentation before packaging.
$paths=@('README.md','LICENSE','THIRD_PARTY_LICENSE.txt','docs','firmware',
    'halo-studio-dotnet/README.md','halo-studio-dotnet/LICENSE','halo-studio-dotnet/THIRD_PARTY_LICENSE.txt',
    'halo-studio-dotnet/docs','halo-studio-dotnet/firmware-color','halo-studio-dotnet/firmware-fullscreen','halo-studio-dotnet/firmware-matrix',
    'halo-studio-dotnet/src','halo-studio-dotnet/themes','halo-studio-dotnet/palettes','halo-studio-dotnet/demos','halo-studio-dotnet/tests','halo-studio-dotnet/scripts',
    'legacy-python/halo','legacy-python/references','legacy-python/firmware-lab','legacy-python/scripts/build_firmware.py','legacy-python/requirements.txt','legacy-python/requirements-dev.txt','legacy-python/LICENSE','legacy-python/THIRD_PARTY_LICENSE.txt')
$files=& git -C $repo ls-files -- $paths
if($LASTEXITCODE -ne 0){throw 'Git file inventory failed'}
foreach($relative in $files){
    if($relative -match '(^|/)(runtime|validation|bin|obj|backups|vendor-[^/]*)(/|$)'){throw "Private/generated path indexed: $relative"}
    $target=Join-Path $stage $relative
    New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo $relative) -Destination $target
}
if(!(Test-Path (Join-Path $stage 'docs/FIRMWARE_USAGE.md'))){throw 'Missing staged usage guide'}
$manifest=@(Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
    @{path=$_.FullName.Substring($stage.Length+1).Replace('\','/');size=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
})
ConvertTo-Json -InputObject $manifest -Depth 5 | Set-Content (Join-Path $stage 'MANIFEST.json') -Encoding utf8
$zip=Join-Path $repo ('packages/HaloPixelBar-MCU-'+$Version+'.zip')
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force
$hash=(Get-FileHash -LiteralPath $zip).Hash.ToLowerInvariant()
"$hash  $(Split-Path $zip -Leaf)" | Set-Content ($zip+'.sha256') -Encoding ascii
Write-Output $zip
