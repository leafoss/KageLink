@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title KageLink 3.5.1 - Dojo Vision Lab Local

set "PYTHON_EXE="
for %%P in (py.exe python.exe) do (
    where %%P >nul 2>nul && if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
    echo.
    echo [ERRO] Python 3.11 nao foi encontrado.
    echo Instale Python 3.11 para executar o codigo localmente.
    pause
    exit /b 1
)

set "VENV=.venv-dojo-vision-lab"
set "VENV_PY=%VENV%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [1/4] Criando ambiente local do Dojo Vision Lab...
    if /I "%PYTHON_EXE%"=="py.exe" (
        py -3.11 -m venv "%VENV%"
    ) else (
        python -m venv "%VENV%"
    )
    if errorlevel 1 goto :error
)

echo [2/4] Atualizando dependencias locais...
"%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto :error
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :error

echo [3/4] Ativando gravacao completa do Vision Lab...
"%VENV_PY%" -c "from pc_agent.kage_pilot.dojo_vision_lab_v351 import VisionLabSettings,read_settings,write_settings; s=read_settings(); write_settings(VisionLabSettings(enabled=True,fps=s.fps,record_video=True,save_stages=True,stage_interval=s.stage_interval,jpeg_quality=s.jpeg_quality)); print('Vision Lab ativo em:', write_settings(read_settings()))"
if errorlevel 1 goto :error

echo [4/4] Iniciando KageLink pelo codigo local...
echo.
echo Acesse: Dojo Trainer ^> Vision Lab
"%VENV_PY%" unified_entry.py
set "RESULT=%ERRORLEVEL%"

echo.
echo KageLink encerrado com codigo %RESULT%.
pause
exit /b %RESULT%

:error
echo.
echo [ERRO] Nao foi possivel preparar o KageLink local.
echo Confira a mensagem acima e tente novamente.
pause
exit /b 1
