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
[2026-05-25 S2] NOTE — M31 RESUMED: 2 probe bugs patched (ot_labels cache reuse + None team_id), reran end-to-end. AUC 0.637, mean P(OT) 0.103 vs actual 0.055 (overcalibrated); all 7 stats regress under inflation correction (mean_delta +0.0023, max +0.0065 PTS). Final REJECT. Round 1 (R8) now fully closed: 0/8 ships. No live wiring changes.
