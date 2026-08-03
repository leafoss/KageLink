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
    [int]$RoiRadiusCells = 4,
    [double]$NewCandidateCellRatio = 0.12,
    [double]$TrackedCandidateKeepRatio = 0.04,
    [double]$SelfAcquireThreshold = 0.40,
    [double]$SelfKeepThreshold = 0.28,
    [double]$StationaryCameraMaxShiftPixels = 2.0,
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

if (-not (Test-Path $PcAgentRoot)) { throw "Full KageLink checkout required. Missing: $PcAgentRoot" }
if ($ControlEnabled -or $FaceOnly -or $AcknowledgePhysicalRisk) { throw "PR27_9_PHYSICAL_DISABLED_PENDING_PERCEPTION_ACCEPTANCE" }
if ($Rounds -ne 1) { throw "PR27_9_ONE_PERCEPTION_ROUND_ONLY" }
if ($RoiRadiusCells -ne 4) { throw "PR27.9 fixed ROI is exactly four native cells." }
if ([Math]::Abs($NewCandidateCellRatio - 0.12) -gt 0.0001) { throw "PR27.9 audited new-candidate gate is 0.12." }
if ([Math]::Abs($TrackedCandidateKeepRatio - 0.04) -gt 0.0001) { throw "PR27.9 audited tracked-candidate keep ratio is 0.04." }
if ([Math]::Abs($SelfAcquireThreshold - 0.40) -gt 0.0001) { throw "PR27.9 SELF acquire threshold is 0.40." }
if ([Math]::Abs($SelfKeepThreshold - 0.28) -gt 0.0001) { throw "PR27.9 SELF keep threshold is 0.28." }
if ([Math]::Abs($StationaryCameraMaxShiftPixels - 2.0) -gt 0.0001) { throw "PR27.9 stationary camera limit is 2 px." }
if ($DebugSaveEveryFrames -lt 1) { throw "DebugSaveEveryFrames must be >= 1." }
if ($DebugQueueSize -lt 4) { throw "DebugQueueSize must be >= 4." }
if ($LogEveryFrames -lt 1) { throw "LogEveryFrames must be >= 1." }
if ($TargetFps -lt 1 -or $TargetFps -gt 12) { throw "TargetFps must be between 1 and 12." }

$env:PYTHONPATH = (@($Root, $PcAgentRoot) -join [IO.Path]::PathSeparator)
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $Python) { throw "Python 3 was not found. Install Python or add it to PATH." }

$LogRoot = Join-Path $PcAgentRoot "kage_pilot_loop_logs"
$PreSpawnFile = Join-Path $LogRoot "pr27_9_pre_spawn_scene.png"
$TrainerIdentityFile = Join-Path $LogRoot "pr27_9_trainer_pre_click.png"
$SaveFrames = -not $NoDebugFrames.IsPresent
if ($SaveDebugFrames) { $SaveFrames = $true }

$env:KAGE_PR27_CONTROL_MODE = "PERCEPTION_ONLY"
$env:KAGE_PR27_ALLOW_CONTROL = "0"
$env:KAGE_PR278_SAVE_DEBUG_FRAMES = if ($SaveFrames) { "1" } else { "0" }
$env:KAGE_PR278_SAVE_EVERY_FRAMES = [string]$DebugSaveEveryFrames
$env:KAGE_PR278_DEBUG_QUEUE_SIZE = [string]$DebugQueueSize
$env:KAGE_PR278_TARGET_FPS = [string]::Format([Globalization.CultureInfo]::InvariantCulture, "{0:0.00}", $TargetFps)
$env:KAGE_PR278_PRE_SPAWN_FILE = $PreSpawnFile
$env:KAGE_PR279_TRAINER_IDENTITY_SCENE = $TrainerIdentityFile

Write-Host "PR27.9 NOISE-AWARE OBJECT PERCEPTION" -ForegroundColor Green
Write-Host "  Mode: PERCEPTION_ONLY" -ForegroundColor Cyan
Write-Host "  PHYSICAL INPUT: DISABLED (no R, H, arrows, chase, turn or separation)" -ForegroundColor Yellow
Write-Host "  Native grid: 1920x1037 | 64x64 | offset=(0,21)"
Write-Host "  Fixed SELF: row=6 column=15 | bbox=[960,405,1024,469)"
Write-Host "  New-object gate: 12% per cell; existing RGB tracks may override"
Write-Host "  SELF hysteresis: acquire=0.40 keep=0.28"
Write-Host "  Stationary camera: accepted shift <= 2 px"
Write-Host "  Trainer: PRE-CLICK identity veto; entity blind pixels=0"
Write-Host "  PRE_SPAWN_SCENE: $PreSpawnFile"
Write-Host "  TRAINER_IDENTITY_SCENE: $TrainerIdentityFile"
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
