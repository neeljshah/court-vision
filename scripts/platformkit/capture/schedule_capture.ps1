# schedule_capture.ps1 -- N-CLV-005b: register the daily NBA capture as a
# Windows scheduled task (mirrors the CourtVisionBot pattern in
# scripts/bot_guards/bot_go.py + scripts/bot_cycle.ps1).
#
# capture_nba.py already no-ops cleanly on an off day (games_found=0), so the
# task just fires once daily -- no separate "is there a game today" calendar
# check is needed here.
#
# KNOWN CONSTRAINT (2026-07-05): `schtasks /Create` needs an ELEVATED shell.
# A Limited (non-admin) PowerShell gets "Access is denied" from schtasks, not
# a useful message. This script detects that up front and prints the exact
# command to run instead of registering -- it NEVER attempts a self-elevation
# relaunch (registering unattended persistence is a human action, not
# something the bot does on its own -- see .planning/platform/human-gates.md).
#
# Usage (from an elevated PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\platformkit\capture\schedule_capture.ps1
#
# Usage (non-elevated -- proves the detection path, registers nothing):
#   powershell -ExecutionPolicy Bypass -File scripts\platformkit\capture\schedule_capture.ps1

$ErrorActionPreference = 'Stop'

$TaskName = 'CourtVision_CaptureNBA'
$Proj     = 'C:\Users\neelj\nba-ai-system'
$Python   = 'C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe'
$Script   = Join-Path $Proj 'scripts\platformkit\capture\capture_nba.py'
$StartTime = '09:00'   # local time, ahead of the earliest NBA tip-off

$scriptPath = $MyInvocation.MyCommand.Path

# ---------------------------------------------------------------------------
# 1. Elevation check -- schtasks /Create silently fails ("Access is denied")
#    under a Limited (non-admin) shell. Detect it and tell the human the
#    exact elevated command instead of guessing / retrying.
# ---------------------------------------------------------------------------
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isElevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isElevated) {
    Write-Host '[schedule_capture] NOT elevated -- schtasks /Create would fail with Access denied.'
    Write-Host '[schedule_capture] This script never self-elevates (task registration is a human action).'
    Write-Host ''
    Write-Host '[schedule_capture] To register the task, open PowerShell as Administrator and run:'
    Write-Host "    powershell -ExecutionPolicy Bypass -File `"$scriptPath`""
    Write-Host ''
    Write-Host '[schedule_capture] Detection-only run complete. No task was registered.'
    exit 0
}

# ---------------------------------------------------------------------------
# 2. Elevated path -- register the daily task.
# ---------------------------------------------------------------------------
$taskRun = "`"$Python`" `"$Script`""

$existing = schtasks /Query /TN $TaskName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[schedule_capture] Task '$TaskName' already exists -- updating trigger/action."
    schtasks /Change /TN $TaskName /TR $taskRun /ST $StartTime | Out-Null
} else {
    schtasks /Create /SC DAILY /TN $TaskName /TR $taskRun /ST $StartTime /F | Out-Null
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[schedule_capture] ERROR: schtasks failed even though the shell is elevated."
    exit 1
}

Write-Host "[schedule_capture] '$TaskName' registered: runs daily at $StartTime -> $taskRun"
Write-Host '[schedule_capture] capture_nba.py no-ops on days with no games -- safe to run every day.'
