# S239 CLV Countdown Metric

Verdict: ACCEPT. The dashboard reader now makes the first real
match-the-close calibration reading's countdown explicit. On the current
capture stores, the result is `UNDEFINED`, not a fabricated date.

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a17` (worktree `a17`) because both
specified capture stores are local and the work is reader-only. No pod process
or deployment was used.

The additive route is
`scripts/platformkit/live_edge/clv/clv_countdown.py` (87 LOC, SHA-256
`FB783ADB2E23B83F94250DBFB9F18FE12F14A72FBD89E3460BD4548428600543`). It reads
only the two supplied paths and changes neither capture store.

## Sealed preregistration

Preregistration:
`docs/evidence/harness/S239_clv_countdown_prereg_2026-09-04.md`.

Pre-seal SHA-256:
`9ADC5D5833C62DD594020A7EE021DC9B6559926B808E6251BC3D3C07934A1691`.

The seal was written before either capture store was opened. Its fixed two-case
method and unchanged bar are 200 settled observations, at least 2 sports, and
at least 7 days.

## Inputs and premise reproduction

Inputs opened one at a time:

| input | full path | bytes | resolution | SHA-256 |
|---|---|---:|---|---|
| ledger | `C:\Users\neelj\nba-track-a17\data\frontend\clv_ledger.jsonl` | 18,584 | n/a, JSONL | `F492D8FEA427AC0E6EA2DADA4B8A6DBFE3E092E81579305419B11F64F432C521` |
| status | `C:\Users\neelj\nba-track-a17\data\frontend\analytics\execution_status.json` | 947 | n/a, JSON | `4029D6B0BF489FB8EECF9AA30517F9F78366711214AEB0CB0EA18698F1BF291F` |

The ledger has 20 rows, all `status=open`; it has no settled dated history. The
status object reports `n_settled="INSUFFICIENT"` and
`row_classes.settled=0`. The register was read without modification: S32 is
CLOSED; S20 is OPEN with its 200 / 2 sports / 7 days week bar unmet; S18 is
BLOCKED on S20. S19's cadence bar remains unexercised. A `git grep` on `HEAD`
found the proposed countdown only in the S239 spec, not an existing route or
evidence artifact.

## Results

The committed result dict is
`docs/evidence/harness/S239_clv_countdown_2026-09-04.json`:

```json
{
  "blockers": ["S20: week bar unmet", "S18: blocked on S20"],
  "days_to_first_reading": "UNDEFINED",
  "n_settled_today": 0,
  "settlement_rate_per_day": null
}
```

The construct fixture contains four settled rows across two settlement dates.
It therefore has a rate of 4 / 2 = 2.0 per day; with four settled rows, the
unchanged calculation is `ceil((200 - 4) / 2.0) = 98`. The function returned
98 exactly.

## Reproduction and contract self-check

Test command: `python -m pytest tests/platformkit/live_edge/test_clv_countdown.py -q`

Result: `2 passed in 0.55s`.

- B1/B8/B9: no rows are excluded from the named count and there is no fitted
  comparison; the denominator is the named settled-row count.
- B2/B3/B4/B5/B6/B10: the change is an additive read-only module, no existing
  schema or threshold changed, no item is gated or claimed, and no deployment
  occurred.
- B7 and Q7: the two preregistered cases are exhaustive CONSTRUCT/current
  reproduction cases; no render or head-slice sampling applies.
- Q1: the preregistration path and pre-seal SHA-256 above predate measurement.
- Q2/Q4/Q5/Q9: no charged trial, out-of-sample comparison, ahead claim, or
  paired-loss comparison is present. `walk_forward` and `cpcv_evaluate` are
  therefore not applicable.
- Q3: the 200 / 2 sports / 7 days bar is unchanged.
- Q6: this memo reports calibration status only.

The evidence paths named here exist in this worktree at report time.
