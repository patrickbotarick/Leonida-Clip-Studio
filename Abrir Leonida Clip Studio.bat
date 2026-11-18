@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title Leonida Clip Studio - BTRK Studio
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente ausente. Execute scripts\configurar.ps1 primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\launch.py"
if errorlevel 1 pause
endlocal
