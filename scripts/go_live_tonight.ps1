<#
.SYNOPSIS
    One-command "go-live tonight" launcher for the NBA AI live stack.

.DESCRIPTION
    Brings up the four live-night processes in the correct order, verifies
    each is healthy, and prints a summary table.

    Processes managed (in launch order):
        1. live_inplay_daemon.py        --> drives in-play prediction ledger
        2. capture_closing_lines.py     --> fires Pinnacle close snapshots
        3. closing_capture_watchdog.py  --> respawns (2) if it dies
        4. pinnacle_scraper.py          --> (optional) pre-tip 5-min cadence

    Each child is launched with Start-Process (detached, hidden window),
    stdout/stderr redirected to logs/<name>.log + logs/<name>.err.

.PARAMETER Date
    Slate date (YYYY-MM-DD). Passed to live_inplay_daemon --date.

.PARAMETER GameId
    NBA game_id label (e.g. 0042500315). Used for closing-line scripts.

.PARAMETER TipUTC
    Tip-off in UTC ISO8601 (e.g. 2026-05-27T00:35:00). The script schedules
    capture_closing_lines.py to fire at TipUTC-5min and TipUTC-1min, and the
    watchdog's deadline-utc is TipUTC-1min.

.PARAMETER WithPinnacle
    If set, also launches pinnacle_scraper.py on a 5-min interval for
    pre-tip line refresh.

.PARAMETER DryRun
    Print what WOULD be launched (full command line, log path, intended PID
    placeholder) but do not actually start anything. Does not kill anything.

.PARAMETER StopAll
    Kill any running instances of the four scripts (by command-line match)
    and exit. Mutually exclusive with the normal launch flow.

.EXAMPLE
    .\scripts\go_live_tonight.ps1 -Date 2026-05-26 -GameId 0042500315 -TipUTC 2026-05-27T00:35:00 -DryRun

.EXAMPLE
    .\scripts\go_live_tonight.ps1 -StopAll
#>

[CmdletBinding(DefaultParameterSetName = "Launch")]
param(
    [Parameter(ParameterSetName = "Launch")]
    [Parameter(ParameterSetName = "DryRun")]
    [string]$Date = (Get-Date -Format "yyyy-MM-dd"),

    [Parameter(ParameterSetName = "Launch")]
    [Parameter(ParameterSetName = "DryRun")]
    [string]$GameId,

    [Parameter(ParameterSetName = "Launch")]
    [Parameter(ParameterSetName = "DryRun")]
    [string]$TipUTC,

    [Parameter(ParameterSetName = "Launch")]
    [Parameter(ParameterSetName = "DryRun")]
    [switch]$WithPinnacle,

    [Parameter(ParameterSetName = "DryRun")]
    [switch]$DryRun,

    [Parameter(ParameterSetName = "StopAll")]
    [switch]$StopAll
)

$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------
# 0. Constants
# --------------------------------------------------------------------------
$ProjectRoot = "C:\Users\neelj\nba-ai-system"
$CondaEnv    = "basketball_ai"
$PythonExe   = "C:\Users\neelj\anaconda3\envs\$CondaEnv\python.exe"
$LogDir      = Join-Path $ProjectRoot "logs"
$ScriptsDir  = Join-Path $ProjectRoot "scripts"

# Process matchers (substring of the command line we'll grep for in WMI)
$ProcessMatchers = @(
    "live_inplay_daemon.py",
    "capture_closing_lines.py",
    "closing_capture_watchdog.py",
    "pinnacle_scraper.py"
)

# --------------------------------------------------------------------------
# 1. Helpers
# --------------------------------------------------------------------------
function Write-Section($title) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
}

function Assert-Cwd-Project {
    $cwd = (Get-Location).Path
    if ($cwd -ne $ProjectRoot) {
        Write-Host "[FATAL] cwd is '$cwd' but expected '$ProjectRoot'." -ForegroundColor Red
        Write-Host "Run this script from the project root." -ForegroundColor Red
        exit 2
    }
    Write-Host "[OK]    cwd is project root: $ProjectRoot" -ForegroundColor Green
}

