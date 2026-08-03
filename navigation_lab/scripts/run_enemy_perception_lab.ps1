param(
  [string]$WindowTitle = "Shinobi Story Online",
  [string]$Profile = "default",
  [string]$RegionId = "mapping_input_calibration",
  [double]$CaptureInterval = 0.20,
  [double]$AutoThreshold = 0.95,
  [double]$ReviewThreshold = 0.90,
  [double]$GroupingThreshold = 0.965,
  [int]$OverlayPixelThreshold = 24,
  [double]$MinChangedPixelRatio = 0.03,
  [int]$MinComponentArea = 12,
  [int]$TrackTtlFrames = 10,
  [switch]$DebugFrames,
  [switch]$KeepWindowVisible,
  [string]$SessionName,
  [int]$MaxFrames = 0,
  [double]$MaxSessionMinutes = 0
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

$arguments = @(
  "-m", "navigation_lab.enemy_perception.runtime",
  "--window-title", $WindowTitle,
  "--profile", $Profile,
  "--region-id", $RegionId,
  "--capture-interval", $CaptureInterval,
  "--auto-threshold", $AutoThreshold,
  "--review-threshold", $ReviewThreshold,
  "--grouping-threshold", $GroupingThreshold,
  "--overlay-pixel-threshold", $OverlayPixelThreshold,
  "--min-changed-pixel-ratio", $MinChangedPixelRatio,
  "--min-component-area", $MinComponentArea,
  "--track-ttl-frames", $TrackTtlFrames
)
if ($DebugFrames) { $arguments += "--debug-frames" }
if ($KeepWindowVisible) { $arguments += "--keep-window-visible" }
if ($SessionName) { $arguments += @("--session-name", $SessionName) }
if ($MaxFrames -gt 0) { $arguments += @("--max-frames", $MaxFrames) }
if ($MaxSessionMinutes -gt 0) { $arguments += @("--max-session-minutes", $MaxSessionMinutes) }

python @arguments
exit $LASTEXITCODE
