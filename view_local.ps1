<#
.SYNOPSIS
    READ-ONLY local view of the 4-sport calibrated paper-prediction product.

.DESCRIPTION
    Launches ONLY the read-only view surfaces -- nothing that measures, trades,
    flips a flag, or enables real money:

      * Next.js webapp (court-visions UI)  -> http://localhost:3000
          reads data\frontend\... canonical files + the supervisor status doc
          straight off disk via read-only Next API routes. Never recomputes,
          never writes data\, never spawns a daemon.
      * Read-only boards API (frontend.serve) -> http://localhost:8098
          serves the precomputed honest boards from the canonical store.

    This is NOT the supervised stack. It does NOT start the producer, the paper
    loop, the line daemon, the in-game loop, the in-play capture loop, the CI
    cadence runner, or the self-improve runner. To run the SUPERVISED stack use
    boot.ps1 instead (see docs\research\organization-sprint\RUNBOOK.md).

    SAFETY: never creates a sentinel, never registers autostart, never flips
    real-money (stays default-DENY). View-only.

.PARAMETER NoBoard
    Skip the :8098 boards API; launch only the Next.js UI.
.PARAMETER Stop
    Stop the read-only view processes (UI + boards) launched by this script.
#>
[CmdletBinding(DefaultParameterSetName = "Launch")]
param(
    [Parameter(ParameterSetName = "Launch")] [switch]$NoBoard,
    [Parameter(ParameterSetName = "Stop")]   [switch]$Stop
)

$ErrorActionPreference = "Continue"
$ROOT   = "C:\Users\neelj\nba-ai-system"
$PY     = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
$WEBAPP = Join-Path $ROOT "webapp"

# Only the read-only view procs; deliberately NARROW so -Stop never touches the
# supervised stack or any measurement daemon.
$VIEW_PATTERN = "platformkit\.frontend\.serve|next dev|next-router-worker"
$VIEW_PORTS   = @(3000, 8098)

if ($Stop) {
    Write-Output "Stopping read-only view (UI + boards)..."
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $VIEW_PATTERN } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Output "  stopped PID=$($_.ProcessId)"
        }
    foreach ($port in $VIEW_PORTS) {
        $l = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($l) { $l.OwningProcess | Select-Object -Unique | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            Write-Output "  freed port $port (PID $_)" } }
    }
    Write-Output "Done."
    return
}

Write-Output ""
Write-Output "=== READ-ONLY LOCAL VIEW (no daemons, no flags, no real money) ==="
Write-Output "UI     : http://localhost:3000   (Next.js webapp, reads canonical files)"
if (-not $NoBoard) {
    Write-Output "Boards : http://localhost:8098   (frontend.serve, read-only boards API)"
    Start-Process -FilePath $PY -ArgumentList @("-u","-m","scripts.platformkit.frontend.serve") `
        -WorkingDirectory $ROOT -WindowStyle Hidden | Out-Null
    Write-Output "  started boards API (:8098)"
}
Start-Process -FilePath "npm.cmd" -ArgumentList @("run","dev") `
    -WorkingDirectory $WEBAPP -WindowStyle Hidden | Out-Null
Write-Output "  started Next.js UI (:3000)"
Write-Output ""
Write-Output "Open http://localhost:3000 .  Green LIVE only when the supervised stack"
Write-Output "(boot.ps1) is running fresh; otherwise the UI honestly shows not-green."
Write-Output "Stop the view: .\view_local.ps1 -Stop"