function Assert-CondaEnv {
    # CONDA_DEFAULT_ENV is set when the env is activated.
    $active = $env:CONDA_DEFAULT_ENV
    if ($active -eq $CondaEnv) {
        Write-Host "[OK]    conda env '$CondaEnv' already active." -ForegroundColor Green
        return
    }
    Write-Host "[WARN]  conda env is '$active', not '$CondaEnv'." -ForegroundColor Yellow
    Write-Host "        Using full python path '$PythonExe' for child processes." -ForegroundColor Yellow
    if (-not (Test-Path $PythonExe)) {
        Write-Host "[FATAL] python.exe for env '$CondaEnv' not found at $PythonExe" -ForegroundColor Red
        exit 3
    }
}

function Assert-PythonImports {
    if ($DryRun) {
        Write-Host "[DRY ]  would import-test: live_engine, prop_pergame, win_probability" -ForegroundColor DarkGray
        return
    }
    $code = @'
import sys
try:
    import live_engine          # noqa: F401
    import prop_pergame         # noqa: F401
    import win_probability      # noqa: F401
    print("IMPORT_OK")
except Exception as e:
    print(f"IMPORT_FAIL: {type(e).__name__}: {e}")
    sys.exit(1)
'@
    $tmp = New-TemporaryFile
    Set-Content -Path $tmp -Value $code -Encoding utf8
    $out = & $PythonExe $tmp 2>&1
    Remove-Item $tmp -Force
    if ($out -match "IMPORT_OK") {
        Write-Host "[OK]    python imports clean (live_engine, prop_pergame, win_probability)" -ForegroundColor Green
    } else {
        Write-Host "[WARN]  python import probe: $out" -ForegroundColor Yellow
        Write-Host "        Continuing anyway -- some modules may be optional." -ForegroundColor Yellow
    }
}

function Get-RunningDaemons {
    # Returns an array of @{Name=...; Pid=...; CommandLine=...} for any of our matchers.
    $found = @()
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        if (-not $p.CommandLine) { continue }
        foreach ($m in $ProcessMatchers) {
            if ($p.CommandLine -like "*$m*") {
                $found += [pscustomobject]@{
                    Name        = $m
                    Pid         = $p.ProcessId
                    CommandLine = $p.CommandLine
                }
                break
            }
        }
    }
    return $found
}

function Stop-AllDaemons {
    Write-Section "STOP-ALL: killing stale daemons"
    $running = Get-RunningDaemons
    if (-not $running -or $running.Count -eq 0) {
        Write-Host "[OK]    no matching daemons running -- nothing to kill." -ForegroundColor Green
        return
    }
    foreach ($r in $running) {
        Write-Host ("[KILL]  pid={0,-6} name={1}" -f $r.Pid, $r.Name) -ForegroundColor Yellow
        if (-not $DryRun) {
            try {
                Stop-Process -Id $r.Pid -Force -ErrorAction Stop
                Write-Host "        terminated." -ForegroundColor DarkGray
            } catch {
                Write-Host "        FAILED to kill: $_" -ForegroundColor Red
            }
        }
    }
}

function New-LogPaths($baseName) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    return @{
        Out = Join-Path $LogDir "$baseName.$stamp.out.log"
        Err = Join-Path $LogDir "$baseName.$stamp.err.log"
    }
}

function Start-Daemon {
    param(
        [string]$Name,
        [string]$ScriptRelPath,
        [string[]]$ArgList
    )
    $logs = New-LogPaths $Name
    $scriptFull = Join-Path $ScriptsDir $ScriptRelPath
    $fullArgs = @("-u", $scriptFull) + $ArgList
    $cmdEcho = "$PythonExe " + ($fullArgs -join " ")

    Write-Host ("[LAUNCH] {0,-28} ->  {1}" -f $Name, $cmdEcho) -ForegroundColor Cyan
    Write-Host ("         stdout -> {0}" -f $logs.Out) -ForegroundColor DarkGray
    Write-Host ("         stderr -> {0}" -f $logs.Err) -ForegroundColor DarkGray

    if ($DryRun) {
        return [pscustomobject]@{
            Name    = $Name
            Pid     = "(dry-run)"
            LogOut  = $logs.Out
            LogErr  = $logs.Err
            CmdLine = $cmdEcho
        }
    }

    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

    $proc = Start-Process -FilePath $PythonExe `
        -ArgumentList $fullArgs `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logs.Out `
        -RedirectStandardError  $logs.Err `
        -PassThru
    return [pscustomobject]@{
        Name    = $Name
        Pid     = $proc.Id
        LogOut  = $logs.Out
        LogErr  = $logs.Err
        CmdLine = $cmdEcho
    }
}

