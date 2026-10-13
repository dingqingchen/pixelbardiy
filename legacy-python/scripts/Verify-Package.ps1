param([string]$Directory = (Join-Path $PSScriptRoot '..'))
$ErrorActionPreference = 'Stop'
$taskDirectory = (Resolve-Path -LiteralPath $Directory).Path
$taskManifest = Get-Content -LiteralPath (Join-Path $taskDirectory 'manifest.json') -Raw | ConvertFrom-Json
foreach ($taskFile in $taskManifest.files) {
    $taskPath = [IO.Path]::GetFullPath((Join-Path $taskDirectory $taskFile.path))
    if (-not $taskPath.StartsWith($taskDirectory + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path escapes package' }
    if ((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskFile.sha256) { throw ('Hash mismatch: ' + $taskFile.path) }
}
Write-Host ('Verified ' + $taskManifest.files.Count + ' files.')
