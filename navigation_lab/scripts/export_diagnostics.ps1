[CmdletBinding()]
param(
    [string]$Profile = "default",
    [string]$Destination = "."
)

$ErrorActionPreference = "Stop"
$Source = Join-Path $env:LOCALAPPDATA "KageNavigationLab\profiles\$Profile"
if (-not (Test-Path $Source)) {
    throw "Profile not found: $Source"
}
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Zip = Join-Path (Resolve-Path $Destination) "navigation_diagnostics_${Profile}_$Stamp.zip"
Compress-Archive -Path (Join-Path $Source "*") -DestinationPath $Zip -Force
Write-Host $Zip
