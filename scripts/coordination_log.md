# Coordination Log

Shared channel between Session 1 (execution loop) and Session 2 (model loop).
Append-only; one event per line.

## Conventions
- `[YYYY-MM-DD HH:MM Sx]` prefix — Sx = S1 or S2
- Events: SHIP / NEED / CONFLICT / NOTE
- File-ownership boundary documented in EXECUTION PROMPT (model loop) and Session 1 prompt.

## Log

[2026-05-25 S2] NOTE — Model loop Session 2 starting Round 1. Targets: M3, M4, M21, M22, M25, M27, M30, M31.
[2026-05-25 S2] NOTE — R8 complete: 0/8 ships. M27 audit caught label leakage (last5_min_avg=0 for DNP rows via merge artifact), fixed; honest F1=0.26 fails gate but AUC 0.85 is strong. M31 crashed silently in Stage 1 — INCOMPLETE.
[2026-05-25 S2] NOTE — PIVOT to CLV-positive sizing/timing per user. R9 batch: C1 (historical lines), C2 (multi-book scraper), C3 (synthetic CLV), C4 (clv join repair), C5 (band-Kelly), C6 (portfolio-Kelly), C7 (lineup timing), C8 (CLV ship gate).
[2026-05-25 S2] SHIP — C8: CLV ship gate module + 12 unit tests + integration regression on R8_M22 (REJECT preserved). Wired into scripts/improve_loop/scaffold.py.
[2026-05-25 S2] BLOCKED — C1 historical NBA player prop lines unavailable from free sources; needs ODDS_API_KEY (~$30/mo paid tier).
[2026-05-25 S2] BLOCKED — C4 ledger-vs-snapshot book mismatch: ledger is DK-only, snapshots are PP-only. Wiring (alias patch + ETL) verified end-to-end on synthetic test bet; gate flips once any PP bet enters ledger.
[2026-05-25 S2] FIX — Restored deleted scripts/build_clv_backtest.py from commit 72ee7418. Wrote scripts/build_pnl_ledger_synth.py → rebuilt data/pnl_ledger.csv with 50,986 synthetic bets from prop_residuals.json (was 1 row; 30k voids dropped).
[2026-05-25 S2] BLOCKER — data/cache/pregame_oof.parquet has empty game_id column (335k/335k rows); blocks C3 Tier-3 OOF q50 fallback. Repair agent in flight.
[2026-05-25 S2] FIX — pregame_oof.parquet game_id repaired: 99.92% coverage (335,139/335,405) via (player_id, game_date)->game_id join across adv_stats parquet + boxscores + season_games. scripts/repair_pregame_oof_game_id.py is idempotent.
[2026-05-25 S2] SHIP — C2: PrizePicks scraper extended (fetch_live_prop_lines.py + probe_R9_C2_multibook_scraper.py). 41 snapshots, 27k rows, 6.6k deduped, 100% synthetic-50 CLV join. Persistent daemon PID 22608. DK+FD blocked on ODDS_API_KEY.
[2026-05-25 S2] REJECT — C3: data/pnl_ledger.csv has fake (synthetic) player_ids/game_ids so Tier-3 OOF join can't fire; all 50,986 bets land in Tier 4. Probe code correct. R10: rebuild ledger from OOF parquet rows.
[2026-05-25 S2] WAVE2 — C5 + C6 dispatched (band-Kelly + portfolio-Kelly). C7 deferred (synthetic CLV has no timestamp variance for timing analysis; revisit after more snapshot accumulation).
[2026-05-25 S2] NOTE — M31 RESUMED: 2 probe bugs patched (ot_labels cache reuse + None team_id), reran end-to-end. AUC 0.637, mean P(OT) 0.103 vs actual 0.055 (overcalibrated); all 7 stats regress under inflation correction (mean_delta +0.0023, max +0.0065 PTS). Final REJECT. Round 1 (R8) now fully closed: 0/8 ships. No live wiring changes.
[2026-05-26 S2] NOTE — R10 Round 2 launched, 8 probes (M5 M7 M9 M13 M14 M16 M19 M30v2). Memory pressure (15 GB host, 3 GB free with 6 procs) killed parallel runs; switched to serial.
[2026-05-26 S2] SHIP — R10_M5_inplay_winprob: endQ3 Brier 0.135 < 0.183 gate, accuracy 81.3% > 72% gate. Pregame baseline Brier 0.265. Pending wire to live_engine.
[2026-05-26 S2] REJECT — R10_M19_foul_markov: all 7 stats regress under Q4-min multiplier despite Q4-min regression model having lower MAE than per-player baseline.
[2026-05-26 S2] REJECT — R10_M30v2_foulout: classifier AUC 0.92 (vs M30 v1 AUC 0.30), 7/7 stats directionally improve but mean volume delta -0.0026 misses -0.005 gate; selection bias on pf>=5 (stars who keep playing).
[2026-05-26 S2] SHIP-PER-STAT — R10_M16_streak: FG3M -0.012, STL -0.022, BLK -0.053, TOV -0.011 (all 4/4 WF). PTS/REB/AST fail. R7_A-style per-stat ship.
[2026-05-26 S2] SHIP — R10_M14_playtype: prior-season Synergy playtype freq, 6/7 stats improving, PTS WF 4/4 (-0.027), FG3M WF 4/4 (-0.011), mean -0.0098. Wire to player_props pregame.
[2026-05-26 S2] REJECT — R10_M7_ref_features: full sweep done, mean_delta +0.00229, only 1/7 improving (STL marginal -0.0007); cycle-15 pattern confirmed (ref-crew priors absorbed by form/role).
[2026-05-26 S2] REJECT — R10_M9_fatigue: all 7 stats explode +0.06 to +0.15 mean delta when fatigue features added to residual head (overfits proj_base+residual composition).
[2026-05-26 S2] SHIP-PER-STAT — R10_M13_tracking: PTS strict WF 4/4 + mean -0.00736 (passes both gates). 4 more stats hit 4/4 WF but miss mean gate (AST/FG3M/BLK/TOV marginal). Cycle 14 v2 with strict prior-season discipline works for PTS only.
[2026-05-26 S2] R10 ROUND CLOSED: 4 ships (M5/M14/M16-per-stat/M13-PTS), 4 rejects (M19/M30v2/M7/M9). Best round since R7. Live wiring deferred to maintain stability overnight.
[2026-05-26 S2] REJECT — R11_M30v3 (1st R11 probe): per-stat dampener from training ratios fails because foul-out players are stars who OUTSCORE — multipliers clip to ceiling and boost wrong-direction. Mean delta +0.00727 (worse than M30v2 -0.0026). Foul-out angle definitively saturated via selection bias.
[2026-05-26 S2] REJECT — R11_M16v2 (2nd R11 probe): streak features with L5/L10 windows instead of L3/L20. IDENTICAL per-stat ship pattern as M16 (FG3M/STL/BLK/TOV pass 4/4 WF, PTS/REB/AST fail). Confirms structural saturation — streak signal absent in high-volume stats regardless of window choice.
[2026-05-26 S2] REJECT — R11_M13v2 (3rd R11 probe): broadened M13 tracking from 4 → 10 features. PTS WF 4/4 → 3/4 (LOSES the ship). REB/AST/FG3M/BLK/TOV all hit 4/4 WF but miss mean delta gate. Lesson: feature breadth dilutes signal; keep production at M13's 4-feature config.
