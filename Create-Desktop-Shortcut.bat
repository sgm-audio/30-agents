@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "DESKTOP=%USERPROFILE%\Desktop"
set "LINK=%DESKTOP%\30 Agents.lnk"

if exist "%~dp0dist\30-Agents.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut('%LINK%'); $sc.TargetPath='%~dp0dist\30-Agents.exe'; $sc.Arguments='--start --open'; $sc.WorkingDirectory='%~dp0'; $sc.Description='30 Agents'; $sc.Save(); Write-Host 'Created %LINK% (exe)'"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut('%LINK%'); $sc.TargetPath='%~dp0Start-Agents.bat'; $sc.WorkingDirectory='%~dp0'; $sc.Description='30 Agents'; $sc.Save(); Write-Host 'Created %LINK% (bat). Run Build-Exe.bat for a real .exe.'"
)

echo.
pause
