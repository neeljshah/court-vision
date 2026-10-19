# S670 cloud result -- 2026-09-30 (desk-improve one-off, Opus, Ubuntu cloud clone)

Row: S670 (series-trust gate; QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2, override section 3a).
Branch: `cloud/S670-2026-09-30` from trunk 89218a73 (the row text depends on S669's receipt as an
INPUT shape only; it does not need S666's modules, so the base is trunk, not cloud/S666). exec_policy_stats.py
reused read-only (FLOOR_PAIRED, DRAWS, SEED, MISSING_MAX imported; file byte-identical to trunk).
Spec: docs/evidence/harness/S670_spec_2026-09-30.md (body + AMENDMENT 1 critic + AMENDMENT 2 builder +
AMENDMENT 3 fix pass). Register row and DESK_STATE.md NOT edited on this branch (override).
Execution-quality and calibration language only. TRUSTED is a measurement-trust state, never a claim
about the market; an INSUFFICIENT or NULL series is a valid result.

Codex is not available in the cloud box: every review role below was an INDEPENDENT Opus sub-agent
(Agent tool, fresh context, did not build the code), not a codex run.

## Verdicts

| Tier | Commit | Agent | Verdict |
|---|---|---|---|
| Pre-build critique (astra) | spec only | independent Opus sub-agent | REVISE, 15 items -> all folded as AMENDMENT 1 |
| CONTRACT (A, B1-B10, Q1-Q9 + spec) | 593618d6 | independent Opus sub-agent | ACCEPT WITH CORRECTIONS |
| ADVERSARIAL (probes, mutants) | 593618d6 | independent Opus sub-agent | REJECT (false TRUSTED on float overflow; see below) |
| CONTRACT re-check | 71183b36 | independent Opus sub-agent (new) | ACCEPT WITH CORRECTIONS (only correction: this memo, A7) |
| ADVERSARIAL re-verify (final attempt) | 71183b36 | independent Opus sub-agent (new) | ACCEPT WITH CORRECTIONS (2 corrections, applied as AMENDMENT 4) |



Final ADVERSARIAL tier (71183b36): 19 mutants, 16 killed, 3 survived. The three survivors were the
fills-floor `<` -> `<=` and the two non-finite guards, each redundant with the other; with both guards
dropped together the false TRUSTED returned. Every earlier probe is fixed, and no probe produced a false
TRUSTED on the shipped code. Its two corrections are applied in the final commit (spec AMENDMENT 4):
- decimal.Overflow (unmarked_qty "1e1000000") now raises ValueError (G1).
- New tests G2 ("1e308" sums overflow to inf -> NULL, which kills the combined mutant) and G3 (fills exactly
  at a raised floor are eligible, which kills the `<=` mutant).
No re-verify was needed: the change is one exception class in the wrapper plus tests, the same practice
as S642.

First ADVERSARIAL REJECT (593618d6), fixed in 71183b36 (AMENDMENT 3):
- `net_sum` / `marked_qty` = "1e400" was Decimal-finite but float-infinite; the bootstrap lower bound became
  NaN, `nan <= floor` is False, and a corpus with a negative markout read TRUSTED. Now a ValueError at parse,
  and a non-finite lower bound fails both the interval and the LOO check.
- "1e-400" marked_qty -> ZeroDivisionError; malformed shapes -> KeyError / TypeError / AttributeError. Now
  all ValueError.
- A missing `unmarked_qty` defaulted to 0 and a missing `h` block read as unpaired (B1: missing marks read
  as clean). Now INSUFFICIENT MARKS_UNKNOWN.
- A "night/game_id" string key could collide on "/". Keys are now the tuple.
- Float-typed draws / seed / ci_index loaded. Now refused.
- Nine surviving mutants (floor equality, rounded compare, shared rng across LOO, state precedence,
  missing share == 0.2, input sort, qty/fills consistency) are now killed by test_series_gate_fix.py.

## What was built (new files only)

- `scripts/platformkit/execution/series_gate.py` (275 lines): load_config (hash + never-lower checks),
  a fill-weighted game-cluster bootstrap (the same draw sequence as exec_policy_stats.boot, fresh
  Random(7), 5,000 draws, ci90 = sorted [250], [4749]), a leave-one-game-out bootstrap check, and the
  per-corpus and series states, plus an evaluate() / dumps() / `--input` CLI. Output is canonical ASCII JSON.
- `scripts/platformkit/execution/series_gate_config.json`: DECLARED floors. min_paired_games 30,
  min_marked_fills 30, min_corpora 2 (the both-corpora rule), floor_points "0", horizons 10 / 60 / settle,
  draws 5000, seed 7, ci_index [250, 4749], missing_max "0.2". sha256
  34d22d38e88f03ddecaef9102f9f618f1012c22e0c8d8f74b6fe3fde55cd1f1d. load_config refuses a hash mismatch and
  any floor below the code minimums, even when the hash has been recomputed. Nothing was tuned on any
  window.
- `tests/platformkit/execution/test_series_gate.py` (C1-C13, 34 cases) and `test_series_gate_fix.py`
  (F1-F8 + G1-G3, 18 cases).

Row acceptance, both met on construct fixtures:
- A 7-game corpus reads INSUFFICIENT whatever the mean (C1, +50 and -50 points).
- In C3, one game (g00, markout 8) lifts a 40-game corpus. The full ci90 lower bound (0.038) clears the
  floor, but the bound without g00 (-0.038) does not, so the corpus reads NULL LOO_FLIP:60:2026-09-29/g00.
  With LOO monkeypatched out, the same fixture reads TRUSTED.

## Tests (one file per process, `python3 -m pytest <file> -q`, branch head)

| File | Result |
|---|---|
| tests/platformkit/execution/test_series_gate.py | 34 passed (~53 s) |
| tests/platformkit/execution/test_series_gate_fix.py | 18 passed (~33 s); the F-cases on 593618d6: 11 failed, 4 passed |
| tests/platformkit/test_loc_rail_scope.py | 1 passed |
| tests/platformkit/execution/test_s551_replay.py (exec_policy_stats reader) | 14 passed (CONTRACT tier) |
| tests/platformkit/execution/test_s551_cancel_policy.py | 20 passed (CONTRACT tier) |
| tests/platformkit/execution/test_s551_prereg_report.py | 9 passed, 1 failed: test_seal_record_pins_base_blobs needs seal base commit 4b966112, which the shallow cloud clone lacks (environment; the file is unchanged) |

On trunk, both new files fail at import (the module is absent).

## S669 interface (what S669's receipt must emit for this gate)

This is the per corpus, per game input:

    {night, game_id,
     h: {"10"|"60"|"settle": {marked_qty, net_sum, marked_fills, unmarked_qty}},
     peak_abs_inventory, inventory_bound, fault_trips: [{kind, explained: true|false}]}

- net_sum is sum(qty * fee-inclusive net markout per contract), in price points (exec_policy_stats'
  unit), stored as decimal strings. The keys carry no currency word.
- inventory_bound comes from S667's limit table (its hash goes in S669's sidecar).
- `explained` is a NEW field S669 must add to each breaker trip.
- Missing evidence reads INSUFFICIENT, never a breach.
- The output's per-game `series` stores the printed key "night/game_id" with net_sum and marked_qty, so
  every ci90 and LOO bound can be recomputed from the artifact alone (Q9).

