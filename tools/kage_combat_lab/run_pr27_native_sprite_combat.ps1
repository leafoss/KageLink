[CmdletBinding()]
param(
    [switch]$PerceptionOnly,
    [switch]$FaceOnly,
    [switch]$ControlEnabled,
    [switch]$DebugOverlay,
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
    [int]$MinimumComponentArea = 14,
    [double]$AssociationScore = 0.48,
    [int]$EnemyConfirmFrames = 3,
    [int]$MaximumMissingFrames = 3,
    [int]$AttackDistanceCells = 1,
    [double]$SceneChangedRatio = 0.42,
    [int]$SceneChangedMinimumCells = 8
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $Root "..\..")).Path
$PcAgentRoot = Join-Path $RepoRoot "KageLink Installer\pc_agent"

if (-not (Test-Path $PcAgentRoot)) {
    throw "Full KageLink checkout required. Missing: $PcAgentRoot"
}

$PythonPaths = @($Root, $PcAgentRoot)
$env:PYTHONPATH = ($PythonPaths -join [IO.Path]::PathSeparator)

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "Python 3 was not found. Install Python or add it to PATH."
}

$SelectedModeCount = @(
    @($PerceptionOnly.IsPresent, $FaceOnly.IsPresent, $ControlEnabled.IsPresent) |
        Where-Object { $_ }
).Count
if ($SelectedModeCount -gt 1) {
    throw "Choose only one mode: -PerceptionOnly, -FaceOnly or -ControlEnabled."
}
$ControlMode = if ($ControlEnabled) {
    "CONTROL_ENABLED"
} elseif ($FaceOnly) {
    "FACE_ONLY"
} else {
    "PERCEPTION_ONLY"
}

if ($PixelDelta -lt 1) { throw "PixelDelta must be >= 1." }
if ($ChangedRatio -le 0 -or $ChangedRatio -gt 1) { throw "ChangedRatio must be in (0, 1]." }
if ($UncertainRatio -lt 0 -or $UncertainRatio -gt $ChangedRatio) {
    throw "UncertainRatio must be >= 0 and <= ChangedRatio."
}
if ($MinimumComponentArea -lt 1) { throw "MinimumComponentArea must be >= 1." }
if ($AssociationScore -lt 0 -or $AssociationScore -gt 1) {
    throw "AssociationScore must be between 0 and 1."
}
if ($EnemyConfirmFrames -lt 2) { throw "EnemyConfirmFrames must be >= 2." }
if ($MaximumMissingFrames -lt 1) { throw "MaximumMissingFrames must be >= 1." }
if ($AttackDistanceCells -lt 0) { throw "AttackDistanceCells must be >= 0." }

function Set-InvariantDoubleEnv([string]$Name, [double]$Value) {
    [Environment]::SetEnvironmentVariable(
        $Name,
        [string]::Format(
            [Globalization.CultureInfo]::InvariantCulture,
            "{0:0.0000}",
            $Value
        ),
        "Process"
    )
}

$BaselineFile = Join-Path $Root "kage_pilot_loop_logs\pr27_native_baseline.npz"
$SpriteRoot = Join-Path $Root "data\pr27_sprites"

$env:KAGE_PR27_CONTROL_MODE = $ControlMode
$env:KAGE_PR27_NATIVE_BASELINE_FILE = $BaselineFile
$env:KAGE_PR27_SPRITE_ROOT = $SpriteRoot
$env:KAGE_PR27_DEBUG_OVERLAY = if ($DebugOverlay) { "1" } else { "0" }
$env:KAGE_PR27_SAVE_DEBUG_FRAMES = if ($NoDebugFrames) { "0" } else { "1" }
$env:KAGE_PR27_PIXEL_DELTA = [string]$PixelDelta
$env:KAGE_PR27_MIN_COMPONENT_AREA = [string]$MinimumComponentArea
$env:KAGE_PR27_ENEMY_CONFIRM_FRAMES = [string]$EnemyConfirmFrames
$env:KAGE_PR27_MAX_MISSING_FRAMES = [string]$MaximumMissingFrames
$env:KAGE_PR27_ATTACK_DISTANCE = [string]$AttackDistanceCells
$env:KAGE_PR27_SCENE_CHANGED_MIN_CELLS = [string]$SceneChangedMinimumCells
Set-InvariantDoubleEnv "KAGE_PR27_CHANGED_RATIO" $ChangedRatio
Set-InvariantDoubleEnv "KAGE_PR27_UNCERTAIN_RATIO" $UncertainRatio
Set-InvariantDoubleEnv "KAGE_PR27_ASSOCIATION_SCORE" $AssociationScore
Set-InvariantDoubleEnv "KAGE_PR27_SCENE_CHANGED_RATIO" $SceneChangedRatio

Write-Host "PR27 NATIVE GRID SPRITE COMBAT" -ForegroundColor Green
Write-Host "  Mode: $ControlMode" -ForegroundColor Cyan
Write-Host "  Perception frame: original DreamSeeker client pixels"
Write-Host "  JPEG in perception: OFF" -ForegroundColor Yellow
Write-Host "  Resize in perception: OFF" -ForegroundColor Yellow
Write-Host "  Grid: native 64x64 cells"
Write-Host "  Comparison authority: EACH CELL owns baseline and difference mask"
Write-Host "  Cluster authority: SEARCH ADDRESSES ONLY"
Write-Host "  Identity authority: TrackedSprite ID"
Write-Host "  Baseline: $BaselineFile"
Write-Host "  Sprite references: $SpriteRoot"
Write-Host "  Debug frames: $(-not $NoDebugFrames)"
Write-Host "  Debug window: $($DebugOverlay.IsPresent)"

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
