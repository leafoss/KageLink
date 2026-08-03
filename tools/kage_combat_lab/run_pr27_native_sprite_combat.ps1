[CmdletBinding()]
param(
    [switch]$PerceptionOnly,
    [switch]$FaceOnly,
    [switch]$ControlEnabled,
    [switch]$AcknowledgePhysicalRisk,
    [switch]$DebugOverlay,
    [switch]$SaveDebugFrames,
    [switch]$NoDebugFrames,
    [int]$Rounds = 1,
    [double]$CombatSeconds = 120,
    [double]$PostCombatTimeout = 240,
    [double]$DialogDelay = 5,
    [double]$SpawnDelay = 5,
    [double]$TrainerSearchTimeout = 90,
    [int]$DebugSaveEveryFrames = 1,
    [int]$DebugQueueSize = 32,
    [int]$LogEveryFrames = 1,
    [double]$TargetFps = 6,

    # Legacy PR27.7 parameters are accepted so old command blocks fail safely
    # at the physical-mode gate instead of at PowerShell argument parsing.
    [int]$PixelDelta = 18,
    [double]$ChangedRatio = 0.035,
    [double]$UncertainRatio = 0.018,
    [int]$MinimumComponentArea = 28,
    [int]$MinimumFragmentPixels = 28,
    [int]$MinimumObservationPixels = 72,
    [int]$MaximumFragmentsPerGroup = 32,
    [double]$AssociationScore = 0.48,
    [double]$TargetAssociationScore = 0.40,
    [int]$EnemyConfirmFrames = 5,
    [int]$MaximumMissingFrames = 3,
    [int]$TargetMissingGraceFrames = 4,
    [int]$TargetFocusRadiusCells = 3,
    [int]$MaximumActiveTracks = 18,
    [int]$AttackDistanceCells = 1,
    [double]$HCooldown = 1.75,
    [int]$AttackConfirmFrames = 2,
    [int]$RoiRadiusCells = 4,
    [int]$LocalOcclusionMinimumCells = 10,
    [int]$LocalOcclusionRowSpan = 6,
    [int]$LocalOcclusionMaximumFrames = 6,
    [int]$LocalBackgroundLearnFrames = 5,
    [int]$FacingConfirmFrames = 2,
    [int]$FacingCooldownFrames = 1,
    [double]$HitDisplacementPixels = 10,
    [double]$SelfAssociationScore = 0.56,
    [double]$SelfIdentityScore = 0.34,
    [double]$SelfSizeRatio = 0.48,
    [double]$SelfAmbiguityMargin = 0.08,
    [int]$SelfPredictionFrames = 10,
    [double]$MergedBodyIou = 0.08,
    [double]$MergedBodyAreaRatio = 1.28,
    [double]$MergedAnchorPixels = 12,
    [double]$SubcellDirectionPixels = 4,
    [double]$CloseEnemyPixels = 96,
    [int]$CloseReacquireFrames = 2,
    [int]$CloseIdleSoftFrames = 3,
    [int]$CloseIdleTurnFrames = 5,
    [int]$CloseIdleDropFrames = 8,
    [int]$SeparationPulseMs = 60,
    [int]$SeparationCooldownFrames = 6,
    [double]$FacingTemplateScore = 0.72,
    [double]$FacingTemplateMargin = 0.04,
    [double]$FacingMotionPixels = 3,
    [double]$HitAppearanceSimilarity = 0.60,
    [int]$OverlayEveryFrames = 3
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $Root "..\..")).Path
$PcAgentRoot = Join-Path $RepoRoot "KageLink Installer\pc_agent"

if (-not (Test-Path $PcAgentRoot)) {
    throw "Full KageLink checkout required. Missing: $PcAgentRoot"
}

if ($ControlEnabled -or $FaceOnly -or $AcknowledgePhysicalRisk) {
    throw "PR27_8_PHYSICAL_DISABLED_PENDING_PERCEPTION_ACCEPTANCE"
}

if ($Rounds -ne 1) {
    throw "PR27_8_ONE_PERCEPTION_ROUND_ONLY"
}

if ($RoiRadiusCells -ne 4) {
    throw "PR27.8 fixed combat ROI is exactly four native cells."
}
if ($DebugSaveEveryFrames -lt 1) { throw "DebugSaveEveryFrames must be >= 1." }
if ($DebugQueueSize -lt 4) { throw "DebugQueueSize must be >= 4." }
if ($LogEveryFrames -lt 1) { throw "LogEveryFrames must be >= 1." }
if ($TargetFps -lt 1 -or $TargetFps -gt 12) { throw "TargetFps must be between 1 and 12." }

$env:PYTHONPATH = (@($Root, $PcAgentRoot) -join [IO.Path]::PathSeparator)
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $Python) { throw "Python 3 was not found. Install Python or add it to PATH." }

$LogRoot = (Join-Path $PcAgentRoot "kage_pilot_loop_logs")
$PreSpawnFile = (Join-Path $LogRoot "pr27_8_pre_spawn_scene.png")
$SaveFrames = -not $NoDebugFrames.IsPresent
if ($SaveDebugFrames) { $SaveFrames = $true }

$env:KAGE_PR27_CONTROL_MODE = "PERCEPTION_ONLY"
$env:KAGE_PR27_ALLOW_CONTROL = "0"
$env:KAGE_PR278_SAVE_DEBUG_FRAMES = if ($SaveFrames) { "1" } else { "0" }
$env:KAGE_PR278_SAVE_EVERY_FRAMES = [string]$DebugSaveEveryFrames
$env:KAGE_PR278_DEBUG_QUEUE_SIZE = [string]$DebugQueueSize
$env:KAGE_PR278_TARGET_FPS = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0:0.00}",
    $TargetFps
)
$env:KAGE_PR278_PRE_SPAWN_FILE = $PreSpawnFile

Write-Host "PR27.8 FIXED SELF CELL PERCEPTION" -ForegroundColor Green
Write-Host "  Mode: PERCEPTION_ONLY" -ForegroundColor Cyan
Write-Host "  PHYSICAL INPUT: DISABLED (no R, H, arrows, chase, turn or separation)" -ForegroundColor Yellow
Write-Host "  Native calibration: 1920x1037"
Write-Host "  Grid: 64x64 | offset X=0 Y=21"
Write-Host "  Fixed SELF cell: absolute row=6 column=15 | relative=(0,0)"
Write-Host "  Fixed SELF bbox: [960,405,1024,469)"
Write-Host "  ROI: circular radius 4; it never follows SELF or ENEMY"
Write-Host "  Trainer: dynamic perception mask only; captured RGB is never replaced"
Write-Host "  Hostility: movement alone cannot create ENEMY"
Write-Host "  PRE_SPAWN_SCENE: $PreSpawnFile"
Write-Host "  Debug frames: $SaveFrames every $DebugSaveEveryFrames frames"
Write-Host "  F12: stop remains available" -ForegroundColor Yellow

$Arguments = @(
    "-m", "kage_combat_lab.full_loop_pr27_8",
    "--rounds", "$([Math]::Max(1, $Rounds))",
    "--combat-seconds", "$([Math]::Max(10, $CombatSeconds))",
    "--post-combat-timeout", "$([Math]::Max(30, $PostCombatTimeout))",
    "--dialog-delay", "$([Math]::Max(0, $DialogDelay))",
    "--spawn-delay", "$([Math]::Max(1, $SpawnDelay))",
    "--trainer-search-timeout", "$([Math]::Max(10, $TrainerSearchTimeout))"
)

Push-Location $PcAgentRoot
try {
    & $Python.Source @Arguments
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $ExitCode