function Test-DaemonAlive($result) {
    if ($DryRun) { return "DRY" }
    $p = Get-Process -Id $result.Pid -ErrorAction SilentlyContinue
    if (-not $p) { return "DEAD" }
    # Probe: log file exists + has any bytes OR errlog has nothing fatal.
    $okSig = $false
    if (Test-Path $result.LogOut) {
        $bytes = (Get-Item $result.LogOut).Length
        if ($bytes -gt 0) { $okSig = $true }
    }
    if ($okSig) { return "OK" } else { return "ALIVE_NO_LOG" }
}

function Compute-TipOffsets {
    if (-not $TipUTC) { return $null }
    try {
        $tip = [datetime]::Parse($TipUTC, $null, [System.Globalization.DateTimeStyles]::AssumeUniversal -bor [System.Globalization.DateTimeStyles]::AdjustToUniversal)
    } catch {
        Write-Host "[FATAL] could not parse -TipUTC '$TipUTC' as ISO8601." -ForegroundColor Red
        exit 4
    }
    $minus5 = $tip.AddMinutes(-5)
    $minus1 = $tip.AddMinutes(-1)
    return @{
        Tip       = $tip
        TipMinus5 = $minus5.ToString("yyyy-MM-ddTHH:mm:ss")
        TipMinus1 = $minus1.ToString("yyyy-MM-ddTHH:mm:ss")
    }
}

# --------------------------------------------------------------------------
# 2. -StopAll short-circuit
# --------------------------------------------------------------------------
if ($StopAll) {
    Assert-Cwd-Project
    Stop-AllDaemons
    Write-Host ""
    Write-Host "[DONE]  stop-all complete." -ForegroundColor Green
    exit 0
}

# --------------------------------------------------------------------------
# 3. Pre-flight
# --------------------------------------------------------------------------
Write-Section "PRE-FLIGHT"
Assert-Cwd-Project
Assert-CondaEnv
Assert-PythonImports

