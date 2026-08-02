[CmdletBinding()]
param(
    [string]$Profile = "default",
    [string]$RegionId = "mapping_input_calibration",
    [string]$DataRoot = "",
    [double]$SimilarityThreshold = 0.90,
    [double]$NoveltyThreshold = 0.12,
    [double]$ActivityThreshold = 0.018,
    [double]$TerrainRejectSimilarity = 0.965,
    [double]$DangerConfidence = 0.80,
    [double]$DangerStrongConfidence = 0.90,
    [double]$DangerConfirmedSimilarity = 0.90,
    [double]$DangerLikelySimilarity = 0.82,
    [double]$DangerWeakSimilarity = 0.72,
    [double]$DangerMargin = 0.04,
    [double]$ChangedRatioWeak = 0.04,
    [double]$ChangedRatio = 0.08,
    [double]$ChangedRatioStrong = 0.12,
    [int]$BlobArea = 180,
    [int]$BlobAreaStrong = 250,
    [int]$BlobWidth = 8,
    [int]$BlobHeight = 14,
    [int]$BlobHeightStrong = 18,
    [double]$PixelDeltaThreshold = 18.0,
    [int]$BaselineSamples = 5,
    [double]$BaselineStability = 0.012,
    [double]$DangerMemorySeconds = 2.5,
    [int]$DangerMemoryFrames = 12,
    [double]$MaxSpeedCellsPerSecond = 3.5,
    [double]$Pr24IntervalSeconds = 4.0,
    [double]$EvidenceSaveSeconds = 10.0,
    [double]$NonAggressiveSeconds = 3.0,
    [switch]$HostilityOverlay,
    [switch]$PerceptionOnly,
    [switch]$FaceOnly,
    [switch]$FullCombat,
    [int]$Rounds = 1,
    [double]$CombatSeconds = 120,
    [double]$PostCombatTimeout = 240,
    [double]$DialogDelay = 5,
    [double]$SpawnDelay = 5,
    [double]$TrainerSearchTimeout = 90,
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$SelectedModeCount = @(
    @($PerceptionOnly.IsPresent, $FaceOnly.IsPresent, $FullCombat.IsPresent) |
        Where-Object { $_ }
).Count
if ($SelectedModeCount -gt 1) {
    throw "Choose only one mode: -PerceptionOnly, -FaceOnly or -FullCombat."
}
$ControlMode = if ($FullCombat) {
    "FULL_COMBAT"
} elseif ($FaceOnly) {
    "FACE_ONLY"
} else {
    "PERCEPTION_ONLY"
}

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is not available. Pass -DataRoot explicitly."
    }
    $DataRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab"
}

$ProfileRoot = Join-Path (Join-Path $DataRoot "profiles") $Profile
$CalibrationPath = Join-Path (Join-Path $ProfileRoot "calibrations") "${RegionId}_grid.json"
$KnowledgePath = Join-Path (Join-Path $ProfileRoot "tile_knowledge") "${RegionId}.json"
$EvidenceDir = Join-Path $Root "kage_pilot_loop_logs\occupancy_evidence"
$PreOkBaselineFile = Join-Path $Root "kage_pilot_loop_logs\pr26_pre_ok_baseline.npz"

if (-not (Test-Path $CalibrationPath)) {
    throw "PR26 tile calibration was not found: $CalibrationPath"
}
if (-not (Test-Path $KnowledgePath)) {
    throw "PR26 tile knowledge was not found: $KnowledgePath"
}

$Calibration = Get-Content -Raw -Encoding UTF8 $CalibrationPath | ConvertFrom-Json
if ([int]$Calibration.tile_size_px -ne 64) {
    throw "PR26 requires the immutable 64px grid. Found: $($Calibration.tile_size_px)px"
}

