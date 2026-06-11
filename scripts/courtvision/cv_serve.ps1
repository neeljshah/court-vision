<#
.SYNOPSIS
    CourtVision ONE-COMMAND local go-live: fast local server + ngrok public link +
    CONSTANT DK / FanDuel / Pinnacle odds flow. Runs until you stop it.

.DESCRIPTION
    Idempotent launcher.  On a fresh shell:
      1. Sets all required env vars (PYTHONPATH, offline flags, DK_WS_ENABLED /
         FD_WS_ENABLED, all validated CV_ gates inherited from courtvision_golive.ps1).
      2. Pre-warms the board cache (first page load is instant).
      3. Starts uvicorn on 127.0.0.1:<Port> (detached, logs\cv_serve.*).  The DK/FD
         WebSocket odds subscribers start INSIDE uvicorn via the env flags above.
      4. Polls /health until 200 (max 45 s).
      5. Starts the CONSTANT odds stack directly (no golive delegation, so uvicorn
         is never restarted).  Each daemon is detached + isolated — one failing book
         never blocks the others — verified alive after 5 s with one auto-retry:
         dk_daemon (15s -> <date>_dk.csv) · unified_fdpin (fd,pin -> _fd/_pin.csv) ·
         dk_inplay/fd_inplay (30s, self-gate on live) · register_loop (60s).
      6. Starts ngrok http <Port>, prints the public URL, saves logs\cv_public_url.txt.

    NOTE: cv_serve does NOT build the slate CSV — run scripts\courtvision_golive.ps1
    once per slate date for that (it also starts betrivers/bov fallback books).
    Stop everything:  .\scripts\courtvision\cv_serve.ps1 -StopAll

.PARAMETER Date       NBA slate ET date YYYY-MM-DD (default: today).
.PARAMETER Port       Local port for uvicorn (default: 8077).
.PARAMETER StopAll    Stop uvicorn, ngrok, and all scraper workers, then exit.
                      SAFE BY DEFAULT: ngrok is killed only when it tunnels
                      THIS -Port; the shared odds daemons (CSV writers feed
                      every CourtVision server) are left running while another
                      api.main:app uvicorn (e.g. the live :8099 page) is up.
.PARAMETER Force      With -StopAll: kill ngrok + all odds daemons regardless
                      of other running CourtVision servers (full shutdown).
.PARAMETER NoTunnel   Skip ngrok; serve on localhost only.
.PARAMETER NoScrapers Skip all live-odds scrapers (useful when testing server only).
.PARAMETER OddsOnly      Start JUST the odds scrapers + registrar (no server/ngrok/
                         pre-warm); standalone DK/FD WS subscribers included.
.PARAMETER AnthropicKey  Optional Anthropic API key.  When supplied the key is set
                         in $env:ANTHROPIC_API_KEY for this session and inherited by
                         the uvicorn process, enabling the LLM intelligence narrative
                         (claude-haiku-4-5) immediately without a server restart.
                         If $env:ANTHROPIC_API_KEY is already set in the shell it is
                         used automatically — no need to pass this flag.
#>

param(
    [string]$Date          = (Get-Date -Format "yyyy-MM-dd"),
    [int]$Port             = 8077,
    [switch]$StopAll,
    [switch]$Force,
    [switch]$NoTunnel,
    [switch]$NoScrapers,
    [switch]$OddsOnly,
    [string]$AnthropicKey  = ""
)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\neelj\nba-ai-system"
$PY   = "C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe"
$LOGS = "$ROOT\logs"
New-Item -ItemType Directory -Force -Path $LOGS | Out-Null

# Every worker this script can start (used by -StopAll fallback)
$WORKER_PATTERN = "box_snapshot_poller|draftkings_scraper|betrivers_scraper|unified_scraper_orchestrator|fanduel_inplay_scraper|draftkings_inplay_scraper|pinnacle_scraper|cv_fix_register_book_ids|draftkings_ws\.py|fanduel_ws\.py"

