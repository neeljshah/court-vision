# S631 cloud result -- 2026-09-30 (desk-improve routine, cloud clone, Python 3.11.15)

Row: S631 (nba props, prop line distance calib contract). Branch: cloud/S631-2026-09-30
(build commit d27798d8 on trunk 67a0801b). PORTABLE: yes. Not landed; register and DESK_STATE
not edited (routine override 2: parallel cloud branches).

## Why this row
Claim check: `git ls-remote --heads origin 'cloud/*'` showed every PORTABLE quant-grade row
(S660-S689) already TAKEN; the untaken ones (S661, S662, S665, S673, S680, S681) are WINDOWS.
S631 is OPEN, PORTABLE, has no live owner (test-health lane: NONE), needs no data/ or venue host,
and touches no seal-pinned file (no PREREG*.json under docs/evidence/forward names the module).

## Change
- scripts/platformkit/improve/prop_line_distance_calib.py: 2 lines, LOC stays 374 (LOC rail).
  :222 `list(stats) if stats else ...` -> `if stats is not None else ...`; :210 docstring
  now states the contract (empty -> no rows; None -> all NBA stats).
- NEW tests/platformkit/improve/test_prop_line_distance_calib_s631.py: 6 construct cases.
- Existing test file untouched: sha256 11d755231b5a...7cfd9 at base and head (not weakened).
Contract decision: no caller of run_line_distance_calib exists outside the module and its test
(grep over py/md/ps1/sh/json/toml/yaml), so the docstring + the existing test decide it.
Side effect (AMENDMENT 1 A1): a pd.Series / multi-element ndarray `stats` used to RAISE
ValueError at :222 (outside every try, breaking "never raises"); it now works.

## Verdicts (independent Opus sub-agents; none of them built the change)
- Pre-build critic (astra role): REVISE, 6 items, all folded as spec AMENDMENT 1.
- CONTRACT tier (VERIFIER_CONTRACT A/B/Q + spec with AMENDMENT 1): ACCEPT WITH CORRECTIONS.
  The one correction (A7: this evidence file was missing at d27798d8) is closed by this file.
- ADVERSARIAL tier: ACCEPT. Historical, unverified 11-mutant tally (full definitions/results
  not archived); M1/M2 independently reproduced. Reported red: M1, M2, M3, M6, M7, M8, M11.
  Reported survivors (all outside the spec'd contract): M4 drop list() (generator is consumed twice only
  if list() is removed), M5 sort+dedupe, M9 filter unknown stats, M10 dedupe. Optional
  follow-up: an order-preservation case (["reb","pts"]) would kill M5.
  Probes on the fixed code: "" -> []; empty ndarray/Series -> []; generator, set, unknown stat,
  duplicates behave predictably; a bare string "pts" still splits into characters (pre-existing,
  not a regression, out of scope).

## Test commands (one file per process) and counts
| Command | Base 67a0801b | Head |
|---|---|---|
| python3 -m pytest tests/platformkit/improve/test_prop_line_distance_calib.py -q | 19 passed, 1 failed (test_empty_stats_list) | 20 passed |
| python3 -m pytest tests/platformkit/improve/test_prop_line_distance_calib_s631.py -q | absent (4 of 6 red against the base module) | 6 passed |
| python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q | 1 passed | 1 passed |
Total at head 27/27 = n 27 (CONSTRUCT). Mutations: M1 (`if stats`) -> existing
test_empty_stats_list + new 1, 2, 5, 6 red; M2 (`if True`) -> new 3 red (+ 6 existing, expected).

## NOT VERIFIED
- The Windows laptop / Python 3.10 re-run (the lander does this).
- Any run against the real data/cache/pregame_oof.parquet (absent from the clone; the new tests
  never read the default path, checked by instrumenting os.path.exists / read_parquet).
- Whole-suite effects (never run by rule).

Calibration reporting only.
