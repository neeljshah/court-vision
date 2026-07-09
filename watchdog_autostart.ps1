<#
.SYNOPSIS
    Outer watchdog: keep boot.ps1's SUPERVISOR alive so power-on == always-live.

.DESCRIPTION
    boot.ps1 launches the Python supervisor (which owns + auto-restarts every
    child). This watchdog sits ABOVE that: if the supervisor PROCESS itself dies
    (crash / OOM / manual kill), the watchdog re-runs boot.ps1 to bring it back,
    with capped exponential backoff between relaunches. It is the second safety
    net registered by register_autostart.ps1 so a single supervisor death never
    leaves the box dark.

    ESCALATION, not silent failure: every (re)launch + every supervisor death is
    appended to logs\watchdog_autostart.log with a timestamp, so an operator can
    see the restart history at 2am. After too many rapid deaths it backs off (it
    does NOT hammer) and keeps logging RED until the supervisor stays up.

    SAFETY: never flips a flag, never enables real money. It only (re)runs
    boot.ps1, which itself runs the governance preflight first. -DryRun prints
    the plan and exits without launching anything.

.PARAMETER NoUI
    Pass -NoUI through to boot.ps1 (headless backend profile).
.PARAMETER DryRun
    Print what the watchdog WOULD do (boot command + cadence) and exit.
.PARAMETER MaxLoops
    Bound the watch loop (for testing). Default: run forever.
#>
[CmdletBinding()]
param(
    [switch]$NoUI,
    [switch]$DryRun,
    [int]$MaxLoops = 0,
    [int]$PollSeconds = 15,
    # C1: a WEDGED run_forever (process alive, supervise loop stopped ticking)
    # is treated as DOWN once its self-heartbeat is older than this many seconds.
    #
    # 2026-07-04 ROBUSTNESS FIX (LANE 1, root-cause confirmed in
    # data/frontend/ops/api_crash_20260704_rootcause.json + 36+ WEDGED events
    # in logs/watchdog_autostart.log since 2026-06-23): the OLD 90s threshold
    # had ~ZERO margin. supervise() probes every ProcSpec serially each tick;
    # each TCP/HTTP probe's own timeout is 2.0s (supervisor/health.py
    # _DEFAULT_TIMEOUT), and the fleet is 41 specs as of this fix -- so a tick
    # where several probes each run close to their timeout under heavy CPU
    # load can approach 82s of serial probe time alone, before sleep/beat
    # overhead, against a 90s cutoff. That is why the wedge-storm recurred in
    # bursts with ~103-130s inter-wedge gaps (just past 90s each time) whenever
    # fleet CPU was heavy (e.g. a parallel Sonnet fleet sprint).
    #
    # The supervisor-side fix (supervisor/_beat_thread.py, this same change)
    # decouples the self-heartbeat from supervise()'s own duration via a
    # background thread beating every 20s regardless of tick length, which
    # should make 90s unnecessary in practice -- but 300s is kept as a
    # DEFENSIVE outer bound: even a supervisor that somehow loses its beat
    # thread (e.g. an unforeseen exception path) gets ~15x the 20s beat
    # cadence margin before the watchdog calls it wedged, while a GENUINELY
    # wedged process (loop stopped, thread dead too) still recovers within
    # 5 minutes -- an acceptable bound for an unattended fleet, and far
    # better than a false-positive fleet-wide reboot storm every ~2 minutes.
    [int]$SupervisorStaleSeconds = 300
)

# 2026-07-04 boot-initiator stamping (LANE 1 robustness fix): the supervisor's
# status doc includes a "boot_initiator" field so an operator (or a future
# root-cause read) can see WHO/WHAT launched the currently-running supervisor
# without reconstructing it from log timestamps. supervisor/__main__.py reads
# this from the process env at each refresh_status() call.
$env:NBA_AI_BOOT_INITIATOR = "watchdog_autostart"

# Serve the PRODUCTION webapp dashboard on autostart (parity with go.ps1).
# stack_specs.py reads these from the parent env at import; boot.ps1 inherits this
# process env, so m1_ui launches webapp/ via `npm run start` instead of the legacy
# court-visions dev server. Only set if the operator has not already pinned them.
if (-not $env:NBA_AI_UI_DIR) { $env:NBA_AI_UI_DIR = "webapp" }
if (-not $env:NBA_AI_UI_CMD) { $env:NBA_AI_UI_CMD = "npm run start" }

$ErrorActionPreference = "Continue"
$ROOT   = "C:\Users\neelj\nba-ai-system"
$BOOT   = Join-Path $ROOT "boot.ps1"
$LOGDIR = Join-Path $ROOT "logs"
$LOG    = Join-Path $LOGDIR "watchdog_autostart.log"
# C1: the supervisor stamps its OWN liveness here every supervise tick.
$SV_HB  = Join-Path $ROOT "data\cache\daemon_heartbeats\m9_supervisor.txt"
New-Item -ItemType Directory -Force -Path $LOGDIR | Out-Null

$bootArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BOOT)
# 2026-07-10 USER DIRECTIVE: frontend OFF for the time being -- always boot the
# headless "backend" profile (full fleet, no m1_ui / port 3000). To restore the
# UI: delete the next line's forced flag and run .\go.ps1 manually.
$NoUI = $true
if ($NoUI) { $bootArgs += "-NoUI" }

function Write-WLog([string]$level, [string]$msg) {
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $level, $msg
    Write-Output $line
    try { Add-Content -Path $LOG -Value $line -ErrorAction SilentlyContinue } catch { }
}