# -- STOP ALL ------------------------------------------------------------------
if ($StopAll) {
    Write-Output "=== cv_serve.ps1 -StopAll: stopping all CourtVision workers ==="
    $listenConns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listenConns) {
        $listenConns.OwningProcess | Select-Object -Unique | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            Write-Output "  stopped PID $_ (was listening on :$Port)"
        }
    } else {
        Write-Output "  no process listening on :$Port"
    }
    # ngrok: kill ONLY when it tunnels OUR port. An agent tunneling another
    # CourtVision server (e.g. the user's live :8099 page) is left running.
    # If the local ngrok API is unreachable we fall back to legacy kill.
    $ngrokProcs = @(Get-Process -Name "ngrok" -ErrorAction SilentlyContinue)
    if ($ngrokProcs.Count -gt 0) {
        $killNgrok = $true
        if (-not $Force) {
            try {
                $tunJson = Invoke-WebRequest -Uri "http://127.0.0.1:4040/api/tunnels" `
                    -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
                $addrs = @((($tunJson.Content | ConvertFrom-Json).tunnels) |
                           ForEach-Object { $_.config.addr })
                if ($addrs.Count -gt 0 -and -not ($addrs -match ":$Port`$")) {
                    $killNgrok = $false
                    Write-Output "  ngrok tunnels $($addrs -join ', ') (not :$Port) - left running"
                }
            } catch { }
        }
        if ($killNgrok) {
            $ngrokProcs | ForEach-Object {
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
                Write-Output "  stopped ngrok PID $($_.Id)"
            }
        }
    }
    # Scraper/poller/WS workers are SHARED infrastructure: every CourtVision
    # server reads the same data/lines CSVs. While another api.main:app uvicorn
    # is still serving (e.g. the live :8099 page), leave the odds daemons alive
    # unless -Force. Otherwise kill everything matching the pattern (covers all
    # daemons this script or courtvision_golive.ps1 starts; other uvicorns are
    # never touched).
    $otherServers = @(Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match "uvicorn\s+api\.main:app" `
                       -and $_.CommandLine -notmatch "--port\s+$Port\b" })
    if ($otherServers.Count -gt 0 -and -not $Force) {
        $srvPids = ($otherServers | ForEach-Object { $_.ProcessId }) -join ", "
        Write-Output "  other CourtVision server(s) still up (PID $srvPids) - shared odds daemons left running"
        Write-Output "  (run -StopAll -Force to kill the daemons too)"
    } else {
        Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match $WORKER_PATTERN } |
            ForEach-Object {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
                Write-Output "  stopped worker PID $($_.ProcessId)"
            }
    }
    Write-Output "=== stop complete ==="
    return
}

# -- ANTHROPIC API KEY pass-through -----------------------------------------------
# When -AnthropicKey is supplied it wins; otherwise the existing shell env var is
# kept as-is.  The uvicorn process inherits $env:ANTHROPIC_API_KEY from this shell,
# so the LLM narrative (claude-haiku-4-5) activates without a server restart.
# To enable LLM intel: .\scripts\courtvision\cv_serve.ps1 -AnthropicKey sk-ant-...
if ($AnthropicKey -ne "") {
    $env:ANTHROPIC_API_KEY = $AnthropicKey
    Write-Output "  ANTHROPIC_API_KEY set from -AnthropicKey param (LLM intel enabled)"
} elseif ($env:ANTHROPIC_API_KEY) {
    Write-Output "  ANTHROPIC_API_KEY already set in env (LLM intel enabled)"
} else {
    Write-Output "  ANTHROPIC_API_KEY not set — using rule-based intel fallback (set key to enable LLM)"
}

# -- ENV VARS (needed by server AND scrapers; inherited by Start-Process) -------
$env:PYTHONPATH          = ".;scripts/team_system;src"
$env:PYTHONIOENCODING    = "utf-8"
$env:NBA_OFFLINE         = "1"
# Live odds WebSocket feeds (sub-second DK, ~5-10s FD; HTTP scrapers are the fallback)
$env:DK_WS_ENABLED       = "1"
$env:FD_WS_ENABLED       = "1"
# All validated CV_ flags (inherited from courtvision_golive.ps1; keeps parity)
$env:CV_SLATE_PAD_GAMEID          = "1"
$env:CV_SLATE_HAIRCUT             = "1"
$env:CV_SLATE_VAC_BUMP            = "1"
$env:CV_AVAIL_PARQUET_FALLBACK    = "1"
$env:CV_VAC_BUMP_GATED            = "1"
$env:CV_COUNT_NB                  = "1"
$env:CV_COUNT_STL                 = "1"
$env:CV_QUARTER_IDENTITY          = "1"
$env:CV_QUANTILE_CAL              = "1"
$env:CV_ROW_SIGMA                 = "1"
$env:CV_INGAME_SIGMA              = "1"
$env:CV_ARCHETYPE_CORR            = "1"
# CV_BET_POLICY left at the default (iter57 selection) for /cv DISPLAY. The
# "reb_ast" book is the validated REAL-MONEY policy, but on a Finals slate it
# clears ZERO props here — emptying the Best Bets section. The /cv page is a
# projection/paper product (playoff grades cap at C, no edge claimed), so it
# shows the model's top reads vs live odds rather than the real-betting book.
# $env:CV_BET_POLICY              = "reb_ast"
$env:CV_SHRINK_CALIBRATED         = "1"
$env:CV_INGAME_L5_ANCHOR          = "1"
$env:CV_WP_FOULS_ENDQ3            = "1"
$env:CV_WP_RECONCILED_CALIB       = "1"
$env:CV_INGAME_RETURN             = "1"
$env:CV_OUT_DETECT_HARDEN         = "1"
$env:CV_MEAN_TOTALS_DEBIAS        = "1"
$env:CV_INGAME_ROTMINUTES         = "1"
$env:CV_INGAME_MARGIN_HAIRCUT     = "1"
$env:CV_INGAME_OT_FIX             = "1"
$env:CV_INGAME_LATEQ4_V2          = "1"
$env:CV_INGAME_FOULOUT_CAP        = "1"
$env:CV_INGAME_FINAL_FREEZE      = "1"
$env:CV_INGAME_OUT_BET_CAP        = "1"
$env:CV_INGAME_SBS                = "1"
$env:CV_LIVE_SIM                  = "1"
# In-game bet re-rank: re-anchor each slate card's LINE + per-book ladder to the
# CURRENT in-play market (data/lines/<date>_*inplay*.csv) before the live-q50
# regrade, so during a game the Best Bets move with BOTH the live prediction AND
# the live line. No-op pregame / when no in-play line exists.
$env:CV_SLATE_INPLAY_REANCHOR     = "1"
$env:CV_BBREF_REORDER_FIX         = "1"
$env:CV_RIDGE_FF_FALLBACK         = "1"
$env:CV_PARLAY_FIX_MIXED_SIDE     = "1"
$env:CV_AST_DURABLE_KELLY         = "1"
$env:CV_ALTLINE_SIGMA_FIX         = "1"
$env:CV_LIVE_ODDS_VALID_GUARD     = "1"
$env:CV_DK_FRACSEC_FIX            = "1"
$env:CV_PLAYOFF_SIGMA_MULT        = "0.9"
$env:CV_PLAYOFF_PREGAME_GUARD     = "1"
$env:CV_PLAYOFF_GUARD_FAILCLOSED  = "1"
# DISPLAY playoff projections as paper picks on /cv. The pregame guard above is a
# REAL-BETTING safety (no proven playoff edge); without this allow-flag it blocks
# the ENTIRE slate, leaving the Best Bets section empty. We instead SHOW the
# model's projections vs live odds, graded C-paper with the "no proven playoff
# edge" disclaimer — honesty lives in the C-cap + disclaimers, not in hiding them.
$env:CV_ALLOW_PLAYOFF_PREGAME     = "1"
$env:CV_SYNTH_GATE_BEFORE_TRUNCATE= "1"

# -- ODDS-STACK HELPERS ----------------------------------------------------------
function Start-Det($name, $argv) {
    # Detached python worker, unbuffered, logs to logs\<name>.{out,err}.
    # try/catch so one daemon failing to spawn never blocks the others.
    try {
        Start-Process -FilePath $PY -ArgumentList (@("-u") + $argv) -WorkingDirectory $ROOT `
            -WindowStyle Hidden `
            -RedirectStandardOutput "$LOGS\$name.out" -RedirectStandardError "$LOGS\$name.err"
        Write-Output "    started $name"
    } catch {
        Write-Output "    WARN: $name failed to start: $($_.Exception.Message) (other books unaffected)"
    }
}

function Get-DaemonPids($pattern) {
    try {
        @(Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -match $pattern } |
            Select-Object -ExpandProperty ProcessId)
    } catch { @() }
}

function Start-OddsStack([bool]$IncludeStandaloneWs) {
    # CONSTANT odds daemons: DK + FanDuel + Pinnacle + in-play + registrar loop.
    # Each spec: n=log name, a=argv, p=command-line pattern (idempotent restart + verify).
    $specs = @(
        @{ n="dk_daemon";     a=@("scripts/draftkings_scraper.py","--daemon","--interval","15");        p="draftkings_scraper\.py" },
        @{ n="unified_fdpin"; a=@("scripts/unified_scraper_orchestrator.py","--books","fd,pin");        p="unified_scraper_orchestrator\.py" },
        @{ n="dk_inplay";     a=@("scripts/draftkings_inplay_scraper.py","--daemon","--interval","30"); p="draftkings_inplay_scraper\.py" },
        @{ n="fd_inplay";     a=@("scripts/fanduel_inplay_scraper.py","--daemon","--interval","30");    p="fanduel_inplay_scraper\.py" },
        @{ n="register_loop"; a=@("scripts/cv_fix_register_book_ids.py","--date",$Date,"--loop","--interval","60"); p="cv_fix_register_book_ids\.py" }
    )
    if ($IncludeStandaloneWs) {
        # -OddsOnly: no uvicorn to host the WS subscribers, so run them standalone.
        # (In server mode they start inside uvicorn via DK_WS_ENABLED/FD_WS_ENABLED.)
        $specs += @{ n="dk_ws"; a=@("scripts/draftkings_ws.py"); p="draftkings_ws\.py" }
        $specs += @{ n="fd_ws"; a=@("scripts/fanduel_ws.py");    p="fanduel_ws\.py" }
    }

    # Idempotent: replace any stale instance of each daemon (kills ONLY these scripts).
    foreach ($s in $specs) {
        Get-DaemonPids $s.p | ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            Write-Output "    replaced stale $($s.n) (PID $_)"
        }
    }
    foreach ($s in $specs) { Start-Det $s.n $s.a }

    # Verify each daemon is still alive after 5 s; one auto-retry for any that died.
    Start-Sleep -Seconds 5
    $retried = @()
    foreach ($s in $specs) {
        if ((Get-DaemonPids $s.p).Count -eq 0) {
            Write-Output "    $($s.n) died within 5s - retrying once (see logs\$($s.n).err)"
            Start-Det $s.n $s.a
            $retried += , $s
        }
    }
    if ($retried.Count -gt 0) {
        Start-Sleep -Seconds 5
        foreach ($s in $retried) {
            if ((Get-DaemonPids $s.p).Count -eq 0) {
                Write-Output "    ERROR: $($s.n) failed twice - check logs\$($s.n).err (other books keep flowing)"
            } else {
                Write-Output "    $($s.n) recovered on retry"
            }
        }
    }
    Write-Output "  odds stack up -> data/lines/${Date}_dk.csv / _fd.csv / _pin.csv"
    Write-Output "  (books may post G4 markets late; the page degrades to projections until then)"
}

# -- ODDS-ONLY MODE --------------------------------------------------------------
if ($OddsOnly) {
    Write-Output ""
    Write-Output "=== cv_serve.ps1 -OddsOnly  date=$Date  (scrapers + registrar, no server) ==="
    Start-OddsStack $true
    Write-Output ""
    Write-Output "  Stop  : .\scripts\courtvision\cv_serve.ps1 -StopAll"
    Write-Output "  Watch : Get-Content logs\dk_daemon.out -Tail 5"
    return
}

# -- LAUNCH ----------------------------------------------------------------------
Write-Output ""
Write-Output "=== CourtVision cv_serve.ps1  date=$Date  port=$Port ==="

# -- PRE-WARM board cache (first page load is instant) ----------------------------
Write-Output ""
Write-Output "[1/4] pre-warming board cache for $Date ..."
try {
    & $PY -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'src'); sys.path.insert(0,'scripts/team_system'); import api._cv_board as b; b.build_board('$Date'); print('  pre-warm OK')"
} catch {
    Write-Output "  pre-warm error (non-fatal): $($_.Exception.Message)"
}

# -- START UVICORN -----------------------------------------------------------------
Write-Output ""
Write-Output "[2/4] starting uvicorn api.main:app on 127.0.0.1:$Port ..."
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $existing.OwningProcess | Select-Object -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        Write-Output "  killed existing PID $_ on :$Port"
    }
    Start-Sleep -Seconds 2
}
Start-Process -FilePath $PY `
    -ArgumentList @("-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $ROOT -WindowStyle Hidden `
    -RedirectStandardOutput "$LOGS\cv_serve.out" -RedirectStandardError "$LOGS\cv_serve.err"

$healthUrl = "http://127.0.0.1:$Port/health"
$started   = $false
$deadline  = (Get-Date).AddSeconds(45)
Write-Output "  polling $healthUrl (max 45s) ..."
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $started = $true; Write-Output "  server healthy (HTTP 200)"; break }
    } catch { }
}
if (-not $started) {
    Write-Warning "  server did not become healthy within 45s; continuing anyway."
    Write-Output "  check logs\cv_serve.err for details"
}

