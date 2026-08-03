[CmdletBinding()]
param(
  [string]$WindowTitle = "Shinobi Story Online",
  [string]$Profile = "default",
  [string]$RegionId = "mapping_input_calibration",
  [double]$CaptureInterval = 0.20,
  [double]$AutoThreshold = 0.95,
  [double]$ReviewThreshold = 0.90,
  [double]$GroupingThreshold = 0.965,
  [ValidateSet("Auto", "Visual", "Fallback")][string]$PlayerAnchorMode = "Auto",
  [int]$PlayerTemporalTtlFrames = 10,
  [int]$PlayerAnchorColumn = -1,
  [int]$PlayerAnchorRow = -1,
  [double]$SemanticEntityThreshold = 0.90,
  [double]$BackgroundStrongThreshold = 0.95,
  [double]$BackgroundUsableThreshold = 0.88,
  [double]$BackgroundDiagnosticThreshold = 0.70,
  [double]$MaxBackgroundChangedRatio = 0.65,
  [double]$MaxBackgroundMeanDifference = 55.0,
  [int]$SceneConsensusMinCells = 8,
  [int]$SceneConsensusFrames = 4,
  [double]$SceneConsensusSimilarity = 0.94,
  [double]$PlayfieldBottomRatio = 0.75,
  [int]$InterestRadiusCells = 4,
  [int]$ProcessingRadiusCells = 5,
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
  [ValidateSet("Full", "Balanced", "Off")][string]$DebugMode = "Balanced",
  [int]$DebugStride = 5,
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
if ($DebugFrames) { $DebugMode = "Full" }
if ($NoDebugFrames) { $DebugMode = "Off" }

$DebugRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile\enemy_perception_debug"
$EnemyRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile\enemy_perception\$RegionId"
Write-Host "[Enemy Perception Lab] Python: $Python" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Player: $PlayerAnchorMode; temporal TTL=$PlayerTemporalTtlFrames" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Semantic NPC threshold: $SemanticEntityThreshold" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Background levels: strong=$BackgroundStrongThreshold usable=$BackgroundUsableThreshold diagnostic=$BackgroundDiagnosticThreshold" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] ROI: tracking D<=$InterestRadiusCells; processing D<=$ProcessingRadiusCells" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Debug: $DebugMode; stride=$DebugStride; root=$DebugRoot" -ForegroundColor Cyan
if ($ResetBackgroundReferences) { Write-Host "[Enemy Perception Lab] RESET backgrounds: $(Join-Path $EnemyRoot 'backgrounds')" -ForegroundColor Yellow }
if ($ResetUnknownEntityKnowledge) { Write-Host "[Enemy Perception Lab] RESET unknown entities" -ForegroundColor Yellow }

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
  "--player-anchor-mode", $PlayerAnchorMode,
  "--player-temporal-ttl-frames", $PlayerTemporalTtlFrames,
  "--semantic-entity-threshold", $SemanticEntityThreshold,
  "--background-strong-threshold", $BackgroundStrongThreshold,
  "--background-usable-threshold", $BackgroundUsableThreshold,
  "--background-diagnostic-threshold", $BackgroundDiagnosticThreshold,
  "--max-background-changed-ratio", $MaxBackgroundChangedRatio,
  "--max-background-mean-difference", $MaxBackgroundMeanDifference,
  "--scene-consensus-min-cells", $SceneConsensusMinCells,
  "--scene-consensus-frames", $SceneConsensusFrames,
  "--scene-consensus-similarity", $SceneConsensusSimilarity,
  "--playfield-bottom-ratio", $PlayfieldBottomRatio,
  "--interest-radius-cells", $InterestRadiusCells,
  "--processing-radius-cells", $ProcessingRadiusCells,
  "--overlay-pixel-threshold", $OverlayPixelThreshold,
  "--min-changed-pixel-ratio", $MinChangedPixelRatio,
  "--min-component-area", $MinComponentArea,
  "--max-entity-covered-cells", $MaxEntityCoveredCells,
  "--max-entity-width-cells", $MaxEntityWidthCells,
  "--max-entity-height-cells", $MaxEntityHeightCells,
  "--max-entity-pixel-area", $MaxEntityPixelArea,
  "--max-entity-aspect-ratio", $MaxEntityAspectRatio,
  "--track-ttl-frames", $TrackTtlFrames,
  "--debug-mode", $DebugMode,
  "--debug-stride", $DebugStride
)
if ($PlayerAnchorColumn -ge 0) { $Arguments += @("--player-anchor-column", $PlayerAnchorColumn) }
if ($PlayerAnchorRow -ge 0) { $Arguments += @("--player-anchor-row", $PlayerAnchorRow) }
if ($ResetBackgroundReferences) { $Arguments += "--reset-background-references" }
if ($ResetUnknownEntityKnowledge) { $Arguments += "--reset-unknown-entity-knowledge" }
if ($KeepWindowVisible) { $Arguments += "--keep-window-visible" }
if ($SessionName) { $Arguments += @("--session-name", $SessionName) }
if ($MaxFrames -gt 0) { $Arguments += @("--max-frames", $MaxFrames) }
if ($MaxSessionMinutes -gt 0) { $Arguments += @("--max-session-minutes", $MaxSessionMinutes) }

& $Python @Arguments
$ExitCode = $LASTEXITCODE
if ($DebugMode -ne "Off") {
  Write-Host "[Enemy Perception Lab] Sessions: $DebugRoot" -ForegroundColor Green
  if ($SessionName) { Write-Host "[Enemy Perception Lab] This session: $(Join-Path $DebugRoot $SessionName)" -ForegroundColor Green }
}
exit $ExitCode
