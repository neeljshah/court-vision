# run_liveboard.ps1 -- one-command launcher for the multi-sport LIVE board
# (apps.live_board.server:app on http://127.0.0.1:8090). OddsTrader-style: today's
# MLB / Soccer (incl. World Cup) / Tennis games with live scores from ESPN + our
# calibrated win-prob where the matchup is in-corpus, devigged market-implied
# otherwise. Decision support -- no $ edge claimed.
#
#   powershell -ExecutionPolicy Bypass -File scripts/run_liveboard.ps1           # start
#   powershell -ExecutionPolicy Bypass -File scripts/run_liveboard.ps1 -Status
#   powershell -ExecutionPolicy Bypass -File scripts/run_liveboard.ps1 -Stop
param([switch]$Stop, [switch]$Status, [int]$Port = 8090)

$ErrorActionPreference = "Stop"
$Repo   = Split-Path -Parent $PSScriptRoot
$Python = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
$Url    = "http://127.0.0.1:$Port"
$LogDir = Join-Path $Repo "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$OutLog = Join-Path $LogDir "liveboard.out.log"
$ErrLog = Join-Path $LogDir "liveboard.err.log"

function Get-Listener {
    $lines = netstat -ano | Select-String ":$Port\s" | Select-String "LISTENING"
    if (-not $lines) { return $null }
    return ($lines | ForEach-Object { ($_ -split "\s+")[-1] } | Sort-Object -Unique)
}
function Stop-Board {
    $owners = Get-Listener
    if (-not $owners) { Write-Host "Live board is not running on port $Port."; return }
    foreach ($procId in $owners) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host "Stopped PID $procId." }
        catch { Write-Host "Could not stop PID ${procId}: $_" }
    }
}
if ($Status) {
    $o = Get-Listener
    if ($o) { Write-Host "UP  -> $Url  (PID $($o -join ','))" } else { Write-Host "DOWN (nothing on $Port)" }
    return
}
if ($Stop) { Stop-Board; return }
if (Get-Listener) { Write-Host "Already running -> $Url  (use -Stop to restart)."; return }

Write-Host "Starting LIVE board on $Url ..."
$env:PYTHONIOENCODING = "utf-8"
$a = @("-m", "uvicorn", "apps.live_board.server:app", "--host", "127.0.0.1", "--port", "$Port")
Start-Process -FilePath $Python -ArgumentList $a -WorkingDirectory $Repo `
    -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru | Out-Null

$ok = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    try { if ((Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 4).StatusCode -eq 200) { $ok = $true; break } } catch { }
}
if ($ok) {
    Write-Host ""
    Write-Host "  LIVE board is UP  ->  $Url"
    Write-Host "  Tabs: MLB | Soccer (World Cup default) | Tennis -- auto-refreshes every 25s."
    Write-Host "  Logs: $OutLog / $ErrLog   Stop: ...run_liveboard.ps1 -Stop"
} else {
    Write-Host "Did not come up within ~90s. Tail $ErrLog."
}
