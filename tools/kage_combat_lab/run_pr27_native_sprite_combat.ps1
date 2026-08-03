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
    [int]$OverlayEveryFrames = 3,
    [int]$DebugSaveEveryFrames = 6,
    [int]$DebugQueueSize = 24,
    [int]$LogEveryFrames = 1,
    [double]$TargetFps = 8
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $Root "..\..")).Path
$PcAgentRoot = Join-Path $RepoRoot "KageLink Installer\pc_agent"

if (-not (Test-Path $PcAgentRoot)) { throw "Full KageLink checkout required. Missing: $PcAgentRoot" }
$env:PYTHONPATH = (@($Root, $PcAgentRoot) -join [IO.Path]::PathSeparator)
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $Python) { throw "Python 3 was not found. Install Python or add it to PATH." }

$SelectedModeCount = @(@($PerceptionOnly.IsPresent, $FaceOnly.IsPresent, $ControlEnabled.IsPresent) | Where-Object { $_ }).Count
if ($SelectedModeCount -gt 1) { throw "Choose only one mode: -PerceptionOnly, -FaceOnly or -ControlEnabled." }
if ($ControlEnabled -and -not $AcknowledgePhysicalRisk) {
    throw "CONTROL_ENABLED requires -AcknowledgePhysicalRisk and direct supervision with F12 ready."
}
$ControlMode = if ($ControlEnabled) { "CONTROL_ENABLED" } elseif ($FaceOnly) { "FACE_ONLY" } else { "PERCEPTION_ONLY" }

if ($PixelDelta -lt 1) { throw "PixelDelta must be >= 1." }
if ($ChangedRatio -le 0 -or $ChangedRatio -gt 1) { throw "ChangedRatio must be in (0, 1]." }
if ($UncertainRatio -lt 0 -or $UncertainRatio -gt $ChangedRatio) { throw "UncertainRatio must be >= 0 and <= ChangedRatio." }
if ($MinimumComponentArea -lt 1) { throw "MinimumComponentArea must be >= 1." }
if ($MinimumFragmentPixels -lt $MinimumComponentArea) { throw "MinimumFragmentPixels must be >= MinimumComponentArea." }
if ($MinimumObservationPixels -lt $MinimumFragmentPixels) { throw "MinimumObservationPixels must be >= MinimumFragmentPixels." }
if ($EnemyConfirmFrames -lt 3) { throw "EnemyConfirmFrames must be >= 3." }
if ($TargetMissingGraceFrames -lt $MaximumMissingFrames) { throw "TargetMissingGraceFrames must be >= MaximumMissingFrames." }
if ($HCooldown -lt 0.5) { throw "HCooldown must be >= 0.5 seconds." }
if ($AttackConfirmFrames -lt 2) { throw "AttackConfirmFrames must be >= 2." }
if ($RoiRadiusCells -ne 4) { throw "PR27.7 combat ROI is fixed at exactly 4 native cells." }
if ($FacingConfirmFrames -lt 2) { throw "FacingConfirmFrames must be >= 2." }
if ($SelfPredictionFrames -lt 2) { throw "SelfPredictionFrames must be >= 2." }
if ($CloseReacquireFrames -lt 1) { throw "CloseReacquireFrames must be >= 1." }
if ($CloseIdleTurnFrames -lt $CloseIdleSoftFrames) { throw "CloseIdleTurnFrames must be >= CloseIdleSoftFrames." }
if ($CloseIdleDropFrames -le $CloseIdleTurnFrames) { throw "CloseIdleDropFrames must be greater than CloseIdleTurnFrames." }
if ($SeparationPulseMs -lt 30 -or $SeparationPulseMs -gt 100) { throw "SeparationPulseMs must be between 30 and 100." }
if ($DebugSaveEveryFrames -lt 1) { throw "DebugSaveEveryFrames must be >= 1." }
if ($DebugQueueSize -lt 2) { throw "DebugQueueSize must be >= 2." }
if ($LogEveryFrames -lt 1) { throw "LogEveryFrames must be >= 1." }
if ($TargetFps -lt 1 -or $TargetFps -gt 20) { throw "TargetFps must be between 1 and 20." }

function Set-InvariantDoubleEnv([string]$Name, [double]$Value) {
    [Environment]::SetEnvironmentVariable(
        $Name,
        [string]::Format([Globalization.CultureInfo]::InvariantCulture, "{0:0.0000}", $Value),
        "Process"
    )
}

