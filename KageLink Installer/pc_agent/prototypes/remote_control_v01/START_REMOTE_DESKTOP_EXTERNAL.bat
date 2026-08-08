@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-remote\Scripts\python.exe" (
  echo Execute SETUP.bat primeiro. / Run SETUP.bat first.
  pause
  exit /b 1
)

echo ============================================================
echo KageLink Remote - DESKTOP MODE - EXPLICIT CONTROL
 echo ============================================================
echo ATENCAO: este launcher autoriza controle do desktop selecionado.
echo WARNING: this launcher explicitly authorizes control of the selected desktop.
echo O navegador ainda precisa ser aprovado LOCALMENTE no PC host.
echo The browser still needs LOCAL approval on the host PC.
echo.
echo PARADA DE EMERGENCIA / EMERGENCY STOP: CTRL + ALT + F12
 echo ============================================================

".venv-remote\Scripts\python.exe" remote_host.py --mode desktop --allow-control --allow-desktop-control --monitor 1 --bind 127.0.0.1 --port 8765 --admin-port 8766 --tunnel cloudflare-quick --trust-cloudflare-proxy --max-width 1600 --fps 24
set EXITCODE=%errorlevel%

echo.
echo KageLink Remote finalizado com codigo %EXITCODE%.
pause
exit /b %EXITCODE%
