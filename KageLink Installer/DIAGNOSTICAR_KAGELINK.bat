@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================================
echo KAGELINK - DIAGNOSTICO DE INICIALIZACAO
echo ================================================================
echo.

set "APP=%LocalAppData%\KageLink PC Agent"
set "LOG=%APP%\logs\startup_error.log"

echo Pasta instalada:
echo %APP%
echo.

if exist "%APP%\KageLink.exe" (
    echo KageLink.exe: ENCONTRADO
) else (
    echo KageLink.exe: NAO ENCONTRADO
)

if exist "%APP%\config.json" (
    echo config.json: ENCONTRADO
) else (
    echo config.json: ainda nao criado
)

echo.
tasklist /FI "IMAGENAME eq KageLink.exe"
echo.

if exist "%LOG%" (
    echo Abrindo o log de erro:
    echo %LOG%
    start "" notepad.exe "%LOG%"
) else (
    echo Nenhum startup_error.log foi encontrado.
    echo Tentando abrir o KageLink agora...
    if exist "%APP%\KageLink.exe" start "" "%APP%\KageLink.exe"
)

echo.
pause