$BaselineFile = Join-Path $Root "kage_pilot_loop_logs\pr27_native_baseline.npz"
$SpriteRoot = Join-Path $Root "data\pr27_sprites"
$SaveFrames = $SaveDebugFrames.IsPresent -and -not $NoDebugFrames.IsPresent
$PhysicalMode = $ControlMode -in @("FACE_ONLY", "CONTROL_ENABLED")

$env:KAGE_PR27_CONTROL_MODE = $ControlMode
$env:KAGE_PR27_ALLOW_CONTROL = if ($ControlEnabled -and $AcknowledgePhysicalRisk) { "1" } else { "0" }
$env:KAGE_PR27_NATIVE_BASELINE_FILE = $BaselineFile
$env:KAGE_PR27_SPRITE_ROOT = $SpriteRoot
$env:KAGE_PR27_DEBUG_OVERLAY = if ($DebugOverlay) { "1" } else { "0" }
$env:KAGE_PR27_SAVE_DEBUG_FRAMES = if ($SaveFrames) { "1" } else { "0" }
$env:KAGE_PR27_PIXEL_DELTA = [string]$PixelDelta
$env:KAGE_PR27_MIN_COMPONENT_AREA = [string]$MinimumComponentArea
$env:KAGE_PR27_MIN_FRAGMENT_PIXELS = [string]$MinimumFragmentPixels
$env:KAGE_PR27_MIN_OBSERVATION_PIXELS = [string]$MinimumObservationPixels
$env:KAGE_PR27_MAX_FRAGMENTS_PER_GROUP = [string]$MaximumFragmentsPerGroup
$env:KAGE_PR27_ENEMY_CONFIRM_FRAMES = [string]$EnemyConfirmFrames
$env:KAGE_PR27_MAX_MISSING_FRAMES = [string]$MaximumMissingFrames
$env:KAGE_PR27_TARGET_MISSING_GRACE = [string]$TargetMissingGraceFrames
$env:KAGE_PR27_TARGET_FOCUS_RADIUS = [string]$TargetFocusRadiusCells
$env:KAGE_PR27_MAX_ACTIVE_TRACKS = [string]$MaximumActiveTracks
$env:KAGE_PR27_ATTACK_DISTANCE = [string]$AttackDistanceCells
$env:KAGE_PR27_ATTACK_CONFIRM_FRAMES = [string]$AttackConfirmFrames
$env:KAGE_PR27_ROI_RADIUS_CELLS = [string]$RoiRadiusCells
$env:KAGE_PR27_LOCAL_OCCLUSION_MIN_CELLS = [string]$LocalOcclusionMinimumCells
$env:KAGE_PR27_LOCAL_OCCLUSION_ROW_SPAN = [string]$LocalOcclusionRowSpan
$env:KAGE_PR27_LOCAL_OCCLUSION_MAX_FRAMES = [string]$LocalOcclusionMaximumFrames
$env:KAGE_PR27_LOCAL_BACKGROUND_LEARN_FRAMES = [string]$LocalBackgroundLearnFrames
$env:KAGE_PR27_FACING_CONFIRM_FRAMES = [string]$FacingConfirmFrames
$env:KAGE_PR27_FACING_COOLDOWN_FRAMES = [string]$FacingCooldownFrames
$env:KAGE_PR27_SELF_PREDICTION_FRAMES = [string]$SelfPredictionFrames
$env:KAGE_PR27_CLOSE_REACQUIRE_FRAMES = [string]$CloseReacquireFrames
$env:KAGE_PR27_CLOSE_IDLE_SOFT_FRAMES = [string]$CloseIdleSoftFrames
$env:KAGE_PR27_CLOSE_IDLE_TURN_FRAMES = [string]$CloseIdleTurnFrames
$env:KAGE_PR27_CLOSE_IDLE_DROP_FRAMES = [string]$CloseIdleDropFrames
$env:KAGE_PR27_SEPARATION_PULSE_MS = [string]$SeparationPulseMs
$env:KAGE_PR27_SEPARATION_COOLDOWN_FRAMES = [string]$SeparationCooldownFrames
$env:KAGE_PR27_OVERLAY_EVERY_FRAMES = [string]$OverlayEveryFrames
$env:KAGE_PR27_SAVE_EVERY_FRAMES = [string]$DebugSaveEveryFrames
$env:KAGE_PR27_DEBUG_QUEUE_SIZE = [string]$DebugQueueSize
$env:KAGE_PR27_LOG_EVERY_FRAMES = [string]$LogEveryFrames
Set-InvariantDoubleEnv "KAGE_PR27_CHANGED_RATIO" $ChangedRatio
Set-InvariantDoubleEnv "KAGE_PR27_UNCERTAIN_RATIO" $UncertainRatio
Set-InvariantDoubleEnv "KAGE_PR27_ASSOCIATION_SCORE" $AssociationScore
Set-InvariantDoubleEnv "KAGE_PR27_TARGET_ASSOCIATION_SCORE" $TargetAssociationScore
Set-InvariantDoubleEnv "KAGE_PR27_H_COOLDOWN" $HCooldown
Set-InvariantDoubleEnv "KAGE_PR27_HIT_DISPLACEMENT_PX" $HitDisplacementPixels
Set-InvariantDoubleEnv "KAGE_PR27_SELF_ASSOCIATION_SCORE" $SelfAssociationScore
Set-InvariantDoubleEnv "KAGE_PR27_SELF_IDENTITY_SCORE" $SelfIdentityScore
Set-InvariantDoubleEnv "KAGE_PR27_SELF_SIZE_RATIO" $SelfSizeRatio
Set-InvariantDoubleEnv "KAGE_PR27_SELF_AMBIGUITY_MARGIN" $SelfAmbiguityMargin
Set-InvariantDoubleEnv "KAGE_PR27_MERGED_IOU" $MergedBodyIou
Set-InvariantDoubleEnv "KAGE_PR27_MERGED_AREA_RATIO" $MergedBodyAreaRatio
Set-InvariantDoubleEnv "KAGE_PR27_MERGED_ANCHOR_PX" $MergedAnchorPixels
Set-InvariantDoubleEnv "KAGE_PR27_SUBCELL_DIRECTION_PX" $SubcellDirectionPixels
Set-InvariantDoubleEnv "KAGE_PR27_CLOSE_ENEMY_PX" $CloseEnemyPixels
Set-InvariantDoubleEnv "KAGE_PR27_FACING_TEMPLATE_SCORE" $FacingTemplateScore
Set-InvariantDoubleEnv "KAGE_PR27_FACING_TEMPLATE_MARGIN" $FacingTemplateMargin
Set-InvariantDoubleEnv "KAGE_PR27_FACING_MOTION_PX" $FacingMotionPixels
Set-InvariantDoubleEnv "KAGE_PR27_HIT_APPEARANCE_SIMILARITY" $HitAppearanceSimilarity
Set-InvariantDoubleEnv "KAGE_PR27_TARGET_FPS" $TargetFps

