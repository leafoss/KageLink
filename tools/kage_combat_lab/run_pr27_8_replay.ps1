[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,
    [string]$OutputPath,
    [string]$TrainerBBoxOutput = "541,147,38,35",
    [switch]$NoArtifacts
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedInput = (Resolve-Path $InputPath).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $Root "reports\pr27_8_replay"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

$env:PYTHONPATH = $Root
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) { $Python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $Python) { throw "Python 3 was not found." }

$Arguments = @(
    "-m", "kage_combat_lab.pr27_replay",
    "--input", $ResolvedInput,
    "--output", $OutputPath,
    "--trainer-bbox-output", $TrainerBBoxOutput
)
if ($NoArtifacts) { $Arguments += "--no-artifacts" }

Write-Host "PR27.8 OFFLINE REPLAY" -ForegroundColor Green
Write-Host "  Input: $ResolvedInput"
Write-Host "  Output: $OutputPath"
Write-Host "  Physical input: impossible in replay" -ForegroundColor Yellow

& $Python.Source @Arguments
exit $LASTEXITCODE
