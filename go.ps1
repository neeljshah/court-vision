# go.ps1 -- ONE-COMMAND "GO".
# Arms the calibration self-improve loop, launches the FULL supervised stack
# (detached + self-healing -- it keeps running on its own, without Claude / without
# this shell), then opens the live UI. Stop any time with .\stop.ps1
#
# Honest scope: PAPER / UNITS only. No real money (stays default-DENY).
# "AI getting better" = the do-no-harm calibration ratchet; it ships only changes
# that pass the eval-gate, else NO_CANDIDATE. No dollar-edge is claimed anywhere.

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ROOT

# Serve the comprehensive webapp/ UI (Best Bets cards, card detail, paper-trail
# browse, Models 'AI getting better') instead of the older court-visions app.
# Inherited by boot.ps1's Start-Process supervisor.
$env:NBA_AI_UI_DIR = "webapp"
# Serve the PRODUCTION build (stable, real static CSS) not the dev server
# (dev-mode incremental compile was corrupting under load -> unstyled page).
# A production build must exist (npm run build in webapp/); rebuild after FE changes.
$env:NBA_AI_UI_CMD = "npm run start"

# 1) Arm self-improve (human-authorized). Idempotent -- never overwrites.
$sentinel = Join-Path $ROOT "data\cache\improve\PIPELINE_ENABLED"
$sentDir  = Split-Path -Parent $sentinel
if (-not (Test-Path $sentDir)) { New-Item -ItemType Directory -Force -Path $sentDir | Out-Null }
if (-not (Test-Path $sentinel)) {
    Set-Content -Path $sentinel -Value "self-improve armed (paper/units only; do-no-harm gated). Delete to disarm." -Encoding ASCII
    Write-Output "GO | self-improve ARMED (sentinel created)"
} else {
    Write-Output "GO | self-improve already armed"
}

# 2) Launch the full supervised stack (default profile = includes the live UI :3000).
#    boot.ps1 spawns the supervisor DETACHED and returns; it runs without this shell.
Write-Output "GO | launching supervised stack (detached, self-healing)..."
& (Join-Path $ROOT "boot.ps1")

# 3) Wait for services to come ready, then open the UI.
$statusFile = Join-Path $ROOT "data\frontend\ops\supervisor_status.json"
$deadline = (Get-Date).AddSeconds(150)
$ready = $false
Write-Output "GO | waiting for services to come ready..."
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 6
    if (Test-Path $statusFile) {
        try {
            $st = Get-Content $statusFile -Raw | ConvertFrom-Json
            $summary = ($st.procs | ForEach-Object { "$($_.name):$($_.state)" }) -join "  "
            Write-Output "GO | $summary"
            if ($st.all_ready) { $ready = $true; break }
        } catch {}
    }
}
if ($ready) { Write-Output "GO | ALL SERVICES READY" }
else        { Write-Output "GO | not all-ready yet (the UI may still be compiling) -- opening anyway" }

# 4) Open the live UI.
Start-Process "http://localhost:3000"
Write-Output ""
Write-Output "GO | DONE. Live UI: http://localhost:3000"
Write-Output "GO | The stack now runs ON ITS OWN (survives closing this window / Claude)."
Write-Output "GO | Stop it with:  .\stop.ps1"