Write-Host "PR27.7 SELF AUTHORITY + CLOSE RECOVERY COMBAT" -ForegroundColor Green
Write-Host "  Mode: $ControlMode" -ForegroundColor Cyan
if ($ControlEnabled) {
    Write-Host "  PHYSICAL CONTROL: ENABLED BY EXPLICIT ACKNOWLEDGEMENT" -ForegroundColor Red
    Write-Host "  R: DOWN at combat start; held through every recovery; UP only at combat end" -ForegroundColor Yellow
    Write-Host "  H: blocked during role conflict, merged body, hit recovery and unknown visual facing" -ForegroundColor Yellow
    Write-Host "  F12: emergency stop; keep it ready" -ForegroundColor Yellow
}
if ($PhysicalMode -and $DebugOverlay) {
    Write-Host "  Live overlay: automatically disabled in physical modes to preserve game focus" -ForegroundColor Yellow
}
Write-Host "  SELF authority: dedicated tracker, immutable role, reserved observation"
Write-Host "  ENEMY authority: non-SELF tracker can never promote a body to SELF"
Write-Host "  Combat ROI: circular radius 4 cells (64px each), centered only on SELF"
Write-Host "  Same-cell combat: subcell anchor direction + bounded recovery"
Write-Host "  MERGED_BODY: preserves both identities; H blocked; optional separation pulse"
Write-Host "  Facing: commanded direction is only a prior; visual observation is required"
Write-Host "  SCENE_CHANGED: absent from combat flow"
Write-Host "  Async debug: ROI images by default; full frame only on conflict/state change"
Write-Host "  Target FPS: $TargetFps"
Write-Host "  Debug frames enabled: $SaveFrames every $DebugSaveEveryFrames frames"
Write-Host "  Baseline: $BaselineFile"

$Arguments = @(
    "-m", "kage_combat_lab.full_loop_pr27",
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
