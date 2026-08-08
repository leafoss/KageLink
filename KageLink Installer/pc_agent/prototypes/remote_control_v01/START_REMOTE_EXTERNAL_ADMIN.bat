@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="--elevated" goto elevated

if not exist ".venv-remote\Scripts\python.exe" (
  echo Execute SETUP.bat primeiro. / Run SETUP.bat first.
  pause
  exit /b 1
)

echo KageLink Remote solicitara UAC LOCALMENTE no PC host.
echo KageLink Remote will request UAC LOCALLY on the host PC.
echo O prompt da Secure Desktop nao pode ser controlado remotamente.
echo The Secure Desktop UAC prompt cannot be controlled remotely.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -WorkingDirectory '%~dp0' -Verb RunAs"
exit /b %errorlevel%

:elevated
echo ============================================================
echo KageLink Remote - GAME MODE - ELEVATED HOST
 echo ============================================================
echo Controle continua restrito ao alvo configurado no Game Mode.
echo Control remains restricted to the configured Game Mode target.
echo.
echo PARADA DE EMERGENCIA / EMERGENCY STOP: CTRL + ALT + F12
 echo ============================================================

".venv-remote\Scripts\python.exe" remote_host.py --mode game --allow-control --bind 127.0.0.1 --port 8765 --admin-port 8766 --tunnel cloudflare-quick --trust-cloudflare-proxy --max-width 1600 --fps 24
set EXITCODE=%errorlevel%

echo.
echo KageLink Remote finalizado com codigo %EXITCODE%.
pause
exit /b %EXITCODE%
