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
# G-008: pre-seed games_lookup.json via ScoreboardV2 BEFORE NBA_OFFLINE=1 is set.
# If the user already had NBA_OFFLINE=1 in their shell (e.g. from a prior session),
# we temporarily clear it so the network call succeeds, then restore it afterward.
# Without this, _ensure_games_lookup silently skips the API call when the lookup is
# stale, forcing a manual games_lookup.json edit on every new game night.
$_saved_offline = $env:NBA_OFFLINE
$env:NBA_OFFLINE = $null
& $PY scripts\cv_fix_build_slate.py --date $Date --ensure-lookup-only
if ($_saved_offline) { $env:NBA_OFFLINE = $_saved_offline }
# Refresh tonight's injury feed (writes data/cache/nba_injuries_<date>.parquet).
& $PY scripts\nba_injury_report_scraper.py 2>&1 | Select-Object -Last 2
# Single OUT override file (canonical): data/cache/cv_fix/live_out_<date>.json = ["Name", ...]
# Read by ALL consumers: golive slate builder, live router (courtvision_router.py),
# and CV_INGAME_RETURN (live_return_{date}.json clears a name from this list).
# MIGRATION: if a legacy manual_out_<date>.json exists and live_out_<date>.json does
# not yet, copy its content over so no override is silently dropped.
$liveOut = "data\cache\cv_fix\live_out_$Date.json"
$manOutLegacy = "data\cache\cv_fix\manual_out_$Date.json"
if (-not (Test-Path $liveOut)) {
    if (Test-Path $manOutLegacy) {
        Copy-Item $manOutLegacy $liveOut
        Write-Output "  migrated $manOutLegacy -> $liveOut"
    } else {
        Set-Content -Path $liveOut -Value "[]" -Encoding utf8
        Write-Output "  created empty $liveOut (add OUT names the feed misses)"
    }
}
# ── SLATE-BUILD FLAGS — MUST be set BEFORE the slate build below (ordering fix
#    2026-06-04): cv_fix_build_slate.py reads these env vars at BUILD time. They
#    were previously set in the server block ~30 lines down (AFTER this build),
#    so on a FRESH shell the slate was built with NONE of them (the CV_SLATE_PAD_GAMEID
#    live-regrade fix silently did nothing on a first run). Set them here so they
#    actually take effect on the slate written below.
#   CV_SLATE_PAD_GAMEID — preserve the 10-digit padded game id (else int(gid) strips
#     leading zeros and the router's snapshot lookup never matches -> live regrade off).
#   CV_SLATE_HAIRCUT (2026-06-04 CORRECTNESS FIX) — the garbage-time haircut fires in
#     training/OOF (so the VALIDATED pregame_oof_faithful HAS it) but was DEAD in the
#     cache->slate path because build_prediction_cache writes opp_team="OPP" -> spread
#     None -> haircut no-op. Served PTS/REB/AST were 2-8% TOO HIGH on blowout games
#     (53% of games |spread|>=6). ON re-applies the haircut from the real spread so
#     served == validated (blowout MAE: pts -0.63%/reb -0.23%/ast -0.54%; AST edge
#     preserved bc OOF applied it too; double-count with live_adjustment blowout term
#     reconciled). Byte-identical OFF; tests/test_slate_haircut.py 8/8.
#   CV_SLATE_VAC_BUMP (FRESHNESS) — confirmed-inactives -> vacated minutes/usage ->
#     PTS/REB bump + live total(pace)/spread(blowout), so tonight's served numbers
#     reflect tonight's reality (minutes-surprise is THE dominant PTS/REB error).
#     SAFETY GUARD: a stale/missing injury feed (date != slate date) is a NO-OP, never
#     a wrong-op. Mechanism case-tested (SGA out -> J.Williams PTS +2.10); historical
#     backtest is neutral-by-construction (OOF trained w/ context) -> proof is LIVE as
#     game-nights accrue. Also fixes the /tonight overlay reading the cache directly
#     (bumped cache is written back). tests/test_availability.py 34/34.
#   CV_AVAIL_PARQUET_FALLBACK (WAVE 17i, owner-flipped 2026-06-05 for G2) — the
#     freshness vac-bump above was SILENTLY DEAD in production: golive's scraper writes
#     data/cache/nba_injuries_<date>.parquet but availability.out_players_by_team read
#     data/injuries_<date>.json (never written) -> team_vacated_map empty -> CV_SLATE_VAC_BUMP
#     applied ZERO. This bridges the gap (json absent + same-date parquet -> build the OUT
#     payload from the parquet). Freshness-guarded (date mismatch -> no-op); byte-identical
#     OFF. Case-test 2026-06-05: OFF = 0 vac rows (dead); ON = vac map fires. availability.py.
#   CV_VAC_BUMP_GATED (WAVE 17l, owner-flipped 2026-06-05 for G2) — the FLAT vac bump HURTS
#     served MAE (+0.57%; n=88,386 leak-free) because the base already absorbs typical vac via
#     l10_min; it only HELPS at HIGH vacated-load share. ON restricts the bump to vac_share>=0.60
#     and ONLY {pts,reb} (PTS -3.95% / REB -2.95% MAE on the high-share tail); AST EXCLUDED
#     (mis-tuned coeff, edge-protective). Case-test 2026-06-05: GATED touches only PTS/REB
#     high-share absorbers, AST rows changed = 0; byte-identical OFF. NOTE: these three flip
#     TOGETHER (fallback revives the feed, GATED keeps it net-positive). During the Finals
#     pregame props are guarded OFF so this is DISPLAY-only (OUT-aware projections, no bet risk).
#     VAC_BUMP_ACCURACY_VALIDATION.md. ROI-unvalidated for reg-season (accuracy win, not ROI).
$env:CV_SLATE_PAD_GAMEID = "1"
$env:CV_SLATE_HAIRCUT = "1"
$env:CV_SLATE_VAC_BUMP = "1"
$env:CV_AVAIL_PARQUET_FALLBACK = "1"
$env:CV_VAC_BUMP_GATED = "1"
# == ENABLED 2026-06-07 (validated this session; targeted suite 98/98 green; EDGE_GATE_2026-06-07.md) ==
# Sim count-stat calibration -- mean/total-preserving, shrinks PHANTOM count edges (max |edge| 14.6->8.6pp):
$env:CV_COUNT_NB = "1"          # over-dispersed counts -> negative-binomial: ftm shapeErr 8.2->5.2%, fg3m 3.5->3.2%
$env:CV_COUNT_STL = "1"         # stl chain over-clumped zeros -> Poisson at real mean: shapeErr 5.8->2.5%
$env:CV_QUARTER_IDENTITY = "1"  # per-team quarter shape (SAS Q1 fast-start), total-preserving: shape err 2.2->1.5%
# Distribution / sizing calibration -- honest intervals + per-row sigma (ROI-safe, AST edge preserved):
$env:CV_QUANTILE_CAL = "1"      # conformal q10/q90: PTS cov80 .69->.82, REB .77->.82, AST .73->.81
$env:CV_ROW_SIGMA = "1"         # per-row sigma (vs flat _STAT_SIGMA) for honest pregame edge SIZING
$env:CV_INGAME_SIGMA = "1"      # per-(stat,bucket) in-game sigma -> right-sized live Kelly (fixes 3.9-9x late over-size)
# SGP joint pricing -- 10x better joint calibration (accuracy/calibration only; NOT an edge claim, no SGP prices):
$env:CV_ARCHETYPE_CORR = "1"    # parlay leg correlations recalibrated (teammate stacks priced down ~11%)
# Bet policy -- concentrate on the PROVEN cross-season AST edge, drop PTS (no edge, loses playoffs):
$env:CV_BET_POLICY = "reb_ast"  # +4.31% held-out-late vs +0.22% allow-all; AST served RAW (calibration-protected)
# DELIBERATELY KEPT OFF (re-verified this session to HURT -> enabling would LOWER quality):
#   CV_PREGAME_CAL (kills AST edge +7.22->+1.12), CV_RESIDUAL_HEAD_FIX (worsens 5 q50 stats),
#   CV_LOWSHRINK_BLEND (REB ROI +1.81->+0.50), CV_INGAME_INTEL (-19.5% vs routed),
#   CV_AST_VAC_FEATURE / CV_VAC_LOAD_FEATURE (accuracy-not-edge, refuted on independent cross-book corpus).
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
# CV_LIVE_SIM (2026-06-05, owner-approved for G2): attach the reactive scenario /
#   win-prob panel to the live box card (api/_cv_live_sim_panel.maybe_attach_sim_panel)
#   — coherent win-prob + final-score distribution (q10/q50/q90) + what-if scenarios
#   (star OUT / pace / scheme). DISPLAY-ONLY: player point projections are UNCHANGED
#   (routed ensemble), AST untouched, win-prob/scores clamped, never raises, byte-identical
#   when "0". docs/_audits/LIVE_SIM_PANEL_WIRING.md.
$env:CV_LIVE_SIM = "1"
# ACCURACY FIXES (2026-06-02, validated this session — both verified-clean by adversarial
# skeptics, ROI-neutral / no betting downside, default-OFF gates so removing these reverts):
#   CV_BBREF_REORDER_FIX — the default serve feeds 5/85 features (slots 80-84) to the WRONG
#     model slots on EVERY prediction (bbref_extra where contract_*/pts_share_3pt were trained).
#     ON aligns them on BOTH the point (predict_pergame) AND quantile/sigma (predict_pergame_quantiles)
#     paths -> MORE ACCURATE (dMAE<0 on all 4 corpora: A/B/C reg + playoffs), ROI-neutral. The flag
#     (not _meta.json) is required because predict_pergame_quantiles reads live feature_columns().
#   CV_RIDGE_FF_FALLBACK — with CV_INGAME_SBS=1 the in-game ridge head zero-fills 7 four-factor
#     features it was trained nonzero on (the live snapshot can't supply them) -> projected team
#     TOTAL biased ~-23.5 pts LOW mid-game. ON abstains to the unbiased sim mean (MAE ~22 -> ~11).
$env:CV_BBREF_REORDER_FIX = "1"
$env:CV_RIDGE_FF_FALLBACK = "1"
#   CV_PARLAY_FIX_MIXED_SIDE (CORRECTNESS/ROI, flipped 2026-06-04): on a MIXED
#     OVER/UNDER same-game parlay, _correlation() negated rho — but the MC sampler's
#     per-leg direction thresholds ALREADY encode the OVER/UNDER joint-hit relation,
#     so negating rho double-counts it with the wrong sign → joint hit-prob/EV ~3x
#     OVERSTATED (e.g. pts OVER + reb UNDER displayed +61% EV vs +20% correct; 2M-draw
#     MC). That shows −EV mixed-side SGPs as +EV. ON keeps the covariance physically
#     correct. Byte-identical for non-mixed parlays; only mixed OVER/UNDER same-game
#     leg pairs change. Flipped because the directive is "make it correct + best ROI"
#     and a 3x EV overstatement loses money. (The flag-OFF contract tests intentionally
#     encode the old behavior; they pass when the flag is unset in CI.)
$env:CV_PARLAY_FIX_MIXED_SIDE = "1"
#   CV_AST_DURABLE_KELLY (ROI/risk, flipped 2026-06-04): bet_selector sized AST at the
#     4% cap because kelly_corr used win_prob = implied + the REGIME-INFLATED in-window
#     edge (16-22%) -> AST over-bet ~2.9x vs the honestly-validated durable +5%/55%-win
#     core (AST_EDGE_MAXIMIZATION §4: quarter-Kelly ~1.38%, cap ~2%). ON sizes AST on
#     win_prob_override=0.55 capped 2% -> stake 4%->1.375%, SAME bets selected (selection
#     runs before sizing -> edge ROI% unchanged), variance brought in line with the real
#     edge. Protects the moneymaker. tests/test_bet_selector.py TestASTDurableKelly.
#   CV_ALTLINE_SIGMA_FIX (correctness): alt_line_ladder divided the 80% CI by the IQR
#     divisor 1.349 instead of 2.5631 -> sigma 1.90x too wide -> alt-line P(over) pulled
#     to 0.5 -> EV understated. ON uses the coverage-correct 2.5631. Alt-line endpoint
#     only (/tonight + /parlays already correct). tests/test_alt_line_ladder.py.
$env:CV_AST_DURABLE_KELLY = "1"
$env:CV_ALTLINE_SIGMA_FIX = "1"
#   CV_LIVE_ODDS_VALID_GUARD (WAVE 17c, 2026-06-05, CORRECTNESS/ROI, Finals-G2): the
#     live bet-regrade (_regrade_bet_with_live_q50, all slate+parlay+live sites)
#     picked best price with a bare max() over the ladder with NO |odds|>=100 guard.
#     A glitch in-play quote (0 / +50 / -99) passes the loader's [-400,400] sane
#     filter, gets max()-selected, then the payout formula treats |price|<100 as
#     even-money (+100) -> ladder {-130,+50} OVER served EV +31.32% vs correct
#     +16.17% (~2x), market_prob 0.500 vs 0.667, Kelly maxed at the 4% cap. ON drops
#     |odds|<100 from selection (mirrors the hard pregame grade_bet rule). BYTE-
#     IDENTICAL unless an invalid odd is actually present (real books never post
#     |odds|<100). 4 tests + 100 router/betting green. doc LIVE_INPLAY_EV_KELLY_AUDIT.md.
$env:CV_LIVE_ODDS_VALID_GUARD = "1"
#   CV_SLATE_PAD_GAMEID — the legacy slate builder calls int(gid), stripping leading zeros
#     ('0042500317' -> 42500317). The router's snapshot/alias lookups are keyed by the
#     zero-padded id, so the int form never matches -> live in-game regrade silently
#     disabled on /tonight (users see STALE pregame projections). ON preserves the
#     10-digit padded id (byte-identical when OFF; affects only the written slate CSV).
#     Validated: ingame_calib_eval OFF==ON (slate is not in the projection engine corpus);
#     5/5 pytest tests/test_slate_game_id_pad.py green. ROI/CLV neutral confirmed.
$env:CV_SLATE_PAD_GAMEID = "1"
#   CV_DK_FRACSEC_FIX (WAVE 17d, 2026-06-05, CORRECTNESS/coverage, Finals-G2): DraftKings
#     start_times carry 7 fractional-second digits ('...:00.0000000Z') which
#     datetime.fromisoformat() rejects -> _et_date_of_start_time falls back to the raw UTC
#     iso[:10], mis-bucketing DK night games to the NEXT ET day -> ALL DK rows (4,345 on the
#     audited slate) get date-filtered OUT, so the sharpest US book is silently absent from
#     best-price/arb/steam. ON truncates fractional seconds to 6 digits (microseconds);
#     harmless/byte-identical for 0/3/6-digit (non-DK) timestamps (verified OFF==ON). Restores
#     DK to the slate; glitch DK odds are independently caught by CV_LIVE_ODDS_VALID_GUARD.
#     doc BOOK_LINE_RESOLUTION_AUDIT.md.
$env:CV_DK_FRACSEC_FIX = "1"
# ── OVERNIGHT-VALIDATED ACCURACY + CORRECTNESS WINS (2026-06-04, flipped ON) ──
# All leak-free harness-validated, gated default-OFF (byte-identical when "0"),
# pytest-green. Revert any by setting "0". See docs/_audits/OVERNIGHT_MORNING_REPORT.md.
#   CV_SHRINK_CALIBRATED (W-016): l5floor:12:0.30 shrink curve replaces sigmoid:14:4 →
#     player MAE 1.1914→1.0558 (-11.4%, every stat improves).
#   CV_INGAME_L5_ANCHOR (W-008): tames early-game extrapolation → midQ1 PTS 14.3→9.0 (-37%);
#     endQ1+ byte-identical.
#   CV_WP_FOULS_ENDQ3 (W-005): fouls into endQ3 win-prob → Brier 0.1214→0.1150 (-5.3%).
#   CV_WP_RECONCILED_CALIB (W-032): live win-prob sigma/market recal → ECE 0.075→~0.055.
#   CV_INGAME_RETURN (W-011): clears the OUT flag when a benched/injured player returns
#     (fixes the mis-cap; the Brunson-return case).
#   CV_OUT_DETECT_HARDEN (W-010): hardens the stagnation OUT detector (kills false positives
#     like a resting star flagged OUT).
#   CV_MEAN_TOTALS_DEBIAS (W-012): de-biases the inflated pregame team-total aggregation.
#   CV_INGAME_ROTMINUTES (W-009-RIGHT): rotation-curve remaining-MINUTES consumer —
#     drives the cycle-88 per-minute stat extrapolation off projected minutes
#     (season per-quarter rotation curve × flat clock-share, Bayesian-blended by
#     n_games) instead of the naive flat clock share. Minutes-surprise is THE
#     dominant in-game error lever. Validated on ingame_calib_eval (pig projector,
#     --shrink prod): overall MAE 1.1673→1.1540 (-1.14%, 200g) / 1.2126→1.2012
#     (-0.94%, 500g) with ALL 7 stats improving and no core regression (pts -1.13%,
#     reb -0.94%, ast -1.36%). Byte-identical OFF; engine boundary path unchanged
#     (period heads override there, same as W-021/W-027). This is the rejected
#     naive W-009 (CV_INGAME_ROTCURVE) redone RIGHT: it fixes the two bugs that
#     sank it — the rate basis now uses the player's own minutes (not game-clock),
#     and the atlas range correctly includes the about-to-start quarter at a
#     boundary (period..4, not period+1..4). See docs/_audits/INGAME_OVERNIGHT_LOG.md.
$env:CV_SHRINK_CALIBRATED = "1"
$env:CV_INGAME_L5_ANCHOR = "1"
$env:CV_WP_FOULS_ENDQ3 = "1"
$env:CV_WP_RECONCILED_CALIB = "1"
$env:CV_INGAME_RETURN = "1"
$env:CV_OUT_DETECT_HARDEN = "1"
$env:CV_MEAN_TOTALS_DEBIAS = "1"
$env:CV_INGAME_ROTMINUTES = "1"
#   CV_INGAME_MARGIN_HAIRCUT (W-038): margin->minutes haircut for starters at period < 4.
#     At large margins (> 12 pts), starters' remaining projection delta is scaled down
#     continuously (factor = max(0.70, 1 - 0.010*(|margin|-12))). Fires on BOTH teams'
#     starters (unlike blowout_factor which is leading-only + Q4-only). Validated:
#     pig projector 954-game corpus --shrink prod: overall MAE 1.2601->1.2574 (-0.21%),
#     all 7 stats improve (pts -0.24%, reb -0.22%, ast -0.22%), no core regression.
#     Engine projector: period heads override at exact endQ1/Q2/Q3 boundaries; haircut
#     fires during mid-quarter serving where period heads don't trigger. Byte-identical
#     OFF; 20/20 pytest test_w038_margin_haircut.py green.
$env:CV_INGAME_MARGIN_HAIRCUT = "1"
#   CV_INGAME_OT_FIX (W-007, CORRECTNESS, flipped 2026-06-04): without it, any
#     OT period clamps played_share=1.0 -> projected_final collapses to current_stat
#     for every player in OT (projection breaks). ON extrapolates the remaining OT
#     minutes correctly (game_min_eff=48+5*n_ot). REGULATION (period<=4) is byte-
#     identical both states (16/16 pytest); only OT games differ. Finals can go to OT
#     -> flip ON so live OT projections don't freeze. data/cache eval corpus has no
#     OT games so it was never in the harness MAE, but the regulation no-op is proven.
$env:CV_INGAME_OT_FIX = "1"
#   CV_INGAME_LATEQ4_V2 (2026-06-04, wired + flipped): the held-out routing curve
#     (n=399) mis-routes late-Q4 (42min+) pts/reb to `snapshot`; on the 1987-game
#     fast cache the v2 head is lower-MAE AND mean-preserving there. Re-routes
#     late-Q4 pts/reb -> v2. Live-path verified: pts overall MAE 2.9796->2.9382
#     (-1.39%), reb 1.1914->1.1764 (-1.26%), bias -0.129->+0.031 (mean-preserving=
#     bet-safe), ast UNCHANGED, early-game UNCHANGED. Byte-identical OFF.
#     doc docs/_audits/INGAME_ENSEMBLE_OPTIMALITY.md.
$env:CV_INGAME_LATEQ4_V2 = "1"
#   CV_INGAME_FOULOUT_CAP (WAVE 17b, 2026-06-05, CORRECTNESS, Finals-G2-relevant):
#     a player disqualified at >=6 personal fouls is ejected and cannot accumulate
#     any further stat, so the served projected_final MUST equal the current box.
#     The served routed/v2 head is nearly flat on foul state (sweep: pf 1->6 moves
#     0.03 pts; a fouled-out player was over-projected +5.2 pts at midQ3), biasing
#     every fouled-out prop OVER. Applied as the LAST step of project_from_snapshot
#     so it is the final word on the served value under SBS. Deterministic box clamp
#     (pf is on the live snapshot). Fast-cache: pf>=6 rows (n=2,177) overall MAE
#     0.1104->0.0363 (-67%; pts -82%, reb -85%), full-corpus delta -0.0067% (~0),
#     OFF byte-identical (delta exactly 0.0). doc INGAME_FOULOUT_FINALFREEZE_FIX.md.
$env:CV_INGAME_FOULOUT_CAP = "1"
#   CV_INGAME_FINAL_FREEZE (WAVE 17b, 2026-06-05, CORRECTNESS): a finished game
#     (game_status FINAL, or regulation/OT clock expired with a winner) cannot
#     accumulate further, so every served projected_final == current box. The served
#     v2 head adds a learned remaining-delta even at zero remaining time (sweep: 6
#     real FINAL snapshots over-projected PTS +1.58 avg, max +4.61). _game_is_final
#     excludes a tie at 0:00 (-> OT, not frozen). Deterministic; OFF byte-identical.
$env:CV_INGAME_FINAL_FREEZE = "1"
#   CV_INGAME_OUT_BET_CAP (WAVE 17b, 2026-06-05, CORRECTNESS/ROI, Finals-G2): the
#     live BET-REGRADE path (_build_slate + _build_parlays) re-prices in-play props
#     from the live-engine blend with NO awareness of the operator manual OUT list
#     (data/cache/cv_fix/live_out_<date>.json) — so a star who LEFT injured (box feed
#     can't flag a mid-game injury: status=ACTIVE/oncourt=0 == a normal rest) still
#     regraded his bet near full projection (e.g. 24.8 vs current 22) = phantom OVER
#     edge. Caps an OUT-listed player's blended bet projection to his current box
#     value before edge/EV (mirrors the box-card cap, reuses its exact loader+norm).
#     BYTE-IDENTICAL when the out-list is empty/absent (the default state: load_out_set
#     -> empty frozenset -> `if _out_set:` short-circuits, zero per-bet work). Only
#     bites when an operator marks a player out. 9 tests + phantom-edge case (Brunson
#     OVER->UNDER when capped). Distinct from FOULOUT_CAP(pf>=6)/FINAL_FREEZE(game over)
#     — this is the injury-left case. doc INGAME_OUT_BET_CAP_FIX.md.
$env:CV_INGAME_OUT_BET_CAP = "1"
#   CV_PLAYOFF_SIGMA_MULT (2026-06-04, OWNER-AUTHORIZED real-money lever): the
#     router default 1.20x playoff sigma boost rests on a LITERATURE assumption
#     ("playoff props ~15-25% wider") that the repo's OWN leak-safe playoff sample
#     CONTRADICTS — measured playoff residual dispersion was ~16% NARROWER (pooled
#     ratio 0.842, every stat <1.0), and the flat base already covers >=0.90 before
#     any boost (docs/_audits/PLAYOFF_SIGMA_MULT_ASSESS_2026-06-01.md). 1.20x was
#     therefore silently shrinking Finals single-prop + parlay Kelly stakes ~14-22%
#     on an unsupported premise. Owner reviewed the decision (incl. the caveat that
#     the contrary evidence is one game / 27 players = thin) and chose to LEAN INTO
#     THE DATA at 0.9 (modestly wider stakes than neutral 1.0). Risk note: this is
#     the more-aggressive option; it bets a bit LARGER than regular-season-neutral
#     on limited playoff evidence. Reversible: set "1.0" to neutralize or remove to
#     restore the 1.20x default. Applies on next go-live (server reads env at start).
$env:CV_PLAYOFF_SIGMA_MULT = "0.9"
#   CV_PLAYOFF_PREGAME_GUARD (2026-06-04, ROI-PROTECTIVE, owner directive "best ROI
#     no matter what"): skip ALL pregame prop bets on playoff games (game_id prefix
#     004). Evidence is STRUCTURAL: docs/_audits/{PLAYOFF_PREGAME_EDGE,PLAYOFF_PREGAME_GUARD}.md
#     — at real 2026 playoff odds (leak-free, rolling-origin) every pregame stat is
#     negative (PTS −9.07/REB −6.82/AST −10.62/FG3M −11.05%) AND the closing-line MAE
#     BEATS the model MAE on all 4 stats → a sharper line = no edge by construction.
#     Critically, CV_PLAYOFF_SIGMA_MULT=0.9 AMPLIFIES the loss (stakes ~23% more into
#     the −EV market: −$115 vs −$108 P&L/100 at 1.20×) → the only ROI-correct Finals
#     move is to NOT bet pregame props at all. Pairs with the existing AST playoff
#     guard. Default-OFF would leave REB/PTS/FG3M bettable; turned ON here for the
#     Finals. The live in-play OVER-REACTION fade is the only validated live-playoff
#     edge (separate path, unaffected). Escape hatch: CV_ALLOW_PLAYOFF_PREGAME=1 to
#     re-enable playoff pregame betting. Reg-season betting is UNAFFECTED. 89 tests.
$env:CV_PLAYOFF_PREGAME_GUARD = "1"
#   CV_PLAYOFF_GUARD_FAILCLOSED (WAVE 17e, 2026-06-05, CRITICAL G2): the playoff guard
#     was EVADED on the SYNTH serve path — on a playoff date with no slate_*.csv, /api/slate
#     builds bets that keep the RAW BOOK event id ('35669206' -> zfill '003' != '004'), which
#     _is_playoff_game_id can't classify as playoff -> guard returns True -> 14 of 57 synth
#     playoff props served+bettable during the Finals despite CV_PLAYOFF_PREGAME_GUARD=1
#     (e.g. Josh Hart PTS UNDER 24.5 ev 31.52%, De'Aaron Fox AST evading the always-on AST
#     guard too). FAILCLOSED detects a PLAYOFF WINDOW from the slate DATE (_is_playoff_date,
#     robust to a stale games_lookup) and blocks any UNCLASSIFIABLE game_id (not a known 004
#     playoff nor 002 reg-season NBA id). Verified real path 2026-06-05: 14 served OFF -> 0 ON.
#     BYTE-IDENTICAL when OFF, in the regular season (playoff_window=False), and for known 002
#     ids even in a playoff window; escape CV_ALLOW_PLAYOFF_PREGAME=1. 27 tests + 122 green.
#     doc SYNTH_PATH_PLAYOFF_GUARD.md. LESSON: a guard firing != a guard working (the id it got).
$env:CV_PLAYOFF_GUARD_FAILCLOSED = "1"
#   CV_SYNTH_GATE_BEFORE_TRUNCATE (WAVE 17g, 2026-06-05, CORRECTNESS/ROI): the SYNTH
#     slate path (/api/slate when book lines exist but no slate_<date>.csv — exactly
#     today's 06-05 state + any pre-CSV slate) truncated bets[:TOP_N=50] by RAW
#     un-calibrated EV BEFORE _apply_calibration_gate — the inverse of the main-path
#     BUG 7 FIX. The gate recalibrates EV + prunes whole line-buckets, so a #51-57
#     raw-EV candidate can outrank a gate-pruned top-50 but is already gone: on the
#     06-05 synth slate, gating the full 57 first serves 14 bets vs truncating-first
#     serves 12 -> 2 gate-surviving +EV bets silently dropped (incl. Brunson PTS OVER
#     24.5 +3.45%). ON gates the FULL list -> calibrated-EV sort + edge tie-break ->
#     truncate (mirrors the proven main path). BYTE-IDENTICAL OFF (legacy raw-sort +
#     truncate + later gate). doc BET_DEDUP_RANK_TRUNCATE_AUDIT.md.
$env:CV_SYNTH_GATE_BEFORE_TRUNCATE = "1"
# NOTE: pregame webpage/slate plumbing fixes (CV_SLATE_VAC_BUMP freshness bump,
# CV_BET_POLICY=reb_ast, CV_ROW_SIGMA) are wired + validated (gated default-OFF,
# docs/_audits/SERVE_PATH_PLUMBING_AUDIT.md) but deliberately NOT flipped here —
# the serve/webpage layer is deferred; the prediction-ENGINE work comes first.
# WS odds feeds (2026-05-31): DK and FD WebSocket subscribers give sub-second
# line-move latency (vs 15-30s from HTTP scrapers).  They write to separate
# _ws-suffixed CSV files so the HTTP scrapers remain the fallback for pin/bov
# and for any period when a WS feed is geo-blocked or rate-limited.
# Set to "0" or remove to disable a feed without touching code.
$env:DK_WS_ENABLED = "1"
$env:FD_WS_ENABLED = "1"
# BR_WS_ENABLED left OFF — KAMBI endpoint sees CloudFront 429 off-hours; the
# HTTP scraper (br_daemon below) is the reliable path for BetRivers today.
# $env:BR_WS_ENABLED = "1"
#
# DK IN-PLAY WS (sub-second live prop-line updates during NBA games):
# ─────────────────────────────────────────────────────────────────────
# STEP 1 — Discover live subCategoryIds on YOUR residential network:
#   Open sportsbook.draftkings.com in Chrome during a live NBA game.
#   DevTools → Network → WS → look at "subscribe" message payloads for
#   "clientMetadata.subCategoryId" values (one per stat: pts/reb/ast/fg3m…).
# STEP 2 — Fill _INPLAY_SUBCATEGORY_IDS in scripts/dk_inplay_ws.py
#   (uncomment the dict entries and paste the IDs you recorded).
# STEP 3 — Uncomment the line below and re-run go-live to activate.
# NOTE: until STEP 2 is done, the subscriber idles harmlessly with a warning.
# $env:DK_INPLAY_WS_ENABLED = "1"   # ← uncomment after filling in-play market IDs + validating on residential network
Start-Det "cv_server"   @("-m","uvicorn","api.main:app","--host","127.0.0.1","--port","8077")
# G-001: auto-discover tonight's NBA game ids from games_lookup.json / ScoreboardV2
# when -GameId is not supplied.  When -GameId IS supplied the behavior is byte-identical
# to the pre-G-001 path (the if-block short-circuits immediately, no Python called).
$_pollerGameIds = if ($GameId) {
    $GameId
} else {
    (& $PY "scripts\golive_discover_game_ids.py" "--date" $Date 2>&1 |
        Where-Object { $_ -match '^\d{10}' } |
        Select-Object -Last 1)
}
if (-not $_pollerGameIds) {
    Write-Warning "[golive] No NBA game ids discovered for $Date — box_snapshot_poller will start with empty id list and idle until games go live."
    $_pollerGameIds = ""
}
Write-Output "  [golive] box_poller game ids: $_pollerGameIds"
Start-Det "box_poller"  @("scripts/box_snapshot_poller.py","--game-ids",$_pollerGameIds,"--interval-sec","10")
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
# PowerShell-native verify (was an embedded-Python here-string that failed to PARSE
# under Windows PowerShell 5.1 — 25 parser errors that aborted the WHOLE script, so
# go-live never ran on a 5.1 shell; 2026-06-05 fix). Parses + runs under 5.1 AND 7.
try {
    $_vr = Invoke-WebRequest -Uri "http://127.0.0.1:8077/api/slate?date=$Date" -TimeoutSec 40 -UseBasicParsing
    $_vd = $_vr.Content | ConvertFrom-Json
    Write-Output ("  slate: n_bets " + $_vd.summary.n_bets + " | stale " + $_vd.stale_data)
} catch {
    Write-Output ("  verify error: " + $_.Exception.Message)
}
Write-Output "=== go-live complete. Page: http://127.0.0.1:8077/tonight ==="
Write-Output "Stop with: .\scripts\courtvision_golive.ps1 -StopAll"
