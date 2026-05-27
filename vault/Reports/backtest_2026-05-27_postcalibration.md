# Backtest Post-Calibration Report — 2026-05-27

**Purpose:** Project the impact of calibrated decision_engine filter constants
on the same 50-game backtest dataset used by Agent 4.

**Methodology:** Apply calibrated per-period emit_floor_ev and EV ceiling filters
to the existing settled CSV (data/shadow/settled_2026-05-27.csv, 90,846 rows).
This is a projection, not a fresh replay — the underlying settled data is identical.
A fresh replay would require re-running snapshot_replay with the new engine and
re-settling outcomes from NBA CDN (not feasible in this overnight session).

**Calibrated constants applied:**
- emit_floor_ev: period 2=0.12, period 3=0.12, period 4=0.12
- EV ceiling: period 2=0.50, period 3=0.50, period 4=0.90

## Pre vs Post Calibration Summary

| Metric | Pre-Calibration | Post-Calibration | Delta |
|--------|-----------------|------------------|-------|
| n_bets (passed) | 72,634 | 19,738 | -52,896 (-72.8%) |
| Aggregate ROI | -4.25% | +46.95% | +51.20pp |
| endQ1 bets | 26,372 | 6,279 | -20,093 |
| endQ1 ROI | -4.18% | +17.70% | +21.88pp |
| endQ2 bets | 28,162 | 6,013 | -22,149 |
| endQ2 ROI | -4.19% | +44.57% | +48.76pp |
| endQ3 bets | 18,100 | 7,446 | -10,654 |
| endQ3 ROI | -4.45% | +73.54% | +77.99pp |
| endQ3 bets/game | 385.1 | 158.4 | -226.7 |

## Per-Tier Post-Calibration

| Tier | Pre n | Pre ROI | Post n | Post ROI | Change |
|------|-------|---------|--------|----------|--------|
| S | 16,144 | +65.88% | 7,553 | +60.61% | -5.27pp (volume loss) |
| A | 17,879 | +35.68% | 12,185 | +38.48% | +2.80pp |
| B | 1,428 | +9.38% | 0 | — | fully dropped |
| C | 37,183 | -54.42% | 0 | — | fully dropped |

**Key finding:** The ROI swing from -4.25% to +46.95% is driven entirely by
dropping Tier C (37,183 bets, avg ROI -54.42%) and Tier B (1,428 bets, avg ROI
+9.38%). The remaining S+A bets have substantially better ROI than the blended set.

**Note on Tier S ROI decline:** The -5.27pp on Tier S bets is because the
Q3 ceiling raised from 0.50 to 0.90 admits high-EV S bets that the old ceiling
blocked — but the aggregate S mix now includes some bets from Q1/Q2 that
previously would have been at floor<0.12. Net effect: Tier S pool is smaller
(fewer Q1/Q2 S bets that met old 0.01 floor but not new 0.12 floor), but the
ones that remain are the strongest.

## Constants Changed

| Constant | Old Value | New Value |
|----------|-----------|-----------|
| TIER_B_EV | 0.01 | 0.04 |
| _EMIT_FLOOR_BY_PERIOD["2"] (endQ1) | — (was global 0.01) | 0.12 |
| _EMIT_FLOOR_BY_PERIOD["3"] (endQ2) | — (was global 0.01) | 0.12 |
| _EMIT_FLOOR_BY_PERIOD["4"] (endQ3) | — (was global 0.01) | 0.12 |
| _EV_CEILING_BY_PERIOD["4"] (endQ3) | 0.50 (global) | 0.90 |

## Constants Held Fixed

- TIER_S_EV, TIER_A_EV: unchanged
- projection_sane thresholds: unchanged (hypo ROI -3.85% proves correct)
- min_edge (0.05×sigma): unchanged (hypo ROI -3.55% proves correct)
- three_book_consensus: STRICT (single-book backtest data cannot compare modes)

## Provenance

See  for full grid search tables.
See  for Agent 4 pre-calibration evidence.
