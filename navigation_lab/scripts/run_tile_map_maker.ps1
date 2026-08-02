[CmdletBinding()]
param(
    [string]$WindowTitle = "Shinobi Story Online",
    [string]$RegionId = "mapping_input_calibration",
    [string]$Profile = "default",
    [ValidateRange(0.50, 1.0)]
    [double]$SimilarityThreshold = 0.92
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Navigation virtual environment not found. Run setup_navigation.ps1 first."
}

Set-Location $RepoRoot
& $Python -m navigation_lab `
    --mode tile-mapper `
    --window-title $WindowTitle `
    --region-id $RegionId `
    --profile $Profile `
    --similarity-threshold $SimilarityThreshold `
    --language pt-BR
exit $LASTEXITCODE
