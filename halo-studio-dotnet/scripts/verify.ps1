param([string]$App='')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if(!$App){$App=Join-Path $projectRoot 'dist\HaloStudioNet\HaloStudioNet.exe'}
$report=Join-Path $projectRoot 'validation\self-test.json'
New-Item -ItemType Directory -Force (Split-Path $report -Parent) | Out-Null
$process=Start-Process -FilePath $App -ArgumentList @('--self-test','--fixtures',(Join-Path $projectRoot 'tests\codec-vectors.json'),'--output',$report) -WindowStyle Hidden -PassThru -Wait
if($process.ExitCode -ne 0){throw 'Self-test failed; inspect runtime\last-error.txt'}
Get-Content $report -Raw
