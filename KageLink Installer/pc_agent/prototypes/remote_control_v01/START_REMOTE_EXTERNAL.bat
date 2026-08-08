@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-remote\Scripts\python.exe" (
  echo KageLink Remote ainda nao foi preparado.
  echo KageLink Remote has not been set up yet.
  echo.
  echo Execute SETUP.bat primeiro. / Run SETUP.bat first.
  pause
  exit /b 1
)

echo ============================================================
echo KageLink Remote - GAME MODE - EXTERNAL
 echo ============================================================
echo O navegador remoto precisara ser aprovado localmente no PC host.
echo The remote browser must be approved locally on the host PC.
echo.
echo PARADA DE EMERGENCIA / EMERGENCY STOP: CTRL + ALT + F12
 echo ============================================================

".venv-remote\Scripts\python.exe" remote_host.py --mode game --allow-control --bind 127.0.0.1 --port 8765 --admin-port 8766 --tunnel cloudflare-quick --trust-cloudflare-proxy --max-width 1600 --fps 24
set EXITCODE=%errorlevel%

echo.
echo KageLink Remote finalizado com codigo %EXITCODE%.
pause
exit /b %EXITCODE%
