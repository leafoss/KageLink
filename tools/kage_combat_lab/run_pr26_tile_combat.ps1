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
    [double]$Pr24IntervalSeconds = 1.0,
    [double]$EvidenceSaveSeconds = 2.0,
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
    throw "PR26.3 requires at least one taught PR24 DANGER example."
}
if ($ReferenceCrops.Count -lt 1) {
    throw "PR26.3 requires real PR24 crop images for CLASS_REFERENCE pixel comparison."
}
if ($DangerConfidence -lt 0.50 -or $DangerConfidence -gt 1.0) {
    throw "DangerConfidence must be between 0.50 and 1.0."
}
if ($DangerStrongConfidence -lt $DangerConfidence -or $DangerStrongConfidence -gt 1.0) {
    throw "DangerStrongConfidence must be >= DangerConfidence and <= 1.0."
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
Set-InvariantDoubleEnv "KAGE_PR26_TILE_SIMILARITY" $SimilarityThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_NOVELTY" $NoveltyThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_ACTIVITY" $ActivityThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_REJECT" $TerrainRejectSimilarity
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_CONFIDENCE" $DangerConfidence
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_STRONG" $DangerStrongConfidence
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

Write-Host "PR26.3 MOBILE DANGER OCCUPANCY PREFLIGHT: READY" -ForegroundColor Green
Write-Host "  Grid: 64px"
Write-Host "  Control mode: $ControlMode" -ForegroundColor Cyan
Write-Host "  Profile: $Profile"
Write-Host "  Region: $RegionId"
Write-Host "  PR24 full-frame offset: X=$($Calibration.offset_x_px) Y=$($Calibration.offset_y_px)"
Write-Host "  Terrain examples: $($TerrainExamples.Count)"
Write-Host "  DANGER examples: $($DangerExamples.Count)"
Write-Host "  Real reference crops: $($ReferenceCrops.Count)"
Write-Host "  PR24 semantic interval: $Pr24IntervalSeconds seconds"
Write-Host "  Pixel difference source: EXACT_CELL_BASELINE or CLASS_REFERENCE only"
Write-Host "  bbox_coverage_ratio: telemetry only; never changed_ratio"
Write-Host "  True changed ratio weak/suspect/strong: $ChangedRatioWeak / $ChangedRatio / $ChangedRatioStrong"
Write-Host "  Blob area suspect/strong: $BlobArea / $BlobAreaStrong"
Write-Host "  Pixel delta threshold: $PixelDeltaThreshold"
Write-Host "  Baseline median samples: $BaselineSamples"
Write-Host "  DANGER memory: $DangerMemorySeconds seconds OR $DangerMemoryFrames frames"
Write-Host "  Dynamic movement allowance: $MaxSpeedCellsPerSecond cells/second"
Write-Host "  DANGER identity: transfers to nearby occupied clusters"
Write-Host "  PERCEPTION_ONLY: TURN/MOVE/R/H blocked"
Write-Host "  FACE_ONLY: TURN allowed; MOVE/R/H blocked"
Write-Host "  FULL_COMBAT: requires behavior-confirmed COMBAT_LOCK"
Write-Host "  Synthetic offensive authority: BLOCKED" -ForegroundColor Yellow
Write-Host "  Evidence bundles: $EvidenceDir"
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
