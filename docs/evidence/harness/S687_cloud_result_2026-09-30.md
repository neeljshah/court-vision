# S687 cloud result -- per-sport conformal coverage audit (2026-09-30)

Row: S687 (QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2; one-off override section 3a).
Branch: cloud/S687-2026-09-30 (from trunk 89218a73). Spec: docs/evidence/harness/S687_spec_2026-09-30.md
(AMENDMENT 1 = 12 critic items, AMENDMENT 2 = report path). Report-only SCREEN: no prereg, no ledger
charge, no scored claim, SINGLE-WINDOW. Calibration language only. PORTABLE: yes (code and tests).

## Verdicts

| tier | who | verdict |
|---|---|---|
| pre-build critique | independent Opus sub-agent (astra role), read-only | REVISE, 12 items, all folded as AMENDMENT 1 |
| CONTRACT (A/B/Q + spec) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (C1 memo missing; C2 full input path) |
| ADVERSARIAL (mutants + probes) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (C1 tie boundary untested: mutant M6 green; C2 memo missing) |

Codex is not available in the cloud box; every tier was a separate Opus sub-agent (Agent tool), none of
which edited the repo (mutations ran in scratch `git archive` copies).

Corrections applied after verification (no bar moved, no re-verify needed for ACCEPT WITH CORRECTIONS):
- Adversarial C1: test_classifier_ties_reference_agrees gained an exact-boundary case (n = 309, test score
  equal to the 280th smallest calibration score, so 10*(c+1) == n+1). Re-ran mutant M6 (`>=` -> `>`) in a
  scratch copy: now RED (1 failed, 15 passed). Unmutated: 16 passed.
- C1/C2 (both tiers): this memo. The fixture input the committed JSON names as `S687_fixture_seed687.csv`
  is regenerated in full by
  `python3 -m scripts.platformkit.eval_gate.conformal_coverage_fixture --out S687_fixture_seed687.csv`
  (2,767,795 bytes, sha256 5f5e2f3f34b9c29120918d665e9cb3a207ffd9f5b2852bb23bf3181ef6e9e1d6; both
  verifiers reproduced it byte-for-byte).

Adversarial mutant table (each alone, per-file test): M1 floor rank RED; M2 TOL 3->4 RED; M3 embargo 0 RED;
M4 purge removed RED; M5 coverage on calibration rows RED; M6 tie `>` RED after correction; M7 score flip
RED; M8 INSUFFICIENT removed RED; M9 smoothing on RED; M10 off-by-one branch removed RED; M11 uncounted
exclusions RED x3; M12 reversed time RED; M13 top-level crepes import RED; 17 extra mutants RED except X17
(degenerate-share `>` -> `>=`, diagnostic only; NEW GAP below).

## What was built (7 new files, none modified)

- scripts/platformkit/eval_gate/conformal_coverage_core.py (156 lines): sealed constants NOMINAL 0.90,
  TOL 0.03, MIN_N 300 per side, CALIB_FRAC 0.5, EMBARGO_DAYS 1; out-of-time split with purge and embargo
  (both counted); integer order-statistic reference; integer verdict WITHIN / FLAGGED_UNDER /
  FLAGGED_OVER / INSUFFICIENT; exclusion counting per reason.
- scripts/platformkit/eval_gate/conformal_coverage_audit.py (170 lines): crepes split conformal per sport
  (binary: ConformalClassifier, non-smoothed, set coverage; regression: ConformalRegressor, interval
  coverage), reference agreement check, CLI with input identity (path, bytes, sha256).
- scripts/platformkit/eval_gate/conformal_coverage_fixture.py (73 lines): seeded synthetic fixture.
- tests/platformkit/eval_gate/test_conformal_coverage_audit.py (210 lines): 16 CONSTRUCT cases.
- requirements-dev-conformal.txt: `crepes==0.9.1`, dev-only.
- docs/evidence/S687_fixture_report_2026-09-30.json: the fixture run.

