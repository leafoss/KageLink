@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-remote\Scripts\python.exe" (
  echo Execute SETUP.bat primeiro. / Run SETUP.bat first.
  pause
  exit /b 1
)

echo ============================================================
echo KageLink Remote - GAME MODE - LOCAL NETWORK ONLY
 echo ============================================================
echo Nenhum tunel externo sera iniciado.
echo No external tunnel will be started.
echo.
echo Abra no outro dispositivo: http://IP_DESTE_PC:8765
 echo Open on the other device: http://THIS_PC_IP:8765
 echo.
echo PARADA DE EMERGENCIA / EMERGENCY STOP: CTRL + ALT + F12
 echo ============================================================

".venv-remote\Scripts\python.exe" remote_host.py --mode game --allow-control --bind 0.0.0.0 --port 8765 --admin-port 8766 --tunnel none --max-width 1600 --fps 24
set EXITCODE=%errorlevel%

echo.
echo KageLink Remote finalizado com codigo %EXITCODE%.
pause
exit /b %EXITCODE%
