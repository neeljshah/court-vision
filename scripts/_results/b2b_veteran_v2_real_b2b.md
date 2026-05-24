# cycle 92e (loop 5) — T1-C re-test with REAL is_b2b

## Why v2
v1 (cycle 90b) ran into a data bug: `data/rest_travel.parquet` ended
2025-04-13, so every row in the canonical 2025-26 holdout had
`is_b2b == 0`. v1 fell back to a Q4 in-distribution window. Cycle 91d
shipped a rebuilt parquet through 2026-04-06 (overall `is_b2b` mean
≈ 0.174, 2025-26 mean ≈ 0.178). v2 re-runs on the canonical 80/20
holdout where the b2b cell is real AND out-of-sample.

## Setup
- holdout: chronological 80/20 (n=19964 of full n=99818)
- holdout date range: 2025-10-31T00:00:00 -> 2026-04-12T00:00:00
- holdout seasons: ['2025-26']
- **is_b2b mean in holdout: 0.1770  (3533/19964 rows had is_b2b>=0.5)**
- age source: `data/external/bbref_advanced_<season>.json` (`age` field)
- ages resolved: 17172/19964 (86.0%)
- rows age>=33: 1842
- **rows affected (age>=33 AND is_b2b): 308**
- starter flag: NOT IN DATASET — defaulted to INCLUDE (same as v1)
- target stats: pts, reb, ast (others fg3m/stl/blk/tov untouched)

## Single-split MAE table (per factor)

| factor | stat | n_aff | base_mae | adj_mae | delta |
|--------|------|------:|---------:|--------:|------:|
| 0.88 | pts | 308 | 4.6221 | 4.6220 | -0.0001 |
| 0.88 | reb | 308 | 1.9025 | 1.9021 | -0.0004 |
| 0.88 | ast | 308 | 1.3606 | 1.3601 | -0.0005 |
| 0.88 | fg3m | 0 | 0.8941 | 0.8941 | +0.0000 |
| 0.88 | stl | 0 | 0.7153 | 0.7153 | +0.0000 |
| 0.88 | blk | 0 | 0.4398 | 0.4398 | +0.0000 |
| 0.88 | tov | 0 | 0.8932 | 0.8932 | +0.0000 |
| 0.90 | pts | 308 | 4.6221 | 4.6216 | -0.0005 |
| 0.90 | reb | 308 | 1.9025 | 1.9021 | -0.0004 |
| 0.90 | ast | 308 | 1.3606 | 1.3601 | -0.0005 |
| 0.90 | fg3m | 0 | 0.8941 | 0.8941 | +0.0000 |
| 0.90 | stl | 0 | 0.7153 | 0.7153 | +0.0000 |
| 0.90 | blk | 0 | 0.4398 | 0.4398 | +0.0000 |
| 0.90 | tov | 0 | 0.8932 | 0.8932 | +0.0000 |
| 0.92 | pts | 308 | 4.6221 | 4.6214 | -0.0006 |
| 0.92 | reb | 308 | 1.9025 | 1.9022 | -0.0003 |
| 0.92 | ast | 308 | 1.3606 | 1.3602 | -0.0004 |
| 0.92 | fg3m | 0 | 0.8941 | 0.8941 | +0.0000 |
| 0.92 | stl | 0 | 0.7153 | 0.7153 | +0.0000 |
| 0.92 | blk | 0 | 0.4398 | 0.4398 | +0.0000 |
| 0.92 | tov | 0 | 0.8932 | 0.8932 | +0.0000 |
| 0.94 | pts | 308 | 4.6221 | 4.6214 | -0.0007 |
| 0.94 | reb | 308 | 1.9025 | 1.9022 | -0.0003 |
| 0.94 | ast | 308 | 1.3606 | 1.3602 | -0.0004 |
| 0.94 | fg3m | 0 | 0.8941 | 0.8941 | +0.0000 |
| 0.94 | stl | 0 | 0.7153 | 0.7153 | +0.0000 |
| 0.94 | blk | 0 | 0.4398 | 0.4398 | +0.0000 |
| 0.94 | tov | 0 | 0.8932 | 0.8932 | +0.0000 |
| 0.96 | pts | 308 | 4.6221 | 4.6215 | -0.0006 |
| 0.96 | reb | 308 | 1.9025 | 1.9023 | -0.0002 |
| 0.96 | ast | 308 | 1.3606 | 1.3603 | -0.0003 |
| 0.96 | fg3m | 0 | 0.8941 | 0.8941 | +0.0000 |
| 0.96 | stl | 0 | 0.7153 | 0.7153 | +0.0000 |
| 0.96 | blk | 0 | 0.4398 | 0.4398 | +0.0000 |
| 0.96 | tov | 0 | 0.8932 | 0.8932 | +0.0000 |

