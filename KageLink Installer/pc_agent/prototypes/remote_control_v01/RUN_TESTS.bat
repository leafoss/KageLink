@echo off
setlocal
cd /d "%~dp0"

if exist ".venv-remote\Scripts\python.exe" (
  set "PY=.venv-remote\Scripts\python.exe"
) else (
  set "PY=python.exe"
)

%PY% -m py_compile security.py capture.py input_win32.py remote_host.py
if errorlevel 1 goto fail
%PY% -m unittest discover -s tests -p "test_security.py" -v
if errorlevel 1 goto fail

echo.
echo Testes de seguranca aprovados. / Security tests passed.
pause
exit /b 0

:fail
echo.
echo Falha nos testes. / Tests failed.
pause
exit /b 1
