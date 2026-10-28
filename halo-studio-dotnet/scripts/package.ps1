param([string]$Version='', [string]$Source='')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if(!$Version){$Version=([xml](Get-Content (Join-Path $projectRoot 'src\HaloStudio\HaloStudio.csproj') -Raw)).Project.PropertyGroup.Version}
if($Version -notmatch '^\d+\.\d+\.\d+$'){throw 'Invalid package version'}
if(!$Source){$Source=Join-Path $projectRoot 'dist\HaloStudioNet'}
$source=(Resolve-Path -LiteralPath $Source).Path
$actual=(Get-Item (Join-Path $source 'HaloStudioNet.exe')).VersionInfo.ProductVersion.Split('+')[0]
if($actual -ne $Version){throw "App version $actual does not match package $Version"}
foreach($required in @('coreclr.dll','System.Windows.Forms.dll','native\HaloThermal.exe','native\HaloThermalTask.exe','native\AMDFamily17.bin','native\PawnIO_setup.exe','telemetry-photos\CREDITS.md','telemetry-photos\manifest.json')){
    if(!(Test-Path -LiteralPath (Join-Path $source $required))){throw "Missing dependency: $required"}
}
if(@(Get-ChildItem (Join-Path $source 'telemetry-themes') -Filter '*.json').Count -ne 15){throw 'Expected 15 telemetry themes'}
$packages=Join-Path $projectRoot 'packages'
$stage=Join-Path $packages ('stage-'+$Version+'-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $stage | Out-Null
$appStage=Join-Path $stage 'HaloStudioNet'
New-Item -ItemType Directory -Force $appStage | Out-Null
# Explicitly skip private runtime records, sensor data, settings and logs.
Get-ChildItem -LiteralPath $source | Where-Object Name -ne 'runtime' | Copy-Item -Destination $appStage -Recurse

# Read the actual published runtime versions rather than copying notices from a different SDK.
$deps=Get-Content (Join-Path $source 'HaloStudioNet.deps.json') -Raw | ConvertFrom-Json
$nugetRoot=if($env:NUGET_PACKAGES){$env:NUGET_PACKAGES}else{Join-Path $env:USERPROFILE '.nuget\packages'}
foreach($packageName in @('Microsoft.NETCore.App.Runtime.win-x64','Microsoft.WindowsDesktop.App.Runtime.win-x64')){
    $entry=@($deps.libraries.PSObject.Properties.Name | Where-Object { $_.StartsWith("runtimepack.$packageName/") })
    if($entry.Count -ne 1){throw "Cannot determine runtime version: $packageName"}
    $runtimeVersion=$entry[0].Split('/')[1]
    $packageRoot=Join-Path $nugetRoot ($packageName.ToLowerInvariant()+'/'+$runtimeVersion)
    $notices=@(Get-ChildItem -LiteralPath $packageRoot -File | Where-Object { $_.Name -match '^(LICENSE|THIRD-PARTY-NOTICES)(\..*)?$' })
    if(!$notices){throw "Missing runtime license: $packageName"}
    $licenseDir=Join-Path $appStage ('licenses/'+$packageName)
    New-Item -ItemType Directory -Path $licenseDir -Force | Out-Null
    $notices | Copy-Item -Destination $licenseDir
}

Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md'),(Join-Path $projectRoot 'LICENSE'),(Join-Path $projectRoot 'THIRD_PARTY_LICENSE.txt') -Destination $stage
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs'),(Join-Path $projectRoot 'thermal-native') -Destination $stage -Recurse
foreach($name in @('firmware-fullscreen','firmware-matrix','firmware-color')) {
    $firmwareStage=Join-Path $stage $name
    New-Item -ItemType Directory -Force $firmwareStage | Out-Null
    # Only public top-level sources, images and offline reports; no local evidence.
    Get-ChildItem -LiteralPath (Join-Path $projectRoot $name) -File | Where-Object Extension -in @('.md','.s','.py','.bin','.json','.sha256') | Copy-Item -Destination $firmwareStage
}
$private=Get-ChildItem -LiteralPath $stage -Recurse | Where-Object { $_.FullName.Substring($stage.Length+1) -match '(^|[\\/])(runtime|backups|validation)([\\/]|$)|mcu-installation\.json$|\.log$' }
if($private){throw 'Private runtime or local evidence found in package'}
$manifest=Get-ChildItem -LiteralPath $stage -File -Recurse | ForEach-Object {
    [pscustomobject]@{path=$_.FullName.Substring($stage.Length+1).Replace('\','/');size=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $stage 'MANIFEST.json') -Encoding UTF8
$zip=Join-Path $packages ('HaloStudio-CSharp-'+$Version+'-win64.zip')
Compress-Archive -LiteralPath (Join-Path $stage 'HaloStudioNet'),(Join-Path $stage 'README.md'),(Join-Path $stage 'LICENSE'),(Join-Path $stage 'THIRD_PARTY_LICENSE.txt'),(Join-Path $stage 'docs'),(Join-Path $stage 'thermal-native'),(Join-Path $stage 'firmware-fullscreen'),(Join-Path $stage 'firmware-matrix'),(Join-Path $stage 'firmware-color'),(Join-Path $stage 'MANIFEST.json') -DestinationPath $zip -Force
$hash=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($zip))" | Set-Content -LiteralPath (Join-Path $packages 'SHA256SUMS.txt') -Encoding ascii
Write-Output "SHA256: $hash"
Write-Output $zip
