@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute Configurar Leonida Clip Studio.bat primeiro. Veja docs\INSTALL_WINDOWS.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\verificar.py
pause
endlocal
