[CmdletBinding()]
param(
    [string]$Scenario = "basic_world",
    [ValidateSet("pt-BR", "en-US")]
    [string]$Language = "pt-BR",
    [switch]$DebugWindow,
    [switch]$RecordSession
)

$Run = Join-Path $PSScriptRoot "run_navigation.ps1"
& $Run -Mode simulator -Scenario $Scenario -Language $Language -DebugWindow:$DebugWindow -RecordSession:$RecordSession
exit $LASTEXITCODE
