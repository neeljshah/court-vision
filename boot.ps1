<#
.SYNOPSIS
    M9 one-command boot: supervised, self-restarting, always-on stack.

.DESCRIPTION
    Default action: starts the Python SUPERVISOR (python -m supervisor --profile
    default|backend), which then owns spawning, readiness-gating, and auto-
    restarting every child.  The supervisor writes ONE status document:
        data\frontend\ops\supervisor_status.json
    so the UI (and the ops doctor runbook) can always see what is up.

    Start order is managed by the supervisor (dependency-ordered) and comes from
    supervisor\stack_specs.py.  DO NOT hand-maintain a roster here -- it drifted
    ~40 services out of date once already.  For the authoritative list run:
        .\boot.ps1 -DryRun            (default: 49 procs incl. the UI)
        .\boot.ps1 -NoUI    -DryRun   (backend: 48 procs, no UI)
        .\boot.ps1 -Paper   -DryRun   (paper node: 16 procs, allowlisted)

    Boot profiles: config\boot\default.json (full) / backend.json (headless) /
    paper.json (headless paper NODE -- a services allowlist, ~16 procs not 48).
    Dependency graph + readiness probes live in supervisor\manifest.py.

    -DryRun           : print preflight + supervisor plan; no processes started.
    -NoUI             : boot the headless "backend" profile (no Next.js, port 3000).
    -Paper            : boot the headless "paper" profile (allowlisted paper node).
    -StrictGovernance : ABORT boot if governance preflight exits non-zero.
                        Default: paper stack still boots; stack is marked NOT
                        real-money-eligible for the session.
    -Stop             : drain the supervisor (SIGTERM/CTRL_BREAK) then kill.

    M10 GOVERNANCE PREFLIGHT (always runs before supervisor):
      python -m governance.run_governance
      Gates: honesty_linter | provenance | concurrency | pkl_integrity |
             leak_audit | parity
      Real-money: always default-DENY; human flip + signed token required.
      On fail without -StrictGovernance: paper boots; GOVERNANCE_ELIGIBLE=false.
      On fail with    -StrictGovernance: boot exits 1 (hard block).

.PARAMETER DryRun
    Print the preflight plan + supervised process plan, then exit.
.PARAMETER Stop
    Kill the supervisor and every child process.
.PARAMETER Interval
    Seconds between producer cycles; forwarded via env var BOOT_INTERVAL
    (default 1200 = 20 min).
.PARAMETER NoUI
    Use the headless "backend" profile (no Next.js UI).
.PARAMETER StrictGovernance
    Abort boot entirely if the M10 governance preflight exits non-zero.
    Default behavior: paper stack boots; real-money eligibility denied.
#>
[CmdletBinding(DefaultParameterSetName = "Launch")]
param(
    [Parameter(ParameterSetName = "Launch")] [switch]$DryRun,
    [Parameter(ParameterSetName = "Launch")] [int]$Interval = 1200,
    [Parameter(ParameterSetName = "Launch")] [switch]$NoUI,
    [Parameter(ParameterSetName = "Launch")] [switch]$Paper,
    [Parameter(ParameterSetName = "Launch")] [switch]$StrictGovernance,
    [Parameter(ParameterSetName = "Stop")]   [switch]$Stop
)

$ErrorActionPreference = "Continue"
$ROOT   = "C:\Users\neelj\nba-ai-system"
$PY     = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
$LOGDIR = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $LOGDIR | Out-Null

# Profile selection: -NoUI -> headless "backend" (no npm/port-3000 child);
# -Paper -> the headless paper NODE (config\boot\paper.json services allowlist).
$PROFILE_NAME = if ($Paper) { "paper" } elseif ($NoUI) { "backend" } else { "default" }

