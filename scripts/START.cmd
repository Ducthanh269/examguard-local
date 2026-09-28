@echo off
setlocal
cd /d "%~dp0"
if exist "dist\ExamGuard\ExamGuard.exe" (
  start "" "dist\ExamGuard\ExamGuard.exe"
  exit /b 0
)
if not exist ".runtime\Scripts\pythonw.exe" (
  echo Please run SETUP.cmd first.
  pause
  exit /b 1
)
start "" ".runtime\Scripts\pythonw.exe" "launch.py"