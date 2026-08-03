[CmdletBinding()]
param(
  [string]$WindowTitle = "Shinobi Story Online",
  [string]$Profile = "default",
  [string]$RegionId = "mapping_input_calibration",
  [double]$CaptureInterval = 0.20,
  [double]$AutoThreshold = 0.95,
  [double]$ReviewThreshold = 0.90,
  [double]$GroupingThreshold = 0.965,
  [double]$BackgroundMatchThreshold = 0.985,
  [double]$MaxBackgroundChangedRatio = 0.65,
  [double]$MaxBackgroundMeanDifference = 55.0,
  [double]$PlayfieldBottomRatio = 0.75,
  [int]$InterestRadiusCells = 4,
  [int]$OverlayPixelThreshold = 24,
  [double]$MinChangedPixelRatio = 0.03,
  [int]$MinComponentArea = 12,
  [int]$MaxEntityCoveredCells = 9,
  [int]$MaxEntityWidthCells = 3,
  [int]$MaxEntityHeightCells = 3,
  [int]$MaxEntityPixelArea = 0,
  [double]$MaxEntityAspectRatio = 4.0,
  [int]$TrackTtlFrames = 10,
  [switch]$ResetBackgroundReferences,
  [switch]$ResetUnknownEntityKnowledge,
  [switch]$DebugFrames,
  [switch]$NoDebugFrames,
  [switch]$KeepWindowVisible,
  [string]$SessionName,
  [int]$MaxFrames = 0,
  [double]$MaxSessionMinutes = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  throw "Navigation virtual environment not found. Run .\navigation_lab\scripts\setup_navigation.ps1 first."
}

$DebugEnabled = -not $NoDebugFrames
if ($DebugFrames) { $DebugEnabled = $true }

$DebugRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile\enemy_perception_debug"
$EnemyRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile\enemy_perception\$RegionId"
Write-Host "[Enemy Perception Lab] Python: $Python" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Debug enabled: $DebugEnabled" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Debug root: $DebugRoot" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Visual background catalogue: $(Join-Path $EnemyRoot 'backgrounds')" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] ROI: Manhattan D<=$InterestRadiusCells; processing margin D<=$($InterestRadiusCells + 1)" -ForegroundColor Cyan
if ($ResetBackgroundReferences) {
  Write-Host "[Enemy Perception Lab] RESET requested: $(Join-Path $EnemyRoot 'backgrounds')" -ForegroundColor Yellow
}
if ($ResetUnknownEntityKnowledge) {
  Write-Host "[Enemy Perception Lab] RESET unknown groups: $(Join-Path $EnemyRoot 'entities\unknown')" -ForegroundColor Yellow
}

Set-Location $RepoRoot
$Arguments = @(
  "-m", "navigation_lab.enemy_perception.runtime",
  "--window-title", $WindowTitle,
  "--profile", $Profile,
  "--region-id", $RegionId,
  "--capture-interval", $CaptureInterval,
  "--auto-threshold", $AutoThreshold,
  "--review-threshold", $ReviewThreshold,
  "--grouping-threshold", $GroupingThreshold,
  "--background-match-threshold", $BackgroundMatchThreshold,
  "--max-background-changed-ratio", $MaxBackgroundChangedRatio,
  "--max-background-mean-difference", $MaxBackgroundMeanDifference,
  "--playfield-bottom-ratio", $PlayfieldBottomRatio,
  "--interest-radius-cells", $InterestRadiusCells,
  "--overlay-pixel-threshold", $OverlayPixelThreshold,
  "--min-changed-pixel-ratio", $MinChangedPixelRatio,
  "--min-component-area", $MinComponentArea,
  "--max-entity-covered-cells", $MaxEntityCoveredCells,
  "--max-entity-width-cells", $MaxEntityWidthCells,
  "--max-entity-height-cells", $MaxEntityHeightCells,
  "--max-entity-pixel-area", $MaxEntityPixelArea,
  "--max-entity-aspect-ratio", $MaxEntityAspectRatio,
  "--track-ttl-frames", $TrackTtlFrames
)
if ($ResetBackgroundReferences) { $Arguments += "--reset-background-references" }
if ($ResetUnknownEntityKnowledge) { $Arguments += "--reset-unknown-entity-knowledge" }
if ($DebugEnabled) { $Arguments += "--debug-frames" }
if ($KeepWindowVisible) { $Arguments += "--keep-window-visible" }
if ($SessionName) { $Arguments += @("--session-name", $SessionName) }
if ($MaxFrames -gt 0) { $Arguments += @("--max-frames", $MaxFrames) }
if ($MaxSessionMinutes -gt 0) { $Arguments += @("--max-session-minutes", $MaxSessionMinutes) }

& $Python @Arguments
$ExitCode = $LASTEXITCODE

if ($DebugEnabled) {
  Write-Host "[Enemy Perception Lab] Sessions: $DebugRoot" -ForegroundColor Green
  if ($SessionName) {
    Write-Host "[Enemy Perception Lab] This session: $(Join-Path $DebugRoot $SessionName)" -ForegroundColor Green
  }
}
exit $ExitCode
