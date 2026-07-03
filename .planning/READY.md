# READY -- state of the system (verified 2026-07-03, review session)

One page. Every claim below has a tool-result behind it from THIS session.
No accuracy/edge claim anywhere in this file (see .claude/rules/no-edge-claims.md).

## What runs GREEN (verified live today)

- **Supervised stack: 36/36 procs READY, all_ready=true** (m1 producer/API/boards/UI,
  paper+line+bankroll daemons, m2 in-play, m4-m8, m10-m18, m19-m27 gates, m29-m32
  sentinels) -- data/frontend/ops/supervisor_status.json after this session's repairs.
- **Feed health 25/25 GREEN** -- 5 providers (espn, fanduel, kalshi, pinnacle,
  polymarket) x 5 sports incl. tennis (restored by WAKE-33's league resolver).
- **:8099 Auto-API healthy** -- /health 200; props route /api/predict/props/mlb 200
  with 2,823 rows from the scraped-book bridge (the 2026-07-02 route-collision fix
  460fd0cb verified intact in code AND live).
- **:8098 boards API healthy** -- /health + /api/slate 200 after the anyio repair.
- **:3000 UI healthy** -- 200; /p6 PropsPanel wiring (9bc820d4) intact.
- **go.ps1 / stop.ps1 / boot.ps1 present + coherent**; supervisor/stack_specs.py
  (m1..m32) matches the running stack; skills daily auto-update runs (stamp 09:59
  today + forced re-run exit 0); PreToolUse guard hook LIVE (it blocked a --force
  in this very session); push-to-origin + full-pytest blocks confirmed in the hook
  source; permissions already allow-all with a deny list (no prompt-cutting needed).
- **Tests run this session (per-file only): 99 green** -- props routes 7, sell 92
  (test_serve_sell 32, test_docs_gen/test_evidence 28 after the review fixes, plus
  test_access/test_track_record etc. in the earlier 32-green run).

## What was BROKEN today (found + fixed, evidence in NOW.md MAINTENANCE entry)

- :8099 wedged-alive 2.5h (event loop blocked after GET /api/paper/trail?limit=2000
  at 13:00:30; CPU spin). Killed PID -> supervisor relaunched -> healthy.
- :8098 serving 500s -- MIXED-VERSION anyio in the conda env (WAKE-33's scrapling
  install upgraded anyio under running daemons). Clean reinstall 4.14.1 -> healthy.

## Still OPEN (flagged, not fixed -- chips spawned where noted)

1. **Supervisor gap: no wedge-kill for HTTP/TCP-readiness procs** -- a wedged-alive
   :8099 is invisible to the reaper (heartbeat procs only). [chip spawned]
2. **sell/ deploy configs launch only the demo server** (sell.app :8100); the real
   FastAPI auth/metering stack (serve_sell :8101) is unreachable from every deploy
   artifact; docs/sell/DEPLOY.md referenced 6x but does not exist. [chip spawned]
3. **sell/ duplication debt** -- 3rd copy of the HMAC canonicalizer (already
   diverged: default=str), 4 atomic-write variants vs io_atomic, copy-pasted auth
   in sell_edge_routes, per-request ledger rebuild + O(all-calls) quota reads.
   [chip spawned]
4. **api/templates/parlays.html untracked in a HUMAN-GATED tree** -- extends
   base.html, nothing references it; needs a human decision (commit or delete).
5. **LOC-rail violations (non-spec, non-test):** predict_service/app.py 597,
   scripts/platformkit/ingame/inplay_capture_loop.py 569, sell/docs_gen.py 544,
   sell/serve_sell.py 340 (both sell files self-declare <=300 in their docstrings).
6. Known pre-existing failure: test_inplay_aggregate_grade.py (grade dir grew past
   MIN_GAMES -- reproduces on stash, unrelated to any change; see WAKE-34).
7. Proof-of-edge scoreboard is honestly RED: edge_greenlight.json moneyline n=47/300,
   units negative both halves -- the pre-registered 8.1a-g criteria are NOT met.
   This is the discipline working, not a defect.

## Top 5 highest-leverage next builds (from NOW.md NEXT + today's evidence)

1. **Wedge-kill for HTTP-readiness procs** (supervisor) -- today's 2.5h silent
   outage recurs otherwise; small, testable, protects the whole serving spine.
2. **NEXT#5 MLB deep-intelligence continuation** -- (a) human decision on
   CV_MLB_SP_ADJUST=1 (gate PASSED cross-era + 2026 OOS, verdict on disk);
   (b) asof_bullpen (un-deferred -- SP identity now keyed by game_pk);
   (c) umpire tendencies; (d) per-pitch archetype layer (5 season corpora).
3. **NEXT#1 widen m19 asof-reclaim** to tennis (needs WTA asof_hold companion)
   + soccer (asof_features diffs) -- cheap wire+gate experiments, REJECT expected.
4. **In-play tail-band forward gate accrual** (m32 4th candidate, pre-registered
   H1/H2 2026-07-03) -- pure waiting + capture quality; protect the widened
   in-play capture (WAKE-34) that feeds it.
5. **NBA October readiness** (master plan phase 7) -- Kalshi NBA spread series is
   pre-wired; verify the full funnel on the first preseason slates.

## Entry points per subsystem

| Subsystem | Entry file |
|---|---|
| One-command stack up/down | go.ps1 / stop.ps1 (read-only view: view_local.ps1) |
| Supervised service inventory | supervisor/stack_specs.py (m1..m32) |
| Auto-API :8099 | predict_service/app.py (props: predict_service/frontend/props_routes.py) |
| Boards API :8098 | scripts/platformkit/frontend/serve.py |
| UI :3000 | webapp/ (PROD build -- see webapp/README.md for the .next gotcha) |
| In-game engine | scripts/platformkit/ingame/live_loop.py + inplay_capture_loop.py |
| In-play capture spec | scripts/platformkit/odds_provider/kalshi_series_spec.py |
| Paper trading loop | scripts/platformkit/pm_trading/auto_loop.py |
| CLV ledger + scoreboard | scripts/platformkit/clv_ledger.py + pm_trading/scoreboard.py |
| Signal gates | scripts/platformkit/ceiling/asof_reclaim_daemon.py, mlb_context_autogate_runner.py |
| Sell package | sell/serve_sell.py (deploy gap -- see OPEN #2) |
| Domain adapters | domains/<sport>/ (mlb, basketball_nba, soccer, soccer_intl, tennis) |
| Ops scoreboards | data/frontend/ops/*.json (feed_health, capture_quality, autonomy_status) |
| Daemon logs | logs/<proc>.out|.err|.pid (repo root) |
| Single source of truth | .planning/NOW.md (head + NEXT + P1->P7 ledger; archive in .planning/archive/) |

## Session commit trail (all LOCAL, never pushed)

5201b16d gitignore .vite | 161f0152 webapp README | e48410bd view_local |
0c2118ab sell package | 90022326 NOW.md trim | e5e49466 CLAUDE.md Py3.10.20 |
a87d794f NOW.md NEXT+ledger restore | 35c7f385 sell review fixes
