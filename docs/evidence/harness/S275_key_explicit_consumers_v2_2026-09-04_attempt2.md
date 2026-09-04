# S275 explicit calibration-basis consumers v2: attempt 2

Verdict: ACCEPT.

Machine: local worktree `C:/Users/neelj/nba-track-a16`; local gate corpora
were opened one sport at a time. No deployment occurred.

Preregistration: `docs/evidence/harness/S275_prereg_2026-09-04_attempt2.md`.
Staged LF bytes above its seal line and `git show HEAD:<path>` both hash to
`CFB5E1DC7221EA361A9D029A140D2574670FEB3AF62DCD9F0A9975B6549E982E`.
It was committed as `d3812c39aabd7721d6b81ac87567daa8cbc9c8e3` before attempt-2
scoring.

## ATTEMPT 2 correction

| verifier item | attempt 1 | attempt 2 |
|---|---|---|
| B10 / Q3 rail | resolver allowance 1325; rail failed | allowance retained at 1323; resolver is 1323 lines; rail passed |
| Q1 seal | embedded `C43FB0B...`; committed prefix differed | staged and committed LF-prefix hash both `CFB5E1DC...E982E` |
| explicit readers | 3/3 and flip diff 0.0 | retained 3/3 and flip diff 0.0 |

The resolver keeps `basis = v.get("per_unit", v)`, so older artifacts retain
their top-level fallback. No field, status, or reader behavior was renamed or
removed. The first run and immediate fresh run use `build_report` directly for
each of four sports and both bases, through the existing expanding
walk-forward route.

## Eight-value calibration table

Reference: `docs/evidence/harness/S275_basis_reference_2026-09-04_attempt2.json`.
Second run: `docs/evidence/harness/S275_basis_second_run_2026-09-04_attempt2.json`.

| sport | basis | S50 target | reference | target diff | second run | reference diff |
|---|---|---:|---:|---:|---:|---:|
| nba | positional | 0.024842541854003943 | 0.024842541854003943 | 0.0 | 0.024842541854003943 | 0.0 |
| nba | per_unit | 0.026582546070994170 | 0.026583410555831620 | 8.644848374476932e-07 | 0.026583410555831620 | 0.0 |
| mlb | positional | 0.008076735465020577 | 0.008076824645850213 | 8.918082963597918e-08 | 0.008076824645850213 | 0.0 |
| mlb | per_unit | 0.012666184733512256 | 0.012665595930047123 | 5.888034651339857e-07 | 0.012665595930047123 | 0.0 |
| soccer | positional | 0.009302164221488884 | 0.009301788688995382 | 3.755324935027921e-07 | 0.009301788688995382 | 0.0 |
| soccer | per_unit | 0.028722315180213532 | 0.028722088828783483 | 2.263514300507308e-07 | 0.028722088828783483 | 0.0 |
| tennis | positional | 0.008402944939872484 | 0.008403089761848824 | 1.448219763399566e-07 | 0.008403089761848824 | 0.0 |
| tennis | per_unit | 0.015403176684314482 | 0.015402723519068535 | 4.531652459463520e-07 | 0.015402723519068535 | 0.0 |

All eight target differences are at most `1e-6`; all second-run differences
are at most `1e-9`.

## Explicit consumers and flip invariance

The construct confirms `resolver_registry.py` uses the explicit per-unit
summary with its fallback, `test_calibration_report.py` reads
`report["per_unit"][key]`, and `test_calibration_scoreboard_regex.py` reads
`result["per_unit_ece"]`. Both bases over two calls have summary difference
`0.0`; each of the three consumer readings has difference `0.0` for all four
sports.

## Test lines

- `python -m pytest scripts/platformkit/eval_gate/test_s275_key_explicit_consumers.py -q -p no:cacheprovider`: 1 passed.
- `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider`: 1 passed.
- `python -m pytest scripts/platformkit/test_guard_invariants.py -q -p no:cacheprovider`: 4 passed.
- `python -m pytest tests/platformkit/analytics_verify/test_answers.py -q -p no:cacheprovider`: 15 passed.
- `python -m pytest tests/platformkit/analytics_verify/test_system_map.py -q -p no:cacheprovider`: 15 passed.
- `python -m pytest tests/platformkit/answers/test_atlas_resolver.py -q -p no:cacheprovider`: 8 passed.
- `python -m pytest tests/platformkit/answers/test_prediction_quality_resolver.py -q -p no:cacheprovider`: 6 passed.
- `python -m pytest tests/platformkit/mcp_server/test_edge_refusal.py -q -p no:cacheprovider`: 16 passed.
- `python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q -p no:cacheprovider`: 9 passed, 1 failed on the pre-existing default NBA artifact mismatch (`0.024842541854003943` versus `0.039002202208806645`), identical to master.

## NOT VERIFIED

The required pod command for
`scripts/platformkit/answers/test_calibration_scoreboard_regex.py` returned
`/usr/local/bin/python: No module named pytest` and `POD_RUN_DONE rc=1`.
No local substitution was used. The same missing pod dependency blocks the
remaining resolver-import test files under `scripts/platformkit/answers/`:
`test_answer_consistency_intel.py`, `test_answer_consistency_mlb.py`,
`test_answer_consistency_nba.py`, `test_answer_consistency_soccer.py`,
`test_answer_consistency_tennis.py`, `test_claims_resolver.py`,
`test_edge_calibration_guards.py`, `test_effect_graph.py`,
`test_leaderboard_resolver.py`, `test_leaderboard_team_scope.py`,
`test_mechanism_effect.py`, `test_player_compare.py`, and
`test_resolver_registry_routing.py`.

No register or ledger was read or written. Prior S275 artifacts remain
byte-identical.
