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

rem Optional speaker labels: older private environments get the extra component once. A failed install only turns
rem that feature off and leaves a marker so it is not retried on every start; delete .venv\.no-speakers to try again.
if exist ".venv\.no-speakers" goto :speakers_done
".venv\Scripts\python.exe" -c "import sherpa_onnx, numpy" >nul 2>nul
if not errorlevel 1 goto :speakers_done
echo Installing the optional speaker-labelling component, one time...
".venv\Scripts\python.exe" -m pip install -q -e ".[speakers]"
if errorlevel 1 (
  echo Speaker labels will be unavailable because the install failed. Delete .venv\.no-speakers to try again.
  type nul > ".venv\.no-speakers"
)
:speakers_done

where ffmpeg >nul 2>nul
if errorlevel 1 echo WARNING: ffmpeg was not found on PATH. Install it first ^(see README^), otherwise cutting will fail.

".venv\Scripts\python.exe" -m podclip.cli web
pause
exit /b 0

:fail
echo Setup failed. See the messages above.
pause
exit /b 1