# --------------------------------------------------------------------------
# 4. Kill stale instances (always start fresh)
# --------------------------------------------------------------------------
Write-Section "KILL STALE INSTANCES"
$existing = Get-RunningDaemons
if ($existing.Count -gt 0) {
    Write-Host "[INFO]  found $($existing.Count) existing daemon process(es):" -ForegroundColor Yellow
    foreach ($r in $existing) {
        Write-Host ("        pid={0,-6} name={1}" -f $r.Pid, $r.Name) -ForegroundColor Yellow
    }
    if ($DryRun) {
        Write-Host "[DRY ]  would kill all of the above." -ForegroundColor DarkGray
    } else {
        foreach ($r in $existing) {
            try {
                Stop-Process -Id $r.Pid -Force -ErrorAction Stop
                Write-Host "[KILL]  pid=$($r.Pid) terminated." -ForegroundColor DarkGray
            } catch {
                Write-Host "[WARN]  could not kill pid=$($r.Pid): $_" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "[OK]    no stale daemons -- clean launch." -ForegroundColor Green
}

# --------------------------------------------------------------------------
# 5. Build launch plan
# --------------------------------------------------------------------------
Write-Section "LAUNCH PLAN"

$offsets = Compute-TipOffsets

$launches = New-Object System.Collections.Generic.List[object]

# 5.1 live_inplay_daemon
$inplayArgs = @(
    "--interval-min", "5",
    "--auto-stop-iters", "0",
    "--trigger-alerts"
)
if ($Date) { $inplayArgs += @("--date", $Date) }
$launches.Add([pscustomobject]@{
    Name = "live_inplay_daemon"
    Rel  = "live_inplay_daemon.py"
    Args = $inplayArgs
    NeedsGameId = $false
})

# 5.2 capture_closing_lines (needs game-id + tip)
if ($GameId -and $offsets) {
    $launches.Add([pscustomobject]@{
        Name = "capture_closing_lines"
        Rel  = "capture_closing_lines.py"
        Args = @(
            "--game-id",    $GameId,
            "--at-utc",     $offsets.TipMinus5,
            "--then-at-utc",$offsets.TipMinus1
        )
        NeedsGameId = $true
    })
    # 5.3 closing_capture_watchdog
    $launches.Add([pscustomobject]@{
        Name = "closing_capture_watchdog"
        Rel  = "closing_capture_watchdog.py"
        Args = @(
            "--game-id",      $GameId,
            "--at-utc",       $offsets.TipMinus5,
            "--then-at-utc",  $offsets.TipMinus1,
            "--deadline-utc", $offsets.TipMinus1
        )
        NeedsGameId = $true
    })
} else {
    Write-Host "[SKIP]  capture_closing_lines + watchdog (need -GameId AND -TipUTC)" -ForegroundColor Yellow
}

# 5.4 pinnacle_scraper (optional)
if ($WithPinnacle) {
    $launches.Add([pscustomobject]@{
        Name = "pinnacle_scraper"
        Rel  = "pinnacle_scraper.py"
        Args = @("--interval-min", "5")
        NeedsGameId = $false
    })
}

Write-Host ""
Write-Host "Resolved parameters:" -ForegroundColor Cyan
Write-Host ("  Date        = {0}" -f $Date)
Write-Host ("  GameId      = {0}" -f ($GameId   | ForEach-Object { if ($_) { $_ } else { "(unset)" } }))
Write-Host ("  TipUTC      = {0}" -f ($TipUTC   | ForEach-Object { if ($_) { $_ } else { "(unset)" } }))
if ($offsets) {
    Write-Host ("  Tip-5 (UTC) = {0}" -f $offsets.TipMinus5)
    Write-Host ("  Tip-1 (UTC) = {0}" -f $offsets.TipMinus1)
}
Write-Host ("  WithPinnacle= {0}" -f $WithPinnacle)
Write-Host ("  DryRun      = {0}" -f $DryRun)

# --------------------------------------------------------------------------
# 6. Launch loop
# --------------------------------------------------------------------------
Write-Section "LAUNCHING"
$results = New-Object System.Collections.Generic.List[object]
foreach ($plan in $launches) {
    $res = Start-Daemon -Name $plan.Name -ScriptRelPath $plan.Rel -ArgList $plan.Args
    $results.Add($res)
    if (-not $DryRun) { Start-Sleep -Seconds 2 }  # stagger so logs are obvious
}

# --------------------------------------------------------------------------
# 7. Health probe (wait 30s, check each PID + log tail)
# --------------------------------------------------------------------------
Write-Section "HEALTH PROBE"
if ($DryRun) {
    Write-Host "[DRY ]  would sleep 30s and probe each PID + tail log for activity." -ForegroundColor DarkGray
} else {
    Write-Host "Waiting 30s for daemons to settle..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 30
}

# --------------------------------------------------------------------------
# 8. Summary table
# --------------------------------------------------------------------------
Write-Section "SUMMARY"
$rows = foreach ($r in $results) {
    [pscustomobject]@{
        Name   = $r.Name
        Pid    = $r.Pid
        Status = Test-DaemonAlive $r
        Log    = $r.LogOut
    }
}
$rows | Format-Table -AutoSize | Out-Host

Write-Host ""
if ($DryRun) {
    Write-Host "[DRY-RUN COMPLETE] no processes were started or killed." -ForegroundColor Magenta
} else {
    $bad = @($rows | Where-Object { $_.Status -notin @("OK", "ALIVE_NO_LOG", "DRY") })
    if ($bad.Count -eq 0) {
        Write-Host "[GO-LIVE READY] all $($rows.Count) daemons alive." -ForegroundColor Green
    } else {
        Write-Host "[DEGRADED] $($bad.Count) daemon(s) failed to start -- check logs above." -ForegroundColor Red
        exit 1
    }
}