# Match pattern used by -Stop to find supervisor + every child. BUILT FROM THE
# MANIFEST, not hand-maintained: the previous hardcoded list covered 22 of the 49
# specs, so -Stop silently ORPHANED every daemon added after it was written
# (verified 2026-07-27: 8 children survived a -Stop). "default" is the superset of
# every profile, so this pattern stops a paper/backend stack too. If python cannot
# be reached for any reason we fall back to the old literal list rather than
# leaving -Stop with no pattern at all.
$STOP_PATTERN = & $PY -c "from supervisor.manifest import manifest; import re; mods=sorted({s.module for s in manifest('default') if s.module}); print('|'.join([r'-m supervisor\b','supervisor\.supervisor']+[re.escape(m) for m in mods]+['next-server','next start','next/dist/bin/next']))" 2>$null
if (-not $STOP_PATTERN) {
    Write-Output "WARN: could not derive stop pattern from the manifest; using the legacy literal list."
    $STOP_PATTERN = "-m supervisor\b|supervisor\.supervisor|predict_service\.|platformkit\.|next-server|next start|next/dist/bin/next"
}
$STOP_PORTS   = @(8098, 8099, 3000)

# --------------------------------------------------------------------------- #
# -DryRun: delegate to the supervisor's own --dry-run so the plan is always
#           authoritative (the manifest is the source of truth, not this script).
# --------------------------------------------------------------------------- #
if ($DryRun) {
    Write-Output ""
    Write-Output "M9 BOOT -- DryRun  (no processes started)"
    Write-Output "=========================================="
    Write-Output ""
    Write-Output "Python    : $PY"
    Write-Output "Root      : $ROOT"
    Write-Output "Log dir   : $LOGDIR"
    Write-Output "Profile   : $PROFILE_NAME"
    Write-Output "Status    : data\frontend\ops\supervisor_status.json"
    Write-Output "Cadence   : every $Interval seconds"
    Write-Output ""
    Write-Output "--- PREFLIGHT PHASES (run before supervisor) ---"
    Write-Output ""
    Write-Output "  [PHASE 1] M10 governance preflight"
    Write-Output "         cmd : python -m governance.run_governance"
    Write-Output "         gate: honesty_linter | provenance | concurrency |"
    Write-Output "               pkl_integrity | leak_audit | parity"
    Write-Output "         REAL-MONEY: default-DENY; human flip + signed token required"
    $strictLabel = if ($StrictGovernance) { "ABORT boot" } else { "PAPER still boots; stack marked NOT real-money-eligible" }
    Write-Output "         on fail (default) : $strictLabel"
    Write-Output "         -StrictGovernance : ABORT boot on any governance failure"
    Write-Output ""
    Write-Output "--- SUPERVISOR PLAN (from manifest) ---"
    Write-Output ""
    & $PY -u -m supervisor --dry-run --profile $PROFILE_NAME 2>&1
    Write-Output ""
    Write-Output "To boot supervised    : .\boot.ps1"
    Write-Output "Headless (no UI)      : .\boot.ps1 -NoUI"
    Write-Output "Strict governance     : .\boot.ps1 -StrictGovernance"
    Write-Output "Stop everything       : .\boot.ps1 -Stop"
    Write-Output "Status JSON (UI reads): data\frontend\ops\supervisor_status.json"
    return
}

# --------------------------------------------------------------------------- #
# -Stop: drain the supervisor (SIGTERM), then fall back to pattern/port kill.
# --------------------------------------------------------------------------- #
function Stop-Stack {
    Write-Output "Stopping supervisor + stack..."
    $killed = 0

    # Attempt a clean drain: send CTRL_BREAK to the supervisor process group.
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "-m supervisor" } |
        ForEach-Object {
            try {
                # taskkill /PID sends CTRL_BREAK on Win; supervisor drains gracefully.
                $null = taskkill /PID $_.ProcessId /T 2>&1
                Write-Output "  drained supervisor PID=$($_.ProcessId)"
                $killed++
            } catch { }
        }

    # Wait a moment for children to drain, then sweep any stragglers.
    Start-Sleep -Seconds 3

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $STOP_PATTERN } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Output "  stopped PID=$($_.ProcessId)"
            $killed++
        }

    foreach ($port in $STOP_PORTS) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            $listener.OwningProcess | Select-Object -Unique | ForEach-Object {
                Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
                Write-Output "  freed port $port (PID $_)"
                $killed++
            }
        }
    }

    if ($killed -eq 0) { Write-Output "  (no supervisor/stack processes found)" }
    Write-Output "Done."
}

