@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Setup is incomplete. Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py
echo.
echo The bot stopped. Review logs\ffcu.log if this was unexpected.
pause
