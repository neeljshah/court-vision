# S317 preregistration: additive series schema

Spec: `docs/evidence/tracking/specs/S317_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

Binding premise rerun before this file: S287's legacy per-game CSV stores `timestamp`
as `<game_id>:<elapsed>` and has no probability or outcome fields. S287's selected-tick
CSV has `game`, `ts`, `elapsed`, `outcome_home_win`, `market_prob`, `p_null`,
`p_simulator`, and all three loss columns. This run will read those committed inputs only.

Inputs and realised-source rule:

| Input | Purpose | Bytes |
| --- | --- | ---: |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_selected_tick_series.csv` | v2 regeneration | 628595 |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_summary.json` | equality target | 994392 |
| `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04.md` | archive-path check input | existing committed memo |

This local-only run stages no external inputs. The exact scratch path is `NONE (committed
evidence read in place)` and the memo will print that realised path verbatim. No pod,
registry, ledger, or `data/` path is used.

Predeclared computation: transform every selected tick into one v2 row; calculate Brier
and 10-bin equal-width ECE for market, null, and simulator from all 2,130 rows; compare
those values to S287's summary at tolerance 1e-9. This is an archived-artifact
recomputation, not a new model comparison. Improvement convention, if a delta is printed:
baseline loss minus candidate loss; positive means candidate better.

The archive-location check will enumerate every present memo matching the amended S317
list and record absent named memos as `ABSENT`. It parses declared prereg input/scratch
paths and memo realised staging paths only; `UNSTATED` is pass-through reporting, not a
failure classification.

No threshold, model, or landed artifact will change. Tests cover v1/v2 round trips, a
hand-pinned 12-tick Brier/ECE construct, and constructed archive-location pairs.
SEAL sha256 06829751df5ee24cde6599e228ee366dc6744f4350cf0be2a738d214eaa320ca
