# S13 -- FWER ledger additive schema (2026-09-03)

VERDICT: ACCEPT (self-check). Schema is additive; the real ledger is byte-identical.

## Premise (step 0) -- CONFIRMED, not falsified

- `data/cache/eval_gate/backtest_fwer.jsonl` holds exactly **13 rows**.
- Key union across all 13: `['at', 'end', 'k_cumulative', 'predictor', 'sport', 'start']`.
  None of `family`, `k_family`, `hypothesis_hash`, `tier`, `prereg_sha256` exists. Before = 0/5 on 13/13.
- `_charge_ledger(path, spec, sport, start, end) -> dict` confirmed on disk at
  backtest_runner.py:131 with no family / hypothesis_hash / tier / prereg_sha256 parameter.
- `k_cumulative` sequence on disk is 1..13, one per row.

Pre-existing test state recorded BEFORE any edit:
- `test_ledger.py` -- **RED, collection ImportError** (`from ledger import ...`, no `scripts.` prefix;
  `ModuleNotFoundError: No module named 'ledger'`). Pre-existing, not caused by and not fixed by S13.
- `test_backtest_runner.py` -- 2 passed.

## Byte-identity of the real ledger (READ-ONLY throughout)

| when | sha256 | rows |
|------|--------|------|
| before | `52785ad273e24782dc7e94eeffbd47ed23c1a198d8a9d717e767d9947bb24cb7` | 13 |
| after  | `52785ad273e24782dc7e94eeffbd47ed23c1a198d8a9d717e767d9947bb24cb7` | 13 |

Identical. No `_charge_ledger` call against the real path anywhere in the new test -- every case
runs on a `shutil.copyfile` copy under `tmp_path`. This row is a schema change, not a charged trial.

## Change (additive only, contract B2)

- `ledger.py` (113 -> 149 LOC), APPEND-ONLY at the end; nothing above line 113 moved:
  `FWER_OPTIONAL_FIELDS`, `FWER_TIERS = ("T2", "T3")`, `load_fwer(path)` (fills the five absent keys
  with `None`), `next_k_family(rows, family)` (`1 + max(k_family of that family)`, first row = 1,
  no family -> `None`).
- `backtest_runner._charge_ledger` gains four KEYWORD-ONLY parameters (`family`, `hypothesis_hash`,
  `tier`, `prereg_sha256`, all default `None`) and writes them, plus the derived `k_family`, ONLY
  when not `None`. Unknown `tier` raises `ValueError` before the lock is taken. The inline row read
  is replaced by `load_fwer(path)` so writer and readers share one shape.
- `k_cumulative` is UNTOUCHED: same `cumulative_k(prior, 1)` call, same monotone global sequence.
  `combo/fwer_budget.py` was not opened. No threshold under `scripts/platformkit/eval_gate/` moved.
  No correction procedure changed -- that is S14 and it ships last.

## Callers of `_charge_ledger` (A5 -- every one grepped, zero call sites changed)

| caller | form | effect of S13 |
|--------|------|----------------|
| `eval_gate/backtest_runner.py:161` (`run_backtest`) | 5 positional | none -- keyword-only additions |
| `hedge_trial_runner.py:229` | 5 positional (lambda) | none |
| `eval_gate/student_gate.py:161` | 5 positional | none; it stores the whole row in its artifact, which for a legacy call is still the pre-S13 six keys |
| `eval_gate/test_redteam2.py:111` | 5 positional (concurrency test) | none; 7 passed after |

Readers of the ledger ROWS (all `.get()`-based, none asserts a closed key set):
`eval_gate/harness_health_report.py:119` `_fwer` (filters on `k_cumulative` / `at`),
`signals/foundry_run.py:173` and `analytics_showcase/mechanism_foundry.py:108` (read `k_cumulative`,
`dm_alpha` off the report), `mcp/test_gate_manifest_tool.py` and
`analytics_showcase/test_mechanism_wiring.py` (path/name only, no row keys).
`ledger.load` / `LedgerRow` read a DIFFERENT file (the prediction track-record JSONL, keys
`ts/sport/market/inputs_hash/prob/outcome`); no FWER row ever reaches it, so it needed no change.

## Test output

`scripts/platformkit/eval_gate/test_ledger_schema_s13.py` -- **5 passed in 9.02s**
(13 real rows load with k_cumulative unchanged; legacy charge writes exactly the six old keys;
k_family 1,2,1 across f1/f1/f2 with k_cumulative 1..16 monotone; all five fields round-trip;
`tier="T1"` raises and leaves the file byte-identical). n = 5 (CONSTRUCT) + the 13 real rows.

Pre-existing files re-run after the change, state UNCHANGED from step 0:
- `test_ledger.py` -- same collection ImportError (RED before, RED after, same message).
- `test_backtest_runner.py` -- 2 passed.

Downstream callers, run as an A5 safety check (not part of the bar):
`tests/platformkit/test_eval_gate_ledger_drift.py` 9 passed; `test_student_gate.py` 3 passed;
`test_redteam2.py` 7 passed.

## NOT VERIFIED

- `test_ledger.py` remains RED (pre-existing import-path defect). S13 neither caused nor fixed it;
  the module's `load`/`drift_report` behaviour is covered instead by
  `tests/platformkit/test_eval_gate_ledger_drift.py` (9 passed). Worth its own gap.
- No family has ever been charged in the real ledger, so `k_family` continuity across a genuine
  multi-day family is unexercised; only the tmp-copy construct cases prove the arithmetic.
- The spec on disk names the new test `test_ledger_schema_fields.py`; this lane's work order named
  `test_ledger_schema_s13.py` and that is the file that exists. Same content, different name.
- Concurrency of `k_family` under `ledger_lock` is not separately measured; it inherits the same
  lock as `k_cumulative`, whose concurrent behaviour `test_redteam2.py` covers.
- On a clean clone `data/` is absent and all five cases SKIP -- the bar is only measurable where
  the real 13-row ledger exists.

## Addendum (append-only, after the S13 commit 6a70efcba)

A sixth reader landed after this memo was committed: `eval_gate/ledger_backup.py` (S29, commit
a9a3a74a0). It opens the ledger `"rb"` for its sha256 and otherwise does
`json.loads(line).get("k_cumulative")` on one key only -- tolerant of the five optional keys, and it
never calls `_charge_ledger`. No S13 change is needed for it. Re-checked against current master:
`backtest_fwer.jsonl` still sha256 `52785ad2...7bb24cb7` at 13 rows, and
`test_ledger_schema_s13.py` still 5 passed (8.28s).
