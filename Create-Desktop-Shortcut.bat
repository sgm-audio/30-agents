@echo off
REM Double-click helper: creates a Desktop shortcut to Start-Agents.bat
setlocal
cd /d "%~dp0"

set "TARGET=%~dp0Start-Agents.bat"
set "DESKTOP=%USERPROFILE%\Desktop"
set "LINK=%DESKTOP%\30-Agents.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $sc = $ws.CreateShortcut('%LINK%'); ^
   $sc.TargetPath = '%TARGET%'; ^
   $sc.WorkingDirectory = '%~dp0'; ^
   $sc.WindowStyle = 1; ^
   $sc.Description = 'Start 30-Agent System and open chat UI'; ^
   $sc.Save(); ^
   Write-Host 'Shortcut created:' '%LINK%'"

echo.
echo Double-click "30-Agents" on your Desktop next time.
pause
