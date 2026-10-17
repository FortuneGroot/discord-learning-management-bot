@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag a .db backup file onto restore_database.bat.
  pause
  exit /b 1
)
echo STOP THE BOT before continuing.
set /p FFCU_CONFIRM=Type RESTORE to replace the current database: 
if /I not "%FFCU_CONFIRM%"=="RESTORE" exit /b 1
.venv\Scripts\python.exe scripts\restore_database.py "%~1" --yes
pause
