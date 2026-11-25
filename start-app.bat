@echo off
rem Start Studio as a desktop app (pywebview window). Uses pythonw next to the selected Python when available.
cd /d "%~dp0"
if "%STUDIO_PYTHON%"=="" (set "PY=python") else (set "PY=%STUDIO_PYTHON%")
for %%I in ("%PY%") do set "PYW=%%~dpIpythonw.exe"
if exist "%PYW%" (start "" "%PYW%" -I "%~dp0studio\app.py") else (start "" "%PY%" -I "%~dp0studio\app.py")
