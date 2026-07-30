@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title KageLink - Criar Instalador Final

set "ROOT=%~dp0.."
set "BUILD_VENV=%~dp0.builder_venv"
set "PYTHON_EXE="
set "ISCC="

 echo ================================================================
 echo KAGELINK 3.5.1 - CRIADOR DO INSTALADOR COM DOJO TRAINER
 echo ================================================================
 echo.
 echo Este processo gera KageLink.exe e os dois motores isolados do
 echo Dojo Trainer, depois cria o instalador para os usuarios finais.
 echo.

call :FindPython
if not defined PYTHON_EXE (
  echo [1/6] Python nao encontrado. Instalando automaticamente...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ERRO] winget nao esta disponivel para instalar o Python.
    pause
    exit /b 1
  )
  winget install --id Python.Python.3.11 -e -s winget --scope user --silent --accept-source-agreements --accept-package-agreements
  call :FindPython
)
if not defined PYTHON_EXE (
  echo [ERRO] Python nao foi localizado apos a instalacao.
  pause
  exit /b 1
)

echo [1/6] Python localizado: !PYTHON_EXE!

if not exist "%BUILD_VENV%\Scripts\python.exe" (
  echo [2/6] Criando ambiente de compilacao isolado...
  "!PYTHON_EXE!" -m venv "%BUILD_VENV%"
  if errorlevel 1 goto :error
)

set "VPY=%BUILD_VENV%\Scripts\python.exe"
echo [3/6] Instalando ferramentas de compilacao...
"%VPY%" -m pip install --disable-pip-version-check --upgrade pip
"%VPY%" -m pip install --disable-pip-version-check -r "%ROOT%\pc_agent\requirements.txt" "pyinstaller>=6.10,<7"
if errorlevel 1 goto :error


echo [4/6] Preparando conexao externa incorporada...
if exist "%~dp0payload\cloudflared.exe.download" del /q "%~dp0payload\cloudflared.exe.download" >nul 2>&1
if exist "%~dp0payload\cloudflared.download.exe" del /q "%~dp0payload\cloudflared.download.exe" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\prepare_cloudflared.ps1"
if errorlevel 1 goto :error

echo [5/6] Gerando KageLink e motores do Dojo com Python incorporado...
if exist "%~dp0build" rmdir /s /q "%~dp0build"
if not exist "%~dp0build_output" mkdir "%~dp0build_output"
for %%F in (KageLink.exe KagePilotDojo.exe KagePilotRound.exe) do if exist "%~dp0build_output\%%F" del /q "%~dp0build_output\%%F"

"%BUILD_VENV%\Scripts\pyinstaller.exe" --noconfirm --clean --distpath "%~dp0build_output" --workpath "%~dp0build\KageLink" "%~dp0KageLink.spec"
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\pyinstaller.exe" --noconfirm --clean --distpath "%~dp0build_output" --workpath "%~dp0build\KagePilotDojo" "%~dp0KagePilotDojo.spec"
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\pyinstaller.exe" --noconfirm --clean --distpath "%~dp0build_output" --workpath "%~dp0build\KagePilotRound" "%~dp0KagePilotRound.spec"
if errorlevel 1 goto :error

for %%F in (KageLink.exe KagePilotDojo.exe KagePilotRound.exe) do if not exist "%~dp0build_output\%%F" goto :error
"%~dp0build_output\KagePilotDojo.exe" --help >nul
if errorlevel 1 goto :error
"%~dp0build_output\KagePilotRound.exe" --help >nul
if errorlevel 1 goto :error

call :FindISCC
if not defined ISCC (
  echo Inno Setup nao encontrado. Instalando automaticamente...
  where winget >nul 2>nul
  if not errorlevel 1 winget install --id JRSoftware.InnoSetup -e -s winget --silent --accept-source-agreements --accept-package-agreements
  call :FindISCC
)
if not defined ISCC (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_inno_setup.ps1"
  call :FindISCC
)
if not defined ISCC (
  echo [ERRO] Inno Setup nao foi localizado.
  pause
  exit /b 1
)

echo [6/6] Compilando o instalador final...
"!ISCC!" "%~dp0KageLink_PC_Agent.iss"
if errorlevel 1 goto :error

set "OUTPUT=%~dp0output\KageLink-PC-Agent-Setup-v3.5.1.exe"
if not exist "%OUTPUT%" goto :error

echo.
echo ================================================================
echo INSTALADOR CRIADO COM SUCESSO
echo %OUTPUT%
echo ================================================================
explorer /select,"%OUTPUT%"
pause
exit /b 0

:FindPython
set "PYTHON_EXE="
for /f "delims=" %%P in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
exit /b 0

:FindISCC
set "ISCC="
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
exit /b 0

:error
echo.
echo [ERRO] Nao foi possivel concluir a criacao do instalador.
echo A pasta de compilacao foi mantida para diagnostico.
pause
exit /b 1
