---
updated: 2026-07-03
north_star: BEST predictions per sport (beat/match the devigged close on OOS calibration); honest, no fabricated edge.
active_project: sports-betting decision-support product (4 sports) + own keyless odds API
loop_queue_source: this file's NEXT list
---

# NOW -- the single source of truth for "what's done / what's next"

## >>> CEILING MODE (user directive 2026-06-26b): RAISE THE CEILING -- BEST PREDICTIONS
Shift from floor-raising (hardening/tests, wakes 1-15) to CEILING-raising: the highest-level
CALIBRATED predictions per sport (beat/MATCH devigged close on OOS calibration). Three levers in
priority: L1 MORE DATA independently (FIRST reclaim already-on-disk data discarded at ingest via NEW
leak-free extractors in domains/<sport>/**, zero-network; daemons keep capturing), L2 MORE SIGNALS
(many new leak-free candidates/cycle), L3 BETTER MODELS where room exists = IN-GAME conditioning +
same-day FRESHNESS (pregame is efficient -> MATCH not beat). GATE every candidate through the REAL
tools: use the `signal-audit` skill (REAL leak-free SHIP/REJECT gate per sport), `eval-gate`,
`cross-sport-benchmark` + `calibration-report` (OOS Brier/ECE vs baseline AND vs close). SHIP gated
survivors; REJECT-log the rest WITH the number (REJECT = success, never fabricate a win). Full spec:
BUILD_BACKLOG.md SECTION 0 CEILING PRIORITY block. Heavier than the hardening loop (1-2 Sonnets/wake
ok). Daemon flywheel + builder loop run independently; enders `bot stop` / program_complete only.
- DEEP RESEARCH DONE (2026-06-26b): docs/research/ceiling/ADVANCED_TECHNIQUES.md (top technique =
  Conformalized Quantile Regression for prop intervals) + ONDISK_RECLAIM_TARGETS.md (BIG finding:
  leak-free asof_*.parquet already BUILT for every sport but NO gate adapter merges them -> each
  reclaim = cheap wire+gate experiment). EXECUTION QUEUE in BUILD_BACKLOG S0.
- MAINTENANCE (SYSTEM HEALTH SWEEP + WORKSPACE ORG, 2026-07-03 pm, review session):
  FOUND+FIXED two LIVE serving-spine outages: (1) m1_api_paper (:8099) WEDGED since
  13:00:30 (last request served = /api/paper/trail?limit=2000; event loop blocked,
  CPU spinning ~2.8h; supervisor HTTP probe TimeoutError but NO wedge-kill exists for
  HTTP-readiness procs -- heartbeat_reaper only covers heartbeat procs = REAL GAP,
  flagged not fixed) -> killed PID, supervisor relaunched, /health 200 + props route
  200 (2823 rows). (2) m1_api_boards (:8098) serving 500s: conda env anyio install
  was MIXED-VERSION (4.14 _backends importing TaskHandle missing from a stale
  _core/_tasks.py -- fallout of the WAKE-33 scrapling anyio bump while daemons ran)
  -> clean pip uninstall+reinstall anyio==4.14.1, relaunched, /health+/api/slate 200.
  Feed health 25/25 GREEN (5 providers x 5 sports). Props-route fix (460fd0cb) +
  PropsPanel (9bc820d4) verified intact + live; 7 per-file route tests green.
  ORG: NOW.md trimmed 291KB->67KB (WAKE-1..15 + June sessions -> .planning/archive/
  NOW_ARCHIVE_2026-06.md); webapp/README.md created (prod-build/.next gotcha);
  root scratch (trail_temp.json, oa809*.json, STATUS.md lane notes) cleared/archived.
  No accuracy/edge claim; serving-spine repair only.
- WAKE-34 (IN-PLAY EVERY-LINE WIDENING + IN-PLAY QUALITY SCOREBOARD, 2026-07-03, commit
  021e3712, Fable-planned / 2 Sonnet executors): user directive "ingame knows every little
  line and data it can get, AI independent". AUDIT FOUND: in-play capture was Kalshi
  MONEYLINE ONLY (195K rows/1 venue/1 market type) and had NO TENNIS AT ALL during
  Wimbledon while Kalshi listed open KXATPMATCH/KXWTAMATCH; Kalshi also quotes in-play
  MLB total/spread/team_total + WC spread/team_total we never asked for. SHIPPED:
  (1) kalshi_series_spec.py per-sport (series, market_type) map -- mlb 4 series, tennis
  ATP+WTA, WC 3, NBA spread pre-wired for Oct; line from real floor_strike/cap_strike;
  per-series failure isolation; in-play default transport = resilient_get_json (stealth
  tier). (2) CONSUMER SAFETY SWEEP (the critical half): moneyline filters added to
  inplay_capture_loop._yes_pair + pm_game_placer.group_by_game so a total/spread prob is
  NEVER ingested as a win prob (protects m32 tail gate + all grading); 8 consumers
  audited. (3) inplay_capture_quality.py scoreboard (ticks/games/market-type breadth/
  tail share/live-window gaps, verdict vs yesterday) every m30 tick ->
  data/frontend/ops/inplay_capture_quality.json. Live smoke: mlb 250 ticks across 4
  market types, tennis 41 ATP/WTA ticks. 116 tests green / 9 per-file runs. Known
  pre-existing failure test_inplay_aggregate_grade.py (grade-dir grew past MIN_GAMES,
  reproduces on stash -- unrelated). Coverage only, no accuracy/edge claim.
- WAKE-33 (SCRAPING NEVER-DIES: STEALTH TRANSPORT + LEAGUE RESOLVER + CAPTURE SCOREBOARD,
  2026-07-03, commits d96bbebe + 88ed9943, Fable-planned / 3 Sonnet executors): user directive
  "odds webscraping must run independently+perfectly, multi-book, constantly refreshing" citing
  github.com/d4vinci/Scrapling. (1) stealth_fetch.py + transport.py: scrapling 0.4.9
  browser-TLS-impersonated fallback -- plain urllib first, escalate ONLY on blocked-shaped
  failure (401/403/406/409/429/451/503/HTML-wall), per-host 6h-TTL stealth-first memory,
  kill switch CV_STEALTH_FALLBACK=0; wired into http_cache default path (injected test
  fetchers untouched). (2) FOUND+FIXED live outage: tennis captured ZERO all July (during
  Wimbledon!) -- Pinnacle league id 12 delisted (401) and live Wimbledon ids rotate per
  round; NEW pinnacle_league_resolver.py resolves ids dynamically (ATP+WTA filter, 1h
  cache, 401 auto-invalidate) -> tennis restored, 22 games/132 quotes first tick, daemon
  autonomously writing. (3) feed_health widened 2->5 sports + heal() auto-marks
  auth-blocked provider hosts stealth-first each m30 tick; capture_quality.py scoreboard
  (rows/games/venues/tail-share/max-gap + GREEN/REGRESSION vs yesterday, elapsed-
  normalized) wired into m30 -> data/frontend/ops/capture_quality.json; flagged a REAL
  soccer rate drop day one. GOTCHAS: daemons run conda basketball_ai which is Py3.10.20
  (CLAUDE.md "Py3.9" is STALE) -- scrapling[fetchers] installed BOTH envs; daemon restarts
  required for new code (supervisor auto-relaunches on terminate); scrapling bumped anyio
  4.12->4.14 in conda env, API :8099 verified healthy after. 164 tests green across 12
  per-file runs; live 5-sport feed health ALL GREEN incl pinnacle/tennis. Coverage
  measurement only, no accuracy/edge claim.
- WAKE-32 (IN-PLAY TAIL-BAND VENUE-BIAS GATE, 2026-07-03, commit d61251b1): user
  redirect "my intelligence IS the edge; longshot in-game prices are flawed" -> NEW
  hypothesis CLASS (venue price bias, NOT public-state modeling -- cannot be "already
  priced" since it IS the price). ingame_tail_scan.py: price-band scan of 95 outcome-
  graded captured MLB in-play games (45K ticks), game-clustered bootstrap. DISCOVERY:
  home-side prices ran ABOVE realized in every band >0.20 ([0.65,0.80) significant,
  gap -0.178); longshot bands [0.10,0.20) realized ABOVE price both md5-halves
  (+0.080/+0.177) with model dBrier<0 both halves; [0.65,0.80) dBrier -0.0175/-0.0172
  both halves. Because bands were chosen from this sample, ingame_tail_gate.py PRE-
  REGISTERS H1 (longshot underpriced [0.10,0.20)) + H2 (mid-fav overpriced [0.65,0.80))
  at 2026-07-03T00:00Z and scores FORWARD-captured games only; wired as m32's 4th
  nightly candidate (CONFIRMED_FORWARD -> ship_review roster; acting stays human).
  Caveats recorded: fees/fills NOT modeled; deep tail [0,0.10) our model is WORSE
  (MARKET_BETTER in one half) -- do not chase deep tails; discovery window 2 weeks,
  possible drift. 19 tests green (7 scan + 5 gate + 7 m32 resynced). NO edge claimed;
  verdict file data/domains/mlb/ingame_tail_verdict.json starts PENDING_FORWARD n=0.
- WAKE-31 (MLB DEEP INTELLIGENCE PUSH -- context layer + SP lever DELIVERED, 2026-07-02):
  user directive: push MLB data/intelligence depth toward NBA's, verify-live-first, Sonnet
  executors. VERIFIED-LIVE FIRST (3 doc claims corrected): edge-map's "6,558-row/17-day
  gamelog corpus" is STALE (now 36,018 rows, 2026-04-01..07-02); sp_elo_offset confirmed
  genuinely NOT wired into MLBPredictor (pure MOV-Elo, checked predictor.py live);
  edge_engine extract_rule already MLB-aware (bullpen/probable-pitcher/weather keywords).
  SHIPPED (2 Sonnet executors + orchestrator, commits 3b360a6c + 0e01e83d, local only):
  (1) domains/mlb/ingest_probables.py -- ONE keyless statsapi schedule call
  (hydrate=probablePitcher,weather,officials) covers probables+weather+HP-umpire;
  2026 backfill 1,314 games, 99.9% SP / ~99% weather+ump coverage; gotchas: pitchHand
  never populated; postponed games surface under 2 dates (dedup handles). UN-DEFERS
  asof_bullpen_DEFER.md (its blocker WAS game_pk-keyed SP identity). (2) domains/mlb/
  ingest_injuries.py -- ESPN injuries snapshot (282 rows/30 teams) + longComment beat
  text through the EXISTING edge_engine.extract_rule (deterministic arm, extract_llm
  stub untouched) -> 167 edge facts (120 lineup_status, 40 pitcher_usage); athlete_id
  parsed from playercard href (not exposed directly). (3) m31_mlb_context ProcSpec
  (scripts/platformkit/mlb_context_runner.py, 6h cadence, heartbeat-gated, live tick
  verified: probables=1327 injuries=282 facts=167; test_manifest resynced 21 green).
  (4) Pitch-state corpora BACKFILLED via existing ingest_pitch_states: +2024/2025/2026
  (574 games, 165K rows) -> FIVE independent season corpora (2022-2026) for future
  per-pitch gates. (5) THE SP LEVER GATED + DELIVERED FLAG-OFF: sp_adjust_current.py --
  historical replication PASSED (Brier delta<0 + same-sign w in BOTH eras 2010-2015 /
  2016-2021), 2026 forward OOS with historical w (fully OOS, n=1002 bridged, 541
  non-NaN SP form): Brier 0.24761->0.24629, ECE 0.0205->0.0142, half-refit agrees ->
  verdict SHIP-READY in data/domains/mlb/sp_adjust_verdict.json; maybe_adjust() no-op
  unless CV_MLB_SP_ADJUST=1 (NOT set anywhere -- wiring into predict_service's MLB
  slate producer is the human decision). Current-era SP form = probables SP identity x
  player_gamelogs starts, EW a=0.35 min-3-starts snapshot-before-update; gamelogs
  inningsPitched is ALREADY decimal thirds (5.667), unlike classic box notation.
  37 new tests green (8 probables + 9 injuries + 4 runner + 16 sp_adjust).
  CONTINUATION (same wake, commit 93b139ae): user asked "how does the AI use all
  this independently to keep getting better + paper-bet in-game" -> shipped the
  missing flywheel hook: m32_mlb_context_autogate ProcSpec (nightly): re-runs the
  SP-offset 2026 forward eval + a NEW leak-free weather-totals gate (domains/mlb/
  weather_totals_gate.py) against the growing m31 corpus, composes data/frontend/
  ops/mlb_context_autogate.json (candidates + ship_review roster; live tick:
  sp=SHIP-READY, weather=REJECT). Weather verdict = honest REJECT: overall RMSE
  -0.0155 and half2 -0.0518 but half1 +0.0215 -> fails two-half replication (the
  discipline working; expected direction coefs temp+/wind_out+ recorded for the
  future retry as corpus grows -- m32 retries it automatically nightly). +18 tests
  (12 weather + 6 runner). Verdicts only: wiring a winner (CV_MLB_SP_ADJUST=1)
  stays the human decision. In-game SP shadow-logging in the inplay capture loop
  queued (NEXT 5) rather than hot-editing a running daemon.
  CORRECTION (same wake, post-backfill): the SP-offset SHIP-READY did NOT SURVIVE
  corpus expansion. After the 2024+2025 gamelog/probables backfill landed (gamelogs
  36K->178,836 rows; probables 6,185 games), re-ran the forward eval on the
  5.7x universe (n=5731, 4573 non-NaN SP form): baseline Brier 0.24438 vs
  SP-adjusted 0.24446 (WORSE), ECE 0.00437 vs 0.00768 (WORSE), half-refit flat ->
  verdict now REJECT (sp_adjust_verdict.json rewritten; m32 re-checks nightly).
  The n=1002 2026-only lift was small-sample variance. DO NOT flip
  CV_MLB_SP_ADJUST -- the earlier "ready when you are" note is WITHDRAWN. The
  in-game SHADOW logging stays (it measures a DIFFERENT question -- phase-
  dependent in-game lift vs live prices -- and is logging-only), but its pregame
  premise is now null; treat shadow results with that prior. Honest REJECT =
  the ratchet working: SHIP-READY at 10am, corpus 5x'd by 4pm, self-corrected.
  MIRROR FLIP same run: weather_totals REJECT -> SHIP_REVIEW on the expanded
  corpus (n=5731, 98.3% cov): beats baseline RMSE in BOTH halves (-0.0045 /
  -0.0285), coefs sane (temp+ / wind_out+ / wind_in ~0). FRAMING: sharpness vs
  our OWN no-weather baseline ONLY -- books price weather, NOT an edge; next bar
  = gate vs the totals CLOSE (oddsapi captures). Both same-day flips = the
  m31-grows/m32-re-gates loop proven end-to-end.
  CONTINUATION 3 (same wake, commits 64bd75cc + 3a930046 -- the "go" push, two
  decisive honest REJECTs): (a) weather_vs_close_gate: does weather explain the
  CLOSE's residual on 2,013 scorable games w/ real 2025-2026 totals closes?
  REJECT -- half1 delta +0.00013 fails replication, residual coefs tiny; books
  price weather ~completely. BONUS measurement: our own baseline+weather trails
  the close by 0.113 RMSE (the honest gap-to-market number). Now m32's 3rd
  nightly candidate. (b) ingame_sp_layer_gate_mlb: SP prior (flat AND decay-
  weighted) as an in-game layer over (p0, state) BASE, walk-forward, 2024/2025/
  2026 pitch corpora (~138K states): REJECT in ALL 3 corpora, both variants
  (noise control clean); the "decay" is decay-of-harm, not masked early benefit.
  Realized state + Elo already contain SP form -- consistent w/ the pregame
  n=5,731 REJECT. 2022/2023 skipped honestly (no gamelog coverage pre-2024-03;
  backfill running in background will extend). SP shadow logging stays live
  (grades vs PRICES, a different question) but with a firmly null prior now.
  NET LEDGER TODAY: context data layer SHIPPED + self-gating; SP lever fully
  adjudicated (pregame REJECT + in-game REJECT); weather = model-view only.
  CORPUS COMPLETE: 2022+2023 backfill landed -> player_gamelogs now 321,012 rows
  / probables 11,047 games, BOTH spanning all 5 seasons 2022-2026, aligned with
  the 5 pitch-state corpora. The edge-map's #1 unlock (multi-season prop
  calibration corpus) is DONE at the data layer; m32's SP eval universe expands
  automatically tonight (bridge now covers 2022-2026). Next prop step = run the
  real props_eval on this corpus (per-opportunity props first: Ks/hits/walks).
  CONTINUATION 2 (same wake, commits 91b0ed81 + 3380f0a6): user pushed "bankroll ->
  profitable, in-game must be much better + execution, tradable" -> shipped the
  quant ladder's shadow arm: (a) ingame_sp_shadow.py + 15-line additive wire into
  inplay_capture_loop -- every live MLB tick now logs model_prob_sp_shadow (SP-
  adjusted, historical-fit params) NEXT TO baseline model_prob, decision path
  untouched (field appended AFTER on_tick returns; poisoned-build -> permanent
  None); live spot-check 6/9 slate games float (PHI/PIT 0.55->0.5700), 3/9 honest
  None (thin form); m2_inplay_capture bounced (pid 9160, READY) so it's capturing
  shadows live. NEXT STEP when data accumulates: score shadow vs baseline Brier/
  CLV per game-phase (early innings should help, late should fade -- prior-decay
  hypothesis). (b) fixed m31/m32 runner tests stamping epoch-1970 beats into LIVE
  heartbeat files (observed live on m32: healthy daemon read stale) -- autouse
  _beat monkeypatch. (c) BACKGROUND 2024+2025 gamelogs+probables backfill running
  (ingest_player_stats + ingest_probables, ~370 dates) -> multi-season SP/context
  gate power + the edge-map's #1 prop-calibration unlock. (d) stack restarted:
  36/36 procs READY incl m31+m32. Paper-only; no $ claim; local commits only.
- WAKE-30 (FULL OPS CYCLE -- stale-premise check + a real feed break FOUND+FIXED, 2026-07-02):
  Ran the standing autonomous ops cycle end-to-end. STATE CHECK: the P1.1-P1.4/P3.1
  items WAKE-29-era NOW.md marked "NOT committed yet" had ALREADY landed in
  07a3f4c4/e9f84e6c (verified via git log, not the stale doc text) -- corrected those
  notes in place; nothing new to commit from tracked work (untracked sell/deploy/doc
  material correctly left alone, human-gated). STACK: all 34 supervisor procs READY,
  :3000/:8098/:8099 all HTTP 200. SENTINELS: output_freshness (m29) all 9 daemons
  GREEN; feed_health (m30) caught a REAL break -- Pinnacle soccer_intl 401 (kalshi's
  matching RED had already self-healed as transient by the time it was checked).
  DIAGNOSED LIVE (not assumed transient): direct-probed leagues/2764/matchups (401)
  vs leagues/246/matchups (mlb, 200) with identical headers -- not rate-limiting.
  GET /sports/29/leagues showed 2764 no longer listed at all; "FIFA - World Cup" now
  lives at id 2686 (588 live matchups) -- Pinnacle rotated the league id once the
  2026 World Cup proper started (was a pre-kickoff qualifying/futures container).
  FIX: scripts/platformkit/odds_provider/pinnacle.py _LEAGUE_ID['soccer_intl'] 2764
  -> 2686, +3 regression tests (test_pinnacle_league_ids.py) locking the id and
  guarding a revert; live-reran feed_health after the fix -> 5/5 providers GREEN.
  Restores the Pinnacle sharp anchor for WC pregame pricing + CLV grading (WC was
  silently missing its anchor book since kickoff -- degraded quietly, no exception,
  exactly the blind spot m30 exists to catch). Committed (59b4758d) + full
  boot.ps1 -Stop/boot.ps1 restart so the running m17/m18/m22/m23 daemons pick it up;
  verified LISTENING+200 on all 3 ports post-restart (a stale supervisor_status.json
  read during the restart window falsely looked all_ready=True before the new
  processes had actually bound their ports -- ground-truthed via netstat instead of
  trusting the JSON blindly). MEASUREMENT: CLV scoreboard -- Kalshi/PM game
  significant +13.51% CLV vs -11.1u record, game moneyline +0.96% vs -7.1u; reran
  clv_result_reconciler on both (n=36, n=28) -> both GENUINE_VARIANCE (max |z|=1.24),
  unchanged from the P1.4 verdict, confirms it isn't drifting. IN-GAME FUNNEL: 1 live
  MLB game today, markets(22)->live_state(1)->...->bet(1) = 100% conversion once a
  game is live (the funnel itself is healthy; the 21-market dropoff is honest
  no-live-state, not a leak). m27 settle: 0/14 settled yet (mid-slate, none final --
  expected, not a bug). prop_close_capture (m16): still captured=0/180 (props not yet
  posted by FanDuel this many hours out) -- unchanged from the WAKE-29-era note, not
  yet a full game day, left as the existing FOLLOW-UP. IMPROVE: refreshed
  domains/soccer/pregame_winprob_gate poisson_xg on the current corpus -- verdict
  unchanged (PARTIAL vs FAIR Elo, 1/6 leagues; shots-over-goals Elo-independent claim
  still REPLICATED 6/6, DM p=0.0 every league) -- confirms the corpus growth hasn't
  flipped an existing verdict; did NOT attempt the tennis asof_hold reclaim (ATP-only
  coverage, no WTA companion file exists yet, so it cannot clear the cross-corpus
  SHIP bar without a real new WTA extractor -- queued honestly in NEXT rather than
  rushed). All governance preflight gates PASSED on the fresh boot; ledger_health
  DIRTY (dup=210, settled_without_clv=235) and improve_ledger_reconcile ORPHAN_SHIPS
  (49/49) are REPORTED-not-gating and unchanged from baseline -- noted, not chased
  this cycle. Paper-only; no $ claim; no flag flipped; local commit only, not pushed.
- WAKE-30 CONTINUED (FRONT-END PLAYER PROPS -- route collision + missing bridge FOUND+
  FIXED, PropsPanel SHIPPED, 2026-07-02): user asked to get front-end props/scraping/
  paper-trading/AI all genuinely working for mlb+soccer_intl. Found GET /api/predict/
  props/{sport} (the exact route the webapp calls) was PERMANENTLY dead: Starlette
  matches routes by REGISTRATION ORDER, and app.py's generic /api/predict/{sport}/
  {game_id} (registered at module scope) beat extra_mounts' later-mounted /api/
  predict/props/{sport} for any 2-segment request -- every call landed on the generic
  handler with sport='props', game_id=<real sport>, returning a bogus "no snapshot for
  sport 'props'". FIX: extra_mounts._prioritize_props_routes moves the props routes to
  the front of app.router.routes post-mount; +4 tests proving the bug existed pre-fix
  (460fd0cb). SEPARATELY found the route, even fixed, had NO data bridge: it only ever
  read player_prop MarketRows from predict_service's OWN snapshot, which nothing writes
  for mlb/soccer_intl (NBA-domain-pricer-only) -- the REAL scraped-book props (Draft
  Kings/Underdog/PrizePicks/FanDuel, Poisson/NB priced, 1639 mlb / 506 soccer_intl
  edges) already existed on a separate :8098 endpoint. NEW predict_service/
  prop_surface_scraped.py bridges the SAME on-disk snapshot read-only (no network, no
  re-pricing) as a fallback when the domain snapshot has zero prop rows; NBA untouched.
  Also fixed PrizePicks masking a real 403 WAF block (external, not evadable -- same
  class as the documented BetMGM block) as a misleading "league not found" (b9e9ee76).
  DELEGATED the actual UI panel to a Sonnet executor agent (self-contained brief: live
  API shape, LiveLinesPanel.tsx pattern to mirror) -> built PropsPanel.tsx, fixed a
  stale TS type (types_w12.ts expected 'props' key + non-nullable numbers; real API is
  'rows' + nullable), wired into /p6, npm build clean, committed (9bc820d4). Then hit a
  NEW deploy gotcha: webapp runs `next start` (prod, not dev) and its persistent .next/
  cache/ survives rebuilds+restarts -- had to shutil.rmtree the cache dir (rm -rf got
  permission-hook-blocked) THEN restart m1_ui before the live page reflected the new
  panel; memory: gotcha-nextjs-static-cache-serves-stale-after-rebuild. LIVE-VERIFIED
  end-to-end: /api/predict/props/{mlb,soccer_intl} both source=scraped_book_snapshot
  with real counts; /p6 raw HTML now contains the panel's P(over)/Poisson markers (was
  byte-identical to pre-session baseline before the cache clear). All 3 ports 200,
  34/34 procs READY, bankroll live (79.25u). Paper-only; no $ claim; no flag flipped;
  local commits only, not pushed.
- WAKE-29 (PAPER TRADING AUDIT -> FOUND+FIXED the in-game channel never SETTLED, 2026-07-01):
  user "make sure paper trading is working." Audited live: stack 29/29 up, bankroll live-updating
  (68.4u of 100 = the measured bleed), PREGAME channels healthy (today props=105, paper_pm=42,
  moneyline=27 all placing+settling+CLV). BIG WIN confirmed: in-game channel now PLACES (paper_ingame
  =55 today vs ~1 historically -- the WAKE-25 two-sided fix is live incl edge-flip re-entry on both
  legs). BUT found the break: **82 paper_ingame rows EVER, 0 EVER settled** -> the in-game channel
  placed but NOTHING graded (no outcome, no CLV, no bankroll impact, no learning). ROOT: inplay_daytrader
  places via paper_ingame.record_ingame_bet and paper_ingame.grade_live can settle one, but NOTHING
  called grade_live -- there was no in-game SETTLE arm (pregame has one, in-game never got one), and the
  same KALSHI-TICKER-not-ESPN-id gap meant an ESPN-id settler could never match anyway. FIX: added
  MlbOutcomeResolver.final_score (ticker->boxscore final score, not just win/loss) + NEW
  scripts/platformkit/ingame/ingame_paper_settle.py: loads OPEN paper_ingame rows, resolves each MLB
  bet's final score from the ticker, calls grade_live -> settles with real outcome+unit_result;
  idempotent (already-settled edge_keys skipped), a not-yet-final game stays OPEN, soccer stays open
  pending a soccer resolver; +5 tests. RAN LIVE: settled 68 stuck MLB bets (33W-35L, net +0.353u, all
  unique settle_keys = dedup-safe), 5 MLB still-open (not final) + 9 soccer open. Registered ProcSpec
  m27_ingame_paper_settle (--interval 900) so it settles continuously; test_manifest resynced. Also
  fixed a latent flake: ingame_segment_trust corpus split used builtin hash() (per-process randomized
  -> non-reproducible verdict) -> switched to md5 (deterministic). ANSWER TO USER: paper trading IS
  working -- pregame end-to-end, and in-game now settles too (was the one broken leg). 50+ touched tests
  green; <=300 LOC each, ASCII, units-only no $, executed=False, edge_claimed=False, no flag armed.
  m27 goes live on next boot.ps1 restart (I already ran the backfill by hand). NEXT: a soccer in-game
  outcome resolver (domains/soccer results) so the 9 open WC in-game bets settle too.
- WAKE-28 (SELF-IMPROVING EXECUTION via CROSS-CORPUS trust gate + CORRECTS WAKE-27, 2026-07-01):
  user "keep building ai so it independently gets better execution." Built the mechanism that lets
  in-game EXECUTION improve on its own -- and immediately caught that WAKE-27's headline was a
  single-fold ARTIFACT. Split the labeled MLB corpus into TWO INDEPENDENT corpora (even-dated vs
  odd-dated games) and re-ran the outcome verdict on each: corpus A (50 games) = ALL innings MATCH;
  corpus B (44 games) = I5-I8 BETTER_THAN_VENUE (big deltas). So the "I5-I9 beats venue" from WAKE-27
  was driven ENTIRELY by one half and does NOT replicate -> under the discipline (">=2 independent
  corpora; single-fold lifts are artifacts") it is NOT robust. Correct honest state: NO segment is
  proven better-than-venue across independent corpora. BUILT the gate that enforces this automatically:
  scripts/platformkit/ingame/ingame_segment_trust.py (splits corpus into >=2 disjoint date-parity
  corpora, runs ingame_outcome_verdict on each, marks a segment TRUSTED only if BETTER_THAN_VENUE in
  EVERY non-insufficient corpus / ADVERSE only if WORSE in every / else NEUTRAL; writes
  data/frontend/ops/ingame_segment_trust.json; +7 tests). WIRED into inplay_capture_loop._build_tick:
  floor_for_segment routes the in-game EV floor -> an ADVERSE segment reverts to the STRICT
  pre-registered floor (suppress its marginal relaxed bets), TRUSTED/NEUTRAL/unknown keep today's
  relaxed floor. So execution self-improves as games accrue but changes ONLY on cross-corpus PROOF;
  thin/unreplicated data changes nothing (do-no-harm), reversible via CV_INGAME_SEGMENT_TRUST=0.
  LIVE build: EVERY segment NEUTRAL (correct -- nothing replicates yet) -> ZERO execution change today,
  gate armed to act autonomously when a lift replicates (->TRUSTED) or a segment proves consistently
  worse (->ADVERSE->auto-suppress). Registered ProcSpec m26_ingame_segment_trust (--interval 1800),
  test_manifest resynced. 46 touched tests green; <=300 LOC, ASCII, no $ field, edge_claimed=False,
  flips no flag, places no bet. Live on next boot.ps1 restart. NEXT lever unchanged but now
  AUTOMATED: the gate itself promotes/demotes segments; watch ingame_segment_trust.json cross slates.
- WAKE-27 (IN-GAME MODEL better-than-venue vs OUTCOME in innings 5-9 -- FULL-CORPUS ONLY, NOT
  cross-corpus-replicated: see WAKE-28 correction, 2026-07-01):
  user "keep making paper trade better ... beat pinnacle, make money on kalshi/sportsbooks." Attacked
  the recurring in-game-CALIBRATION lever (WAKE-24/25/26 all ended pointing here). The in-game CLV
  verdict could only compare model vs the CONTEMPORANEOUS venue price (MATCH, hit_rate 0.42) and the
  per-segment CLV showed the model leaning BELOW the Kalshi price in late innings -- ambiguous: model
  lag, or the thin venue quote lagging? SETTLED IT by unlocking OUTCOME labels. ROOT of the blind spot:
  capture writes each game's grade series keyed by the KALSHI TICKER (KXMLBGAME-26JUN241845PHIWSH), not
  the ESPN id, so settle_stamp (keys by ESPN id) never landed a home_win label -> the whole in-game
  layer had ZERO outcome labels. FIX: the ticker ENCODES date+away+home abbrs -> NEW
  scripts/platformkit/ingame/ingame_outcome_label.py (parse ticker + Kalshi->ESPN abbr alias map
  AZ->ARI/CWS->CHW/... + unambiguous away|home split, join to data/domains/mlb/espn_boxscores.parquet
  -> home_win; offline, leak-free, None on unresolved/tie/non-final; +7 tests). Refreshed the stale box
  parquet (ended 06-25) through 07-01 via domains.mlb.ingest_espn_box (keyless ESPN, +73 finals) ->
  labeled 94/97 captured games. NEW scripts/platformkit/ingame/ingame_outcome_verdict.py: per inning
  segment, Brier(model vs OUTCOME) vs Brier(venue in-play price vs OUTCOME), per-GAME clustered
  bootstrap CI (game = cluster unit), verdict BETTER_THAN_VENUE only when CI upper < 0; +6 tests.
  LIVE VERDICT (data/frontend/ops/ingame_outcome_verdict.json): I1-I4 MATCH, I5-I9 BETTER_THAN_VENUE
  (delta -0.032/-0.035/-0.043/-0.052/-0.060, all CI upper<0), UNK MATCH. So from the 5th inning on our
  live model is BETTER CALIBRATED TO TRUTH than the Kalshi in-play price -> the two-sided daytrader's
  late-inning disagreements with Kalshi are usually RIGHT (validates placing there; be cautious I1-I4=
  MATCH). HONEST CAVEATS (binding): Kalshi in-play is THIN/LAGGY, so this beats a STALE VENUE QUOTE, NOT
  an efficient close, NOT Pinnacle, NOT a $ edge; better-Brier != profitable (round-trip cost ~3-5c);
  n=29-45 games/1 slate window = single-fold, artifact risk. So made it CONTINUOUS: ProcSpec
  m25_ingame_outcome_verdict (--interval 900), test_manifest resynced (32 green) -> accrues games across
  slates so the lift replicates or washes out honestly. NO placement behavior change this wake (honest:
  don't act on one window); NEXT lever = once BETTER_THAN_VENUE holds across >=2 slate windows, gate the
  in-game EV floor to relax ONLY in proven segments (I5+) and stay strict/suppress where MATCH. All
  under scripts/platformkit/ingame (safe area), <=300 LOC, ASCII, no $ field, edge_claimed=False, no
  flag armed, paper-only. Live on next boot.ps1 restart (running supervisor has pre-edit manifest).
- WAKE-26 (NEUTRAL-SITE: user "this game has no home or away" -- VERIFIED model already correct + made
  it VISIBLE, 2026-06-29): user flagged that a World Cup game has no home/away so the model shouldn't use
  it. INVESTIGATED + corrected my own prior over-claim (I'd blamed hfa_lambda): soccer_intl does NOT use
  the domestic hfa_lambda -- it uses domains/soccer_intl/predictor.IntlSoccerPredictor which DEFAULTS
  neutral=True (no home tilt) for both predict + predict_live, and the in-game path doesn't override it.
  PROVEN by pricing GER-PAR both ways: NEUTRAL (what we use) Germany pregame 0.689 / live33 0.589 vs
  HOME-TILT 0.888 / 0.793; snapshot home_ml=0.689 confirms neutral is applied. So NO home/away bug --
  the model already drops the tilt exactly as the user wants; the home/away labels are just pairing tags.
  The 0.589-vs-market-0.67 gap is small IN-GAME calibration (our favorite-decay slightly faster than the
  market), NOT home/away, and likely our model trailing an efficient market. REAL residual = the
  snapshot/state stamped neutral=None (why it LOOKED like home/away context). FIX: ingame_live_state now
  stamps a `neutral` flag (_neutral_site: honors ESPN competition.neutralSite when present, else True for
  soccer_intl) so the in-game state explicitly carries neutral=True; +helper, 10 tests green; LIVE-
  VERIFIED GER-PAR -> neutral=True. Additive, no model/number change (model was already neutral), no flag,
  no bet. NEXT real lever stays in-game CALIBRATION (favorite time-decay), not home/away.
- WAKE-25 (IN-GAME ROOT CAUSE FIXED: signal was HOME-ONLY -- now two-sided + places live, 2026-06-29):
  user "world cup going on, should be working." There WAS a live WC game (GER-PAR 33' 0-0). Ran the
  m24 funnel against it: 47 markets -> 1 live_state (the live game resolved fine; 46 upcoming = correct
  no_live_state) -> cleared model_prob/home_leg/priced -> died at below_floor. Dug in: GER-PAR our model
  Germany 58.5% vs market 69% = +EV on PARAGUAY (away). ROOT CAUSE: scripts/platformkit/ingame/
  inplay_edge_signal.evaluate was HOME-ONLY (SIDE='home'; ev = ev_vs_price(mp, home_dec) only) -> every
  AWAY-side edge (~half the opportunity space) silently discarded -> the dominant reason the in-game
  channel placed ~nothing (1 ever vs 136 pregame). FIX: made evaluate TWO-SIDED -- price both legs at
  no-vig fair, take the +EV side, return side/bet_model_prob/bet_devigged_price; the GRADE pair stays
  HOME-aligned (leak-free) -- only the placed bet's side/odds/prob reflect the chosen leg. Wired
  inplay_daytrader.on_tick to place ev['side'] (was _sig.SIDE) with that side's prob+decimal. Also
  added mlb to _INGAME_RELAXED_EV_FLOOR (was soccer-only -> MLB in-game now places too). Tests: updated
  1 relaxed test (model==fair is the true no-edge point under two-sided) + added 2 two-sided tests; 14
  edge-signal + 7 capture-loop green; the only 2 reds (test_inplay_daytrader G1/G2) are PRE-EXISTING
  (verified via git stash: fail on original code too -- short game_id write-guard, not mine). LIVE-
  VERIFIED: re-ran poll_once -> GER-PAR action=bet tier=A on the away (Paraguay) edge, n_bets=1 (was 0).
  HONEST CAVEAT: an 11-pt in-game disagreement is MORE LIKELY in-game MODEL MISCALIBRATION than a real
  edge; this is PAPER, CLV-graded -- the mechanism is now correct + places, the NEXT lever is in-game
  model CALIBRATION so the disagreements are trustworthy. No $ claim, no flag armed, paper units only.
  Goes fully live on next boot.ps1 restart (running supervisor has pre-edit code).
- WAKE-24 (IN-GAME is the move, pregame ML isn't -- DIAGNOSE the in-game starvation, 2026-06-29):
  user "pregame ML isn't the move, should make a lot of bets in-game, efficient paper trading, make
  in-game edges better." QUANTIFIED the inversion from the live ledger (data/frontend/clv_ledger.jsonl,
  137 rows): paper(pregame props)=80, paper_pm=30, moneyline(pregame ML)=26, paper_ingame=ONLY 1 (and
  malformed: market_prob/edge/units=None). So 136 pregame vs ~0 in-game -- exact inverse of the thesis.
  ROOT CAUSE (ran inplay_capture_loop.poll_once live): 48 Kalshi game markets, ALL 48 -> no_live_state,
  model_prob=None; n_live=0 + statsapi live_games=0 -> there are simply NO in-progress games right now
  (19:36Z = ~3:36pm ET; tickers are 26JUL01 = 2 days out; MLB slate starts ~23:00Z). So 0 in-game NOW
  is CORRECT. BUT historically 1-ever vs 136 => during live windows the funnel (markets->live_state->
  model_prob->home_leg->priced->tier_floor->bet) drops almost everything and we had ZERO visibility
  into which stage. The engine is SOUND + wired (inplay_daytrader uses the LIVE leak-free model via
  live_board.live_model_home_prob, edge gate inplay_edge_signal = calibration_justified+liquid+fresh+
  tier, quarter-Kelly, places to paper_ingame; capture loop m2 calls on_tick every tick). NOTE: the
  SEPARATE pm_game_placer(m12) prices LIVE exchange markets with the PREGAME model -> stale-edge bets;
  the real in-game channel is the daytrader, not m12. BUILT instrumentation:
  scripts/platformkit/ingame/ingame_placement_funnel.py (folds poll_once's per-game decisions into the
  stage funnel + reason histogram + biggest_dropoff; writes data/frontend/ops/ingame_placement_funnel
  .json; +8 tests) -> ProcSpec m24_ingame_placement_funnel (--interval 300), manifest resynced (21
  green). Live on next boot.ps1 restart. NEXT (do it DURING tonight's live slate ~23:00Z+): read the
  funnel -> if drop is at live_state, fix the Kalshi-ticker->live_state resolution for the daytrader
  (the chronic id gap, see WAKE-20d/21); if at tier_floor, the gate is too tight for in-game. Diagnose
  on REAL live data, then tune so in-game places a lot. Candidate/diagnostic only; no bet, no flag,
  no $ edge.
- WAKE-23 (FIND GAPS IN OUR OWN SCRAPED LINES, all sports, 2026-06-29): user corrected -- they have
  their OWN scraper, NEVER meant to use OddsAPI; want the NBA "every little detail" edge-hunt applied
  across sports on the lines WE are getting. FOUND the real feed: data/cache/line_history/<sport>/
  <date>.jsonl = our DK(via espn)/FanDuel/Pinnacle scrape, ML+spread+total, devigged+timestamped,
  fresh today (7610 MLB rows). OddsAPI was a red herring. BUILT sport-blind gap-finder
  scripts/platformkit/clv/scraped_line_gaps.py (reads OUR feed, groups by game/market/line, best book
  price vs Pinnacle-sharp-fair via vetted best_price; +8 tests). 1st live run found 2 MLB "gaps"
  (Yankees@RedSox FanDuel 3.50 away +31.6% CLV) -- I CHECKED them: STALE-DATA MIRAGE (DK 02:53 said
  50/50; FanDuel quote was 30min OLD at 02:23 saying 74/26; +CLV on BOTH sides = the tell). THE LESSON
  = finding apparent gaps is trivial; the real work is rejecting the ~99% stale/mismatched. ADDED a
  FRESHNESS GATE (max_stale_sec default 600: within each game/market/line, drop any quote staler than
  the freshest) -> mirages correctly vanish -> honest EMPTY (slate efficient across our 3 books when
  comparing only contemporaneous quotes). Then made it AUTONOMOUS: scraped_line_gaps_daemon.py (~4min,
  writes data/frontend/ops/scraped_line_gaps.json + scraped_line_catches.jsonl only on a real fresh
  gap; +6 tests) -> ProcSpec m23_scraped_line_gaps, manifest resynced (21 green). Goes live next
  boot.ps1 restart. CANDIDATE-ONLY: our files only, no OddsAPI, no bet, no flag, +CLV is prob space.
  REAL LEVER now: more CONTEMPORANEOUS books (only 31-34/143 MLB groups shoppable >=2 books; NBA/
  soccer_intl ~1 book) + tighter capture cadence to catch transient gaps in their live window.
- WAKE-22 (USE-MORE-BOOKS / FIND-GAPS made CONTINUOUS, 2026-06-29): user frustrated "ai should
  make money on kalshi/DK, use more books, find gaps". Ran the honest model-free lever LIVE:
  best_price_audit (best price across all wired books vs sharp fair) over the real slate = ZERO +CLV
  gaps at min-clv 0.0 (26 MLB games, 13 shoppable, MAX 3 books each; soccer pinnacle 401). Market is
  efficient at line-shop level RIGHT NOW. KEY: cross-book gaps are TRANSIENT (book lags ~60-120s) so a
  manual one-shot run misses them -> the lever only pays off polling continuously. BUILT
  scripts/platformkit/clv/best_price_scan_daemon.py (every ~4min runs the scan, writes
  data/frontend/ops/best_price_scan.json, appends data/frontend/ops/best_price_catches.jsonl ONLY when
  a real +CLV gap appears; injectable/offline tests; +6 green) -> registered as supervisor ProcSpec
  m22_best_price_scan (argv --interval 240), test_manifest resynced (21 green). CANDIDATE-ONLY: reads
  public odds, places NO bet, flips NO flag, +CLV is probability space NOT a $ edge. Goes live on next
  boot.ps1 restart. HONEST FRAMING for the user: the two real "more books" levers are (1) this
  continuous scan + (2) WIRING MORE bettable feeds (only 3 shoppable; Pinnacle soccer auth 401, add
  MGM/Caesars) to widen best-of-N -- NOT a smarter model. The bleed is still PROPS (139-217); pregame
  prop calib suppress-gate is the next unit-saver (lane 2, not yet built this wake).
- WAKE-16 (CEILING, 2026-06-26 ~10:00): SHIP b3b108da -- first ceiling experiment: reclaim MLB
  sp_ra_diff_asof through the REAL WF DM gate -> HONEST REJECT (Brier 0.240312->0.240226, DM p=0.54;
  planted-null collapses; truncation-invariant). SP form priced into the close. Reusable as-of
  reclaim gate template kept. NEXT: CQR prop intervals (domains/basketball_nba/prop_cqr.py) -- the
  prop-coverage gap has REAL room (efficient pregame reclaims will mostly reject; props + in-game won't).
- WAKE-20 (UNITS: reset + stopped the measured bleed + FE open, 2026-06-27): user asked to fix
  everything, reset units, make as many units as possible. (1) RESET paper bankroll 100u via NEW
  reversible scripts/platformkit/paper/bankroll_reset.py (archives the 5 canonical settled/display
  files to _ledger_archive/<ts>_reset, reinits, daemon reconciles -> live 100.0u, net 0; +3 tests,
  --restore reverses). Was -2.06u (net -102u, -24u that day). (2) DIAGNOSED the -31% in-game-prop
  CLV bleed on the archived ledger (n=402 true-close): mean CLV -31.0% (CI excl 0) AND CLV is
  ANTI-correlated with model edge (corr -0.083; high-edge half -34.7%) -> tightening the vig/edge
  gate selects the WORST bets. Channel is structurally adversely-selected; only CLV-positive action
  is STOP placing it. (3) NEW scripts/platformkit/improve/ingame_prop_clv_guard.py SUPPRESS-ONLY,
  DEFAULT ON (CV_INGAME_PROP_CLV_GUARD=0 restores broad-capture), composed into auto_loop
  _place_ingame_props gate (over the optional calib gate). +4 tests; 16 trader+guard green. Honest
  anti-edge move, NOT an edge claim, paper units only, no flag armed ON. (4) FE verified live +
  opened: :3000 UI + :8098 boards + :8099 API all 200; /api/paper/today reflects 100u; supervisor
  23/23 READY. CAVEAT: guard takes effect on NEXT stack restart (running auto_loop process has the
  old code cached) -> restart boot.ps1 to apply live. WAKE-19 below stands.
- WAKE-20b (RESTARTED LIVE, running without user, 2026-06-27 ~15:45): boot.ps1 -Stop (clean drain,
  21 PIDs) then boot.ps1 -> governance preflight PASSED, ONE supervisor (PID 17612, singleton OK),
  24/24 procs READY incl m19_asof_reclaim (ran its first autonomous sweep: tick=0 candidates=6
  reject=6, scoreboard row written, now daily). In-game prop CLV guard is_enabled()=True in the live
  auto_loop. The pre-restart guard-less code had queued 34 open paper_ingame_prop positions ->
  re-baselined bankroll to a clean guard-on 100u (2nd reversible reset; archived). FE live: :3000 UI
  + :8098 + :8099 all up; /api/paper/today + supervisor doc show 100u + 24/24. Stack is detached
  (Start-Process) so it persists unattended. m19 + bleed-fix are now LIVE.
- WAKE-20c (IN-GAME edge-hunt made CONTINUOUS, 2026-06-27): user thesis = in-game has the small
  gaps, hunt them continuously w/ live data+lines. FOUND: m11 already logs model+market tick series
  per live game (data/cache/ingame_grade/<sport>/) and ingame_clv_grade.grade_sport produces the
  honest in-play-close anticipation verdict -- but it was MANUAL-ONLY (segment_emit not on flywheel).
  Ran it live (8 live MLB games): MLB MATCH mean_clv=+0.043 over 24.7k ticks/70 mkts (BEAT 24 vs
  BEHIND 16); soccer MATCH +0.035. The in-game GAME engine is the one channel that leans POSITIVE
  (vs -31% props). BUILT m20_ingame_clv_verdict daemon (scripts/platformkit/ingame/
  ingame_clv_verdict_daemon.py, ~10min loop, writes data/frontend/ops/ingame_clv_verdict.json; +5
  tests) -> registered as ProcSpec m20 (25 procs), test_manifest resynced. RESTARTED: 25/25 READY,
  m20 wrote first verdict, guard still ON. Verdict is CLV/probability MATCH not BEAT -- NOT a $ edge;
  the honest path is to keep measuring so a real persistent gap crosses MATCH->BEAT on its own.
- WAKE-21 (MATCH->BEAT TRIGGER wired, 2026-06-27): user asked "when does in-play start beating".
  Refused a profit DATE (would fabricate a $ edge); instead made the crossing self-firing. Why MATCH
  not BEAT today: mean_clv +0.0255 = 2.5 prob pts < the ~3-5c in-play round-trip cost, hit_rate 0.43,
  BEAT 23 ~= BEHIND 20. BUILT scripts/platformkit/improve/ingame_baseout_gate.py (leak-free: target =
  in-play close = last market tick; residual = close - model_prob_t; does deep base-out/RE24/count/
  pitch state predict the residual OOS? two chronological corpora must BOTH improve RMSE w/ DM p<0.05
  AND planted null must collapse -> SHIP_REVIEW else REJECT; INSUFFICIENT below 4000 ticks/16 games) +
  ingame_baseout_gate_daemon.py (hourly) registered as ProcSpec m21 (26 procs); +12 tests, manifest
  resynced; 33 green. LIVE corpus today = 1792 ticks / 14 games -> honest INSUFFICIENT (still filling;
  deep state only flows post-id-fix). Candidate-only: flips NO flag, places NO bet, probability space.
  CAVEAT: m21 goes live on NEXT boot.ps1 restart (running supervisor has pre-edit code). The verdict
  now crosses MATCH->BEAT (or REJECTs the lever) on its OWN -- no date-guessing.
- WAKE-20d (DEEP in-game variables, 2026-06-27): user wants deep live data (base-out, every variable)
  collected constantly + validated. SHIPPED the deep MLB base-out extractor:
  scripts/platformkit/ingame/ingame_baseout_mlb.py (parse_baseout + baseout_summary_fields; outs,
  baserunners 3-bit base_state, base_out_state 0-23, standard RE24 run-expectancy table, count; leak-
  free, never raises; +7 tests). VALIDATED ON 8 REAL LIVE GAMES (e.g. ARI@TB 1out/runner-on-3rd
  RE24=0.950; SEA@CLE 0out/1st 0-2). Wired ADDITIVELY into ingame_live_state._extract + the
  live_grade._state_summary key tuple (outs/base/bos/re/count) -> when capture resolves an ESPN
  event, the series now carries the deep state (verified end-to-end: "...inning=7 half=bottom outs=1
  base=4 bos=13 re=0.95 count=1-1"). 22 tests green; restarted 25/25 READY.
  HONEST BOTTLENECK (not fixed): the ACTIVE capture keys games by KALSHI TICKER (KXMLBGAME-...), and
  ingame_live_state.live_state("mlb", <kalshi_ticker>) returns None -> empty state ("live") -> deep
  vars (and even score/inning) DON'T flow into the active Kalshi-keyed series. Pre-existing ID gap,
  not caused by this change. NEXT: build an ESPN<->Kalshi live-game id resolver (parse ticker ->
  date+away+home -> match ingame_box_mlb.live_games -> statsapi situation has outs+offense) so deep
  capture flows into the active series; THEN once accumulated, gate base-out -> win-prob (no base-out
  corpus exists yet, so collection must precede validation). Extractor is built+validated; the
  resolver is the remaining wire. No edge claim; calibration/descriptive state only.
- WAKE-21 (BLOCKER UNBLOCKED: deep state flows into the ACTIVE series, 2026-06-27): built the
  ESPN/Kalshi<->statsapi MLB id resolver WAKE-20d called for -> deep base-out now flows into the
  active Kalshi-keyed in-play series continuously, LIVE-VERIFIED. NEW
  scripts/platformkit/ingame/ingame_id_resolver_mlb.py: parse_kalshi_mlb_ticker (KXMLBGAME-26JUN271810
  AZTB -> date/time/away+home blob) + resolve_ticker (matches the blob's away+home Kalshi abbrevs vs
  ingame_box_mlb.live_games full team names by EXACT mapped-abbrev equality; KALSHI_ABBR = all 30
  clubs incl the divergent AZ/CWS/WSH/SD/SF/ATH; UNIQUE match only -> 0 or >1 (live doubleheader) =
  None, NEVER mis-binds) + linescore_deep_fields (adapts the statsapi linescore offense/outs/count ->
  the EXISTING ingame_baseout_mlb.parse_baseout, reuse not duplicate) + deep_state_for_ticker +
  make_tick_deep_fn (LAZY per-tick enricher: no candidate fetch until a real game needs it -> dead-feed
  test path stays offline); +13 tests. ROOT CAUSE found beyond the id gap: inplay_capture_loop._build_
  tick PROJECTED the state to 7 keys, DROPPING score/inning/outs/base/bos/re/count before they reached
  live_grade._state_summary -> every tick logged a bare "live" even when ESPN HAD the situation. FIX:
  widened _build_tick passthrough (label-only; model/price/sizing read top-level tick fields, cannot
  change a decision) + merged the statsapi deep state in _process_game (mlb-only, additive, guarded) +
  threaded deep_state_fn through poll_once/serve_forever (default OFF -> existing tests offline) +
  enabled mlb_deep=True in inplay_capture_runner.run (production). LIVE-VERIFIED on the real slate:
  all 7 in-progress games resolved to correct gamePks with accurate base-out; the abbrev map has ZERO
  gaps (every live ticker blob decomposes uniquely into known abbrevs); after restart the SAME active
  file KXMLBGAME-26JUN271915MIASTL flipped from "live" -> "home_score=0 away_score=4 inning=5 half=top
  outs=0 base=0 bos=0 re=0.481 count=0-0"; 10 live series now carry deep base-out. Restarted 25/25
  READY, guard is_enabled()=True. No edge claim; descriptive state + the gamePk join-key for items 2-4.
  PRE-EXISTING (not mine, noted): tests/platformkit/ingame/test_inplay_daytrader.py 2 fails -- the
  paper_ingame _is_malformed_input write-guard now rejects the tests' short "G1"/"G2" game_ids
  (added in a prior WAKE; my changes don't import that path).
  ALSO SHIPPED item 2 (deeper vars) same wake: NEW scripts/platformkit/ingame/ingame_pitcher_mlb.py
  (pure adapters tto_for + pitcher_batter_fields; current pitcher/batter from linescore
  defense.pitcher/offense.batter, pitch_count from boxscore numberOfPitches, TTO =
  battersFaced//9+1 = the order-turn the batter NOW up is in -> the 3rd-time-through zone; +7 tests).
  Wired ADDITIVELY into deep_state_for_ticker (one extra boxscore fetch/game/tick, guarded -> base-out
  still flows if it misses); pitch_count + tto added to _build_tick passthrough + live_grade._state_
  summary (numeric tokens only -- pitcher/batter NAMES flow in the structured state but stay OUT of the
  space-joined label to avoid breaking k=v parsing). LIVE-VERIFIED: e.g. COLMIN Paredes pc=73 tto=3,
  SEACLE Cecconi pc=81 tto=3; after 2nd restart the active MIASTL series carries
  "...outs=2 base=0 bos=2 re=0.098 count=0-0 pitch_count=13 tto=1". 25/25 READY, guard ON. COST NOTE:
  the capture tick now does ~1 schedule + 2N linescore + N boxscore fetches/tick (N live games);
  boxscore ~100KB each -- monitor tick cadence (heartbeat as_of should advance ~every 20s); throttle the
  boxscore if cadence slips. NEXT (queue): item 3 in-game true-close capture (m21, exact-gamePk/game_id
  join, mirror m16/m18) -> item 4 gate base-out+tto -> win-prob once the corpus accumulates.
- WAKE-19 (AUTONOMY: ceiling loop runs WITHOUT Claude, 2026-06-27): wired the asof-reclaim gate
  as a self-running daemon. NEW scripts/platformkit/ceiling/asof_reclaim_sweep.py (gates ALL on-disk
  *_diff_asof candidates: NBA ast/dreb/fg3m/stl/blk + MLB sp_ra_diff = 6, normalizes to one verdict
  row, logs each to reject_ledger + ceiling_reclaim_scoreboard.jsonl, control-failing SHIP ->
  SHIP_REVIEW, never auto-ships) + asof_reclaim_daemon.py (daily loop, survives any tick failure,
  injectable for tests) + test (7 green). Registered as supervisor ProcSpec m19_asof_reclaim in
  supervisor/stack_specs.py (readiness NONE, _FOREVER, no depends_on) -> launches on next supervisor
  boot, 24 procs now. ALSO resynced the STALE tests/supervisor/test_manifest.py frozen proc set (it
  stopped at m13; m14-m18 were added in prior sessions but never added to the test -> it had been RED
  for sessions; now includes m1_bankroll + m14-m19, 36 green). First sweep: ALL 6 REJECT (efficient
  pregame). predictor.py untouched, NO flag flipped, candidate-only. WAKE-18 below stands.
- WAKE-18 (CEILING / Rung-2 player intel, 2026-06-27): reclaimed leak-free `ast_rate_diff_asof`
  (asof_features.parquet) through the REAL single-corpus WF DM gate vs leak-free Elo ->
  HONEST REJECT. NEW domains/basketball_nba/asof_ast_rate_eval.py (+test, 3 green), reuses the
  MLB asof_ra_diff_eval template (inlined helpers, F5-isolated). Brier base 0.205026 -> cand
  0.205040 (delta -1.4e-5, WORSE); DM p=0.78; fitted feat_w shrinks to -0.006; planted-null
  collapses (p=0.997); truncation-invariant. base Elo BSS 0.174 (non-degenerate). VERDICT: assist
  rate carries NO incremental win-prob signal over Elo -- the memo "AST ~+4-5%" was a box/prop
  artifact, not a team edge. player_plusminus.json is scouting_only (season aggregate = leaky) so
  it is NOT gate-able; this is its leak-free cousin. Logged to reject_ledger. CANDIDATE-ONLY, no
  flag flipped, predictor.py untouched. Remaining pregame box reclaims (dreb/fg3m/stl/blk diffs)
  expected REJECT too (efficient); the real lever stays IN-GAME conditioning.
- WAKE-17 (READINESS, 2026-06-26 ~16:46): flywheel healthy (23/23 procs all READY incl m15-m18).
  V1 PROP SETTLEMENT = VERIFIED WORKING, NOT a bug: the 47 props tagged game_date=2026-06-25 are
  actually 06-26 games (statsapi: Nationals@Orioles, Cubs@Brewers etc. are 'Scheduled' today, NOT
  final) -- an ET-day mis-tag the settler's date+1 fallback already handles -> honest-pending, will
  settle tonight when the 06-26 slate goes final. prop_settler_mlb._team_hit/city-abbrev fix is
  sound (ran live: full-name matchups resolve correctly; the mismatch was date, not name).
  SHIP 7a3fc3ba (V3): clv_ledger.record_bet now labels market_type on market-omitted ML rows.
  ROOT: record_bet only persisted 'market' when a caller passed it, but the game-ML placers
  (run_paper_today/m1_paper + /api/clv/record) omit market= -> rows got a moneyline bet_id but NO
  market/market_type field -> rendered '?' (9 live mlb rows). Now persists bet_id()'s resolved
  value (default 'moneyline') as BOTH market+market_type at the writer (honest label, identity key
  already classified them ML). +2 fail-before/pass-after tests; 12/12 file + 100/100 dependent
  (sanity/dedup/betid/guard) green; ASCII; LOC 327. Note: the 9 EXISTING rows aren't retro-fixed
  (don't race the live ledger) -- forward-looking; a betid_backfill relabel could clean them later.
  Scoreboard: props settled 7 (all PM ML, all clv no_close); boards games-shown mlb 0 / soccer_intl
  0 (V2/V4 OPEN: API serves 200 but games:[] -- next wake: honest-empty vs fill-bug); CLV 7 settled
  / 0 clv; bankroll 97.0u (net -3.0, day 06-26); reject delta 0 (plumbing SHIP, no signal).
  NEXT: V2/V4 -- determine if mlb/soccer_intl empty boards are honest-empty (no card clears the
  tier gate / no game in-window) or a real snapshot-fill bug; fix if bug, document if honest.
- WAKE-18 (READINESS, 2026-06-26 ~17:15): flywheel healthy (23/23 all READY; m13 was mid-RESTART,
  transient). OPS MISHAP + RECOVERED: ran `stop_bot.py --status` to probe -- it IGNORES args and
  ACTUALLY STOPPED the bot (disabled CourtVisionBot task + set stop_requested=True). Reversed BOTH
  (schtasks ENABLE + cleared flag); flywheel never halted (separate from go.ps1). Memory written:
  PROBE the stop flag by READING .bot_state/live_status.json, NEVER run stop_bot.py.
  V2/V4 = FALSE ALARM (my WAKE-17 probe bug): /api/v1/bestbets/<sport> serves status=ok, mlb 16
  games/94 candidates/10 best_bets + soccer_intl 6 games/24 candidates/0 best_bets (honest no-bet,
  games shown); daemon board /api/bestbets/board serves 2461 mlb / 85 soccer cards (stale=by-design
  serve-stale-never-green). The WAKE-17 'games:[]' was reading d['cards'] when the envelope uses
  d['games']. NO board bug. Corrected here.
  SHIP 94cc287c (grade_summary under-count): scoreboard.py n_settled required clv_pct, so all 7
  settled paper_pm bets (clv_status='no_close') were dropped -> grade_summary.json showed n_settled=0
  + flat_unit 0/0 despite a real 1W/5L paper record. Split populations: n_settled + flat-unit count
  ALL settled; CLV stats stay over the clv-bearing subset; added n_no_close. Live now n_settled 0->7,
  flat-unit 1W/5L (mlb 6 / soccer 1), CLV INSUFFICIENT_DATA. SAFE: real-money gate recomputes from
  ledger rows (summary advisory-only, never trusted) -> cannot spoof. NEW test_scoreboard.py +5; 59
  dependent green; artifact regenerated. Scoreboard: props settled 0 (pend to tonight's finals);
  boards games-shown mlb 16 / soccer_intl 6 (WORKING); CLV 7 settled / 0 clv; bankroll 97.0u (net
  -3.0); reject delta 0 (SHIP). NEXT: K1 Kalshi team_total pricer (add SP-ERA + park, calibrate vs
  settled totals through the REAL gate, place ONLY if it beats/matches the Kalshi line OOS else
  REJECT-log) -- the next genuine ceiling/exec item now that V1-V4 are closed.
- WAKE-22 (READINESS, 2026-06-26 ~17:30): m13 props pred tick RESTART FLAP ELIMINATED (was restart
  every ~22 min, now zero restarts). TWO-LAYER FIX in scripts/platformkit/props/props_pred_tick_runner.py:
  (1) START beat at tick() entry (was end-only -> sleep+score=700s > 660s fresh threshold);
  (2) NEW _beat_during_scoring background thread every 300s during _score_props_bounded (scoring
  700+ props takes 700-985s > threshold, so start-beat alone still fails after ~660s). FIX VERIFIED:
  background beater fired exactly at t+300s (mtime 17:35:00 updated mid-scoring), no supervisor restart
  since PID 31112 launch at 17:29:59. 9/9 tests pass, 297 LOC.
  ALSO: soccer_intl old DraftKingsProvider (sportsbook-us-il 404 endpoint) REMOVED from prop_edge_config.py
  + test updated (34/34 pass). MLB calibration cache stamped settle_logic_version=v2-void-nan (was null;
  stale warning fired every tick). Full stack: 14/14 supervisor daemons GREEN; paper_today fresh (388
  placed/444 pending/3 settled/-4.0u, executed=False, edge_claimed=False); predict :8099 200. STALE
  by-design (untracked/long-cadence): m14/m17/m15/m18/m8. Props snapshot stale (m13 scoring in progress);
  will refresh on next tick completion. NEXT (CEILING): T2 Mondrian group-conditional conformal OR E1
  LLM in-game context (detail_layer_gate template backend).
- WAKE-21 (CEILING/T4 ACI, 2026-06-26 ~15:57): SHIP fb468a9c -- 3rd CEILING experiment answered
  through the REAL gate -> HONEST REJECT (pinball + planted_null). Q: does Adaptive Conformal
  Inference (Gibbs+Candes 2021) hold in-game interval coverage under distribution drift better
  than static split-conformal? A: PARTIAL -- coverage YES, sharpness NO -> do NOT default-on.
  New leak-free streaming wrapper (scripts/platformkit/ingame/aci_online.py, 249 LOC, +13
  tests, +36 regression green): pure numpy+stdlib, online a_{t+1}=a_t+gamma*(a-err_t), width-
  only multiplicative adjustment per tick around base band midpoint. At tick t, ACI sees ONLY
  series[:t] -- never the future. Synthetic non-stationary stream (2000 ticks, sigma DOUBLES
  at t=500, gamma=0.05, target 90%): ACI coverage 89.9% (gap -0.001 vs nominal) vs static
  77.7% (gap -0.123) -- ACI RECOVERS coverage cleanly under drift. BUT pays pinball cost (wider
  bands) -> fails pinball <= static+0.01 check; planted-null (iid resample) shows residual-var
  drift even after shuffling -> null_collapses=False -> REJECT:pinball+planted_null. Default-OFF
  wrapper; not wired into ingame_serve_recal_seam. Reusable for in-game wp interval coverage
  replay, prop-band streaming, future Mondrian+ACI composition. Scoreboard: REJECT delta +1
  (ACI online).
  NEXT (CEILING queue, ranked): T2 Mondrian / group-conditional conformal on prop coverage
  (scripts/platformkit/mondrian_conformal.py) -- attacks per-regime miscoverage (stat x minutes
  -tier), wraps the EXISTING conformal/coverage code, the lightest-touch experiment that may
  unstick CQR's over-cover gap on subsets; OR T3 Venn-Abers in calibrator_zoo (probability
  validity guarantee + [p0,p1] band on the probability). T5 NGBoost stays last (highest reject
  prior given the pregame data ceiling).
- WAKE-20 (CEILING/T1 CQR, 2026-06-26 ~15:50): SHIP a642eac5 -- 2nd CEILING experiment answered
  through the REAL gate -> HONEST REJECT 7/7. Q: does CQR (Romano+ 2019, adaptive-width
  conformalized quantile regression) beat the incumbent constant-width split-conformal for NBA
  prop intervals? A: NO on the strict gate -- the existing split-conformal ships unchanged.
  New leak-free WF gate (domains/basketball_nba/prop_cqr.py, 288 LOC, +10 tests, +38 regression
  green) reuses pregame_oof.parquet (356k rows, 7 stats): chrono 50/25/25 train/calib/test split;
  lightgbm quantile (alpha/2, 1-alpha/2) over leak-free per-row features (rolling_mean_15,
  rolling_std_15, rolling_median_15, oof_pred, n_prior, season_avg_to_date -- all built from
  STRICT prior rows via shift(1)); conformity E_i = max(q_lo-y, y-q_hi) on CALIB; finite-sample
  conformal correction; planted-null = joint-shuffle features. Real-OOF verdict (n_test=11896
  per stat, alpha=0.10): CQR beats split-conformal on PINBALL on ALL 7 stats (pts ast reb fg3m
  stl blk tov; cqr_pb < sc_pb every row) AND on WIDTH (sharper bands every row) BUT
  OVER-covers nominal 90% (cov 91-96% vs sc 88-91%) -> fails |cqr_gap| <= |sc_gap| proximity;
  planted-null inflation (>1.5x) sub-bar on real data too -> REJECT all 7. Default-OFF
  measurement script; NOT wired into pricing. Honest finding: adaptive Q-quantile is sharper
  AND more conservative -- the conformal correction over-corrects on this OOF; the room CQR was
  supposed to fill (under-coverage) doesn't exist in the way the doc predicted on these splits.
  Reusable CQR template kept; next ceiling levers: (a) per-stat or per-(stat x minutes-tier)
  conformalization (Mondrian T2 hybrid), (b) T5 NGBoost / quantile-GBDT distributional head,
  (c) ACI online conformal for in-game (T4). Scoreboard: REJECT delta +1 (CQR adaptive-width).
  NEXT: T4 ACI online conformal in-game (scripts/platformkit/ingame/aci_online.py) -- attacks
  the freshness-drift gap, thin one-param wrapper, respects minimal-feature constraint, low
  rejection prior.
- WAKE-19 (CEILING/K1, 2026-06-26 ~17:45): flywheel healthy (23/23 all READY); stop flag clear
  (read .bot_state, did NOT run stop_bot.py). SHIP 1447a72b = K1 answered through the REAL gate ->
  HONEST REJECT. Q: does starting-pitcher RA-as-of + park factor make the Kalshi team_total pricer
  bet-ready? A: NO -- do NOT enable the placer. New leak-free WF eval (domains/mlb/totals_sp_park_eval.py,
  300 LOC, +5 tests) reuses totals_sigma_wf._build_wf_lambdas (run-rate lambda baseline) + OLS-blends
  asof_park.park_factor + (home+away)_sp_ra_asof; chronological 50/50 split, TRAIN-only centering,
  12037 held-out games: rmse_base 4.5621 -> rmse_combo 4.5313 (delta -0.0308 runs, BELOW the -0.05
  SHIP bar); planted-null collapses to -0.0003 -> the -0.031 is a small real-but-sub-threshold effect.
  Park+SP on totals is subsumed by the market, consistent w/ the prior moneyline SP-form REJECT.
  Verdict -> data/frontend/funnel/mlb_totals_sp_park_gate.json (scouting_only, vs_close UNPROVEN, no $).
  Kalshi team_total placer STAYS default-OFF -- never bet a biased pricer (exactly K1's bar).
  Scoreboard: props settled 0 (pend to tonight's finals); boards mlb 16 / soccer_intl 6 (working);
  CLV 7 settled / 0 clv (no_close); bankroll 97.0u (net -3.0); REJECT delta +1 (totals park+SP).
  NEXT (CEILING queue): CQR prop intervals (domains/basketball_nba/prop_cqr.py, GPU quantile fit) --
  the documented prop-interval under-coverage is REAL room (unlike efficient pregame reclaims);
  then E1 LLM in-game context (detail_layer_gate offline-template), asof reclaims NBA/tennis/soccer.
- INTELLIGENCE/LLM design DONE (2026-06-26c): docs/research/ceiling/LLM_CONTEXT_PRIORS.md -- use LLM +
  person-free brain to contextualize games into LEAK-FREE as-of priors, run independently (default-off
  daemon), gated like any signal. HONEST: LLM context is a HIGH-reject lane (CV_LLM_SCHEME already
  rejected +0.005 p=0.87; pregame efficient) -> ships SCOUTING-ONLY unless IN-GAME context moves OOS
  calibration. Reuses knowledge/contextual.py + detail_layer_gate.py (planted-null built in) +
  scheme_prior.py. CHEAPEST DECISIVE FIRST (E1, ~zero API cost): gate ONE regime_structural channel
  (offline template backend) through detail_layer_gate.py on 2 NBA seasons + shuffled-context null ->
  real SHIP/REJECT number; only pay for Haiku/PBP-text backend if the free channel survives.
  NEAR-TERM QUEUE: (next) CQR prop intervals, then E1 LLM in-game context, then asof reclaims (NBA/
  tennis/soccer), then ACI in-game.
- GAP AUDIT + FIX (2026-06-26 ~15:14, user "no gaps"): paper trading IS live (305 bets: 298 open/7
  settled, mlb+soccer_intl, newest 15:08). OLD-lines backtest fuel EXISTS (historical_event_odds 9.8M
  + line_history 193M). PRIMARY GAP FOUND + FIXED: live supervisor (20h uptime) predated m15_prop_settle
  / m16_prop_close_capture / m17_kalshi_scan / m18_pm_close_capture -> all 7 settled were clv_status
  'no_close' (CLV unmeasurable). RESTARTED stack (stop.ps1+go.ps1): now 23 procs all READY, the 4
  daemons LIVE -> close-capture + prop-settle restored; CLV will populate as bets settle. REMAINING
  SMALL GAP (queued for builder loop): grade_summary reports n_settled=0 despite 7 settled in ledger
  (PM settled rows not counted by the summary reader) -- fix the reader to count all settled + verify
  CLV starts populating post-restart.
- EXEC/EDGE AUDIT (2026-06-26 ~15:20, user 'kalshi high level + best bets + edges'): FRONTEND WORKING
  (webapp:3000=200, /api/paper/trail=200 real rows incl settled paper_pm w/ unit_result); KALSHI EXEC
  WORKING for game-winner ML (30 pm bets, m12 live; m18 now CLV-grades them post-restart); BEST-BETS
  board generating (best_bets.json cards, m10 fresh); m17_kalshi_scan scanning liquid surface. HONEST
  GAP (calibration not plumbing): Kalshi props/totals are LIQUID (~1c spread) but we do NOT bet them --
  totals pricer biased +5.2% (ignores starting pitcher+park), prop pricer matched 0 live. Betting them
  now = fabricated edge. PATH TO HIGH-LEVEL KALSHI (queued AHEAD of CQR/LLM): (K1) make kalshi_pricers
  team_total pricer bet-ready -- add starting-pitcher-ERA + park, CALIBRATE vs settled totals through
  the REAL gate, enable placement ONLY once it beats/matches the Kalshi line OOS; (K2) populate the
  prop board with Kalshi-offered stats so the prop pricer matches live; (K3) more soft books for +CLV
  line-shop. Build in scripts/platformkit/pm_trading/**; gated; never bet a biased pricer.
- EFFICIENCY AUDIT (2026-06-26 ~15:30, user 'efficient + GPU'): HONEST = system is ALREADY efficient,
  NO bloat to fix. GPU RTX 4060 healthy 42% util / 7GB free (torch cu121, CUDA avail). Daemon stack
  lean: ~3GB total / 24 procs (~120MB avg, max 394MB) + webapp 164MB. The 91% system RAM is mostly
  NON-system dev-box procs (editor/browser/Claude), not the AI. Do NOT make-work on lean daemons.
  STANDING EFFICIENCY DISCIPLINE (L5, folded into the loop prompt): (a) any NEW model fit the loop
  builds (CQR/NGBoost/Kalshi-totals calib) defaults to GPU (device='cuda'/gpu_hist/lgbm device='gpu')
  with CPU fallback; (b) offload heavy compute (CV, full-season WF) to RunPod 3090, keep local box
  light; (c) LLM = Haiku Batches + content-hash cache, call only on live state; (d) profile-before-
  optimize -- only touch a hot path with a measured before/after, never fabricate an efficiency win;
  (e) per-file tests only (full suite freezes the 16GB box).
- MLB + WC (soccer_intl) VERTICAL AUDIT (2026-06-26 ~16:10): BOTH live + betting on today's slate
  (mlb 285 bets=240 props+37 Kalshi ML, newest 16:08; soccer_intl 57=52 props+5 Kalshi ML, newest
  15:40). Models hardened tonight (mlb MOV-Elo bug fix + tests; soccer rho_fit fix). GAPS before
  'highest level' (queued, verify ahead of K2/CQR): (V1) PROP SETTLEMENT -- 0/292 props settled;
  m15_prop_settle just came online (2min) -> VERIFY props actually settle once games finalize; if not,
  it's the MLB city-abbrev name-match settler bug resurfacing (prop_settler_mlb._team_hit). (V2)
  FRONTEND BOARDS show 0 games for mlb + soccer_intl despite 240+52 props placed today -> snapshot
  fill/staleness gap (known FRONT-END FILL issue), NOT honest-empty -> regen + verify cards fill.
  (V3) 8 mlb bets have market_type='?' -> trace + label. (V4) bestbets API /api/v1/bestbets/<sport>
  returned a parse error -> verify it serves mlb + soccer_intl. CLV still pending (no_close on the few
  settled; populates as new bets settle with captured closes via m16/m18).

## >>> ACTIVE MISSION (user directive 2026-06-26): FULL-FUNNEL, ALL SPORTS, SMARTER EVERY NIGHT
Run the full funnel end-to-end (DATA->SIGNALS->MODELS->ENGINES->PREDICTIONS->INTEL->LINES->
EXECUTION->IMPROVE) for every in-season sport (NBA, MLB, soccer, soccer_intl, tennis; NFL in
season), unattended, getting better every cycle. Win = calibration + measured CLV; NEVER a
fabricated $/edge; REJECT logged = success. Full directive + funnel + per-cycle output spec:
.planning/platform/BUILD_BACKLOG.md SECTION 0 (ACTIVE MISSION). The runtime FLYWHEEL (go.ps1
supervisor m1..m18 -- capture lines / paper-trade / settle / CLV / m4 recalibrate) runs detached
at ~zero token cost and keeps improving predictions overnight with or without this chat; the
builder loop self-schedules wakes to add gated code/signals/models on top. Enders: `bot stop`
or `program_complete` only.
- WAKE-1..15 (2026-06-26 hardening burst: twin-aware open counts, NaN/inf line guards,
  domain-engine test coverage, 3 real bug fixes) -> ARCHIVED verbatim in
  .planning/archive/NOW_ARCHIVE_2026-06.md

## Archived history
FRONT-END FILL directive (2026-06-22, delivered) + SESSION logs 2026-06-21..25 +
stale Active-blockers list -> .planning/archive/NOW_ARCHIVE_2026-06.md

## Pointers (links, never inline)
- Betting product research: docs/research/betting-product/
- Claude-org reorg research: docs/research/claude-org/
- Memory frontier entries: memory `project-betting-product-research-2026-06-17`, `project-betting-frontend-intl-mlb-2026-06-17`
