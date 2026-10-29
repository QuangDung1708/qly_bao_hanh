@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Please install Python 3.12 from python.org and enable the Python launcher.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto :error
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo Open http://127.0.0.1:5000 in your browser. Press Ctrl+C to stop.
.venv\Scripts\python.exe app.py
if errorlevel 1 goto :error
exit /b 0
:error
echo Failed. Read the error above. No data has been reset.
pause
exit /b 1
