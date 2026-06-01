#requires -Version 5.1
<#
.SYNOPSIS
  Nightly NBA data refresh — keeps season_games + gamelogs + injuries +
  prediction cache fresh for tomorrow's slate.

.DESCRIPTION
  Runs in order:
    1) fetch_playoff_games_2025_26.py   — pull latest playoff games into
       season_games_<season>.json
    2) fetch_season_games_2025_26.py    — backfill any newly-completed RS games
    3) refresh_active_gamelogs.py       — refresh gamelogs for every player on
       a team playing tomorrow
    4) fetch_injury_espn.py             — daily injury snapshot
    5) build_prediction_cache.py        — recompute q10/q50/q90 cache

  All output is tee'd to logs/nightly_refresh_<YYYYMMDD>.log.

.PARAMETER DryRun
  Run each step with --dry-run where supported (or skip if not). Lets the
  task scheduler integration be smoke-tested without making API calls.

.PARAMETER SkipPredictionCache
  Skip step 5 (predictions cache build) — useful when the slate is empty.

.EXAMPLE
  pwsh scripts/nightly_refresh.ps1
  pwsh scripts/nightly_refresh.ps1 -DryRun
#>
param(
    [switch]$DryRun,
    [switch]$SkipPredictionCache
)

$ErrorActionPreference = 'Continue'

# Project root (script lives at scripts/, project at parent)
$ProjectDir = Split-Path -Parent $PSScriptRoot
if (-not $ProjectDir) {
    $ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
Set-Location $ProjectDir

# Conda python from basketball_ai env
$Python = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "basketball_ai python not found at $Python"
    exit 2
}

# Log file
$LogDir = Join-Path $ProjectDir 'logs'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$Stamp = (Get-Date).ToString('yyyyMMdd')
$LogFile = Join-Path $LogDir "nightly_refresh_$Stamp.log"

function Write-Log {
    param([string]$Msg)
    $line = "[$((Get-Date).ToString('s'))] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

function Invoke-Step {
    param(
        [string]$Name,
        [string]$ScriptRel,
        [string[]]$ExtraArgs = @()
    )
    Write-Log "===== STEP: $Name ====="
    $script = Join-Path $ProjectDir $ScriptRel
    if (-not (Test-Path $script)) {
        Write-Log "  [SKIP] script not found: $script"
        return
    }
    $argsList = @($script) + $ExtraArgs
    if ($DryRun) { $argsList += '--dry-run' }
    Write-Log "  CMD: $Python $($argsList -join ' ')"
    $stepStart = Get-Date
    try {
        & $Python @argsList 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Host
        $rc = $LASTEXITCODE
    } catch {
        Write-Log "  EXCEPTION: $_"
        $rc = 99
    }
    $elapsed = (Get-Date) - $stepStart
    Write-Log ("  step '{0}' exit={1} elapsed={2:N1}s" -f $Name, $rc, $elapsed.TotalSeconds)
}

Write-Log "================================================="
Write-Log "Nightly refresh starting (DryRun=$DryRun)"
Write-Log "ProjectDir=$ProjectDir"
Write-Log "Python    =$Python"
Write-Log "LogFile   =$LogFile"
Write-Log "================================================="

# 1) Playoff games
Invoke-Step -Name 'playoff_games' -ScriptRel 'scripts/fetch_playoff_games_2025_26.py'

# 2) Regular-season game refresh (idempotent merge)
#    Note: this script doesn't have --dry-run; we just skip it on dry runs.
if ($DryRun) {
    Write-Log "===== STEP: season_games (skipped on dry-run) ====="
} else {
    Invoke-Step -Name 'season_games' -ScriptRel 'scripts/fetch_season_games_2025_26.py'
}

# 3) Active rotations gamelog refresh
Invoke-Step -Name 'active_gamelogs' -ScriptRel 'scripts/refresh_active_gamelogs.py'

# 4) Injuries snapshot (ESPN). No --dry-run; skip on dry runs.
if ($DryRun) {
    Write-Log "===== STEP: injuries (skipped on dry-run) ====="
} else {
    Invoke-Step -Name 'injuries' -ScriptRel 'scripts/fetch_injury_espn.py'
}

# 5) Prediction cache rebuild for tomorrow's slate
if ($SkipPredictionCache) {
    Write-Log "===== STEP: prediction_cache (skipped via -SkipPredictionCache) ====="
} elseif ($DryRun) {
    Write-Log "===== STEP: prediction_cache (skipped on dry-run) ====="
} else {
    Invoke-Step -Name 'prediction_cache' -ScriptRel 'scripts/build_prediction_cache.py'
}

# 6) Snapshot prop lines + starters into leak-safe parquet archive (idempotent)
#    No --dry-run flag; skip on dry runs (same pattern as season_games / injuries).
if ($DryRun) {
    Write-Log "===== STEP: lines_archive (skipped on dry-run) ====="
} else {
    Invoke-Step -Name 'lines_archive' -ScriptRel 'scripts/ingest/snapshot_lines_archive.py'
}

# 7) Auto-shadow unified in-game projector for any newly-finished games.
#    Reads data/live snapshots, skips already-logged games, safe to re-run.
#    Passes --dry-run in dry-run mode so it only detects without running log_existing.
Invoke-Step -Name 'auto_shadow_games' -ScriptRel 'scripts/ingame/auto_shadow_new_games.py'

# 8) Propagate CV _cv_fields from atlas parquets into per-player profile JSONs
#    + regenerate PLAYER_INDEX.json/TEAM_INDEX.json.
#    No --dry-run flag; skip on dry runs.
if ($DryRun) {
    Write-Log "===== STEP: persist_cv_profiles (skipped on dry-run) ====="
} else {
    Invoke-Step -Name 'persist_cv_profiles' -ScriptRel 'scripts/intel/persist_cv_to_profiles.py'
}

Write-Log "================================================="
Write-Log "Nightly refresh COMPLETE."
Write-Log "================================================="
exit 0
