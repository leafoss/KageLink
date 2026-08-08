@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo KageLink Remote - Setup local do prototipo
 echo ============================================================

if exist ".venv-remote\Scripts\python.exe" goto install

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.11 -m venv .venv-remote
) else (
  python -m venv .venv-remote
)
if errorlevel 1 goto fail

:install
".venv-remote\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail
".venv-remote\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo.
echo Setup concluido. Nenhum servico de inicializacao automatica foi criado.
echo Setup complete. No automatic-start service was created.
pause
exit /b 0

:fail
echo.
echo Falha no setup. Verifique Python 3.11 e sua conexao.
echo Setup failed. Check Python 3.11 and your connection.
pause
exit /b 1
