<#
.SYNOPSIS
    M12 sell-stack boot: Auto-API + Sell API + read-only demo.

.DESCRIPTION
    Thin launcher for the SELLABLE subset of the stack. Governs:
      (1) sell_api   -- sell.app read-only demo API      :8100
      (2) auto_api   -- predict_service.app Auto-API     :8099

    The paper loop (pm_trading.auto_loop) and the full supervisor are NOT
    launched directly here; call boot.ps1 (the M9 supervisor) separately
    for the complete live stack.

    -DryRun prints the process graph and exits; no processes are started.

    HONEST: no $ edge is claimed; edge_claimed=false on every sell API
    response; calibration + CLV are the only yardsticks.

    PUBLIC DEPLOY IS HUMAN-GATED.  This script is LOCAL ONLY.
    See docs/sell/DEPLOY.md for the human-gated public-deploy checklist.

.PARAMETER DryRun
    Print the preflight graph and service plan, then exit. No processes started.
.PARAMETER SellPort
    Port for the sell API (default 8100).
.PARAMETER AutoApiPort
    Port for the Auto-API (default 8099).
.PARAMETER DemoOnly
    Seed the demo dataset and start the sell API in demo mode (no auto-API).
#>
[CmdletBinding(DefaultParameterSetName = "Launch")]
param(
    [Parameter(ParameterSetName = "Launch")] [switch]$DryRun,
    [Parameter(ParameterSetName = "Launch")] [int]$SellPort    = 8100,
    [Parameter(ParameterSetName = "Launch")] [int]$AutoApiPort = 8099,
    [Parameter(ParameterSetName = "Launch")] [switch]$DemoOnly
)

$ErrorActionPreference = "Continue"
$ROOT   = "C:\Users\neelj\nba-ai-system"
$PY     = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
$LOGDIR = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force -Path $LOGDIR | Out-Null

$DEMO_DIR  = Join-Path $ROOT "data\frontend\sell\demo"
$SELL_APP  = "sell.app"
$AUTO_APP  = "predict_service.app"

# --------------------------------------------------------------------------- #
# Process graph -- always printed so a buyer can see the plan.
# --------------------------------------------------------------------------- #
function Show-ProcessGraph {
    param([string]$Mode)
    Write-Output ""
    Write-Output "=== M12 SELL STACK -- $Mode ==="
    Write-Output ""
    Write-Output "Python     : $PY"
    Write-Output "Root       : $ROOT"
    Write-Output "Log dir    : $LOGDIR"
    Write-Output "Demo dir   : $DEMO_DIR"
    Write-Output ""
    Write-Output "--- SELL PROCESS GRAPH ---"
    Write-Output ""
    if (-not $DemoOnly) {
        Write-Output "  [1] sell_api   -- $SELL_APP                   :$SellPort"
        Write-Output "         routes : GET /health"
        Write-Output "                  GET /track_record"
        Write-Output "                  GET /demo/snapshot"
        Write-Output "         honest : edge_claimed=false on every response"
        Write-Output ""
        Write-Output "  [2] auto_api   -- $AUTO_APP                   :$AutoApiPort"
        Write-Output "         routes : /health, /predict/game, /snapshot"
        Write-Output "         honest : no $ field; EV-only; CLV is the yardstick"
        Write-Output ""
    } else {
        Write-Output "  [1] sell_api   -- $SELL_APP (demo mode)       :$SellPort"
        Write-Output "         reads from: $DEMO_DIR"
        Write-Output "         (auto_api SKIPPED -- DemoOnly mode)"
        Write-Output ""
    }
    Write-Output "--- WHAT IS NOT STARTED HERE ---"
    Write-Output ""
    Write-Output "  paper_loop  -- pm_trading.auto_loop: call boot.ps1 for the full stack"
    Write-Output "  supervisor  -- call boot.ps1 for the M9 supervised stack"
    Write-Output "  UI (Next.js)-- call boot.ps1 for the CourtVision front-end"
    Write-Output ""
    Write-Output "--- HONESTY INVARIANTS ---"
    Write-Output ""
    Write-Output "  edge_claimed  : false  (structural; no $ field anywhere; EV-only)"
    Write-Output "  yardstick     : CLV (better-number-than-close)"
    Write-Output "  real-money    : HUMAN-GATED (default DENY; signed token required)"
    Write-Output "  public deploy : HUMAN-GATED (see docs\sell\DEPLOY.md)"
    Write-Output ""
    Write-Output "--- GOVERNANCE ---"
    Write-Output ""
    Write-Output "  Run before any sell session:"
    Write-Output "    python -m governance.run_governance"
    Write-Output ""
}

