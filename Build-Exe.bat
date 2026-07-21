@echo off
setlocal EnableExtensions
title Build 30-Agents.exe
cd /d "%~dp0"

echo.
echo  Building 30-Agents.exe (one-file Windows app)
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [ERROR] Python not found.
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo [..] Creating venv...
  %PY% -m venv venv
)

set "VPY=%~dp0venv\Scripts\python.exe"
set "VPIP=%~dp0venv\Scripts\pip.exe"

echo [..] Installing PyInstaller...
"%VPIP%" install -q pyinstaller

echo [..] Building...
"%VPY%" -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name "30-Agents" ^
  --distpath "%~dp0dist" ^
  --workpath "%~dp0build\pyinstaller" ^
  --specpath "%~dp0build" ^
  --add-data "%~dp0launcher;launcher" ^
  "%~dp0launcher\app.py"

if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo.
echo  ========================================
echo   DONE:  dist\30-Agents.exe
echo  ========================================
echo.
echo  Double-click dist\30-Agents.exe
echo  Or run Create-Desktop-Shortcut.bat to pin it.
echo.
pause
