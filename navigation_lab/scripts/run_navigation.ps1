[CmdletBinding()]
param(
    [ValidateSet("simulator", "observer", "teaching", "assisted", "autonomous", "replay")]
    [string]$Mode = "simulator",
    [string]$Scenario = "basic_world",
    [string]$WindowTitle = "Shinobi Story Online",
    [string]$Profile = "default",
    [ValidateSet("pt-BR", "en-US")]
    [string]$Language = "pt-BR",
    [string]$Destination = "",
    [switch]$DebugWindow,
    [switch]$ArmInput,
    [switch]$RecordSession
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv-navigation\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run navigation_lab\scripts\setup_navigation.ps1 first."
}

$Arguments = @(
    "-m", "navigation_lab",
    "--mode", $Mode,
    "--scenario", $Scenario,
    "--window-title", $WindowTitle,
    "--profile", $Profile,
    "--language", $Language
)
if ($DebugWindow) { $Arguments += "--debug-window" }
if ($ArmInput) { $Arguments += "--arm-input" }
if ($RecordSession) { $Arguments += "--record-session" }
if ($Destination) { $Arguments += @("--destination", $Destination) }

Push-Location $RepoRoot
try {
    & $Python @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
