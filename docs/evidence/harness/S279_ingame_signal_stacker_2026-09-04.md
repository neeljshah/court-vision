# S279 NBA in-game AS-OF-safe signal stacker

## Verdict: NULL

The complete all-tick comparison is an identity fallback: no S223 AS-OF-safe
store has a strict-prior player or team join key represented in the checkpoint
grid. All 465,249 ticks therefore use the recalibrated-null prediction for
both arms. This is an honest calibration non-finding, not a narrowed sample.

## Premise binding

Source `docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.json`
(95,845 bytes) was reread before scoring. Its whole-set label distribution was
AS-OF SAFE=49, SNAPSHOT-ONLY=55, and UNDATED=54. The safe enumeration is four
`atlas` rows and 45 `intelligence` rows. Every safe path exists in this
worktree and retains its declared temporal column; none is NOT FOUND.

The exhaustive per-store inventory, grouped by its `category` and including
path, byte size, grain, temporal column, join status, and joined-tick count,
is committed in
`docs/evidence/harness/S279_ingame_signal_stacker_2026-09-04_summary.json`
and its standalone
`docs/evidence/harness/S279_ingame_signal_stacker_2026-09-04_join_manifest.json`.
All 49 have zero joined ticks: player/team keys are absent from the tick grid,
or matching an available current-game key would violate the strict-prior date
rule.

## Sealed evaluation

Preregistration:
`docs/evidence/harness/S279_ingame_signal_stacker_prereg_2026-09-04.md`.
Its staged LF-byte prefix seal was verified before scoring:
`be8beb5ba9f50ebab84d967a6db625467962186f9651df30bf727fc0b8309961`.
No ledger was read or changed, and no trial was charged.

Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2,829,826 bytes;
465,249 ticks; 1,593 game clusters; tabular, resolution not applicable).
The shared `cpcv_evaluate` route used one state per stable
`game_id|ts|source_row` tick, two chronological groups, the existing purge,
and a symmetric one-day embargo. The fitted shrinkage path was
`0.01, 0.1, 1.0, 10.0, 100.0, maximum`; with no joinable columns it selected
`maximum`, whose weight vector is zero for each of the 49 named stores and
whose prediction is exactly recal_null.

| metric | result |
|---|---:|
| recal_null Brier | 0.073546695 |
| stacker Brier | 0.073546695 |
| stacker minus recal_null Brier | 0.0000000000000000 |
| game-clustered 95 pct CI | [0.0000000000000000, 0.0000000000000000] |
| game clusters | 1,593 |
| imputed ticks | 465,249 |
| frozen bar | +0.004 |

The archived all-tick paired losses are
`docs/evidence/harness/S279_ingame_signal_stacker_2026-09-04_paired_losses.csv`;
the zero weight vector and per-store statuses are
`docs/evidence/harness/S279_ingame_signal_stacker_2026-09-04_weights.csv`.
The summary was regenerated only from those evaluator records after the pod
calculation. An independent streamed CSV recomputation reproduces both Briers
within 1e-9 and finds zero nonzero paired loss deltas. The finalizer RSS was
371,331,072 bytes; the pod wrapper reported a host-wide HWM observation of
1,726,204 KB. The recorded route SHA-256 is
`349d4980d62efc582ed6c4b528f0120c8f32d0c3f137e185d0ad3643c36b00fb`.

Focused test:

    python -m pytest scripts/platformkit/ingame/test_s279_ingame_signal_stacker.py -q -p no:cacheprovider

It passed: `1 passed`.

## Contract self-check

- B1: every input tick is present; fallback ticks were not removed.
- B2-B6: this is additive, opt-in measurement code with no changed reader schema,
  production callers, flag, registry, ledger, or deployment write.
- B7-B9: no render or head slice was used; the denominator is 465,249 distinct
  evaluator states clustered by 1,593 games.
- B10/Q3: the +0.004 bar is unchanged.
- Q1: the preregistration seal predates the metric.
- Q4/Q9: the shared CPCV route supplies purge and symmetric embargo; the
  committed paired-loss file has one record per scored tick with cluster id and
  timestamp, and the summary is reproducible from it.
- Q5: no AHEAD is claimed.
- Q6: calibration language only.

## NOT VERIFIED

- Finite shrinkage fits/selection were not exercised because all joins fell back; finalizer RSS is run-dependent (verifier 1347907584 bytes vs claimed 371331072; peak HWM matched 1726204 KB).
- The 97255627-byte paired-loss artifact remains local-only at the named path under `.git/info/exclude`; it exceeds the 50 MB evidence landing limit and is not in the landed commit.
