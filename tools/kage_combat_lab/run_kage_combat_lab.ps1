[CmdletBinding()]
param(
    [switch]$RunAll,
    [switch]$Interactive,
    [switch]$LiveChecklist,
    [string]$Scenario = "distance_1_adjacent",
    [double]$Delay = 0.4
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = $Root

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "Python 3 was not found. Install Python or add it to PATH."
}

$Arguments = @("-m", "kage_combat_lab.cli", "--scenario", $Scenario, "--delay", "$Delay")
if ($RunAll) { $Arguments += "--run-all" }
if ($Interactive) { $Arguments += "--interactive" }
if ($LiveChecklist) { $Arguments += "--live-checklist" }

& $Python.Source @Arguments
exit $LASTEXITCODE
