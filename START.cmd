@echo off
cd /d "%~dp0"
if exist "dist\ExamGuard\ExamGuard.exe" (
  echo Starting ExamGuard.exe...
  start "" "dist\ExamGuard\ExamGuard.exe"
) else (
  echo Starting from source...
  call scripts\START.cmd
)