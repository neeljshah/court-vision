# S74 Family Tier Filter -- 2026-09-04

Verdict: **NOT VALIDATED**. The isolated DB construct passes, but the T1 SCREEN producer is intentionally not wired to pass `screen_p`, so no live record exercises this API.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
## Step 0 -- premise re-measured (Q8)

`family_p_values` had one `family` argument, fresh `result` had no `screen_p`, and `tiers._EMPTY["raw_p"]` was `None`. The premise holds.
## Construct metric (n = 4, CONSTRUCT)

All four named rows are the denominator; none is omitted. `other` is the named negative control excluded by the `fam74` family filter.
| Construct row | Family | Tier | raw_p | screen_p |
|---|---|---|---:|---:|
| SCREEN | fam74 | T1 | null | 0.03 |
| charged one | fam74 | T2 | 0.10 | null |
| charged two | fam74 | T2 | 0.20 | null |
| negative control | other | T2 | 0.40 | null |

| Call | Before | After |
|---|---|---|
| `family_p_values("fam74")` | [0.10, 0.20] | [0.10, 0.20] |
| `family_p_values("fam74", tier="T1")` | TypeError; no column | [0.03] |
| `family_p_values("fam74", tier="T2")` | TypeError | [0.10, 0.20] |
Untiered SQL text/result are preserved. New databases declare `screen_p REAL`; opening a pre-S74 schema adds it. Direct SQLite read the four rows shown above.
## Verification

```text
python -m pytest tests/platformkit/foundry/test_results_db.py -q
22 passed in 3.16s
```
The single new test checks the column, all three lists, and direct SQLite rows; an independent legacy-schema reproduction reported `legacy_migrated=True`.
No bar moved: `family_bars.py`, the untiered charged-only default, `data/registry/**`, and `data/cache/eval_gate/backtest_fwer.jsonl` are untouched. No pod contact.

## B and Q self-check

B1 all rows named; B2 additive/readers grepped; B3-B4 no gate/claim change; B5 no deploy; B6 no move; B7-B8 n/a; B9 exhaustive denominator; B10 no threshold moved. Q1-Q2/Q4-Q5/Q9 n/a: no score or charge; Q3 no bar moved; Q6 calibration language only; Q7 exhaustive construct; Q8 re-measured premise.

## NOT VERIFIED

- `tiers.py` still archives T1 `screen_p` instead of passing it to `record()`; F1 owns that follow-on, so no live writer/caller uses `family_p_values(..., tier="T1")`.
- This is a worktree check; the verifier performs the master re-run after landing.
