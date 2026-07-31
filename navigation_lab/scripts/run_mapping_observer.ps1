[CmdletBinding()]
param(
    [string]$WindowTitle = "Shinobi Story Online",
    [string]$RegionId = "mapping_calibration",
    [ValidateRange(1, 512)]
    [int]$TileSize = 64,
    [ValidateRange(1, 30)]
    [double]$Fps = 12,
    [ValidateSet("following", "hybrid", "fixed")]
    [string]$CameraMode = "following",
    [ValidateSet("input", "continuous")]
    [string]$MappingStrategy = "input",
    [string]$Profile = "default",
    [ValidateRange(0.01, 1.0)]
    [double]$MotionConfidence = 0.18,
    [ValidateRange(0.10, 3.0)]
    [double]$CommandTimeout = 0.70,
    [ValidateRange(0.25, 64.0)]
    [double]$MinCommandShift = 2.0,
    [switch]$InvertX,
    [switch]$InvertY,
    [switch]$NewMap,
    [switch]$NoAutoStart,
    [switch]$KeepWindowVisible
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Navigation virtual environment not found. Run setup_navigation.ps1 first."
}

$Arguments = @(
    "-m", "navigation_lab",
    "--mode", "observer",
    "--debug-window",
    "--window-title", $WindowTitle,
    "--region-id", $RegionId,
    "--tile-size", $TileSize,
    "--fps", $Fps,
    "--camera-mode", $CameraMode,
    "--mapping-strategy", $MappingStrategy,
    "--profile", $Profile,
    "--motion-confidence", $MotionConfidence,
    "--command-timeout", $CommandTimeout,
    "--min-command-shift", $MinCommandShift,
    "--language", "pt-BR"
)
if ($InvertX) { $Arguments += "--invert-x" }
if ($InvertY) { $Arguments += "--invert-y" }
if ($NewMap) { $Arguments += "--new-map" }
if ($NoAutoStart) { $Arguments += "--no-auto-start" }
if ($KeepWindowVisible) { $Arguments += "--keep-window-visible" }

Set-Location $RepoRoot
& $Python @Arguments
exit $LASTEXITCODE
