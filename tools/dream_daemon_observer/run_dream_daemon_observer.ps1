param(
    [string]$Python = "py"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv-dream-observer"
$PythonExe = Join-Path $Venv "Scripts\python.exe"

Write-Host "KageLink - Dream Daemon Observer" -ForegroundColor Green
Write-Host "Passive, read-only traffic visualization." -ForegroundColor DarkGreen

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating isolated Python environment..."
    & $Python -3.11 -m venv $Venv
}

& $PythonExe -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements.txt")

$TsharkCandidates = @(
    (Get-Command tshark.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "C:\Program Files\Wireshark\tshark.exe",
    "C:\Program Files (x86)\Wireshark\tshark.exe"
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $TsharkCandidates) {
    Write-Host ""
    Write-Host "TShark was not found." -ForegroundColor Yellow
    Write-Host "Install Wireshark with TShark and Npcap enabled, then run this file again." -ForegroundColor Yellow
    Write-Host "The observer will not inject code or modify traffic."
    Read-Host "Press Enter to close"
    exit 2
}

$env:TSHARK_PATH = $TsharkCandidates[0]
Write-Host "TShark: $env:TSHARK_PATH"
Write-Host "For packet capture, open PowerShell as Administrator if Npcap requires it." -ForegroundColor Cyan

& $PythonExe (Join-Path $Root "dream_daemon_observer.py")
