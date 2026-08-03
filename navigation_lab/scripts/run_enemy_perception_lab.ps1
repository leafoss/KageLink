[CmdletBinding()]
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

# Frame-by-frame evidence is the default for this laboratory. It can only be
# disabled explicitly with -NoDebugFrames. -DebugFrames remains accepted for
# backwards compatibility and makes the intention visible in test commands.
$DebugEnabled = -not $NoDebugFrames
if ($DebugFrames) { $DebugEnabled = $true }

$DebugRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile\enemy_perception_debug"
Write-Host "[Enemy Perception Lab] Python: $Python" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Debug enabled: $DebugEnabled" -ForegroundColor Cyan
Write-Host "[Enemy Perception Lab] Debug root: $DebugRoot" -ForegroundColor Cyan

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
  "--overlay-pixel-threshold", $OverlayPixelThreshold,
  "--min-changed-pixel-ratio", $MinChangedPixelRatio,
  "--min-component-area", $MinComponentArea,
  "--track-ttl-frames", $TrackTtlFrames
)
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
    $SessionPath = Join-Path $DebugRoot $SessionName
    Write-Host "[Enemy Perception Lab] This session: $SessionPath" -ForegroundColor Green
  }
}
exit $ExitCode
