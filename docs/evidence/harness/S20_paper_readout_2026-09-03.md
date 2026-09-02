# S20 paper readout evidence -- 2026-09-03

## Premise

Before the change, `scripts/platformkit/pm_trading/clv_daily_readout.py` and
`data/frontend/analytics/execution_status.json` were absent. `DEFAULT_LEDGER`
exists at `data/frontend/clv_ledger.jsonl`; its safe reader returned 20 rows,
all open, with zero settled rows.

## Reproduction

`python -m pytest tests/platformkit/execution/test_paper_week_rollup.py -q`
reported `4 passed in 0.59s`.

The four exhaustive construct cases are: a 24-row, two-sport, eight-day maker
series; empty and absent ledgers; a result-without-outcome integrity row; and a
gross legacy row. The real local run was:

`python -m scripts.platformkit.pm_trading.clv_daily_readout`

## Day-zero readout

| source_artifact | as_of | status | n_settled | median_clv_units | verdict |
|---|---|---|---:|---|---|
| `C:/Users/neelj/nba-track-a15/data/frontend/clv_ledger.jsonl` | `2026-09-03T00:00:00+00:00 (no rows)` | `no_data` | `INSUFFICIENT` | `INSUFFICIENT` | `INSUFFICIENT` |

The consumer artifact is `data/frontend/analytics/execution_status.json`; the
daily table is `docs/evidence/execution/PAPER_LIVE_2026-09-03.md`.

## Contract self-check

| item | result | check |
|---|---|---|
| B1 | PASS | Every input row has one named class; no class is removed from a measure. |
| B2 | PASS | Additive new module, test, and artifacts only. |
| B3 | PASS | Missing ledger returns a no-data envelope rather than an exception. |
| B4 | PASS | The write is a daily append and does not create a new claim path. |
| B5 | PASS | No remote copy occurred. |
| B6 | PASS | New module has its direct `-m` path and one focused test. |
| B7 | PASS | The construct enumerates all four specified cases. |
| B8 | PASS | No fitted comparison is reported. |
| B9 | PASS | Counts are distinct ledger rows, classified once. |
| B10 | PASS | No existing bar or threshold was changed. |
| Q1 | PASS | No scored comparison is reported. |
| Q2 | PASS | No charge or ledger write occurs. |
| Q3 | PASS | The stated minimum is eight settled rows. |
| Q4 | PASS | No out-of-sample measure is reported. |
| Q5 | PASS | Day zero is INSUFFICIENT, not AHEAD. |
| Q6 | PASS | CLV series language and fields are units-only. |
| Q7 | PASS | `n = 4 (CONSTRUCT)` enumerates the acceptance cases. |
| Q8 | PASS | The absent-module and absent-consumer-artifact premise was remeasured first. |

## NOT VERIFIED

- A settled-row weekly series has not accrued locally.
- Capture cadence rows have not been supplied to the readout.
- The orchestrator's pod launch and keeper decision is outside this change.
