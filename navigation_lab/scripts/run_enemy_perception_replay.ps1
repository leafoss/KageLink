[CmdletBinding(DefaultParameterSetName="Zip")]
param(
  [Parameter(Mandatory=$true, ParameterSetName="Zip")][string]$InputZip,
  [Parameter(Mandatory=$true, ParameterSetName="Session")][string]$InputSession,
  [string]$Profile = "default",
  [string]$RegionId = "mapping_input_calibration",
  [string]$OutputSession = "enemy_detection_replay_fix_01",
  [ValidateSet("Auto", "Visual", "Fallback")][string]$PlayerAnchorMode = "Auto",
  [double]$SemanticEntityThreshold = 0.90,
  [double]$BackgroundStrongThreshold = 0.95,
  [double]$BackgroundUsableThreshold = 0.88,
  [double]$BackgroundDiagnosticThreshold = 0.70,
  [int]$InterestRadiusCells = 4,
  [ValidateSet("Full", "Balanced", "Off")][string]$DebugMode = "Balanced",
  [int]$DebugStride = 5
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  throw "Navigation virtual environment not found. Run .\navigation_lab\scripts\setup_navigation.ps1 first."
}
Set-Location $RepoRoot
$Arguments = @(
  "-m", "navigation_lab.enemy_perception.replay",
  "--profile", $Profile,
  "--region-id", $RegionId,
  "--output-session", $OutputSession,
  "--player-anchor-mode", $PlayerAnchorMode,
  "--semantic-entity-threshold", $SemanticEntityThreshold,
  "--background-strong-threshold", $BackgroundStrongThreshold,
  "--background-usable-threshold", $BackgroundUsableThreshold,
  "--background-diagnostic-threshold", $BackgroundDiagnosticThreshold,
  "--interest-radius-cells", $InterestRadiusCells,
  "--debug-mode", $DebugMode,
  "--debug-stride", $DebugStride
)
if ($PSCmdlet.ParameterSetName -eq "Zip") {
  $Arguments += @("--input-zip", (Resolve-Path $InputZip).Path)
} else {
  $Arguments += @("--input-session", (Resolve-Path $InputSession).Path)
}
Write-Host "[Enemy Perception Replay] Python: $Python" -ForegroundColor Cyan
Write-Host "[Enemy Perception Replay] Output session: $OutputSession" -ForegroundColor Cyan
& $Python @Arguments
exit $LASTEXITCODE