$Knowledge = Get-Content -Raw -Encoding UTF8 $KnowledgePath | ConvertFrom-Json
$TerrainClasses = @(
    "walkable",
    "wall",
    "walkable_with_jutsu",
    "blocking_object",
    "transition",
    "danger"
)
$TerrainExamples = @(
    $Knowledge.examples | Where-Object { $TerrainClasses -contains [string]$_.category }
)
$DangerExamples = @(
    $Knowledge.examples | Where-Object { [string]$_.category -eq "danger" }
)
$ReferenceCrops = @(
    $TerrainExamples | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_.crop_path)
    }
)
if ($TerrainExamples.Count -lt 1) {
    throw "PR26 requires at least one taught PR24 terrain example."
}
if ($DangerExamples.Count -lt 1) {
    throw "PR26.15 requires at least one taught PR24 DANGER example."
}
if ($ReferenceCrops.Count -lt 1) {
    throw "PR26.15 requires real PR24 crop images for semantic affinity."
}
if ($DangerConfidence -lt 0.50 -or $DangerConfidence -gt 1.0) {
    throw "DangerConfidence must be between 0.50 and 1.0."
}
if ($DangerStrongConfidence -lt $DangerConfidence -or $DangerStrongConfidence -gt 1.0) {
    throw "DangerStrongConfidence must be >= DangerConfidence and <= 1.0."
}
if (
    $DangerWeakSimilarity -lt 0.50 -or
    $DangerLikelySimilarity -lt $DangerWeakSimilarity -or
    $DangerConfirmedSimilarity -lt $DangerLikelySimilarity -or
    $DangerConfirmedSimilarity -gt 1.0
) {
    throw "DANGER affinity thresholds must satisfy 0.50 <= weak <= likely <= confirmed <= 1.0."
}
if ($DangerMargin -lt 0.0 -or $DangerMargin -gt 1.0) {
    throw "DangerMargin must be between 0.0 and 1.0."
}
if (
    $ChangedRatioWeak -lt 0.0 -or
    $ChangedRatio -lt $ChangedRatioWeak -or
    $ChangedRatioStrong -lt $ChangedRatio
) {
    throw "Changed-ratio thresholds are invalid."
}
if ($BaselineSamples -lt 3) {
    throw "BaselineSamples must be at least 3."
}
if ($DangerMemorySeconds -le 0 -or $DangerMemoryFrames -lt 1) {
    throw "DANGER memory must be positive in seconds and frames."
}
if ($Pr24IntervalSeconds -lt 0.2) {
    throw "Pr24IntervalSeconds must be at least 0.2 seconds."
}
if ($EvidenceSaveSeconds -lt 1.0) {
    throw "EvidenceSaveSeconds must be at least 1.0 second."
}

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

$env:KAGE_PR26_TILE_DATA_ROOT = $DataRoot
$env:KAGE_PR26_TILE_PROFILE = $Profile
$env:KAGE_PR26_TILE_REGION = $RegionId
$env:KAGE_PR26_CONTROL_MODE = $ControlMode
$env:KAGE_PR26_EVIDENCE_DIR = $EvidenceDir
$env:KAGE_PR26_PREOK_BASELINE_FILE = $PreOkBaselineFile
Set-InvariantDoubleEnv "KAGE_PR26_TILE_SIMILARITY" $SimilarityThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_NOVELTY" $NoveltyThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_ACTIVITY" $ActivityThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_REJECT" $TerrainRejectSimilarity
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_CONFIDENCE" $DangerConfidence
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_STRONG" $DangerStrongConfidence
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_CONFIRMED_SIMILARITY" $DangerConfirmedSimilarity
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_LIKELY_SIMILARITY" $DangerLikelySimilarity
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_WEAK_SIMILARITY" $DangerWeakSimilarity
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_MARGIN" $DangerMargin
Set-InvariantDoubleEnv "KAGE_PR26_OCCUPANCY_WEAK" $ChangedRatioWeak
Set-InvariantDoubleEnv "KAGE_PR26_CHANGED_RATIO" $ChangedRatio
Set-InvariantDoubleEnv "KAGE_PR26_CHANGED_RATIO_STRONG" $ChangedRatioStrong
Set-InvariantDoubleEnv "KAGE_PR26_PIXEL_DELTA" $PixelDeltaThreshold
Set-InvariantDoubleEnv "KAGE_PR26_BASELINE_STABILITY" $BaselineStability
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_MEMORY_SECONDS" $DangerMemorySeconds
Set-InvariantDoubleEnv "KAGE_PR26_MAX_SPEED_CELLS" $MaxSpeedCellsPerSecond
Set-InvariantDoubleEnv "KAGE_PR26_PR24_INTERVAL_SECONDS" $Pr24IntervalSeconds
Set-InvariantDoubleEnv "KAGE_PR26_EVIDENCE_SAVE_SECONDS" $EvidenceSaveSeconds
Set-InvariantDoubleEnv "KAGE_PR26_NON_AGGRESSIVE_SECONDS" $NonAggressiveSeconds
$env:KAGE_PR26_BASELINE_SAMPLES = [string]([Math]::Max(3, $BaselineSamples))
$env:KAGE_PR26_DANGER_MEMORY_FRAMES = [string]([Math]::Max(1, $DangerMemoryFrames))
$env:KAGE_PR26_BLOB_AREA = [string]([Math]::Max(1, $BlobArea))
$env:KAGE_PR26_BLOB_AREA_STRONG = [string]([Math]::Max($BlobArea, $BlobAreaStrong))
$env:KAGE_PR26_BLOB_WIDTH = [string]([Math]::Max(1, $BlobWidth))
$env:KAGE_PR26_BLOB_HEIGHT = [string]([Math]::Max(1, $BlobHeight))
$env:KAGE_PR26_BLOB_HEIGHT_STRONG = [string]([Math]::Max($BlobHeight, $BlobHeightStrong))
$env:KAGE_PR26_HOSTILITY_OVERLAY = if ($HostilityOverlay) { "1" } else { "0" }

