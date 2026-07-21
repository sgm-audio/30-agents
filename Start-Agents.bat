@echo off
setlocal EnableExtensions EnableDelayedExpansion
title 30 Agents
cd /d "%~dp0"

REM Prefer the real Windows app when built
if exist "%~dp0dist\30-Agents.exe" (
  start "" "%~dp0dist\30-Agents.exe" --start --open
  exit /b 0
)

REM Prefer GUI launcher (no console spam)
set "PY="
if exist "%~dp0venv\Scripts\pythonw.exe" set "PY=%~dp0venv\Scripts\pythonw.exe"
if not defined PY if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python not found. Install from https://python.org and check "Add to PATH".
  pause
  exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
  echo First run: creating environment...
  %PY% -m venv venv
  "%~dp0venv\Scripts\pip.exe" install -U pip
  "%~dp0venv\Scripts\pip.exe" install -r requirements.txt
  set "PY=%~dp0venv\Scripts\pythonw.exe"
)

start "" %PY% "%~dp0launcher\app.py" --start --open
exit /b 0
