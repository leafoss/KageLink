[CmdletBinding()]
param(
    [string]$WindowTitle = "Shinobi Story Online",
    [string]$RegionId = "mapping_input_calibration",
    [string]$Profile = "default"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Navigation virtual environment not found. Run setup_navigation.ps1 first."
}

Set-Location $RepoRoot
& $Python -m navigation_lab `
    --mode grid-calibration `
    --window-title $WindowTitle `
    --region-id $RegionId `
    --profile $Profile `
    --language pt-BR
exit $LASTEXITCODE
