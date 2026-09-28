@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".runtime\Scripts\python.exe" (
  echo Please run SETUP.cmd first.
  pause
  exit /b 1
)
echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
echo.
echo === Building ExamGuard.exe (this may take several minutes) ===
".runtime\Scripts\python.exe" -m PyInstaller --noconfirm --clean examguard.spec
if errorlevel 1 goto failed
echo.
echo === Verifying output ===
if not exist "dist\ExamGuard\ExamGuard.exe" (
  echo Build did not produce ExamGuard.exe
  goto failed
)
if not exist "dist\ExamGuard\models\face_landmarker.task" (
  echo WARNING: face_landmarker.task missing from bundle
)
if not exist "dist\ExamGuard\models\yolox.onnx" (
  echo WARNING: yolox.onnx missing from bundle
)
echo.
echo === Build complete ===
echo Output: dist\ExamGuard\ExamGuard.exe
echo Run:    dist\ExamGuard\ExamGuard.exe
echo.
pause
exit /b 0
:failed
echo.
echo Build failed. See messages above.
pause
exit /b 1