if ($Stop) { Stop-Stack; return }

# --------------------------------------------------------------------------- #
# Ensure the producer runner stub exists (predict_service needs it at import).
# Written once; safe to delete and re-generated on next boot.
# --------------------------------------------------------------------------- #
$RUNNER = Join-Path $ROOT "predict_service\_boot_producer_runner.py"
if (-not (Test-Path $RUNNER)) {
    $runner_src = @'
"""predict_service._boot_producer_runner -- repeating producer cadence.

Runs produce_once(sport) for EACH sport in BOOT_SPORTS (csv, default
"nba,mlb,soccer_intl") each cycle, sleeping BOOT_INTERVAL seconds between cycles
(default 1200 = 20 min). Producing every live sport keeps the canonical store fresh
for /api/v1/bestbets/<sport>; nba alone is offseason-empty. BOOT_SPORT (singular) is
still honored. Written by boot.ps1 on first launch; safe to delete (regenerated).
"""
from __future__ import annotations
import os, sys, time, traceback
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.produce import produce_once

_INTERVAL = max(60, int(os.environ.get("BOOT_INTERVAL", "1200")))


def _sports():
    raw = os.environ.get("BOOT_SPORTS") or os.environ.get("BOOT_SPORT") \
        or "nba,mlb,soccer_intl"
    seen, out = set(), []
    for s in raw.split(","):
        s = s.strip().lower()
        if s and s not in seen:
            seen.add(s); out.append(s)
    return out


def _cycle() -> None:
    for sport in _sports():
        try:
            path = produce_once(sport)
            print("producer | %s saved=%s" % (sport, path), flush=True)
        except Exception as exc:
            traceback.print_exc()
            print("producer | %s error: %s" % (sport, exc), flush=True)


if __name__ == "__main__":
    print("producer | started sports=%s interval=%ss" % (",".join(_sports()), _INTERVAL), flush=True)
    _cycle()
    while True:
        time.sleep(_INTERVAL)
        _cycle()
'@
    [System.IO.File]::WriteAllText($RUNNER, $runner_src, [System.Text.Encoding]::ASCII)
    Write-Output "  wrote $RUNNER"
}

# --------------------------------------------------------------------------- #
# Default action: hand the whole stack to the Python supervisor.
# The supervisor boots dependency-ordered + readiness-gated, auto-restarts dead
# children with capped exponential backoff, and writes supervisor_status.json
# every tick.  This script exits immediately; the supervisor is the long-lived
# parent that "just always runs".
# --------------------------------------------------------------------------- #
$env:BOOT_INTERVAL = "$Interval"
# Produce EVERY live sport each cycle so the canonical store stays fresh for the
# per-sport best-bets boards (nba alone is offseason-empty -> mlb/soccer went stale).
$env:BOOT_SPORTS   = "nba,mlb,soccer_intl"

# 2026-07-04 LANE 6 fix: boot_initiator was only ever stamped by the OUTER
# watchdog_autostart.ps1 ($env:NBA_AI_BOOT_INITIATOR = "watchdog_autostart").
# A direct/manual `.\boot.ps1` invocation (no watchdog in the process tree)
# left this env var unset, so supervisor/__main__.py read None and the status
# doc's boot_initiator stayed null forever -- post_restart_verify's
# supervisor_beat_thread check then FAILed even though the beat-thread code
# path itself was live. Only default it here if not already supplied by an
# outer caller, so watchdog_autostart's more specific "watchdog_autostart"
# tag still wins when boot.ps1 is launched THROUGH the watchdog.
if (-not $env:NBA_AI_BOOT_INITIATOR) { $env:NBA_AI_BOOT_INITIATOR = "boot_ps1_manual" }

# Serve the PRODUCTION webapp/ dashboard on :3000 (parity with go.ps1 + the
# autostart watchdog). Without this, a BARE `boot.ps1` falls back to stack_specs'
# legacy default (court-visions `npm run dev`), which collides with any stale
# court-visions dev server and leaves :3000 empty. Only default if the operator
# has not already pinned a UI, so an explicit override still wins.
if (-not $env:NBA_AI_UI_DIR) { $env:NBA_AI_UI_DIR = "webapp" }
if (-not $env:NBA_AI_UI_CMD) { $env:NBA_AI_UI_CMD = "npm run start" }

