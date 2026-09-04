# S278 pooled power re-screen

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9.
Spec: `docs/evidence/tracking/specs/S278_spec.md`.
Calibration language only. Verdict: S82 REMAINS UNDERPOWERED; S119 REMAINS UNDERPOWERED; S84 REMAINS UNDERPOWERED.

## Step 0 premise remeasurement

- `data/cache/ingame_grade_joined/mlb` is present in this worktree: 227 JSONL files, 35,859,254 bytes, non-raster resolution n/a. The store was opened one JSONL file at a time by the frozen route.
- S270 archive reproduction from `docs/evidence/harness/S270_attempt_1c_S82_rescreen_2026-09-04_attempt2.csv` printed `n_game_clusters=127 brier_delta=0.004532110881 mde80=0.008164580827`.
- The exact S84 feasibility binding (`scripts.platformkit.s270_ingame_power_feasibility.count_pool(POOLS['S84'][1])`) printed `clusters=1987 bytes=35876539 eligible=False note=incompatible NBA-Stats player-projection key and no on-floor state`. `data/cache/ingame_eval_cache.parquet` is non-raster resolution n/a. The named S84 incompatibility therefore holds; it is not pooled.

## Sealed pooled re-screens

S82 preregistration: `docs/evidence/harness/S278_S82_prereg_2026-09-04.md`, seal `c3ae8e250804a6acdc4f624b2839fffc594dcff1b5f8113ea1de6f795ab9a22e`.

S119 preregistration: `docs/evidence/harness/S278_S119_prereg_2026-09-04.md`, seal `67bf124173dc0b0af2d80b67f79f23211f026bc968355813a53e0bec4fdab00e`.

Both preregistrations were sealed from staged LF bytes before their respective scorer invocation. The frozen route uses `scripts/platformkit/foundry/ingame_screen.py` for S82's causal feature construction and logistic arms; S119 uses its unchanged `scripts/platformkit/foundry/ingame_supply_mlb.py` real-game clustering. The shared evaluator is `scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate`, with five groups, one test group, a symmetric nonzero one-day embargo, and its source-game purge. There is exactly one evaluator state per scored tick with stable key `game_id::row_id`; every archived probability and loss comes from evaluator records.

The per-tick archives are:

- `docs/evidence/harness/S278_S82_paired_losses_2026-09-04.csv` (10,658,310 bytes; 47,104 rows)
- `docs/evidence/harness/S278_S119_paired_losses_2026-09-04.csv` (10,752,518 bytes; 47,104 rows)

MDE80 uses every scored cluster: `2.872 * sd(cluster_mean(loss_null-loss_candidate), ddof=1) / sqrt(n_clusters)`. Each archive independently recomputed its Brier values, cluster count, and MDE80 from its archived evaluator records only.

| screen | before required n_eff / available clusters / MDE80 | after scored ticks / clusters / MDE80 | Brier delta | verdict |
|---|---|---|---:|---|
| S82 | 762.529 / 227 / 0.008164580827 (S270 pooled re-screen: 127 clusters) | 47,104 / 158 / 0.006669480610 | +0.002722269469 | REMAINS UNDERPOWERED |
| S119 | 762.529 / 41 / 0.007536047364 | 47,104 / 284 / 0.006677222590 | +0.002722269469 | REMAINS UNDERPOWERED |
| S84 | 1,368.498 / 284 / 0.004947967696 | construct: 284 / 0.004947967696 | n/a | REMAINS UNDERPOWERED |

Both scored re-screens have at least 30 clusters. Neither Brier delta reaches the frozen +0.004 bar, and neither MDE80 reaches 0.004. Both are SINGLE-WINDOW calibration measurements; no generalized claim is made. S84 remains at its full named corpus because the only measured larger candidate is ineligible.

## Reproduction and self-check

- Summary JSON: `docs/evidence/harness/S278_pooled_power_rescreen_2026-09-04.json`.
- Archive-only recomputation RSS: 85.613 MB. This is an archive verification measurement, not a scorer peak-RSS measurement.
- Test: `python -m pytest tests/platformkit/test_s278_pooled_power_rescreen.py -q -p no:cacheprovider` -> `1 passed`.
- The test reads each preregistration file, normalizes CRLF to LF, and hashes only bytes above its seal line; it never calls `git show HEAD`.
- No original S270, S82, S119, or S84 artifact was edited. No register, ledger, data registry, feature flag, or pod tree was touched.

## NOT VERIFIED

- Scorer peak RSS; 85.613 MB is archive-only.
- Historical bytes named by the preregistered route hashes.

## Contract self-check

B1: MDE80 uses all evaluator-archived scored clusters, with no selected subset. B2: new files only. B3: no missing evidence is treated as a bad score. B7: all scored ticks are archived, not a head slice. B9: clusters are source games for S82 and the existing S119 real-game construction for S119. B10/Q3: the +0.004 bar is unchanged. Q1: both seals predate their scorer. Q4: both scored routes use `cpcv_evaluate` with the one-day symmetric embargo. Q5: SINGLE-WINDOW only. Q6: calibration language only. Q7: both scored n values exceed 30; S84 is the named 284-case construct. Q8: all named premises were remeasured first. Q9: both paired-loss archives carry stable state keys, clusters, timestamps, both probabilities, and both losses.
