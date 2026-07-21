@echo off
setlocal
cd /d "%~dp0"
echo Stopping 30 Agents on port 8000...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
  taskkill /PID %%P /F >nul 2>&1
)
taskkill /FI "WINDOWTITLE eq 30 Agents*" /F >nul 2>&1
taskkill /FI "IMAGENAME eq 30-Agents.exe" /F >nul 2>&1
echo Stopped.
timeout /t 2 >nul
