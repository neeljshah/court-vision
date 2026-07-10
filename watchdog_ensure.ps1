<#
.SYNOPSIS
    Bottom-turtle failsafe: relaunch watchdog_autostart.ps1 if it is not running.

.DESCRIPTION
    watchdog_autostart.ps1 keeps the supervisor alive; NBA-AI-Stack-Autostart
    (at-logon task) starts the watchdog after a reboot+logon. But a watchdog
    that CRASHES mid-session (no reboot) had no relauncher -- this script is
    that relauncher, run every 15 min by the NBA-AI-Watchdog-Ensure scheduled
    task (registered 2026-07-10 for unattended weekend running).

    SINGLETON-SAFE: exits immediately if any watchdog_autostart.ps1 process is
    already alive, so the 15-min cadence can never stack duplicates (the
    2026-06-25 duplicate-supervisor lesson). Every relaunch is logged to
    logs\watchdog_autostart.log so the monitoring pulse sees it.
#>
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG = Join-Path $ROOT "logs\watchdog_autostart.log"

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "watchdog_autostart\.ps1" -and $_.ProcessId -ne $PID }
if ($existing) { exit 0 }

$line = "{0} [ENSURE] watchdog_autostart.ps1 NOT RUNNING -- relaunching (watchdog_ensure.ps1)" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
try { Add-Content -Path $LOG -Value $line -ErrorAction SilentlyContinue } catch { }

Start-Process -FilePath (Get-Command powershell.exe).Source `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                    "-File", (Join-Path $ROOT "watchdog_autostart.ps1")) `
    -WorkingDirectory $ROOT -WindowStyle Hidden | Out-Null
exit 0
