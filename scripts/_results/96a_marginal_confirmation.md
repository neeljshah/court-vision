# Cycle 98e (loop 5) — cycle 96a garbage-time haircut marginal CONFIRMATION

## Method
After cycle 97a fixed the validator to mirror `apply_garbage_time_haircut` in `_bulk_predict`, the canonical 80/20 holdout baseline now INCLUDES the cycle-96a haircut. To confirm the wire-in is genuinely better than ablation, this script flips `_APPLY_GARBAGE_HAIRCUT=False` and re-scores. The delta (abl - prod) is the TRUE marginal benefit.

## Per-stat MAE

| stat | prod_mae (haircut ON) | abl_mae (haircut OFF) | delta (abl-prod) | note |
|------|----------------------|----------------------|------------------|------|
| pts | 4.6104 | 4.6221 | +0.0117 | targeted |
| reb | 1.9075 | 1.9025 | -0.0050 | targeted |
| ast | 1.3570 | 1.3606 | +0.0036 | targeted |
| fg3m | 0.8941 | 0.8941 | +0.0000 | not targeted (no-op) |
| stl | 0.7153 | 0.7153 | +0.0000 | not targeted (no-op) |
| blk | 0.4398 | 0.4398 | +0.0000 | not targeted (no-op) |
| tov | 0.8932 | 0.8932 | +0.0000 | not targeted (no-op) |

**PTS+REB+AST aggregate delta:** +0.0103 (positive = haircut helps)

## Verdict: **CONFIRMED**

PTS improves by +0.0117 MAE when haircut is enabled (gate: >= 0.005). Cycle 96a wire-in is genuinely beneficial.

## Comparison to cycle 96a's reported numbers

Cycle 96a probe (`probe_garbage_time_haircut_v2.py` on a broken baseline) reported:
- PTS -0.0117 MAE
- REB +0.0050 MAE
- AST -0.0036 MAE
- agg(PTS+REB+AST) -0.0103

Cycle 98e (this run, correct baseline) measured:
- PTS -0.0117 MAE
- REB +0.0050 MAE
- AST -0.0036 MAE
- agg(PTS+REB+AST) -0.0103

Numbers should match cycle 96a's reported deltas within noise — confirms the validator fix (97a) didn't change the underlying marginal effect.