## NOT VERIFIED

- Any real series. The clone has no data/ and there are no archived paper_account receipts, so every
  result above is on construct fixtures.
- The S669 receipt emitter (not built) and any wiring into a runner. The gate has zero callers.
- Runtime on real sizes. LOO costs O(n^2 x 5,000); the adversarial tier measured 96.6 s for 2 corpora x 200
  games on one horizon.
- test_s551_prereg_report.py::test_seal_record_pins_base_blobs on a full clone (laptop).
- The Windows / Py3.10 re-run by the landing session.

PORTABLE: yes (code and construct tests). Landing is by a laptop session. After landing,
series_gate_config.json joins the must-not-move list.

## NEW GAP candidates (for the orchestrator; ids are not allocated here)

- The declared min_marked_fills 30 cannot bind at min_paired_games 30, because each paired game has at
  least 1 fill. The owner should declare a binding fills floor by amendment. It must never be lowered.
- LOO runtime is O(n^2 x draws). Before real series arrive, set a budget or an exact early exit.
- A den sum that overflows float (marked_qty "1e308" on 3 games) gives NULL, which is conservative, but
  mean NaN then makes dumps() raise, so the CLI crashes instead of printing NULL.
- unmarked_qty "9e999999" on two games raises decimal.Overflow out of evaluate(). The docstring promises a
  ValueError.
- The F4 assertion `state in (TRUSTED, NULL)` is loose after the "/" key edit.
- test_s551_prereg_report.py should skip when its seal base commit is absent (shallow clones).
- (final ADVERSARIAL) "h": {} or an absent horizon key drops a game from h without naming it (allowed by
  A1.5). 4 games at net -500 with h {} turned NULL into TRUSTED (32 of 36 paired). A per-game
  expected-horizon count is needed.
- (final ADVERSARIAL) The missing-share check runs in 28-digit Decimal and can round 0.2 + 1.6e-29 down to
  0.2, which passes.
- (final ADVERSARIAL) Under a raised floor such as "0.1", the float floor compare (A1.8) passes lower ==
  floor, because 0.1 is not exact in float.
- (final ADVERSARIAL) The overlap check does not normalise keys: whitespace, case and NFC/NFD variants of
  the same game are not caught. The printed "night/game_id" is also ambiguous.
- (final ADVERSARIAL) Decimal accepts non-ASCII digits through evaluate(); only the CLI enforces ASCII
  input.