# -- CONSTANT ODDS STACK -------------------------------------------------------------
if (-not $NoScrapers) {
    Write-Output ""
    Write-Output "[3/4] starting CONSTANT odds stack (DK + FanDuel + Pinnacle + registrar) ..."
    Start-OddsStack $false   # WS subscribers already live inside uvicorn (env flags)
    # Live box snapshots for tonight's game (in-game layer; not part of odds flow)
    Get-DaemonPids "box_snapshot_poller\.py" | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Det "box_poller" @("scripts/box_snapshot_poller.py","--game-ids","0042500404","--interval-sec","10")
} else {
    Write-Output ""
    Write-Output "[3/4] -NoScrapers: skipping live-odds scrapers"
}

# -- NGROK TUNNEL -------------------------------------------------------------------
$publicUrl = ""
if (-not $NoTunnel) {
    Write-Output ""
    Write-Output "[4/4] starting ngrok tunnel on port $Port ..."
    Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Output "  killed existing ngrok PID $($_.Id)"
    }
    Start-Sleep -Seconds 1
    Start-Process -FilePath "ngrok" -ArgumentList @("http", "$Port") -WindowStyle Hidden `
        -RedirectStandardOutput "$LOGS\ngrok.out" -RedirectStandardError "$LOGS\ngrok.err"
    Start-Sleep -Seconds 4
    try {
        $ngrokApi = Invoke-WebRequest -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
        $tunnels  = ($ngrokApi.Content | ConvertFrom-Json).tunnels
        $httpsTunnel = $tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
        if (-not $httpsTunnel) { $httpsTunnel = $tunnels | Select-Object -First 1 }
        if ($httpsTunnel) { $publicUrl = $httpsTunnel.public_url }
    } catch {
        Write-Warning "  could not fetch ngrok tunnel URL: $($_.Exception.Message)"
        Write-Output  "  check logs\ngrok.err and logs\ngrok.out for details"
    }
    if ($publicUrl) {
        Set-Content -Path "$LOGS\cv_public_url.txt" -Value $publicUrl -Encoding utf8
        Write-Output ""
        Write-Output "================================================================"
        Write-Output "  PUBLIC URL: $publicUrl/tonight"
        Write-Output "  PUBLIC URL: $publicUrl/cv"
        Write-Output "================================================================"
    } else {
        Write-Warning "  ngrok tunnel URL not obtained; server is local-only."
    }
} else {
    Write-Output ""
    Write-Output "[4/4] -NoTunnel: skipping ngrok"
}

# -- SUMMARY --------------------------------------------------------------------------
Write-Output ""
Write-Output "=== CourtVision is UP ==="
Write-Output "  Local  : http://127.0.0.1:$Port/tonight  +  /cv"
if ($publicUrl) { Write-Output "  Public : $publicUrl/tonight  (saved to logs\cv_public_url.txt)" }
Write-Output "  Running: uvicorn :$Port (DK/FD WS inside)"
if (-not $NoTunnel)   { Write-Output "           ngrok http $Port (public tunnel)" }
if (-not $NoScrapers) { Write-Output "           CONSTANT odds: dk_daemon / unified_fdpin / dk_inplay / fd_inplay / register_loop / box_poller" }
Write-Output "  Odds   : /api/odds/$Date.json (per-book) - slate bets carry all_books for the book picker"
Write-Output "  Logs   : logs\cv_serve.out / logs\<daemon>.out|.err"
Write-Output "  Stop   : .\scripts\courtvision\cv_serve.ps1 -StopAll"
