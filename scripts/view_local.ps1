<#
  view_local.ps1 -- LOCAL viewer launcher for the CourtVision predictor product.

  Starts the canonical FastAPI predict_service on :8099 and the Next.js webapp
  on :3000, waits until both answer, then prints OPEN http://localhost:3000.

  LOCAL ONLY. No deploy, no push, no autostart register. This is for YOU to run
  on your own machine to browse the product. Units / probabilities only -- no $.

  Usage:
    powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1          # start both, wait, print OPEN
    powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Dev     # use 'next dev' (skip build)
    powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Stop    # stop both servers, exit
    powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Health  # HONEST health: STALE != GREEN

  -Health does NOT start anything. It probes the running predict_service and
  reports an HONEST status that CONSUMES THE FRESHNESS FIELD: a service that is
  merely REACHABLE but whose producer data is STALE / never produced reads STALE
  (yellow) or DOWN (red), NEVER green. A stale/missing feed can never read GREEN
  -- the same stale-never-green rail the product enforces. Exit code: 0=READY,
  3=STALE/DEGRADED, 4=DOWN/unreachable. Units / probabilities only -- no $.

  Ctrl-C while running stops both servers cleanly.
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$Dev,
    [switch]$Health
)

$ErrorActionPreference = "Stop"
$ApiPort = 8099
$WebPort = 3000
$ApiBase = "http://127.0.0.1:$ApiPort"
$WebUrl  = "http://localhost:$WebPort"

# Repo root = parent of this script's dir.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PidDir   = Join-Path $RepoRoot ".local_view"
$ApiPidFile = Join-Path $PidDir "api.pid"
$WebPidFile = Join-Path $PidDir "web.pid"

function Stop-FromPidFile {
    param([string]$PidFile, [string]$Label)
    if (Test-Path $PidFile) {
        $procId = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($procId) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "Stopping $Label (pid $procId)..."
                # Kill the whole tree (uvicorn/node spawn children).
                taskkill /PID $procId /T /F 2>$null | Out-Null
            }
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
}

function Stop-All {
    Stop-FromPidFile -PidFile $ApiPidFile -Label "predict_service :$ApiPort"
    Stop-FromPidFile -PidFile $WebPidFile -Label "webapp :$WebPort"
    Write-Host "Both servers stopped."
}

if ($Stop) {
    Stop-All
    exit 0
}

