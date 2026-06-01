<#
.SYNOPSIS
    CourtVision one-command go-live for ANY game night (no odds-api; your scrapers only).

.DESCRIPTION
    Idempotent launcher that makes the /tonight page correct + live for a date:
      1. Builds data/predictions/slate_<date>.csv from predictions_cache (real model bets,
         not the synthesized fallback). Builds the cache first if missing.
      2. Starts (detached, survive shell exit):
           - uvicorn api.main:app  (server, :8077, NBA_OFFLINE=1, TTL=8 fast refresh)
           - box_snapshot_poller   (NBA CDN live box, 10s)
           - draftkings_scraper    (--daemon 15s)
           - betrivers_scraper     (--daemon 15s)
           - unified_scraper_orchestrator  (FanDuel/Pinnacle/Bovada)
           - cv_fix_register_book_ids --loop  (collapses per-book event ids -> one game card, 60s)
      3. Verifies: one game card, slate has bets, box have_data.

    Stop everything:  .\scripts\courtvision_golive.ps1 -StopAll

.PARAMETER Date    NBA slate ET date YYYY-MM-DD (default: today local).
.PARAMETER GameId  Optional NBA game_id to restrict the slate to.
#>
[CmdletBinding(DefaultParameterSetName = "Launch")]
param(
    [Parameter(ParameterSetName = "Launch")] [string]$Date = (Get-Date -Format "yyyy-MM-dd"),
    [Parameter(ParameterSetName = "Launch")] [string]$GameId = "",
    [Parameter(ParameterSetName = "Stop")]   [switch]$StopAll
)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\neelj\nba-ai-system"
$PY   = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
Set-Location $ROOT
New-Item -ItemType Directory -Force -Path "$ROOT\logs" | Out-Null

$PATTERN = "box_snapshot_poller|draftkings_scraper|betrivers_scraper|unified_scraper_orchestrator|inplay_scraper|cv_fix_register_book_ids|uvicorn api.main"

function Stop-Workers {
    Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $PATTERN } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; "  stopped PID $($_.ProcessId)" }
    # free port 8077
    $c = Get-NetTCPConnection -LocalPort 8077 -State Listen -ErrorAction SilentlyContinue
    if ($c) { $c.OwningProcess | Select-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
}

if ($StopAll) { Write-Output "Stopping CourtVision workers..."; Stop-Workers; Write-Output "Done."; return }

function Start-Det($name, $argv) {
    # -u = unbuffered stdout so logs/<name>.out updates live (observability)
    $full = @("-u") + $argv
    Start-Process -FilePath $PY -ArgumentList $full -WorkingDirectory $ROOT -WindowStyle Hidden `
        -RedirectStandardOutput "logs\$name.out" -RedirectStandardError "logs\$name.err"
    "  started $name"
}

Write-Output "=== CourtVision go-live for $Date $(if($GameId){"(game $GameId)"}) ==="
Write-Output "[1/4] stopping any existing workers"; Stop-Workers; Start-Sleep -Seconds 3

Write-Output "[2/4] refreshing injuries + building slate CSV (real model bets, OUT players removed + usage redistributed)"
# Refresh tonight's injury feed (writes data/cache/nba_injuries_<date>.parquet).
& $PY scripts\nba_injury_report_scraper.py 2>&1 | Select-Object -Last 2
# Manual OUT override (feed misses late actives): data/cache/cv_fix/manual_out_<date>.json = ["Name", ...]
$manOut = "data\cache\cv_fix\manual_out_$Date.json"
if (-not (Test-Path $manOut)) { Set-Content -Path $manOut -Value "[]" -Encoding utf8; Write-Output "  created empty $manOut (add OUT names the feed misses)" }
$slateArgs = @("scripts\cv_fix_build_slate.py", "--date", $Date)
if ($GameId) { $slateArgs += @("--gid", $GameId) }
& $PY @slateArgs

Write-Output "[3/4] starting workers (server + poller + scrapers)"
$env:NBA_OFFLINE = "1"
# FULL-SEND (2026-05-31): serve the VALIDATED routed in-game player-line ensemble
# on the live page. live_engine.project_from_snapshot overlays the routed head
# (held-out pooled player MAE 1.01 vs 1.87 production) ONLY when this flag is set;
# the uvicorn server inherits it from this session env. To REVERT, set "0" or
# delete this line and re-run go-live (the server is stop/restarted each run).
$env:CV_INGAME_SBS = "1"
Start-Det "cv_server"   @("-m","uvicorn","api.main:app","--host","127.0.0.1","--port","8077")
Start-Det "box_poller"  @("scripts/box_snapshot_poller.py","--game-ids",$(if($GameId){$GameId}else{"0042500317"}),"--interval-sec","10")
Start-Det "dk_daemon"   @("scripts/draftkings_scraper.py","--daemon","--interval","15")
Start-Det "br_daemon"   @("scripts/betrivers_scraper.py","--daemon","--interval","15")
Start-Det "unified_fbp" @("scripts/unified_scraper_orchestrator.py","--books","fd,pin,bov")
# In-play (live) prop lines -> data/lines/<date>_{fd,dk}_inplay.csv. These power the
# per-quarter "best bets" reconstruction on /results during + after the game.
Start-Det "fd_inplay"   @("scripts/fanduel_inplay_scraper.py","--daemon","--interval","30")
Start-Det "dk_inplay"   @("scripts/draftkings_inplay_scraper.py","--daemon","--interval","30")

Write-Output "[3b] waiting 25s for first scraper tick, then registering book ids + starting loop"
Start-Sleep -Seconds 25
& $PY scripts\cv_fix_register_book_ids.py --date $Date
Start-Det "register_loop" @("scripts/cv_fix_register_book_ids.py","--date",$Date,"--loop","--interval","60")

Write-Output "[4/4] verifying"
Start-Sleep -Seconds 6
& $PY -c @"
import urllib.request, json, re
try:
    h=urllib.request.urlopen('http://127.0.0.1:8077/',timeout=40).read().decode('utf-8','replace')
    print('  home .game-card count:', len(re.findall(r'class=\"game-card', h)))
    d=json.loads(urllib.request.urlopen('http://127.0.0.1:8077/api/slate?date=$Date',timeout=40).read())
    print('  slate: n_bets', d['summary']['n_bets'], '| books', d.get('all_books_universe'),
          '| stale', d.get('stale_data'), '| all_calibrated', all(b.get('calibrated') for b in d['bets']))
except Exception as e:
    print('  verify error:', repr(e))
"@
Write-Output "=== go-live complete. Page: http://127.0.0.1:8077/tonight ==="
Write-Output "Stop with: .\scripts\courtvision_golive.ps1 -StopAll"
