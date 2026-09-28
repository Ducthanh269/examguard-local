@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".runtime\Scripts\python.exe" (
  py -3.12 -m venv .runtime
  if errorlevel 1 goto failed
)
".runtime\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".runtime\Scripts\python.exe" -m examguard download-models
if errorlevel 1 goto failed
".runtime\Scripts\python.exe" -m examguard doctor
if errorlevel 1 goto failed
echo Ready. Double-click START.cmd.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.12 from python.org and try again. See the message above.
pause
exit /b 1
