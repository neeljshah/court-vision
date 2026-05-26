# CourtVision — Current State

> Loaded by Claude on demand. Update at session start or when state changes.
> Local-only (gitignored on fresh clones); maintainer working-copy mirror.
> Platform identity: **The Renaissance of Sports** — agentic AI sports intelligence.

## Current State (2026-05-26)
- Branch: `master` | Head commit: `1c2ff08a` (`merge: R21_N3 layered alert with vault + critical-stack fallback`)
- improve_loop rounds_completed: **23** · ships array: **48 entries** (R12 BATCH-10 most recent in state.json; R15-R21 ships tracked via commits + coordination_log).
- Tests dir: 280+ test files; latest additions for R20_M3 (+169 tests, +11pp coverage), R21_N1 PTS/AST artifact load.
- Daemon registry: `scripts/daemon_registry.json` — **14 daemons** wired into `scripts/daemon_watchdog.py` (R19_L3).

## What changed in R15–R21 (wave)

### Scrapers / odds ingestion (R15–R16)
- R15: Pinnacle NBA scraper (mainline + props via guest API) `2c1b041f`; Bovada production daemon `1cff8d58`.
- R15 alt: Bovada NBA+WNBA+MLB 5-min ticks; `clv.py` aliases (bov/pin) `305f9d44`.
- R16_E5: cross-book middle-finder daemon `d4f32d36`.
- R16_E6: unified asyncio scraper orchestrator (FD+Bov+Pin in one PID, health port 8765) `61d08639`.
- R16_E4: line-move / steam-signal detector `7d9a147f`.
- R16_E8: real-time CLV tracker daemon `e38c3e3d`.
- R16_E3: sub-100ms prediction cache (parquet + serve helper) `f19b590c` / `0fd42930` (p50 3ms, p99 82ms, 2100 rows).
- R16_E7: place/settle/show-bet CLIs — intent-to-bet ledger `5853c3fe`.
- R16_E2: live_bet_ranker daemon (30s tick, atomic write) `e606d357`.

### Live game-night layer (R17–R18)
- R17_J1: NBA lineup scraper + bet-kill alerts `6a3bd603`.
- R17_J2: line-freshness validator gate for `place_bet.py` `730ca111`.
- R17_J3: auto-placement daemon (7 safety gates, dry-run default) `7460ff66`.
- R17_J4: continuous bankroll + portfolio-risk monitor daemon `27d5f90d`.
- R17_J5: game tip-time detector + live-ranker handoff `9e5ea8f8`.
- R17_J7: single-pane-of-glass vault dashboard daemon `c1c7767d`.
- R17_J8: 2025-26 gamelog backfill (875 players, prediction cache regen) `89b23d04`.
- R18_K1: Playwright stealth probe for DK/Caesars/MGM — **all 3 IP-blocked** `0c7775c7`.
- R18_K2: in-play (live) bet-ranker daemon `c11a8b6c`.
- R18_K3: Discord webhook push for 5 alert daemons `0280ca34`.
- R18_K4: mobile HTML dashboard server on `:8766` `19a88bf2`.
- R18_K5: `incremental_oof_refresh` daemon `c5e1fa3a`.
- R18_K7: multi-game portfolio Kelly (slate-level 25% cap) `be2ab091`.
- R18_K8: post-game auto-settle daemon `04b9e171`.

### Hardening + ops (R19–R20)
- R19_L2: `kelly_pct` invariant — `clamp_kelly_pct` + writer hardening `68f3e90b`.
- R19_L3: **daemon watchdog** with heartbeat + auto-restart + Discord `6a2947c3` (consumes `scripts/daemon_registry.json`).
- R19_L8: bankroll dashboard filter — excludes synthetic + start-bankroll `4d296156`.
- R20_M1: Bovada alt-line normalizer + arb-join guard `defe6703` / `35d00ebe`.
- R20_M3: betting pipeline pytest coverage **+169 tests, +11pp coverage** `ad48312d` / `6a91f2fc`.
- R20_M5: game-night E2E validation harness `996ff0d2` / `54c28c47`.
- R20_M7: model deployment audit + **wired the M2 multi5 ensemble** (one un-wired ship) `78abab5a` / `99df7ebf`.
- Fix `c3131e24`: `middle_finder_daemon` heartbeat was trapped inside docstring (R19_L3 regression) — flipped stale test `bcc06e0e`.

### Polish wave (R21)
- R21_N1: PTS/AST artifact audit + resolver fix (silent `None` bug) `216b8491` / `8fbfa4dc`.
- R21_N2: `line_killed` bet recovery tool `cb79a213` / `274030cd`.
- R21_N3: **layered alert** with vault + critical-stack fallback `3d85c8fb` / `1c2ff08a`.
- R21_N5: m2_family predictions cache (**21× speedup**) `ed10f991` / `2ea26fec` — cache at `data/cache/m2_family_predictions_2024-25_last100.json`.

