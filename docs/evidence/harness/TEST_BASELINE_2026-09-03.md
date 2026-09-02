# Test-health baseline -- S-register landing verification

**Commit:** `e0eb96e12dd9746beac4a671ffd196f7624a955c` (`e0eb96e12`, branch `master`)
**Captured:** 2026-09-02 local, single sequential sweep, nothing else writing the repo.
**Interpreter:** `C:\Users\neelj\AppData\Local\Programs\Python\Python310\python.exe` (system Py3.10, not the
`basketball_ai` conda env).
**Command shape, every row, no exceptions:**

```
timeout 300 python -m pytest <one file> -q -p no:cacheprovider -rfE
```

Run from the repo root, one file at a time, never a directory and never the whole tree.
`-rfE` was added over the lane's shape purely to force the short failure summary into the log so the
first failing id could be read; it changes no verdict.

**Totals:** 53 files run - 42 GREEN - 10 RED - 0 TIMEOUT - 1 collects nothing - 1 ABSENT.

## Purpose

These are the pre-existing red/green states the S-register landings are verified against. A verifier
that finds one of the RED-LIST files failing has found nothing new: the file was already failing
before today's landing. This memo exists so no landing is rejected for a failure it did not cause.

---

## Results (RED first, then not-collected, then GREEN)

| File | passed | failed | skipped | secs | First failure |
|---|---|---|---|---|---|
| `scripts/platformkit/eval_gate/test_behind_is_not_blocked.py` | 0 | 0 (1 collect error) | 0 | 12 | collection ERROR -- `ModuleNotFoundError: No module named 'run_gate'` |
| `scripts/platformkit/eval_gate/test_freshness.py` | 0 | 0 (1 collect error) | 0 | 8 | collection ERROR -- `ModuleNotFoundError: No module named 'freshness_schema'` |
| `scripts/platformkit/eval_gate/test_gate.py` | 0 | 0 (1 collect error) | 0 | 4 | collection ERROR -- `ModuleNotFoundError: No module named 'run_gate'` |
| `scripts/platformkit/eval_gate/test_ingame_blend.py` | 0 | 0 (1 collect error) | 0 | 9 | collection ERROR -- `ModuleNotFoundError: No module named 'ingame_blend'` |
| `scripts/platformkit/eval_gate/test_ledger.py` | 0 | 0 (1 collect error) | 0 | 5 | collection ERROR -- `ModuleNotFoundError: No module named 'ledger'` |
| `scripts/platformkit/eval_gate/test_shin.py` | 0 | 0 (1 collect error) | 0 | 5 | collection ERROR -- `ModuleNotFoundError: No module named 'shin'` |
| `scripts/platformkit/eval_gate/test_walkforward.py` | 0 | 0 (1 collect error) | 0 | 5 | collection ERROR -- `ModuleNotFoundError: No module named 'walkforward'` |
| `tests/platformkit/ingame/test_inplay_capture_loop.py` | 51 | 10 | 0 | 131 | `::test_one_cycle_captures_pair_with_prior_and_paper_decides` -- `assert (False is True)` on the decision field |
| `tests/platformkit/mcp_server/test_server.py` | 7 | 1 | 0 | 138 | `::test_ask_no_data_backfills_source_artifact` -- `subprocess.TimeoutExpired: ... '-m', 'scripts.platformkit.mcp_server.server' timed out after 120 seconds` |
| `tests/platformkit/test_scoreboard.py` | 24 | 2 | 0 | 11 | `::test_settled_no_close_excluded_from_clv_count` -- `assert 2 == 0` |
| `scripts/platformkit/eval_gate/dm_test.py` | 0 | 0 | 0 | 4 | collects nothing -- see "Not a test file" below |
| `scripts/platformkit/combo/test_run_nba_teamadv_stack_v1.py` | 12 | 0 | 0 | 25 | -- |
| `scripts/platformkit/eval_gate/test_backtest_runner.py` | 2 | 0 | 0 | 7 | -- |
| `scripts/platformkit/eval_gate/test_combo_search.py` | 2 | 0 | 0 | 11 | -- |
| `scripts/platformkit/eval_gate/test_cpcv_engine.py` | 5 | 0 | 0 | 7 | -- |
| `scripts/platformkit/eval_gate/test_deflated_metrics.py` | 20 | 0 | 0 | 7 | -- |
| `scripts/platformkit/eval_gate/test_eval_core.py` | 16 | 0 | 0 | 8 | -- |
| `scripts/platformkit/eval_gate/test_false_discovery.py` | 1 | 0 | 0 | 5 | -- |
| `scripts/platformkit/eval_gate/test_gate_manifest.py` | 14 | 0 | 0 | 4 | -- |
| `scripts/platformkit/eval_gate/test_leak_contract.py` | 6 | 0 | 0 | 4 | -- |
| `scripts/platformkit/eval_gate/test_null_ship_calibration.py` | 4 | 0 | 0 | 8 | -- |
| `scripts/platformkit/eval_gate/test_pbo.py` | 15 | 0 | 0 | 7 | -- |
| `scripts/platformkit/eval_gate/test_redteam2.py` | 7 | 0 | 0 | 18 | -- |
| `scripts/platformkit/eval_gate/test_retro_correction.py` | 1 | 0 | 0 | 5 | -- |
| `scripts/platformkit/eval_gate/test_romano_wolf.py` | 4 | 0 | 0 | 5 | -- |
| `scripts/platformkit/eval_gate/test_spa_test.py` | 4 | 0 | 0 | 8 | -- |
| `scripts/platformkit/execution/test_book_replay.py` | 11 | 0 | 0 | 7 | -- |
| `scripts/platformkit/execution/test_smoke_e2e.py` | 3 | 0 | 0 | 10 | -- |
| `scripts/platformkit/execution/test_venue_fees.py` | 29 | 0 | 0 | 4 | -- |
| `scripts/platformkit/ingame/test_arm_evaluation.py` | 1 | 0 | 0 | 24 | -- |
| `scripts/platformkit/ingame/test_arm_registry.py` | 2 | 0 | 0 | 24 | -- |
| `scripts/platformkit/ingame/test_forward_evidence_scoreboard.py` | 13 | 0 | 0 | 24 | -- |
| `scripts/platformkit/ingame/test_gap_effective_n.py` | 3 | 0 | 0 | 18 | -- |
| `scripts/platformkit/ingame/test_hedge_combiner.py` | 19 | 0 | 0 | 25 | -- |
| `scripts/platformkit/ingame/test_mlb_book_capture.py` | 8 | 0 | 0 | 17 | -- |
| `scripts/platformkit/ingame/test_quote_freshness.py` | 15 | 0 | 0 | 9 | -- |
| `scripts/platformkit/test_hedge_trial_arms.py` | 6 | 0 | 0 | 18 | -- |
| `tests/platformkit/execution/test_circuit_breaker.py` | 11 | 0 | 0 | 11 | -- |
| `tests/platformkit/execution/test_exec_quality_daemon.py` | 7 | 0 | 0 | 5 | -- |
| `tests/platformkit/execution/test_expected_clv_gate.py` | 7 | 0 | 0 | 11 | -- |
| `tests/platformkit/execution/test_sizing.py` | 7 | 0 | 0 | 11 | -- |
| `tests/platformkit/execution/test_writer_identity.py` | 5 | 0 | 0 | 13 | -- |
| `tests/platformkit/ingame/test_inplay_breaker.py` | 6 | 0 | 0 | 17 | -- |
| `tests/platformkit/ingame/test_inplay_capture_runner.py` | 5 | 0 | 0 | 88 | -- |
| `tests/platformkit/ingame/test_inplay_daytrader.py` | 41 | 0 | 0 | 68 | -- |
| `tests/platformkit/ingame/test_latency_scoreboard.py` | 5 | 0 | 0 | 8 | -- |
| `tests/platformkit/ingame/test_maker_only_wiring.py` | 12 | 0 | 0 | 10 | -- |
| `tests/platformkit/ingame/test_prospective_scoreboard.py` | 8 | 0 | 0 | 19 | -- |
| `tests/platformkit/mcp_server/test_artifact_tools.py` | 5 | 0 | 0 | 23 | -- |
| `tests/platformkit/test_clv_honesty.py` | 6 | 0 | 0 | 7 | -- |
| `tests/platformkit/test_eval_gate_ledger_drift.py` | 9 | 0 | 0 | 7 | -- |
| `tests/platformkit/test_grade_paper_close.py` | 18 | 0 | 0 | 10 | -- |
| `tests/platformkit/test_mcp_http.py` | 4 | 0 | 0 | 15 | -- |