Write-Host "PR26.15 CURRENT BODY AUTHORITY PREFLIGHT: READY" -ForegroundColor Green
Write-Host "  Grid: 64px immutable"
Write-Host "  Control mode: $ControlMode" -ForegroundColor Cyan
Write-Host "  Profile: $Profile"
Write-Host "  Region: $RegionId"
Write-Host "  PR24 full-frame offset: X=$($Calibration.offset_x_px) Y=$($Calibration.offset_y_px)"
Write-Host "  Terrain examples: $($TerrainExamples.Count)"
Write-Host "  DANGER examples: $($DangerExamples.Count)"
Write-Host "  Real reference crops: $($ReferenceCrops.Count)"
Write-Host "  PR24 semantic interval: $Pr24IntervalSeconds seconds"
Write-Host "  Evidence save interval: $EvidenceSaveSeconds seconds"
Write-Host "  Comparison authority: EACH INDIVIDUAL 64x64 CELL" -ForegroundColor Yellow
Write-Host "  Cluster role: SEARCH HINT ONLY; identity/hostility/ReID authority OFF"
Write-Host "  Same-cell equality: SEARCH LOCATION ONLY; not body identity"
Write-Host "  Body binding: bbox/foot must overlap changed pixels of the component"
Write-Host "  Latched visual continuation: CURRENT RAW BODY or TARGET CAPSULE required"
Write-Host "  Pixel-cluster ReID: BLOCKED"
Write-Host "  Dominant 43x64 / 64x23 terrain fields: BLOCKED"
Write-Host "  Baseline: every stable 64px cell retained; player core inpainted"
Write-Host "  Runtime player exclusion: narrow capsule; side/top overlap preserved"
Write-Host "  Camera: low-response jumps blocked; meaningful shifts require temporal confirmation"
Write-Host "  Initial acquisition radius: D<=3"
Write-Host "  Raw-less compact vertical change: isolated TURN hint only"
Write-Host "  TURN_ONLY: never forwarded as a combat candidate or logical target"
Write-Host "  Logical target: COMPONENT_OVERLAP -> CURRENT_BODY -> HOSTILE_CONFIRMED -> COMBAT_LOCK -> ROUND_TARGET_LATCHED" -ForegroundColor Yellow
Write-Host "  ReID/OCCLUDED_COAST: only after a valid round target latch"
Write-Host "  ReID search after latch: Target Capsule D1 -> D2 -> D3; never beyond D3"
Write-Host "  CONTACT_MEMORY / REID_PENDING / OUTSIDE_D3: valid identity retained; MOVE/H blocked"
Write-Host "  Event JSON: occupancy/decision/candidate frozen at trigger frame"
Write-Host "  PERCEPTION_ONLY: TURN/MOVE/R/H blocked"
Write-Host "  FACE_ONLY: TURN allowed; MOVE/R/H blocked"
Write-Host "  FULL_COMBAT: current body-bound visual confirmation required for MOVE/H"
Write-Host "  Synthetic offensive authority: BLOCKED" -ForegroundColor Yellow
Write-Host "  Evidence bundles: $EvidenceDir"
Write-Host "  Baseline file: $PreOkBaselineFile"
Write-Host "  Calibration: $CalibrationPath"
Write-Host "  Knowledge: $KnowledgePath"

if ($PreflightOnly) {
    exit 0
}

& (Join-Path $Root "run_kage_combat_lab.ps1") `
    -FullLoop `
    -Rounds ([Math]::Max(1, $Rounds)) `
    -CombatSeconds ([Math]::Max(10, $CombatSeconds)) `
    -PostCombatTimeout ([Math]::Max(30, $PostCombatTimeout)) `
    -DialogDelay ([Math]::Max(0, $DialogDelay)) `
    -SpawnDelay ([Math]::Max(0, $SpawnDelay)) `
    -TrainerSearchTimeout ([Math]::Max(10, $TrainerSearchTimeout))

exit $LASTEXITCODE
