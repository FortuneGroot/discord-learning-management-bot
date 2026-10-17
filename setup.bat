@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "FFCU_PYTHON=py -3.12"
) else (
  set "FFCU_PYTHON=python"
)
echo Creating the private Python environment...
%FFCU_PYTHON% -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
if not exist .env copy .env.example .env >nul
python scripts\initialize_database.py
if errorlevel 1 goto :error
echo.
echo Setup finished. Open .env in Notepad and enter your Discord settings.
echo Then double-click run_bot.bat.
pause
exit /b 0
:error
echo.
echo Setup did not finish. Read TROUBLESHOOTING.md, then try again.
pause
exit /b 1
