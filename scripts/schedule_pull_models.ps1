<#
.SYNOPSIS
  Registers an hourly Windows Scheduled Task that runs scripts/pull_models.py
  so missing/interrupted Ollama model pulls get retried automatically.

.DESCRIPTION
  Idempotent: unregisters any existing task with the same name before
  creating it, so re-running this script (e.g. after moving the repo) is
  safe.

.EXAMPLE
  .\scripts\schedule_pull_models.ps1
#>

$ErrorActionPreference = "Stop"

$TaskName = "30Agents-PullModels"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectRoot "scripts\pull_models.py"

if (-not (Test-Path $PythonExe)) {
    Write-Warning ("venv not found at {0} - create it first (python -m venv venv; pip install -r requirements.txt), then re-run this script." -f $PythonExe)
}

# Idempotent: remove any existing task with this name first.
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host ("Removing existing scheduled task '{0}'..." -f $TaskName)
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$quotedScriptPath = '"{0}"' -f $ScriptPath
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument $quotedScriptPath -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Hourly Ollama model pull/resume for the 30-Agent system" | Out-Null

Write-Host ("Scheduled task '{0}' registered - runs hourly via:" -f $TaskName)
Write-Host ("  {0} {1}" -f $PythonExe, $ScriptPath)
Write-Host ""
Write-Host "Manage it with:"
Write-Host ("  Get-ScheduledTask -TaskName '{0}' | Get-ScheduledTaskInfo" -f $TaskName)
Write-Host ("  Unregister-ScheduledTask -TaskName '{0}' -Confirm:`$false" -f $TaskName)
Write-Host ""
Write-Host "Equivalent one-liner via schtasks.exe (if you prefer not to use the ScheduledTasks module):"
$schtasksCmd = 'schtasks /Create /TN "{0}" /TR "\"{1}\" \"{2}\"" /SC HOURLY /F' -f $TaskName, $PythonExe, $ScriptPath
Write-Host ("  {0}" -f $schtasksCmd)
