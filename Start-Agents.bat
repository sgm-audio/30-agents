@echo off
setlocal EnableExtensions EnableDelayedExpansion
title 30-Agent System
cd /d "%~dp0"

echo.
echo  ========================================
echo   30-Agent System — starting...
echo  ========================================
echo.

REM Prefer py launcher, then python
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [ERROR] Python not found. Install Python 3 from https://python.org
  echo         Check "Add python.exe to PATH" during install.
  pause
  exit /b 1
)

if not exist "logs" mkdir logs
if not exist "data\chroma" mkdir data\chroma

REM Create venv if missing
if not exist "venv\Scripts\python.exe" (
  echo [..] Creating virtual environment...
  %PY% -m venv venv
  if errorlevel 1 (
    echo [ERROR] Could not create venv.
    pause
    exit /b 1
  )
)

set "VPY=%~dp0venv\Scripts\python.exe"
set "VPIP=%~dp0venv\Scripts\pip.exe"

REM Install deps if FastAPI missing
"%VPY%" -c "import fastapi,uvicorn,typer" >nul 2>&1
if errorlevel 1 (
  echo [..] Installing dependencies (first run only^)...
  "%VPIP%" install -U pip
  "%VPIP%" install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
  )
)

REM Start Redis via Docker if available and not already up
"%VPY%" -c "import socket;s=socket.socket();s.settimeout(1);s.connect(('127.0.0.1',6379));s.close()" >nul 2>&1
if errorlevel 1 (
  where docker >nul 2>&1
  if not errorlevel 1 (
    echo [..] Starting Redis container...
    docker start redis-agent >nul 2>&1
    if errorlevel 1 (
      docker run -d --name redis-agent --restart unless-stopped -p 6379:6379 redis:7-alpine >nul 2>&1
    )
  ) else (
    echo [WARN] Redis not running and Docker not found.
    echo       API will start anyway; some features need Redis.
  )
)

REM If already healthy, just open the UI
curl -sf --max-time 2 http://127.0.0.1:8000/api/health >nul 2>&1
if not errorlevel 1 (
  echo [ok] Already running — opening chat UI...
  start "" "http://127.0.0.1:8000/"
  echo.
  echo  Chat UI:  http://127.0.0.1:8000/
  echo  Stop with: Stop-Agents.bat
  echo.
  pause
  exit /b 0
)

echo [..] Starting API server...
start "30-Agents API" /MIN cmd /c ""%VPY%" "%~dp0main.py" serve >> "%~dp0logs\server.log" 2>&1"

echo [..] Waiting for API...
set /a TRIES=0
:waitloop
set /a TRIES+=1
curl -sf --max-time 2 http://127.0.0.1:8000/api/health >nul 2>&1
if not errorlevel 1 goto ready
if !TRIES! GEQ 40 goto fail
timeout /t 1 /nobreak >nul
goto waitloop

:ready
echo [ok] Ready.
echo.
echo  ========================================
echo   OPEN THIS:  http://127.0.0.1:8000/
echo  ========================================
echo.
echo  Type a task in the browser chat and hit Send.
echo  Stop later with Stop-Agents.bat
echo.
start "" "http://127.0.0.1:8000/"
pause
exit /b 0

:fail
echo [ERROR] API did not start. Last log lines:
echo.
powershell -NoProfile -Command "if (Test-Path 'logs\server.log') { Get-Content 'logs\server.log' -Tail 30 }"
echo.
pause
exit /b 1