### Model wins documented earlier but worth carrying
- R10_M5 in-play winprob: endQ3 Brier 0.135 / acc 0.81 / AUC 0.90 (pregame baseline Brier 0.27).
- R11 game-level M2 family: **95 ships / 22 rejects across 113 probes** — total/spread/team-pts/Q1/H1 regression + O/U + ATS binary surfaces. Production canonical: multi5 ensemble (3 LGB seeds + 2 XGB seeds) + isotonic calibration on binaries.
- R12 BATCH-9 interactions_only: total -16.27% (-1.18pp vs B6); rest×travel + b2b×pace interactions carry signal.
- R12 BATCH-10: 4-snapshot in-play winprob endQ1/endQ2/endQ3 + remaining-total endQ2 (-25.38% vs naive — biggest delta of R12).

## Open issues / known gaps

1. **ISSUE-021**: PostgreSQL (DATABASE_URL) not wired — Phase G work.
2. **ISSUE-022**: `defender_distance=200.0` sentinel must be NULL in ML (corrupts CV xFG); CV scale-up blocked behind this.
3. **ISSUE-023**: Shot clock MAE 17.16 s — clock doesn't decrement per-frame.
4. **Injury feed** not integrated end-to-end — R14_H4 probe was in flight, never wired into live pipeline.
5. **DK / Caesars / MGM scrapers IP-blocked** (R18_K1) — Pinnacle/Bovada/FD/PrizePicks-only line coverage.
6. **ODDS_API_KEY** missing — blocks R9_C1/C2 historical and live DK/FD player props (~$30/mo paid tier).
7. **Gate 1 vs REAL Pinnacle**: no historical Pinnacle closes in `prop_lines` (offseason); one-shot run scheduled for Oct 2026 preseason.
8. **`pnl_ledger.csv` book mismatch**: ledger is DK-only, snapshots PP-only — C4 alias patch in place, gate flips once PP bet lands in ledger.
9. **CV registry sparse**: 29 usable / 80 CLEAN target.
10. **11 games still need reprocess** via `scripts/reprocess_failed_games.py`.

## What's running / what's wired

**Daemon registry** (`scripts/daemon_registry.json`, 14 entries, consumed by `scripts/daemon_watchdog.py`):
- `vault_dashboard_daemon` (30s) · `clv_tracker_daemon` (60s) · `middle_finder_daemon` (30s) · `line_move_detector` (30s) · `nba_lineup_daemon` (60s) · `bankroll_monitor_daemon` (300s) · `auto_settle_daemon` (300s) · `auto_place_daemon` (60s) · `unified_scraper_orchestrator` (FD+Bov+Pin, 60s, health :8765) · `live_bet_ranker` (30s) · `inplay_bet_ranker` (30s) · `fd_scraper` (60s) · `bov_scraper` (60s) · `pinnacle_scraper` (30s).
- Watchdog rule: heartbeat staler than `expected_interval_sec * 3` → restart via daemon's `restart_cmd` + Discord alert.

**Alert layers** (R21_N3 layered fallback):
- Primary: webhook (Slack/Discord) via `scripts/wire_live_alerts_webhook.py`.
- Fallback: vault append (`vault/Improvements/*.log`).
- Critical-stack fallback wired through `tests/test_alert_fallback.py`.

**Caches**:
- `data/cache/m2_family_predictions_2024-25_last100.json` (R21_N5).
- `data/cache/daemon_heartbeats/*.txt` (R19_L3).
- `data/cache/bankroll_state.json`, `clv_running_total.json`, `middles_live.json`, `injury_status_*.json`, `line_moves_*.json`.

**Resolvers** (R21_N1):
- PTS / AST artifact resolver fixes silent `None` bug — covered by `tests/test_R21_N1_pts_ast_load.py`.

**M2 multi5 ensemble** (R20_M7 wired): 3 LGB seeds (42/7/100) + 2 XGB seeds (42/7) for total/spread/team-pts.

## What to load first next session
1. `CLAUDE.md` — project identity + task→files map.
2. `docs/CLAUDE-state.md` (this doc).
3. `scripts/coordination_log.md` (last 80 lines for S1/S2 events).
4. `scripts/improve_loop/state.json` (ships array + saturated_angles).
5. `scripts/daemon_registry.json` (operational topology).
6. Task-specific: `vault/Improvements/Tracker Improvements Log.md` for CV bugs; `data/models/*` registry for model lookups.

## Pregame prod MAE (still canonical, post cycle 96a + R10 wires)
PTS 4.6210 · REB 1.9023 (LGB-q50) · AST 1.3559 (multitask MLP) · FG3M 0.8943 (XGB-q50) · STL 0.7153 (XGB-q50) · BLK 0.4398 (XGB-q50, -16.6% session win) · TOV 0.8932 (XGB-q50).

## In-game endQ3 MAE (550-game retro)
PTS 2.46 · REB 1.00 · AST 0.68 · FG3M 0.42 · STL 0.32 · BLK 0.20 · TOV 0.45 — 7/7 stats vs prod pergame, -43% to -53%.
