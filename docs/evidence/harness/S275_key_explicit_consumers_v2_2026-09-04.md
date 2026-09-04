# S275 explicit calibration-basis consumers v2

Verdict: ACCEPT.

Machine: local worktree `C:/Users/neelj/nba-track-a16`; local gate corpora were
opened one sport at a time and no pod operation occurred.

Preregistration: `docs/evidence/harness/S275_prereg_final_2026-09-04.md`.
LF staged-byte seal:
`C43FB0B12DA955B80658500D4D85F156A3AC43521C9395FCAF9DE1C3084E1BB4`.
It was committed as `c0b822ded36cfa3b69158d695dbb8997ea5eadf8` before the
valid eight-value comparison. Two earlier S275 preregistrations selected stale
artifact families; their NBA output is excluded from all tables below.

## Binding premise

Fresh source census confirmed all three reads were implicit before the change:

- `scripts/platformkit/answers/resolver_registry.py:650` used `v["ece_after"]`.
- `scripts/platformkit/eval_gate/test_calibration_report.py:192` used `report[key]`.
- `scripts/platformkit/answers/test_calibration_scoreboard_regex.py:50` asserted
  resolver-derived `improved_ece`.

`build_report()` contained neither `positional` nor `per_unit`. Fresh absolute
differences from the canonical S50 values were: NBA positional `0.0`, per-unit
`8.64484837447693222e-07`; MLB positional `8.91808296359791752e-08`, per-unit
`5.88803465133985737e-07`; soccer positional `3.75532493502792053e-07`,
per-unit `2.26351430050730773e-07`; tennis positional
`1.44821976339956637e-07`, per-unit `4.53165245946351991e-07`. All are within
the unchanged `1e-6` bar, so the premise holds.

## Inputs and code identity

Inputs were JSON with no raster resolution and opened one at a time:

| path | bytes | resolution |
|---|---:|---|
| `docs/evidence/calibration/nba_reliability_2026-09-03.json` | 7774 | none |
| `docs/evidence/calibration/nba_reliability_per_unit_2026-09-03.json` | 7522 | none |
| `docs/evidence/calibration/mlb_reliability_2026-09-03.json` | 7700 | none |
| `docs/evidence/calibration/mlb_reliability_per_unit_2026-09-03.json` | 7419 | none |
| `docs/evidence/calibration/soccer_reliability_2026-09-03.json` | 8772 | none |
| `docs/evidence/calibration/soccer_reliability_per_unit_2026-09-03.json` | 8472 | none |
| `docs/evidence/calibration/tennis_reliability_2026-09-03.json` | 7856 | none |
| `docs/evidence/calibration/tennis_reliability_per_unit_2026-09-03.json` | 7585 | none |

Route identity: `scripts/platformkit/eval_gate/calibration_report.py` SHA-1
`a6b68f181cc7d631e2cb8e7b075d7cc01f711189`. It retains its expanding
walk-forward report route; no evaluator, corpus, or threshold changed.

## Eight S50 and second-run values

Reference: `docs/evidence/harness/S275_basis_reference_2026-09-04.json`.
Immediate reproduction: `docs/evidence/harness/S275_basis_second_run_2026-09-04.json`.

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

All target differences are at most `1e-6`; all second-run differences are at
most `1e-9`.

## Explicit consumers and flip-invariance

`build_report()` now publishes nine-field fixed-basis `positional` and
`per_unit` summaries while its default top-level fields are unchanged. The
resolver reads `v.get("per_unit", v)` for old-artifact fallback; the report test
reads `report["per_unit"][key]`; the scoreboard test reads
`result["per_unit_ece"]`. The construct runs both bases and source-checks all
three sites; no current or future default can change a consumer reading.

| construct item | count | maximum absolute difference |
|---|---:|---:|
| basis summaries across two calls | 2 bases | 0.0 |
| resolver explicit basis read | 1 site | 0.0 |
| report-test explicit basis read | 1 site | 0.0 |
| scoreboard explicit basis read | 1 site | 0.0 |

Test: `python -m pytest scripts/platformkit/eval_gate/test_s275_key_explicit_consumers.py -q -p no:cacheprovider`
reported `1 passed in 1.84s`.

No ledger or register was read or written. No deployment occurred.