Total measured wall time across the 53 files: 964 s. No file reached the 300 s cap.

### ABSENT

- `scripts/platformkit/eval_gate/test_dm_test.py` -- **does not exist.** The module
  `scripts/platformkit/eval_gate/dm_test.py` (the Diebold-Mariano implementation) exists but has no
  test file beside it. Do not read this as a red.

### Not a test file

`scripts/platformkit/eval_gate/dm_test.py` was run in place of the absent test file and collected
zero tests (`no tests ran in 0.71s`, exit 5). `pytest.ini` sets `python_files = test_*.py`, so the
default `*_test.py` pattern is off and this module is never collected by any run. It is a module,
not a test.

### `tests/platformkit/pm_trading/`

Directory exists and contains only `__init__.py`. There are no test files under it, so nothing was
run. Recorded as ABSENT rather than green.

---

## RED LIST

**These ten files are pre-existing red as of commit `e0eb96e12dd9746beac4a671ffd196f7624a955c`. A
landing that touches none of their modules must not be rejected for them.** They were red before any
S-register work landed today and their failure carries no information about a new landing. A verifier
who sees one of these fail should confirm the failure signature matches the one recorded above and
then move on; only a *changed* signature, or a red in a file this memo records as GREEN, is evidence
against a landing.

The ten split into two groups with very different meanings.

