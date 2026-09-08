# S297 minutes and DNP distribution (2026-09-04)

## Result

SINGLE-WINDOW calibration comparison. Improvement is baseline loss minus candidate loss; positive means candidate better.
The primary unit is minutes CRPS. DNP Brier/log loss and pinball are secondary; the NBA in-game Brier bar does not apply.

| Metric | Baseline | Candidate | Improvement | Paired game-cluster 95 pct CI (corrected at landing) |
|---|---:|---:|---:|---|
| minutes_crps | 9.682305 | 8.549927 | 1.132378 | [1.090696, 1.170901] |
| dnp_brier | 0.215952 | 0.215875 | 0.000077 | [0.000030, 0.000131] |
| dnp_logloss | 5.851326 | 5.851607 | -0.000281 | [-0.001317, 0.000668] |
| pinball_q10 | 2.034523 | 1.698524 | 0.335999 | [0.325139, 0.346571] |
| pinball_q50 | 5.960666 | 5.075985 | 0.884681 | [0.854364, 0.918170] |
| pinball_q90 | 5.567781 | 5.402712 | 0.165069 | [0.155928, 0.172688] |
| inside80 | 0.642312 | 0.648965 | -0.006653 | [-0.009075, -0.003867] |

Verdict: ACCEPT. Primary bar requires positive minutes-CRPS improvement with CI lower above zero.

## Corrections applied at landing

Applied 2026-09-08 from `docs/evidence/harness/S297_VERIFY_2026-09-08.md` (verifier codex-sol,
VERDICT: ACCEPT WITH CORRECTIONS). The verifier reproduced every point estimate and found one defect
in the interval only.

- Defect: the scored revision mixed a ROW-WEIGHTED point estimate with an EQUAL-GAME cluster
  bootstrap (`scripts/platformkit/s297_minutes_dnp_distribution.py:183-189` as scored). Games hold
  16-33 rows, so the two weightings are not the same estimand.
- Estimand now stated and used throughout: the point estimate is the row-weighted mean of
  (baseline loss minus candidate loss); the interval is a 500-draw cluster bootstrap that resamples
  whole games with replacement and re-aggregates each draw ROW-WEIGHTED (sum of deltas over sum of
  counts), so the interval and the point estimate share one weighting.
- Code fix applied at landing (the verifier's minimal diff): the `_summary` group aggregation is
  `agg(["sum", "count"])` and `boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)`. Replaying
  the archived paired losses through the patched `_summary` reproduces every corrected interval
  exactly, including minutes CRPS [1.090696, 1.170901].
- The table above and the JSON summary now carry the corrected intervals. The candidate's original
  intervals stay visible in the JSON under `improvement_ci95_as_scored`; for the primary unit that
  was minutes CRPS [1.066859, 1.148917].
- Unchanged by the correction: baselines, candidates, improvements, folds, denominators, verdict.
  The primary bar (positive improvement with a positive CI lower bound) is met on the corrected
  interval as well.
- `route_sha256` in the JSON records the revision that produced these scores; the landing patch
  changes the harness file, so its current hash differs from the recorded one.
- Test rerun at landing: `python -m pytest tests/platformkit/test_s297_minutes_dnp_distribution.py -q
  -p no:cacheprovider` (1 passed) and `tests/platformkit/test_loc_rail_scope.py` (1 passed).

## Open gaps recorded at landing

- NEW GAP: the positive-only quantiles use player-only history when a player history is present,
  not partial pooling (`scripts/platformkit/s297_minutes_dnp_distribution.py:129-130` vs
  `docs/evidence/tracking/specs/S297_spec.md:8`).
- NEW GAP: the focused tests do not cover the summary/bootstrap weighting
  (`tests/platformkit/test_s297_minutes_dnp_distribution.py:18-42`); the corrected weighting above was
  verified by an archived-loss replay at landing, not by a test.

## Folds

| Split | Dates | Rows | Held-out games | Status |
|---|---|---:|---:|---|
| 0 | 2023-10-24 .. 2024-02-09 | 16705 | 775 | SCORED |
| 1 | 2024-02-10 .. 2024-12-08 | 17522 | 812 | SCORED |
| 2 | 2024-12-09 .. 2025-03-30 | 16088 | 755 | SCORED |
| 3 | 2025-03-31 .. 2026-01-21 | 16624 | 768 | SCORED |
| 4 | 2026-01-22 .. 2026-06-05 | 11828 | 535 | SCORED |

## Provenance

- Preregistration: `docs/evidence/harness/S297_minutes_dnp_distribution_2026-09-07_prereg.md`; LF-normalized bytes above its seal line SHA-256: `3dad9bc2d19a288b9938e74909f20b2b0d05059d8dc01743db775c5875b837ea`. The Git index was sandbox-denied, so this is the direct LF-normalized file hash; lane_commit must stage the explicit path and verify it from staged bytes.
- Binding premise rerun, one input store at a time: `data/domains/basketball_nba/player_boxscores.parquet` had 326 zero-minute rows of 77,744; `data/cache/omni_box_refresh/nba_player_box_extension.parquet` had 221 of 1,023. The premise is CONFIRMED.
- Inputs, bytes, SHA-256, rows, and resolution are in the JSON summary.
- Shared `cpcv_evaluate_vector_distributional` CPCV used one player-game state per tick, purging and a symmetric one-day embargo.
- Scores CSV re-emits game_id/player_id/date, explicit DNP status, probabilities, mixture quantiles, and positive-minute quantiles.
- Paired losses CSV derives only from evaluator records and retains the split/game/player/date keys.
- RSS was 188.80 MB before and 866.76 MB after; this scorer ran once on the pod. The pod emitted `POD_RUN_DONE`; the wrapper did not retain an exit-code suffix, so the process exit code is not asserted here.
- Focused test: `python -m pytest tests/platformkit/test_s297_minutes_dnp_distribution.py -q -p no:cacheprovider` (1 passed).
- Every exercised route hash is in the JSON summary.
- Sandbox note: the orchestrator commits these files by explicit pathspec through lane_commit.

## NOT VERIFIED

- A second independent corpus or any AHEAD promotion; this is SINGLE-WINDOW only.
- Missing roster records, because absent players have no record and are never made into DNP labels.
- Live, deployment, or forward-operating behavior.
- Whether the fixed pooling weight, sample count, or 70/30 mixture is optimal.
