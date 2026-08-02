[CmdletBinding()]
param(
    [string]$WindowTitle = "Shinobi Story Online",
    [string]$RegionId = "mapping_input_calibration",
    [string]$Profile = "default",
    [ValidateRange(0.20, 10.0)]
    [double]$CaptureInterval = 0.75,
    [ValidateRange(0.50, 1.0)]
    [double]$AutoThreshold = 0.95,
    [ValidateRange(0.50, 1.0)]
    [double]$ReviewThreshold = 0.90,
    [ValidateRange(0.50, 1.0)]
    [double]$GroupingThreshold = 0.965,
    [switch]$NewMap,
    [switch]$KeepWindowVisible
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Navigation virtual environment not found. Run setup_navigation.ps1 first."
}
if ($ReviewThreshold -gt $AutoThreshold) {
    throw "ReviewThreshold cannot be greater than AutoThreshold."
}

$Arguments = @(
    "-m", "navigation_lab",
    "--mode", "continuous-mapper",
    "--window-title", $WindowTitle,
    "--region-id", $RegionId,
    "--profile", $Profile,
    "--capture-interval", $CaptureInterval,
    "--auto-threshold", $AutoThreshold,
    "--review-threshold", $ReviewThreshold,
    "--grouping-threshold", $GroupingThreshold,
    "--language", "pt-BR"
)
if ($NewMap) {
    $Arguments += "--new-map"
}
if ($KeepWindowVisible) {
    $Arguments += "--keep-window-visible"
}

Set-Location $RepoRoot
& $Python @Arguments
exit $LASTEXITCODE
