@echo off
rem Uninstall: stops Studio and removes the program, models and temporary files in this folder.
rem Personal data (private space, libraries, outputs, voices) is kept unless you confirm deleting it.
copy /y "%~dp0scripts\uninstall.ps1" "%TEMP%\studio-uninstall.ps1" >nul
cd /d "%TEMP%"
start "Uninstall Studio" powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\studio-uninstall.ps1" -Root "%~dp0."
exit
