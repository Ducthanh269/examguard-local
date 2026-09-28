@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
".runtime\Scripts\python.exe" -m unittest discover -s tests -v
pause