Write-Output ""
Write-Output "=== M9 supervised boot -- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Output "Python  : $PY"
Write-Output "Root    : $ROOT"
Write-Output "Profile : $PROFILE_NAME  (auto-restart + readiness-gated)"
Write-Output "Cadence : every $Interval seconds"
Write-Output "Status  : data\frontend\ops\supervisor_status.json"
Write-Output "Logs    : $LOGDIR\m9_supervisor.out  /  .err"
Write-Output ""

# --------------------------------------------------------------------------- #
# M10 GOVERNANCE PREFLIGHT -- runs BEFORE the supervisor.
# Checks every honesty/correctness gate (linter / provenance / concurrency /
# pkl integrity / leak / parity) over current artifacts.
#
#   exit 0 : all gates clean -- stack is honest; boot continues.
#   exit 1 : a gate failed --
#             default (-StrictGovernance NOT set): paper stack still boots but
#               the session is marked NOT real-money-eligible.  A human must
#               review and re-run boot once the gate is clean.
#             -StrictGovernance set: boot is ABORTED entirely (exit 1).
#
# DECISION-ONLY: never authorizes a bet, never moves money, never flips a flag.
# Real-money authorization is always default-DENY; a human flip + signed token
# is required regardless of this preflight's verdict.
# --------------------------------------------------------------------------- #
Write-Output "=== M10 governance preflight ==="
& $PY -u -m governance.run_governance
$govExit = $LASTEXITCODE
if ($govExit -ne 0) {
    Write-Output ""
    Write-Output "!!! GOVERNANCE PREFLIGHT FAILED (exit $govExit) !!!"
    Write-Output "A honesty/correctness gate was violated (see scoreboard above)."
    Write-Output "Stack is NOT real-money-eligible this session."
    Write-Output ""
    if ($StrictGovernance) {
        Write-Output "-StrictGovernance: boot ABORTED.  Fix the flagged gate, then re-run."
        exit $govExit
    }
    Write-Output "Paper stack will still boot (paper is always allowed)."
    Write-Output "Real-money eligibility: DENIED until governance passes."
    Write-Output "To block boot on failure, use: .\boot.ps1 -StrictGovernance"
    Write-Output ""
    $env:GOVERNANCE_ELIGIBLE = "false"
} else {
    Write-Output "Governance preflight PASSED -- stack is honest; handing off."
    $env:GOVERNANCE_ELIGIBLE = "true"
    Write-Output ""
}

$svArgs = @("-u", "-m", "supervisor", "--profile", $PROFILE_NAME)
$svProc = Start-Process -FilePath $PY `
    -ArgumentList $svArgs `
    -WorkingDirectory $ROOT -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $LOGDIR "m9_supervisor.out") `
    -RedirectStandardError  (Join-Path $LOGDIR "m9_supervisor.err")

Write-Output "  m9_supervisor  PID=$($svProc.Id)"
Write-Output ""
Write-Output "The supervisor now owns the stack (boots + restarts every child)."
Write-Output ""
# Roster printed from the MANIFEST, not a hand-maintained list -- the old
# hardcoded 7-9 line roster had drifted ~40 services out of date.
Write-Output "Processes it will start (profile: $PROFILE_NAME):"
& $PY -u -m supervisor --dry-run --profile $PROFILE_NAME 2>&1 |
    Select-String -Pattern '^\s+\[\d+\]' | ForEach-Object { $_.Line }
Write-Output ""
Write-Output "HONEST: paper-only; no dollar-edge claimed; CLV is the yardstick."
Write-Output "Stop: .\boot.ps1 -Stop  |  Plan: .\boot.ps1 -DryRun  |  Strict: .\boot.ps1 -StrictGovernance"
Write-Output "Status: data\frontend\ops\supervisor_status.json  |  Logs: $LOGDIR"
