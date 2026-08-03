param(
    [string]$Python = "py"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv-dream-observer"
$PythonExe = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    & $Python -3.11 -m venv $Venv
}

& $PythonExe -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements.txt") pytest
Push-Location $Root
try {
    & $PythonExe -m pytest -q
}
finally {
    Pop-Location
}
