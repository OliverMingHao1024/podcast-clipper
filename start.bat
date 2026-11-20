@echo off
rem Double-click to open the podclip browser UI. Everything runs on this computer.
setlocal
cd /d "%~dp0"

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating a private Python environment and downloading components from PyPI.
  echo This happens once and can take a few minutes...
  python -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install -q -e ".[asr]" || goto :fail
)

where ffmpeg >nul 2>nul
if errorlevel 1 echo WARNING: ffmpeg was not found on PATH. Install it first ^(see README^), otherwise cutting will fail.

".venv\Scripts\python.exe" -m podclip.cli web
pause
exit /b 0

:fail
echo Setup failed. See the messages above.
pause
exit /b 1
