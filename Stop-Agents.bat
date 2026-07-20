@echo off
setlocal EnableExtensions
title Stop 30-Agent System
cd /d "%~dp0"

echo Stopping 30-Agent API on port 8000...

REM Kill anything listening on 8000 (the uvicorn server)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  echo Killing PID %%P
  taskkill /PID %%P /F >nul 2>&1
)

REM Also stop minimized window titled "30-Agents API" if still around
taskkill /FI "WINDOWTITLE eq 30-Agents API*" /F >nul 2>&1

echo Done.
echo Chat UI will no longer respond until you run Start-Agents.bat again.
pause