# -------------------------------------------------------------------------- #
# -Health : HONEST status that CONSUMES the freshness field.
#
# Reachability is NECESSARY but NOT sufficient for green. A predict_service that
# answers 200 but whose producer data is STALE / never produced is reported as
# STALE, never GREEN -- the stale-never-green rail. We read the canonical
# producer-freshness surface (/api/produce/status: per sport {ok,status,age_seconds})
# and roll up monotone-DOWN: any not-ok / stale sport degrades the whole.
# -------------------------------------------------------------------------- #
function Invoke-HealthCheck {
    $apiBase = "http://127.0.0.1:$ApiPort"

    # 1) Reachability. If the service does not answer at all -> DOWN (red), never green.
    $reachable = $false
    try {
        $h = Invoke-WebRequest -Uri "$apiBase/api/status.all_honest" -UseBasicParsing -TimeoutSec 5
        if ($h.StatusCode -eq 200) { $reachable = $true }
    } catch { $reachable = $false }

    if (-not $reachable) {
        Write-Host "HEALTH: DOWN  -- predict_service :$ApiPort is UNREACHABLE."
        Write-Host "  The product would show Unavailable panels (honest), not fabricated data."
        Write-Host "  Units / probabilities only -- NO dollar figures."
        return 4
    }

    # 2) Freshness. CONSUME the freshness field -- do NOT treat reachable as green.
    $worst = "ok"   # monotone-DOWN: ok -> stale -> down (never upgrades)
    $rows  = @()
    try {
        $resp = Invoke-WebRequest -Uri "$apiBase/api/produce/status" -UseBasicParsing -TimeoutSec 6
        $doc  = $resp.Content | ConvertFrom-Json
    } catch {
        # The freshness surface itself is unavailable -> we cannot assert fresh.
        # Honest DEGRADED (never green-on-merely-reachable).
        Write-Host "HEALTH: STALE -- reachable, but the producer-freshness surface is"
        Write-Host "  UNAVAILABLE (/api/produce/status). Cannot assert fresh -> NOT green."
        Write-Host "  Units / probabilities only -- NO dollar figures."
        return 3
    }

    # The producer-status doc carries the per-sport entries under .sports, which is
    # a JSON ARRAY of objects [{sport,ok,status,age_seconds,...}, ...] (it may also
    # appear as a property-bag map for legacy producers). Normalize to a flat list
    # of entry objects, then read the embedded 'sport' name -- NEVER iterate the
    # array's intrinsic PSObject properties (Count/Length/Rank/SyncRoot/...), which
    # is what produced the garbled rows.
    $entries = @()
    if ($doc.PSObject.Properties.Name -contains "sports") { $sportsNode = $doc.sports }
    else { $sportsNode = $doc }
    if ($sportsNode -is [System.Array]) {
        $entries = $sportsNode                                   # array of entry objects
    } elseif ($null -ne $sportsNode) {
        $entries = @($sportsNode.PSObject.Properties | ForEach-Object { $_.Value })  # legacy map
    }
    foreach ($e in $entries) {
        if ($null -eq $e) { continue }
        $name = "?"
        try { if ($e.sport) { $name = [string]$e.sport } } catch { }
        $okField = $false
        try { $okField = [bool]$e.ok } catch { $okField = $false }
        $st = "unavailable"
        try { if ($e.status) { $st = [string]$e.status } } catch { }
        $age = $null
        try { if ($null -ne $e.age_seconds) { $age = [double]$e.age_seconds } } catch { }
        # ok=True only when a real 'ok' snapshot exists; anything else is NOT green.
        $rowStatus = "ok"
        if (-not $okField -or $st -ne "ok") {
            if ($st -eq "stale") { $rowStatus = "stale" }
            elseif ($st -eq "empty") { $rowStatus = "ok" }   # empty slate is honest-OK
            else { $rowStatus = "stale" }                    # unavailable/missing -> not green
        }
        if ($rowStatus -eq "stale" -and $worst -eq "ok") { $worst = "stale" }
        $ageTxt = if ($null -ne $age) { ("age={0}s" -f [math]::Round($age)) } else { "age=?" }
        $rows += ("  {0,-12} ok={1,-5} status={2,-12} {3}" -f $name, $okField, $st, $ageTxt)
    }

    if ($rows.Count -eq 0) {
        # Reachable but the producer has NO sports at all -> cannot assert fresh.
        $worst = "stale"
        $rows += "  (no producer entries -- producer has not run; NOT green)"
    }

    $banner = switch ($worst) {
        "ok"    { "HEALTH: READY -- reachable AND producer data is FRESH." }
        "stale" { "HEALTH: STALE -- reachable, but producer data is STALE/missing. NOT green." }
        default { "HEALTH: DEGRADED -- reachable, freshness uncertain. NOT green." }
    }
    Write-Host $banner
    $rows | ForEach-Object { Write-Host $_ }
    Write-Host "  stale-never-green: a reachable-but-stale feed is YELLOW, never GREEN."
    Write-Host "  Units / probabilities only -- NO dollar figures."

    if ($worst -eq "ok") { return 0 }
    return 3
}

if ($Health) {
    exit (Invoke-HealthCheck)
}

# Stop any prior instance first (idempotent).
Stop-All
New-Item -ItemType Directory -Force -Path $PidDir | Out-Null