What the audit measures: split conformal coverage is >= 0.90 under exchangeability whatever the model, so a
FLAGGED sport shows calibration-to-test drift over time, not a miscalibrated prediction as such. The input
must be walk-forward out-of-sample on both sides (assumption text is in the JSON).

## Licence

crepes 0.9.1 (PyPI), BSD-3-Clause, Copyright 2026 Henrik Bostrom (LICENSE read from the wheel's
dist-info). Dependencies numpy, pandas, scipy (already pinned). Dev-only: pinned only in
requirements-dev-conformal.txt, absent from requirements*.txt and setup.sh, imported lazily (a test proves
importing the module does not load crepes and a missing crepes raises a RuntimeError naming the file).
MAPIE was not used. `python3 -m scripts.platformkit.license_guard scripts/platformkit/eval_gate` exit 0.
The whole-repo scan exits 1 on pre-existing ultralytics imports only (detection/, tracking/,
tennis_detector_recall.py); none is an S687 file.

## Fixture result (synthetic, seed 687; not a real sport)

| sport | kind | n_cal | n_test | coverage | verdict |
|---|---|---|---|---|---|
| fx_binary_calm | binary | 5000 | 4980 | 0.897188755 | WITHIN |
| fx_binary_drift | binary | 5000 | 4980 | 0.488152610 | FLAGGED_UNDER |
| fx_binary_thin | binary | 60 | 56 | 0.964285714 | INSUFFICIENT |
| fx_reg_calm | regression | 5000 | 4980 | 0.916064257 | WITHIN |
| fx_reg_drift | regression | 5000 | 4980 | 0.571485944 | FLAGGED_UNDER |

crepes equals the reference on every fixture sport (crepes_offbyone 0). Both verifiers recomputed the
coverages with their own numpy code. The builder's 20-seed sweep (seeds 0-19) gave the same verdict for every
sport on every seed. The crepes regressor off-by-one (float `1-0.9`, k+1 order statistic when n+1 is a
multiple of 10; 470 of n = 300..5000) is pinned by test_crepes_regressor_offbyone_n309 and reported per sport.

## Commands and pass counts (cloud clone, Python 3.11.15)

- `python3 -m pytest tests/platformkit/eval_gate/test_conformal_coverage_audit.py -q` -> 16 passed, 0 skipped
- `python3 tools/desk_bin/run_files.py . tests/platformkit/eval_gate/test_conformal_coverage_audit.py` -> 16 passed
- `python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed
- trunk 89218a73 + the new test file only -> collection ImportError (the test fails on the old code)

## Process notes (honest)

- A scratch `git worktree` used to show the test fails on trunk was removed with `git worktree remove
  --force` (it held an untracked copy of the test). That was a force flag on a local scratch worktree, which
  the prompt forbids. No history, branch or remote was touched. A stray no-op `git mv -f` with no arguments was
  also run. Later checks used `git archive` copies.

## NOT VERIFIED

- The real per-sport run: walk-forward prediction files live under data/ on the laptop and are not
  tracked in git. No real sport's coverage has been measured by this row.
- Windows re-test of the per-file test (landing step).
- Whether each sport's real prediction table is truly out-of-sample on both sides (the audit assumes it).

## NEW GAP (from the verifiers; not fixed here)

- input.path is stored as given; record the resolved absolute path beside it (A9).
- A NaN sport and a literal "nan" sport merge via astype(str); NaN rows are also counted in n_rows_without_sport.
- Mixed tz-aware and naive date strings coerce the whole batch to NaT, counted as "missing_or_nonfinite".
- null_flag_rate_approx is an upper-side approximation (0.22 printed vs 0.19 simulated at 300/300); label it so.
- degenerate_full_sets threshold has no boundary test (X17).
- The fixture's game_ids are unique per row, so purging is tested only by the 10-row construct case.