## Best factor: **0.92**
- aggregate (pts+reb+ast) delta: -0.0014
- single-split ship gate (PTS AND REB AND AST strictly down): **FAIL**

## Walk-forward (4 chronological folds within holdout, no retrain)

| stat | fold | base | adj | delta | positive? |
|------|-----:|----:|----:|------:|:---------:|
| pts | 1 | 4.6074 | 4.6069 | -0.0004 | YES |
| pts | 2 | 4.5830 | 4.5812 | -0.0018 | YES |
| pts | 3 | 4.6056 | 4.6091 | +0.0035 | no |
| pts | 4 | 4.6925 | 4.6886 | -0.0039 | YES |
| reb | 1 | 1.8906 | 1.8901 | -0.0005 | YES |
| reb | 2 | 1.9284 | 1.9278 | -0.0006 | YES |
| reb | 3 | 1.9130 | 1.9124 | -0.0006 | YES |
| reb | 4 | 1.8780 | 1.8783 | +0.0004 | no |
| ast | 1 | 1.3497 | 1.3492 | -0.0005 | YES |
| ast | 2 | 1.3325 | 1.3321 | -0.0005 | YES |
| ast | 3 | 1.3811 | 1.3809 | -0.0002 | YES |
| ast | 4 | 1.3792 | 1.3786 | -0.0006 | YES |

- PTS: 3/4 folds positive
- REB: 3/4 folds positive
- AST: 4/4 folds positive

## WF gate (4/4 on PTS, REB, AST): **FAIL**

## Selection-bias context (still applies in v2)

The landyourbets prior is 'veterans aged 33+ sit ~80% of second
nights of b2bs'. But `gamelog_*.json` ONLY contains games the player
ACTUALLY PLAYED — the 80% who sat are SILENT in the dataset. The
~308 rows we adjust are the ~20% who DID suit up: by
selection, these are the vets in good health/form. Shrinking their
projections fights what the model already learned from the `is_b2b`
+ `rest_days` features (which DO see the survivor distribution).

**Expected ceiling on this probe is ~3-4% headline effect** (single-
digit basis-point MAE win) — NOT the 1-3bp/8-12% the headline prior
would suggest. If we land near zero or negative, that confirms the
selection-bias ceiling, not noise.

## Verdict
**REJECT** — single-split gate failed (not all 3 stats strictly down); WF gate failed (not 4/4 on all target stats).

Even with real 2025-26 `is_b2b` (cycle 91d), the gamelog selection
bias dominates. The vets who PLAY on the b2b are the survivor
subset, and the model's per-row `is_b2b` feature already captures
whatever residual fatigue effect remains in that subset.

**Follow-up:** T1-C is structurally untestable on game-log data.
Deferring to a DNP-aware projection-set infra cycle — that loop
would let us validate the FULL sit-rate effect (the 80% who DNP)
by predicting for ALL rostered vets pre-game and weighting by
realized play-probability. Without that, every flavor of this
probe (age 33, 32, 30; starter only; PT-weighted) will hit the
same survivor-bias ceiling.
