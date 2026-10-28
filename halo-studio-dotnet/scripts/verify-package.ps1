param([Parameter(Mandatory)][string]$Archive, [Parameter(Mandatory)][string]$Version, [switch]$CheckStartup)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$destination=Join-Path $projectRoot ('validation\package-'+$Version+'-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $destination | Out-Null
$archivePath=(Resolve-Path -LiteralPath $Archive).Path
$zip=[IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach($entry in $zip.Entries){
        $relative=$entry.FullName.Replace('\','/')
        if($relative -match '(^|/)\.\.(/|$)|^/|:|(^|/)(runtime|backups|validation)(/|$)|mcu-installation\.json$|\.log$'){throw "Unexpected archive entry: $relative"}
    }
} finally { $zip.Dispose() }
Expand-Archive -LiteralPath $archivePath -DestinationPath $destination
$manifest=Get-Content (Join-Path $destination 'MANIFEST.json') -Raw | ConvertFrom-Json
$manifestPaths=@{}
foreach($entry in $manifest){
    if($entry.path -match '(^|/)\.\.(/|$)|^/|:'){throw 'Invalid manifest path'}
    $path=Join-Path $destination $entry.path
    if($manifestPaths.ContainsKey($entry.path)){throw 'Duplicate manifest path'}
    $manifestPaths[$entry.path]=$true
    if(!(Test-Path -LiteralPath $path -PathType Leaf)){throw "Missing file: $($entry.path)"}
    if((Get-Item -LiteralPath $path).Length -ne $entry.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256){throw "Hash mismatch: $($entry.path)"}
}
$actualFiles=@(Get-ChildItem -LiteralPath $destination -Recurse -File)
if($actualFiles.Count -ne $manifest.Count+1){throw 'Unmanifested files in package'}
$app=Join-Path $destination 'HaloStudioNet\HaloStudioNet.exe'
if((Get-Item $app).VersionInfo.ProductVersion.Split('+')[0] -ne $Version){throw 'Wrong executable version'}
if(@(Get-ChildItem (Join-Path $destination 'HaloStudioNet\telemetry-themes') -Filter '*.json').Count -ne 15){throw 'Missing telemetry themes'}
if(@(Get-ChildItem (Join-Path $destination 'HaloStudioNet\telemetry-photos') -Filter '*.jpg').Count -ne 30){throw 'Missing vehicle photos'}
$reportDir=Join-Path $destination 'checks'
New-Item -ItemType Directory -Path $reportDir | Out-Null
function RunCheck([string[]]$Arguments,[string]$Report){
    $quoted=@($Arguments | ForEach-Object {'"'+$_+'"'})
    $process=Start-Process -FilePath $app -ArgumentList $quoted -PassThru -WindowStyle Hidden
    if(!$process.WaitForExit(90000)){Stop-Process -Id $process.Id; throw 'Package check timed out'}
    if($process.ExitCode -ne 0){throw "Package check failed: $Report"}
    $result=Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    if(!$result.Passed){throw "Failed report: $Report"}
    return $result
}
$selfReport=Join-Path $reportDir 'self-tests.json'
$self=RunCheck @('--self-test','--runtime',(Join-Path $reportDir 'self-runtime'),'--fixtures',(Join-Path $projectRoot 'tests\codec-vectors.json'),'--output',$selfReport) $selfReport
$integrationReport=Join-Path $reportDir 'integration.json'
$integration=RunCheck @('--telemetry-integration-test','--runtime',(Join-Path $reportDir 'udp-runtime'),'--output',$integrationReport) $integrationReport
if($CheckStartup){
    $startupReport=Join-Path $reportDir 'startup.json'
    $startup=RunCheck @('--preview','--background','--background-audit','--runtime',(Join-Path $reportDir 'startup-runtime'),'--output',$startupReport) $startupReport
}
[pscustomobject]@{Passed=$true;Version=$Version;ManifestFiles=$manifest.Count;SelfTests=$self.Count;IntegrationChecks=$integration.Count;StartupChecked=[bool]$CheckStartup;ExtractedTo=$destination;ArchiveSHA256=(Get-FileHash $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
