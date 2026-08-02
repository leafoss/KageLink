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
    [double]$DangerStrongConfidence = 0.95,
    [double]$ChangedRatio = 0.08,
    [double]$ChangedRatioStrong = 0.12,
    [int]$BlobArea = 180,
    [int]$BlobAreaStrong = 250,
    [int]$BlobWidth = 8,
    [int]$BlobHeight = 14,
    [int]$BlobHeightStrong = 18,
    [int]$EntityPersistence = 2,
    [double]$NonAggressiveSeconds = 3.0,
    [double]$SuspiciousTtlSeconds = 5.0,
    [switch]$HostilityOverlay,
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

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw "LOCALAPPDATA is not available. Pass -DataRoot explicitly."
    }
    $DataRoot = Join-Path $env:LOCALAPPDATA "KageNavigationLab"
}

$ProfileRoot = Join-Path (Join-Path $DataRoot "profiles") $Profile
$CalibrationPath = Join-Path (Join-Path $ProfileRoot "calibrations") "${RegionId}_grid.json"
$KnowledgePath = Join-Path (Join-Path $ProfileRoot "tile_knowledge") "${RegionId}.json"

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
if ($TerrainExamples.Count -lt 1) {
    throw "PR26 requires at least one taught PR24 terrain example."
}
if ($DangerExamples.Count -lt 1) {
    throw "PR26.1 requires at least one taught PR24 DANGER example before physical combat."
}
if ($DangerConfidence -lt 0.50 -or $DangerConfidence -gt 1.0) {
    throw "DangerConfidence must be between 0.50 and 1.0."
}
if ($DangerStrongConfidence -lt $DangerConfidence -or $DangerStrongConfidence -gt 1.0) {
    throw "DangerStrongConfidence must be >= DangerConfidence and <= 1.0."
}
if ($ChangedRatio -lt 0.0 -or $ChangedRatioStrong -lt $ChangedRatio) {
    throw "ChangedRatio thresholds are invalid."
}
if ($EntityPersistence -lt 2) {
    throw "EntityPersistence must be at least 2 frames."
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
Set-InvariantDoubleEnv "KAGE_PR26_TILE_SIMILARITY" $SimilarityThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_NOVELTY" $NoveltyThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_ACTIVITY" $ActivityThreshold
Set-InvariantDoubleEnv "KAGE_PR26_TILE_REJECT" $TerrainRejectSimilarity
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_CONFIDENCE" $DangerConfidence
Set-InvariantDoubleEnv "KAGE_PR26_DANGER_STRONG" $DangerStrongConfidence
Set-InvariantDoubleEnv "KAGE_PR26_CHANGED_RATIO" $ChangedRatio
Set-InvariantDoubleEnv "KAGE_PR26_CHANGED_RATIO_STRONG" $ChangedRatioStrong
Set-InvariantDoubleEnv "KAGE_PR26_NON_AGGRESSIVE_SECONDS" $NonAggressiveSeconds
Set-InvariantDoubleEnv "KAGE_PR26_SUSPICIOUS_TTL" $SuspiciousTtlSeconds
$env:KAGE_PR26_BLOB_AREA = [string]([Math]::Max(1, $BlobArea))
$env:KAGE_PR26_BLOB_AREA_STRONG = [string]([Math]::Max($BlobArea, $BlobAreaStrong))
$env:KAGE_PR26_BLOB_WIDTH = [string]([Math]::Max(1, $BlobWidth))
$env:KAGE_PR26_BLOB_HEIGHT = [string]([Math]::Max(1, $BlobHeight))
$env:KAGE_PR26_BLOB_HEIGHT_STRONG = [string]([Math]::Max($BlobHeight, $BlobHeightStrong))
$env:KAGE_PR26_ENTITY_PERSISTENCE = [string]([Math]::Max(2, $EntityPersistence))
$env:KAGE_PR26_HOSTILITY_OVERLAY = if ($HostilityOverlay) { "1" } else { "0" }

Write-Host "PR26.1 HOSTILITY GATE PREFLIGHT: READY" -ForegroundColor Green
Write-Host "  Grid: 64px"
Write-Host "  Profile: $Profile"
Write-Host "  Region: $RegionId"
Write-Host "  PR24 full-frame offset: X=$($Calibration.offset_x_px) Y=$($Calibration.offset_y_px)"
Write-Host "  Terrain examples: $($TerrainExamples.Count)"
Write-Host "  DANGER examples: $($DangerExamples.Count)"
Write-Host "  DANGER candidate confidence: $DangerConfidence"
Write-Host "  DANGER strong confidence: $DangerStrongConfidence"
Write-Host "  Changed ratio suspect/strong: $ChangedRatio / $ChangedRatioStrong"
Write-Host "  Blob area suspect/strong: $BlobArea / $BlobAreaStrong"
Write-Host "  Blob minimum WxH: ${BlobWidth}x${BlobHeight}"
Write-Host "  Entity persistence: $EntityPersistence frames"
Write-Host "  Passive non-aggressive window: $NonAggressiveSeconds seconds"
Write-Host "  Suspicious entity TTL: $SuspiciousTtlSeconds seconds"
Write-Host "  VISUAL_LOCK: passive only"
Write-Host "  COMBAT_LOCK: requires HOSTILE_CONFIRMED"
Write-Host "  Synthetic offensive authority: BLOCKED" -ForegroundColor Yellow
Write-Host "  Movement pulse, R, facing, H, Trainer, KO and meditation: UNCHANGED"
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
