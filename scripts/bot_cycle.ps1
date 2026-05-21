# CourtVision autonomous bot - one work cycle.
# Run by the 'CourtVisionBot' Windows scheduled task every 15 minutes while the task is ENABLED.
#   'bot go'   -> enables the task  (bot runs)
#   'bot stop' -> disables the task (bot stops, zero usage)
# Each cycle launches a fresh headless Claude Code that runs /workday-loop, ships a burst, exits.

$ErrorActionPreference = 'Continue'
$proj   = 'C:\Users\neelj\nba-ai-system'
$claude = 'C:\Users\neelj\AppData\Roaming\npm\claude.cmd'
$lock   = Join-Path $proj '.bot_state\cycle.lock'
$logdir = Join-Path $proj 'logs'
$log    = Join-Path $logdir 'bot_cycle.log'

Set-Location $proj
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory -Force -Path $logdir | Out-Null }

# Overlap guard: if a previous cycle is still running, skip this one.
# A lock older than 3h is treated as stale (crashed cycle) and ignored.
if (Test-Path $lock) {
    $age = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($age.TotalHours -lt 3) {
        "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] previous cycle still running - skipped" | Out-File -Append -Encoding utf8 $log
        return
    }
}
New-Item -ItemType File -Force -Path $lock | Out-Null

try {
    "`n===== cycle start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" | Out-File -Append -Encoding utf8 $log
    & $claude -p '/workday-loop' --dangerously-skip-permissions *>&1 | Out-File -Append -Encoding utf8 $log
    "===== cycle end   $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" | Out-File -Append -Encoding utf8 $log
}
finally {
    Remove-Item -Force $lock -ErrorAction SilentlyContinue
}