**Group 1 -- seven collection-time import failures in `scripts/platformkit/eval_gate/`, measured as
invocation-shape, not module breakage.** `test_walkforward`, `test_ledger`, `test_shin`, `test_gate`,
`test_freshness`, `test_ingame_blend`, and `test_behind_is_not_blocked` all import their module under
test by bare sibling name (`from walkforward import walk_forward, assert_vintage`) rather than by the
fully-qualified path (`from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate`) that
every GREEN file in the same directory uses. Because `scripts/`, `scripts/platformkit/` and
`scripts/platformkit/eval_gate/` all carry `__init__.py`, pytest's prepend import mode walks up to
the repo root and puts *that* on `sys.path`, never the `eval_gate` directory -- so the bare name
cannot resolve and collection aborts before a single test runs. This was confirmed, not assumed: with
the directory on `PYTHONPATH` all seven pass outright, measured this session --

```
PYTHONPATH=C:/Users/neelj/nba-ai-system/scripts/platformkit/eval_gate \
  python -m pytest scripts/platformkit/eval_gate/<file> -q -p no:cacheprovider
```

`test_walkforward` 6 passed - `test_ledger` 5 passed - `test_shin` 5 passed - `test_gate` 7 passed -
`test_freshness` 6 passed - `test_ingame_blend` 4 passed - `test_behind_is_not_blocked` 11 passed.

The consequence for verification is the load-bearing part: **under the canonical command shape these
seven assert nothing at all.** A landing that changes `walkforward.py`, `ledger.py`, `shin.py`,
`run_gate.py`, `freshness_schema.py` or `ingame_blend.py` will not be caught by them, and a verifier
must not read their red as a signal either way. Note that `docs/evidence/tracking/specs/S13_spec.md`
instructs a future landing to rerun `test_ledger.py` and requires it to "stay green" -- it is not
green under the canonical shape today, and that instruction cannot be satisfied as written until the
import style is fixed or the invocation carries `PYTHONPATH`.

**Group 2 -- three genuine failures with real assertions running.**
`tests/platformkit/ingame/test_inplay_capture_loop.py` (51 passed, 10 failed) fails a connected block
of ten: the capture cycle's decision field comes back `False` where the fixtures expect `True`
(`assert (False is True)`), and the nine that follow -- the WNBA shadow pair, the NBA ladder shadow
pair, the two enrichment none-safe cases, the MLB identity case, the heartbeat pacing counters and
the shadow-history poisoned-module case -- all assert that same decision is unchanged, so they fall
with it. Treat these ten as one defect, not ten.
`tests/platformkit/mcp_server/test_server.py` (7 passed, 1 failed) fails only
`test_ask_no_data_backfills_source_artifact`, and it fails on a 120 s `subprocess.TimeoutExpired`
launching `python -m scripts.platformkit.mcp_server.server` -- a subprocess that does not come up in
time, which makes this the one red in the list most likely to be environment-sensitive rather than
deterministic. `tests/platformkit/test_scoreboard.py` (24 passed, 2 failed) fails
`test_settled_no_close_excluded_from_clv_count` (`assert 2 == 0`) and
`test_n_settled_counts_only_clv_rows` (`assert 3 == 2`) -- both count settled rows against the
CLV-row denominator, so both are the same counting question.

## Human-gated imports at collection time

One, and it is guarded. `scripts/platformkit/eval_gate/scoring.py` line 39 executes
`from kernel.validation.proof_metrics import brier as _k_brier, ece as _k_ece` at module scope,
inside a `try:` whose `except Exception:` falls back to a self-contained numpy implementation. It
therefore reads the human-gated `kernel/` tree at import time but tolerates its absence, and it
reaches the sweep through `test_eval_core.py` (direct) and through `backtest_runner.py`, `baseline.py`,
`run_gate.py` and `student_gate.py`. The verification consequence: a landing that changes
`kernel/validation/proof_metrics.py` can move the Brier and ECE numbers these eval_gate tests compute
without touching `scripts/platformkit/` at all, and the `except Exception` means a *break* in that
kernel module degrades silently to the fallback rather than erroring. That is the one cross-tree
coupling in this file set.

No other file in the swept set imports `src/`, `kernel/`, `api/` or `intel/` -- checked both at
module scope in the 53 test files and one hop out across the 39 `scripts.platformkit.*` modules they
import.

## NOT VERIFIED

- Whether any of the ten reds is **flaky**. Each file was run exactly once; no repeat run was done,
  so a red recorded here could be intermittent. `test_server.py`'s 120 s subprocess timeout is the
  most likely candidate and the single-run evidence cannot separate a real hang from a slow box.
- Whether the reds are **older than this commit**. The baseline is a point measurement at
  `e0eb96e12`; no history was walked, so "pre-existing" here means "present before today's landings",
  not "present since a named commit".
- Whether these files behave the same under the **`basketball_ai` conda env**. The sweep ran on the
  system Py3.10 interpreter shown above; the conda env was not exercised.
- Whether the 42 GREEN files are green in **any other order**. Each ran in a fresh interpreter, one
  file per process, so cross-file interference was not tested in either direction.
- Whether the ten `test_inplay_capture_loop` failures are truly **one defect**. They share an
  assertion shape and a fixture path, which is why they are grouped, but no root cause was traced.
- Transitive imports beyond **one hop** from the test files. A gated-tree import two or more hops
  deep would not have been seen by the scan described above.
