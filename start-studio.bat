@echo off
rem Start Studio in the browser (http://127.0.0.1:7860). Close this window to stop the server.
title Studio (close this window to stop)
cd /d "%~dp0"
if "%STUDIO_PYTHON%"=="" (set "PY=python") else (set "PY=%STUDIO_PYTHON%")
"%PY%" -I "%~dp0studio\server.py"
if errorlevel 1 pause