function Test-SupervisorAlive {
    $p = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "-m supervisor\b" } |
        Select-Object -First 1
    return ($null -ne $p)
}

# C1: is the supervisor's self-heartbeat FRESH? Returns $true only when the
# heartbeat file exists AND was stamped within $SupervisorStaleSeconds. A missing
# file (just booted, not yet beating) or an old one (wedged run_forever) returns
# $false. The heartbeat is a UTC ISO-8601 stamp (e.g. 2026-06-11T20:25:19Z), the
# same format every other daemon heartbeat uses.
function Test-SupervisorTicking {
    if (-not (Test-Path $SV_HB)) { return $false }
    try {
        $raw = (Get-Content -Path $SV_HB -Raw -ErrorAction SilentlyContinue)
        if (-not $raw) { return $false }
        $stamp = [datetimeoffset]::Parse($raw.Trim()).UtcDateTime
        $ageSec = ([datetime]::UtcNow - $stamp).TotalSeconds
        return ($ageSec -ge 0 -and $ageSec -le $SupervisorStaleSeconds)
    } catch {
        # Unparseable heartbeat -> cannot prove freshness -> treat as not-ticking.
        return $false
    }
}

function Start-Boot {
    Write-WLog "INFO" "launching boot.ps1 (governance preflight -> supervisor)"
    Start-Process -FilePath (Get-Command powershell.exe).Source `
        -ArgumentList $bootArgs -WorkingDirectory $ROOT -WindowStyle Hidden | Out-Null
}

# C1+: a genuinely WEDGED supervisor (alive but its run_forever loop stopped
# ticking) still HOLDS the OS single-instance lock, so a fresh boot would refuse
# to start a duplicate and the wedge would never recover. Kill the wedged
# instance FIRST; the OS releases its lock, the relaunch acquires it cleanly, and
# the new boot's reconcile_survivors() reaps the orphaned children. This is only
# reached on a real wedge -- a booting supervisor now stamps its heartbeat
# immediately, so it is never mistaken for wedged.
function Stop-WedgedSupervisor {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "-m supervisor\b" } |
        ForEach-Object {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                Write-WLog "WARN" "killed WEDGED supervisor pid=$($_.ProcessId) (release single-instance lock for a clean relaunch)"
            } catch { }
        }
    Start-Sleep -Seconds 2  # let the OS release the lock before relaunch
}

if ($DryRun) {
    Write-Output ""
    Write-Output "watchdog_autostart -- DRY RUN (nothing launched)"
    Write-Output "================================================"
    Write-Output "Boot cmd  : powershell $($bootArgs -join ' ')"
    Write-Output "Poll      : every $PollSeconds s; re-run boot.ps1 if supervisor DEAD or WEDGED"
    Write-Output "Liveness  : process-exists AND self-heartbeat fresh (< ${SupervisorStaleSeconds}s)"
    Write-Output "Heartbeat : $SV_HB"
    Write-Output "Backoff   : capped exponential on repeated rapid deaths"
    Write-Output "Log       : $LOG"
    Write-Output "Governance: boot.ps1 runs M10 preflight first; real money default-DENY"
    Write-Output ""
    Write-Output "Supervisor currently alive  : $([bool](Test-SupervisorAlive))"
    Write-Output "Supervisor currently ticking: $([bool](Test-SupervisorTicking))"
    return
}

Write-WLog "INFO" "watchdog started (poll=${PollSeconds}s, NoUI=$NoUI)"
$deaths = 0
$loops  = 0
while ($true) {
    $alive   = Test-SupervisorAlive
    # C1: a process that EXISTS but has stopped ticking (stale self-heartbeat) is
    # WEDGED -- the old process-exists-only check read it green forever. Treat an
    # alive-but-stale supervisor exactly like a dead one (re-run boot.ps1). The
    # supervisor's reconcile_survivors() makes a re-boot idempotent (it reaps the
    # wedged instance + its children before relaunching).
    $ticking = if ($alive) { Test-SupervisorTicking } else { $false }
    $needsBoot = (-not $alive) -or (-not $ticking)
    if ($needsBoot) {
        $deaths++
        # Capped exponential backoff: 0,2,4,8,... up to 60s before relaunch.
        $backoff = [Math]::Min(60, [Math]::Pow(2, [Math]::Max(0, $deaths - 1)))
        $why = if (-not $alive) { "process DOWN" } else { "ALIVE but WEDGED (stale heartbeat > ${SupervisorStaleSeconds}s)" }
        if ($deaths -gt 1) {
            Write-WLog "RED" "supervisor $why (event #$deaths) -- backoff ${backoff}s then relaunch"
            Start-Sleep -Seconds $backoff
        } else {
            Write-WLog "WARN" "supervisor $why -- (re)starting it"
        }
        # A wedged (alive-but-stale) supervisor holds the single-instance lock;
        # kill it first so the relaunch can acquire the lock. A DOWN supervisor
        # already released its lock, so no kill is needed there.
        if ($alive -and (-not $ticking)) { Stop-WedgedSupervisor }
        Start-Boot
        Start-Sleep -Seconds 10  # give boot.ps1 time to spawn the supervisor
    } else {
        if ($deaths -gt 0) { Write-WLog "GREEN" "supervisor back up + ticking; resetting death counter" }
        $deaths = 0
    }
    $loops++
    if ($MaxLoops -gt 0 -and $loops -ge $MaxLoops) {
        Write-WLog "INFO" "MaxLoops=$MaxLoops reached -- watchdog exiting (test mode)"
        break
    }
    Start-Sleep -Seconds $PollSeconds
}
