#
# ngrok_watchdog.ps1
#
# Self-healing watchdog for the ngrok tunnel on port 4040 (control API).
#
# Checks whether port 4040 has a listener every 30 seconds.
# After 3 consecutive misses (90s downtime), spawns a fresh ngrok
# process in a -NoExit PowerShell window pointing at port 3001.
#
# Safety: never spawns if an ngrok.exe process is already running.
# Never kills an existing ngrok that is still alive.
#
# Logs every check and every restart event to:
#   C:\Users\neelj\nba-ai-system\data\cache\ngrok_watchdog.log
#
# Launch via:  .\scripts\start_ngrok_watchdog.ps1
# Written in PowerShell (not Python) so it survives ngrok crashes.
# ASCII-only: no Unicode em-dashes or box-drawing chars (PS 5.1 safe).
#

$ErrorActionPreference = "Continue"

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
$LogFile       = "C:\Users\neelj\nba-ai-system\data\cache\ngrok_watchdog.log"
$NgrokExe      = "C:\Users\neelj\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
$NgrokPort     = 4040   # ngrok control API / web inspector
$TunnelTarget  = 3001   # port ngrok tunnels to
$PollSec       = 30
$MaxConsecFail = 3

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
function Write-Log {
    param([string]$Msg)
    $ts   = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line
    try {
        $dir = Split-Path $LogFile -Parent
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch {
        Write-Host "[WARN] Could not write to log: $_"
    }
}

function Test-NgrokPort {
    # Returns $true if port 4040 has an active listener, $false otherwise.
    try {
        $conn = Get-NetTCPConnection -LocalPort $NgrokPort -State Listen `
                    -ErrorAction SilentlyContinue | Select-Object -First 1
        return ($null -ne $conn)
    } catch {
        return $false
    }
}

function Test-NgrokProcess {
    # Returns $true if at least one ngrok.exe is running, $false otherwise.
    try {
        $procs = Get-CimInstance Win32_Process `
                     -Filter "Name='ngrok.exe'" `
                     -ErrorAction SilentlyContinue
        return ($null -ne $procs -and @($procs).Count -gt 0)
    } catch {
        return $false
    }
}

function Spawn-Ngrok {
    Write-Log "SPAWN: no ngrok listener on port $NgrokPort -- starting new ngrok tunnel -> $TunnelTarget"

    # Guard: skip if ngrok.exe is already alive (process exists but port not up yet, or starting)
    if (Test-NgrokProcess) {
        Write-Log "SPAWN: ngrok.exe process already exists -- skipping spawn to avoid duplicate"
        return
    }

    try {
        $cmdStr  = "Write-Host '=== ngrok tunnel ===' -ForegroundColor Cyan; "
        $cmdStr += "& '$NgrokExe' http $TunnelTarget"

        Start-Process powershell `
            -ArgumentList "-NoExit", "-Command", $cmdStr `
            -WindowStyle Normal
        Write-Log "SPAWN: ngrok respawn window launched (tunnel -> port $TunnelTarget)"
    } catch {
        Write-Log "SPAWN: FAILED to launch ngrok: $_"
    }
}

# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
Write-Log "WATCHDOG START: pid=$PID poll=${PollSec}s threshold=$MaxConsecFail consecutive misses"
Write-Log "WATCHDOG: watching port $NgrokPort (ngrok control API)"
Write-Log "WATCHDOG: log file = $LogFile"

$consecFail = 0

while ($true) {
    $up = $false
    try {
        $up = Test-NgrokPort
    } catch {
        $up = $false
    }

    if ($up) {
        if ($consecFail -gt 0) {
            Write-Log "CHECK OK: ngrok port $NgrokPort is UP (recovered after $consecFail consecutive miss(es))"
        } else {
            Write-Log "CHECK OK: ngrok port $NgrokPort is UP"
        }
        $consecFail = 0
    } else {
        $consecFail++
        Write-Log "CHECK FAIL [$consecFail/$MaxConsecFail]: no listener on port $NgrokPort"

        if ($consecFail -ge $MaxConsecFail) {
            Write-Log "RESTART TRIGGERED: $consecFail consecutive misses hit threshold of $MaxConsecFail"
            Spawn-Ngrok
            $consecFail = 0
            Write-Log "RESTART COMPLETE: watchdog resuming checks"
        }
    }

    Start-Sleep -Seconds $PollSec
}
