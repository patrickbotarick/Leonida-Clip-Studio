@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\configurar.ps1" -DownloadFFmpeg
if errorlevel 1 pause
endlocal
