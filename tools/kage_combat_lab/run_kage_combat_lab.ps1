[CmdletBinding()]
param(
    [switch]$RunAll,
    [switch]$Interactive,
    [switch]$LiveChecklist,
    [switch]$LiveInput,
    [switch]$FullLoop,
    [string]$Scenario = "distance_1_adjacent",
    [double]$Delay = 0.4,
    [double]$MaxSeconds = 80,
    [double]$Fps = 8,
    [double]$Countdown = 3,
    [int]$Rounds = 1,
    [double]$CombatSeconds = 120,
    [double]$PostCombatTimeout = 240,
    [double]$DialogDelay = 5,
    [double]$SpawnDelay = 5,
    [double]$TrainerSearchTimeout = 90,
    [switch]$NoPreview
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $Root "..\..")).Path
$PcAgentRoot = Join-Path $RepoRoot "KageLink Installer\pc_agent"

if ($LiveInput -and $FullLoop) {
    throw "Choose only one armed mode: -LiveInput or -FullLoop."
}

if (($LiveInput -or $FullLoop) -and -not (Test-Path $PcAgentRoot)) {
    throw "Full KageLink checkout required. Missing: $PcAgentRoot"
}

$PythonPaths = @($Root)
if (Test-Path $PcAgentRoot) {
    $PythonPaths += $PcAgentRoot
}
$env:PYTHONPATH = ($PythonPaths -join [IO.Path]::PathSeparator)

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "Python 3 was not found. Install Python or add it to PATH."
}

if ($FullLoop) {
    $Arguments = @(
        "-m", "kage_combat_lab.full_loop",
        "--rounds", "$([Math]::Max(1, $Rounds))",
        "--combat-seconds", "$([Math]::Max(10, $CombatSeconds))",
        "--post-combat-timeout", "$([Math]::Max(30, $PostCombatTimeout))",
        "--dialog-delay", "$([Math]::Max(0, $DialogDelay))",
        "--spawn-delay", "$([Math]::Max(0, $SpawnDelay))",
        "--trainer-search-timeout", "$([Math]::Max(10, $TrainerSearchTimeout))"
    )
}
elif ($LiveInput) {
    $Arguments = @(
        "-m", "kage_combat_lab.live_input",
        "--max-seconds", "$MaxSeconds",
        "--fps", "$Fps",
        "--countdown", "$Countdown"
    )
    if ($NoPreview) { $Arguments += "--no-preview" }
}
else {
    $Arguments = @("-m", "kage_combat_lab.cli", "--scenario", $Scenario, "--delay", "$Delay")
    if ($RunAll) { $Arguments += "--run-all" }
    if ($Interactive) { $Arguments += "--interactive" }
    if ($LiveChecklist) { $Arguments += "--live-checklist" }
}

& $Python.Source @Arguments
exit $LASTEXITCODE