# Point the webapp client at the local API base. The primary transport
# (webapp/lib/p5api.ts) reads NEXT_PUBLIC_P5_BASE; lib/config.ts (WS/REST) reads
# NEXT_PUBLIC_API_BASE. Both already default to :8099, but set them explicitly.
$env:NEXT_PUBLIC_API_BASE = $ApiBase
$env:NEXT_PUBLIC_P5_BASE  = $ApiBase

Write-Host "=== CourtVision LOCAL viewer ==="
Write-Host "API base for webapp -> $ApiBase (NEXT_PUBLIC_P5_BASE / NEXT_PUBLIC_API_BASE)"
Write-Host ""

# --- Start predict_service :8099 -----------------------------------------
Write-Host "Starting predict_service on :$ApiPort ..."
$apiProc = Start-Process -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "predict_service.app:app", "--host", "127.0.0.1", "--port", "$ApiPort") `
    -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden
$apiProc.Id | Out-File -FilePath $ApiPidFile -Encoding ascii

function Wait-Url {
    param([string]$Url, [int]$TimeoutSec = 90, [string]$Label = "service")
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 1000
    }
    Write-Host "WARN: $Label did not answer at $Url within $TimeoutSec s."
    return $false
}

# Health probe: /api/status.all_honest is the canonical honesty bit and returns
# 200 once the app is up. (There is no plain /api/status route -- it 404s.)
$ApiHealth = "$ApiBase/api/status.all_honest"
$apiOk = Wait-Url -Url $ApiHealth -TimeoutSec 90 -Label "predict_service"
if ($apiOk) { Write-Host "predict_service is UP -> $ApiHealth" }

# --- Start webapp :3000 ---------------------------------------------------
Push-Location (Join-Path $RepoRoot "webapp")
try {
    if (-not (Test-Path (Join-Path $RepoRoot "webapp\node_modules"))) {
        Write-Host "Installing webapp dependencies (npm install) ..."
        npm install
    }
    if ($Dev) {
        Write-Host "Starting webapp via 'npm run dev' on :$WebPort ..."
        $webProc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList @("/c", "set NEXT_PUBLIC_API_BASE=$ApiBase&& set NEXT_PUBLIC_P5_BASE=$ApiBase&& npx next dev -p $WebPort") `
            -WorkingDirectory (Join-Path $RepoRoot "webapp") -PassThru -WindowStyle Hidden
    } else {
        Write-Host "Building webapp (npm run build) ... (one-time, ~1-2 min)"
        npm run build
        Write-Host "Starting webapp via 'npm run start' on :$WebPort ..."
        $webProc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList @("/c", "set NEXT_PUBLIC_API_BASE=$ApiBase&& set NEXT_PUBLIC_P5_BASE=$ApiBase&& npx next start -p $WebPort") `
            -WorkingDirectory (Join-Path $RepoRoot "webapp") -PassThru -WindowStyle Hidden
    }
    $webProc.Id | Out-File -FilePath $WebPidFile -Encoding ascii
} finally {
    Pop-Location
}

$webOk = Wait-Url -Url "$WebUrl/" -TimeoutSec 120 -Label "webapp"

Write-Host ""
Write-Host "=================================================="
if ($apiOk -and $webOk) {
    Write-Host "  READY.  OPEN  $WebUrl"
} else {
    Write-Host "  PARTIAL START -- API ok=$apiOk  web ok=$webOk"
    Write-Host "  If web failed, retry with -Dev, or check the build output."
}
Write-Host "  API:    $ApiBase/api/status.all_honest  (docs: $ApiBase/docs)"
Write-Host "  Units / probabilities only -- NO dollar figures."
Write-Host "  Press Ctrl-C to stop, or run:  view_local.ps1 -Stop"
Write-Host "=================================================="

# Keep alive until Ctrl-C; on exit, stop both cleanly.
try {
    while ($true) {
        Start-Sleep -Seconds 2
        $a = Get-Process -Id $apiProc.Id -ErrorAction SilentlyContinue
        if (-not $a) { Write-Host "predict_service exited."; break }
    }
} finally {
    Write-Host ""
    Stop-All
}