# --------------------------------------------------------------------------- #
# -DryRun: print graph and exit.
# --------------------------------------------------------------------------- #
if ($DryRun) {
    Show-ProcessGraph -Mode "DryRun (no processes started)"
    Write-Output "To launch: .\deploy\boot_sell.ps1"
    Write-Output "Demo only: .\deploy\boot_sell.ps1 -DemoOnly"
    Write-Output "Full stack (supervised): .\boot.ps1"
    return
}

# --------------------------------------------------------------------------- #
# Always print the graph when actually launching.
# --------------------------------------------------------------------------- #
Show-ProcessGraph -Mode "Launch -- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# --------------------------------------------------------------------------- #
# Seed the demo dataset (idempotent; no network; no $ numbers).
# --------------------------------------------------------------------------- #
Write-Output "=== Seeding demo dataset ==="
& $PY -u -m sell.demo_seed 2>&1
$seedExit = $LASTEXITCODE
if ($seedExit -ne 0) {
    Write-Output "! demo_seed failed (exit $seedExit); sell_api will return unavailable demo data."
} else {
    Write-Output "Demo dataset ready: $DEMO_DIR"
}
Write-Output ""

# --------------------------------------------------------------------------- #
# Launch sell_api.
# --------------------------------------------------------------------------- #
$env:SELL_PORT    = "$SellPort"
$env:AUTO_API_PORT = "$AutoApiPort"
$env:SELL_DEMO_DIR = $DEMO_DIR

Write-Output "=== Starting sell_api :$SellPort ==="
$sellProc = Start-Process -FilePath $PY `
    -ArgumentList @("-u", "-m", $SELL_APP) `
    -WorkingDirectory $ROOT -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $LOGDIR "m12_sell_api.out") `
    -RedirectStandardError  (Join-Path $LOGDIR "m12_sell_api.err")
Write-Output "  sell_api  PID=$($sellProc.Id)  logs: $LOGDIR\m12_sell_api.out/.err"

# --------------------------------------------------------------------------- #
# Launch auto_api unless DemoOnly.
# --------------------------------------------------------------------------- #
if (-not $DemoOnly) {
    Write-Output ""
    Write-Output "=== Starting auto_api :$AutoApiPort ==="
    $autoProc = Start-Process -FilePath $PY `
        -ArgumentList @("-u", "-m", $AUTO_APP) `
        -WorkingDirectory $ROOT -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $LOGDIR "m12_auto_api.out") `
        -RedirectStandardError  (Join-Path $LOGDIR "m12_auto_api.err")
    Write-Output "  auto_api  PID=$($autoProc.Id)  logs: $LOGDIR\m12_auto_api.out/.err"
}

Write-Output ""
Write-Output "Sell stack running.  Endpoints:"
Write-Output "  sell_api  : http://localhost:$SellPort/health"
Write-Output "              http://localhost:$SellPort/track_record"
Write-Output "              http://localhost:$SellPort/demo/snapshot"
if (-not $DemoOnly) {
    Write-Output "  auto_api  : http://localhost:$AutoApiPort/health"
}
Write-Output ""
Write-Output "HONEST: paper-only; no $ claimed; CLV is the yardstick."
Write-Output "PUBLIC DEPLOY IS HUMAN-GATED.  See docs\sell\DEPLOY.md."
Write-Output "Stop:    Stop-Process -Id <PID>  or  .\boot.ps1 -Stop"
Write-Output "Full supervised stack: .\boot.ps1 -NoUI"
