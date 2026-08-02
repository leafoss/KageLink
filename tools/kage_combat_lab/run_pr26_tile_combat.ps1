[CmdletBinding()]
param(
    [string]$Profile = "default",
    [string]$RegionId = "mapping_input_calibration",
    [string]$DataRoot = "",
    [double]$SimilarityThreshold = 0.90,
    [double]$NoveltyThreshold = 0.12,
    [double]$ActivityThreshold = 0.018,
    [double]$TerrainRejectSimilarity = 0.965,
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
if ($TerrainExamples.Count -lt 1) {
    throw "PR26 requires at least one taught PR24 terrain example."
}

$env:KAGE_PR26_TILE_DATA_ROOT = $DataRoot
$env:KAGE_PR26_TILE_PROFILE = $Profile
$env:KAGE_PR26_TILE_REGION = $RegionId
$env:KAGE_PR26_TILE_SIMILARITY = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0:0.0000}",
    $SimilarityThreshold
)
$env:KAGE_PR26_TILE_NOVELTY = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0:0.0000}",
    $NoveltyThreshold
)
$env:KAGE_PR26_TILE_ACTIVITY = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0:0.0000}",
    $ActivityThreshold
)
$env:KAGE_PR26_TILE_REJECT = [string]::Format(
    [Globalization.CultureInfo]::InvariantCulture,
    "{0:0.0000}",
    $TerrainRejectSimilarity
)

Write-Host "PR26 TILE PERCEPTION PREFLIGHT: READY" -ForegroundColor Green
Write-Host "  Grid: 64px"
Write-Host "  Profile: $Profile"
Write-Host "  Region: $RegionId"
Write-Host "  Terrain examples: $($TerrainExamples.Count)"
Write-Host "  Similarity threshold: $SimilarityThreshold"
Write-Host "  Novelty threshold: $NoveltyThreshold"
Write-Host "  Activity threshold: $ActivityThreshold"
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
