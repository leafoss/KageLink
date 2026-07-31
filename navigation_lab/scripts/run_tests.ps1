[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Push-Location $RepoRoot
try {
    & $Python -m compileall -q navigation_lab
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m unittest discover -s navigation_lab/tests -v
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
