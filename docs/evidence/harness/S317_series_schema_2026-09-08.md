VERDICT: DONE

# S317 additive calibration-series schema

Spec: `docs/evidence/tracking/specs/S317_spec.md`. Contract self-check:
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9.

## Premise and method

The binding before-condition was rerun. S287 legacy-series header and first rows show
`timestamp` values `401809239:120`, `401809241:120`, and `401809510:120`; it has no probability or outcome column.
Opened one store at a time: `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_selected_tick_series.csv`
(628595 bytes, CSV) and `docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/S287_summary.json` (994392 bytes, JSON); no image input/resolution.
The tick fields `game`, `ts`, `elapsed`, `outcome_home_win`, `market_prob`, `p_null`, `p_simulator`, and all losses permit complete v2 regeneration. S287's prereg has no exact
`inputs/` scratch declaration; its memo reports `/workspace/wt/a13/data/cache/eval_gate/`.
Preregistration: `docs/evidence/harness/S317_series_schema_2026-09-08_preregistration.md`,
seal `06829751df5ee24cde6599e228ee366dc6744f4350cf0be2a738d214eaa320ca`, written before
the first recomputation. `git add` was sandbox-denied because the worktree index is
outside the writable root; the orchestrator must make the prereg own explicit-path
commit with `lane_commit`. The seal was computed from LF-normalized bytes above the
seal line. Sign convention for every delta: improvement = baseline loss minus
candidate loss; positive = candidate better.
## Reproduction (n = 2,130 ticks)

| Arm | Brier | ECE, 10 bins | Max absolute difference from S287 |
| --- | ---: | ---: | ---: |
| market | 0.15152952699530517 | 0.023964319248826263 | 0.0 |
| null | 0.15199661253656968 | 0.02432572050776539 | 0.0 |
| simulator | 0.2570908524061033 | 0.07932805164319245 | 0.0 |

`S317_S287_v2_tick_series.csv` retains the legacy key and adds real UTC tick
timestamps, probabilities, outcomes, and losses. `S317_recomputation.json` confirms
all six reproduced metrics meet the 1e-9 bar. This is an archived-artifact
recomputation, not a new model comparison. No new evaluator run, pod run, registry,
ledger, `data/`, `src/`, or preexisting landed artifact was changed. Eye check: NONE.
## Archive location rule

`PREREG_ARCHIVE_RULE.md` and `archive_path_check.py` are additive. The amended census
listed 49 present matching memos plus named absent `S308_attempt2.md`: n = 50 rows,
0 MATCH, 0 MISMATCH, 49 UNSTATED, and 1 ABSENT. The full per-memo table is
`S317_series_schema_2026-09-08/S317_archive_path_check.csv`; UNSTATED is reporting,
not quarantine. The focused test passed: `python -m pytest
tests/platformkit/test_s317_series_schema.py -q -p no:cacheprovider` (4 passed).

## Evidence hashes and handoff

All hashes are LF-normalized SHA-256: prereg `78f7a346cc40f6ad9e58c86b0b0a5cf585b4c4ba8fdf44db052043e497f63fe6`;
schema `cc851cdf0212fde1da9581d173944084cc3b6b2b3d1ed78dc7702a85181f988c`;
checker `79d6807655e8f63a3131a5ab4e174348e9debf70cb007b478c3a4ec6f42aca8a`;
v2 CSV `cc8fae88061347092fdc5953583a93355a848f60f932647100c8234a0fedad92`;
recomputation `d16078e40eeff4d84aabb0acdc201578a9d56bc2058bc3be0c0eb90c63f90877`;
archive table `494ff422307c8392b14a4229d0fb3001c079a4d7c91ef4597a5017e9c16f564f`.
Local wall time: about 25 minutes. Proposed ledger line:
`2026-09-08 | in-game calibration | S317 | additive v2 series reproduces 3-arm Brier/ECE from 2,130 S287 ticks at max difference 0.0; archive census n=50 reports 49 UNSTATED and 1 ABSENT | DONE`

## NOT VERIFIED

- An independent verifier rerun or the orchestrator's explicit-path commits.
- Whether historic rows omitted a scratch declaration for every input; the census only reports declared text.
- Real timestamps beyond the committed S287 tick `ts` values, or any broader corpus.
