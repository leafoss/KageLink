[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Venv = Join-Path $RepoRoot ".venv-navigation"

Write-Host "[Navigation Lab] Repository: $RepoRoot"
& $Python --version
if (-not (Test-Path $Venv)) {
    & $Python -m venv $Venv
}
$VenvPython = Join-Path $Venv "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m compileall -q (Join-Path $RepoRoot "navigation_lab")
& $VenvPython -m unittest discover -s (Join-Path $RepoRoot "navigation_lab\tests") -v
Write-Host "[Navigation Lab] Setup complete."
