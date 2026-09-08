# S322 simulator diagnostics preregistration

Spec: `docs/evidence/tracking/specs/S322_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

This seal is prepared before the first S322 metric. This codex lane prepares
only; it must not open or score the cached series. The finisher must rerun the
binding premise before any comparison: print the v2 tick and cluster counts,
and reproduce the three S287 Brier values to 1e-9. A mismatch is PREMISE FALSE
and ends the row without scoring.

## Frozen inputs and source rule

The finisher opens the following committed inputs one at a time, under this
worktree root. CSV inputs have no image resolution (N/A).

| Repo-relative path | Bytes at preparation | Resolution | Use |
| --- | ---: | --- | --- |
| `docs/evidence/harness/S317_series_schema_2026-09-08/S317_S287_v2_tick_series.csv` | 299286 | N/A | 2130-tick v2 cache |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_selected_tick_series.csv` | 628595 | N/A | frozen replay source |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_summary.json` | 994392 | N/A | Brier equality target |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_per_game_paired_loss_series.csv` | 33690 | N/A | cluster identity reference |

Any quoted `/c/Users/neelj/nba-track-aNN/` store path resolves beneath this
worktree root. A truly absent repo-relative input is printed as
`ABSENT-IN-WORKTREE <path>` and stops the relevant diagnostic.

## Frozen diagnostic design

A selects exactly 30 states: earliest and latest states, tied states, states
with absolute margin at least 15, every overtime state, and both venues.
Selection is deterministic by `timestamp`, then `game_id`, then `elapsed_s`;
duplicates are removed before the remaining slots are filled evenly across the
sorted eligible union. Each state receives PASS/FAIL checks for home-side
polarity, remaining-versus-final score semantics, clock, overtime, and
probability conservation. The frozen cached-logit recalibration replay
tolerance is 1e-9. The trace bar is zero unexplained errors; every error is
listed with its field.

C uses chronological whole-game clusters with the shared `cpcv_evaluate`
evaluator, strict redaction, unique state keys, purge, and a symmetric
nonzero three-calendar-day embargo. One evaluator state exists per tick, never
one state per game. It evaluates: (i) train-only intercept plus temperature on
the simulator logit; (ii) (i) plus a train-only coefficient for pregame M0,
or the tick market probability when pregame M0 is unavailable and the output is
labelled `tick_market_substitution`; and (iii) N alone. All fitted predictions
are OOF evaluator records. Brier, 10-bin ECE, and log loss are reported, with
2000 deterministic paired game-cluster bootstrap resamples of archived
evaluator-record losses. Improvement means baseline loss minus candidate loss;
positive means the candidate has lower loss. The C bar is exactly Brier
improvement of at least 0.002 with bootstrap CI lower bound greater than 0 for
(ii) against N. If it fails, the fixed decision is STOP SIMULATOR EXPANSION
until B is fixed.

B first enumerates only `data/cache/` entries whose names contain `pbp` or
`possession`, one store at a time. If no qualifying historical prefix store is
available, it reports BLOCKED with the exact absent path; it does not create
transitions. If available, it evaluates 200 prior-game prefixes with held-out
one-step transition log loss, paired cluster CIs, and zero illegal transitions.

The hand-pinned 12-tick construct must demonstrate that A catches a planted
polarity flip and overtime clock error, C reproduces pinned intercept and
temperature values, and the comparator returns pinned Brier deltas. No model,
feature flag, `src/`, `data/`, register, ledger, or deployed pod tree changes.
The finisher records the local `basketball_ai` interpreter before running.

SEAL sha256 eb2a883157e6c383f4781ce0df9719651b036ce2f055f5cf97f533fb7a8b5ee5
