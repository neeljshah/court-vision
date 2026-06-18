# run_courtvision.ps1 -- one-command local launcher for the CourtVision dashboard
# (the FastAPI server-rendered "Origin" app: api.main:app on http://127.0.0.1:8077).
#
# The server only READS data files on disk -- it does no live fetching itself, so this
# is safe to run anytime. It shows calibrated predictions + line-shopping (decision
# support); it is NOT a proven money edge (the model matches efficient closing lines;
# see docs/JOB_EVIDENCE_PACKET.md). For a live game night you also need the data feeds
# (scripts/courtvision_golive.ps1) -- this launcher is just the web UI.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/run_courtvision.ps1            # start (default)
#   powershell -ExecutionPolicy Bypass -File scripts/run_courtvision.ps1 -Status    # is it up?
#   powershell -ExecutionPolicy Bypass -File scripts/run_courtvision.ps1 -Stop      # stop it
param(
    [switch]$Stop,
    [switch]$Status,
    [int]$Port = 8077
)

$ErrorActionPreference = "Stop"
$Repo   = Split-Path -Parent $PSScriptRoot
$Python = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
$Url    = "http://127.0.0.1:$Port"
$LogDir = Join-Path $Repo "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$OutLog = Join-Path $LogDir "courtvision.out.log"
$ErrLog = Join-Path $LogDir "courtvision.err.log"

function Get-Listener {
    # PID(s) listening on the port, or $null.
    $lines = netstat -ano | Select-String ":$Port\s" | Select-String "LISTENING"
    if (-not $lines) { return $null }
    return ($lines | ForEach-Object { ($_ -split "\s+")[-1] } | Sort-Object -Unique)
}

function Stop-CourtVision {
    $owners = Get-Listener
    if (-not $owners) { Write-Host "CourtVision is not running on port $Port."; return }
    foreach ($procId in $owners) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host "Stopped PID $procId (port $Port)." }
        catch { Write-Host "Could not stop PID ${procId}: $_" }
    }
}

if ($Status) {
    $owners = Get-Listener
    if ($owners) { Write-Host "UP  -> $Url  (PID $($owners -join ','))" }
    else { Write-Host "DOWN (nothing on port $Port)" }
    return
}

if ($Stop) { Stop-CourtVision; return }

# --- start ---
if (Get-Listener) {
    Write-Host "Already running -> $Url  (use -Stop first to restart)."
    return
}

Write-Host "Starting CourtVision dashboard on $Url ..."
$env:NBA_OFFLINE     = "1"      # never live-fetch; read on-disk data only
$env:PYTHONIOENCODING = "utf-8" # avoid a cosmetic unicode print crash
$args = @("-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "$Port")
Start-Process -FilePath $Python -ArgumentList $args -WorkingDirectory $Repo `
    -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog `
    -WindowStyle Hidden -PassThru | Out-Null

# Health-check (the app takes ~15-20s to import the heavy stack).
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "$Url/" -UseBasicParsing -TimeoutSec 4
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}

if ($ok) {
    Write-Host ""
    Write-Host "  CourtVision is UP  ->  $Url"
    Write-Host "  Pages: /  (home)   /tonight  (slate + projected box)   /live  (edges)"
    Write-Host "  Logs:  $OutLog  /  $ErrLog"
    Write-Host "  Stop:  powershell -ExecutionPolicy Bypass -File scripts/run_courtvision.ps1 -Stop"
} else {
    Write-Host "Did not come up within ~80s. Check $ErrLog (tail it)."
}
