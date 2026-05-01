@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0start-local.ps1" -All
if errorlevel 1 (
  echo.
  echo start-local failed. See the output above.
  pause
  exit /b 1
)
echo.
echo ERP Approval Agent Workbench startup command completed.
pause
