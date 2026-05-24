# cycle 90b (loop 5) — T1-C: B2B × age33+ × starter (probe)

## Setup
- age source: `data/external/bbref_advanced_<season>.json` (`age` field)
- holdout n=19964 (chronological 80/20 of n=99818)
- ages resolved: 19188/19964 (96.1%)
- rows (age>=33): 1719
- rows affected (age>=33 AND is_b2b): 276
- starter flag: NOT IN DATASET — defaulted to INCLUDE all (276 rows)
- target stats: pts, reb, ast (saturated stats fg3m/stl/blk/tov untouched)

## Single-split MAE table (per factor)

| factor | stat | n_aff | base_mae | adj_mae | delta |
|--------|------|------:|---------:|--------:|------:|
| 0.90 | pts | 276 | 4.5016 | 4.5028 | +0.0012 |
| 0.90 | reb | 276 | 1.9066 | 1.9071 | +0.0005 |
| 0.90 | ast | 276 | 1.3026 | 1.3019 | -0.0007 |
| 0.90 | fg3m | 0 | 0.8497 | 0.8497 | +0.0000 |
| 0.90 | stl | 0 | 0.6720 | 0.6720 | +0.0000 |
| 0.90 | blk | 0 | 0.4138 | 0.4138 | +0.0000 |
| 0.90 | tov | 0 | 0.8461 | 0.8461 | +0.0000 |
| 0.92 | pts | 276 | 4.5016 | 4.5024 | +0.0008 |
| 0.92 | reb | 276 | 1.9066 | 1.9069 | +0.0003 |
| 0.92 | ast | 276 | 1.3026 | 1.3020 | -0.0006 |
| 0.92 | fg3m | 0 | 0.8497 | 0.8497 | +0.0000 |
| 0.92 | stl | 0 | 0.6720 | 0.6720 | +0.0000 |
| 0.92 | blk | 0 | 0.4138 | 0.4138 | +0.0000 |
| 0.92 | tov | 0 | 0.8461 | 0.8461 | +0.0000 |
| 0.94 | pts | 276 | 4.5016 | 4.5020 | +0.0004 |
| 0.94 | reb | 276 | 1.9066 | 1.9068 | +0.0002 |
| 0.94 | ast | 276 | 1.3026 | 1.3021 | -0.0005 |
| 0.94 | fg3m | 0 | 0.8497 | 0.8497 | +0.0000 |
| 0.94 | stl | 0 | 0.6720 | 0.6720 | +0.0000 |
| 0.94 | blk | 0 | 0.4138 | 0.4138 | +0.0000 |
| 0.94 | tov | 0 | 0.8461 | 0.8461 | +0.0000 |
| 0.96 | pts | 276 | 4.5016 | 4.5017 | +0.0001 |
| 0.96 | reb | 276 | 1.9066 | 1.9067 | +0.0001 |
| 0.96 | ast | 276 | 1.3026 | 1.3023 | -0.0004 |
| 0.96 | fg3m | 0 | 0.8497 | 0.8497 | +0.0000 |
| 0.96 | stl | 0 | 0.6720 | 0.6720 | +0.0000 |
| 0.96 | blk | 0 | 0.4138 | 0.4138 | +0.0000 |
| 0.96 | tov | 0 | 0.8461 | 0.8461 | +0.0000 |

## Best factor: **0.96**
- aggregate (pts+reb+ast) delta: -0.0001
- single-split ship gate (PTS AND REB AND AST strictly down): **FAIL**

## Walk-forward: SKIPPED (single-split aggregate improvement < 0.005)

## Verdict
**REJECT** — single-split gate failed (not all 3 stats strictly down); aggregate improvement too small to run WF (< 0.005)

## Why (the failure mode is informative, not noise)

1. **Standard 80/20 holdout (2025-26 season) has `is_b2b = 0` for ALL 19,964 rows.**
   `data/rest_travel.parquet` ends 2025-04-13 — the rest/travel pipeline has
   not been backfilled for the 2025-26 season. Probe initial run found 0
   affected rows on the canonical holdout. Switched to Q4 window
   (2024-12-10 to 2025-10-31) where `is_b2b` IS populated.
   **CAVEAT**: this Q4 window overlaps the production models' training
   period — so the directional reading is in-distribution and not an
   honest hold-out. The signal direction is reliable; the magnitude is
   likely understated (the model already saw these rows in training).

2. **Selection bias kills the landyourbets prior.** The hypothesis was
   "veterans aged 33+ sit 80% of second nights of back-to-backs." But
   `gamelog_*.json` only contains games the player ACTUALLY PLAYED. The
   "80% sit" rows are filtered OUT by selection. The 276 rows in our
   probe are the 20% who DID play on the b2b — these are the veterans
   who travel + suit up, i.e. the ones in good health and good form.
   Shrinking THEIR projections moves predictions away from realized stats.

3. **Concretely: PTS/REB get WORSE, AST gets slightly BETTER.** AST is
   pace-coupled (b2b games are slightly slower), so a small shrink helps.
   PTS/REB are dominated by skilled veterans (a young vet at age 33-34
   is still a high-volume scorer when they play). Predictions are
   already calibrated for these players on b2b games because the model
   sees the `is_b2b` + `rest_days` features.

## Lesson + follow-up

- Cycle ~82's REJECTED flat b2b probe was NOT diluted by under-30s.
  It was REJECTED because gamelog selection bias already strips out the
  sit-rate signal. Conditioning on age 33+ does not unlock anything.
- T1-C as written is **structurally untestable on the current dataset**.
  To test the real effect you'd need PRE-game projections for ALL b2b
  veterans (including DNPs), not gamelog-filtered post-hoc rows. That
  requires a DNP-aware projection set — outside this loop's scope.
- **Cheap unlock that would help anyway**: backfill `rest_travel.parquet`
  through 2026-04-12 so the canonical holdout actually has `is_b2b`
  populated. The current production model's `is_b2b` feature is
  effectively dead for every 2025-26 inference. That's a real bug worth
  fixing in a separate cycle (~90c).
- Agent K's cycle 90e commonplayerinfo fetch is NOT a blocker here —
  bbref `age` field gave 96.1% coverage of the Q4 window for free.

## Wire-in path (not exercised)

If a future cycle finds a conditional cell that DOES pass:
- new helper `apply_post_prediction_adjustments(stat, pred, rows)` in
  `src/prediction/prop_pergame.py` would be the single hook. Cycle 90a
  has not landed there yet — adding the hook framework now would be
  speculative wiring; punted.

