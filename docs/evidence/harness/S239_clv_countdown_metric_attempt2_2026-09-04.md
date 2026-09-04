# S239 CLV Countdown Metric, Attempt 2

Candidate verdict: ACCEPT. The reader-only countdown reproduces `UNDEFINED`
for the current stores and 98 for the predeclared construct. `UNDEFINED` is
the correct zero-rate calibration status, not a fabricated day count.

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a17` on worktree `track-a17` because
the two specified capture stores are local and this is a reader-only run. No
pod process or deployment was used.

The route is `scripts/platformkit/live_edge/clv/clv_countdown.py` (105 LOC,
SHA-256 `fb783adb2e23b83f94250dbfb9f18fe12f14a72fbd89e3460bd4548428600543`).
It reads only its two supplied paths; this attempt changed no route or capture
store.

## Sealed preregistration

Preregistration:
`docs/evidence/harness/S239_clv_countdown_prereg_attempt2_2026-09-04.md`.
Its standalone preregistration commit is
`59567cb8898f5ebf4bdb3df0240601197fa78e7f`.

Embedded and independently recomputed pre-seal SHA-256:
`4cdd7a5304229b35b0c65dc2bb0ddf04db26d27a4d58cd86861957d062d69e75`.
The committed-byte command `git show HEAD:<path> | head -n 56 | sha256sum`
returned that same value after the preregistration commit and before this run.

## Inputs and premise reproduction

Inputs were opened one at a time in the fresh Python process.

| input | full path | bytes | resolution | SHA-256 |
|---|---|---:|---|---|
| ledger | `C:\Users\neelj\nba-track-a17\data\frontend\clv_ledger.jsonl` | 18,584 | n/a JSONL | `f492d8fea427ac0e6ea2dada4b8a6dbfe3e092e81579305419b11f64f432c521` |
| status | `C:\Users\neelj\nba-track-a17\data\frontend\analytics\execution_status.json` | 947 | n/a JSON | `4029d6b0bf489fb8eecf9aa30517f9f78366711214aeb0cb0ea18698f1bf291f` |

All 20 ledger rows were classified: 2 legacy rows lack `bet_id`, 18 rows have
`bet_id` and `status=open`, 0 rows have `status=settled`, and 0 rows carry an
integrity flag. This is the requested 2 legacy / 18 open / 0 settled / 0
integrity-flags split; the `status` field itself is `open` on all 20 rows.
The status object reports `n_settled="INSUFFICIENT"` and
`row_classes.settled=0`.

The current register was re-read without modification: S32 is CLOSED; S20 is
OPEN with the frozen 200 settled / 2 sports / 7 days bar unmet; S18 is BLOCKED
on S20; S19's cadence bar is unexercised.

## ATTEMPT 2

| check | attempt 1 | attempt 2 |
|---|---|---|
| preregistration seal | mismatch; Q1 reject | committed bytes and working tree both `4cdd7a...d69e75` |
| current-store result | 0 / null / UNDEFINED | 0 / null / UNDEFINED |
| construct result | 4 / 2.0 / 98 | 4 / 2.0 / 98 |
| frozen bar | 200 / 2 sports / 7 days | unchanged: 200 / 2 sports / 7 days |
| verdict | REJECT only for Q1 | candidate ACCEPT |

The current-store output is:

```json
{
  "blockers": ["S20: week bar unmet", "S18: blocked on S20"],
  "days_to_first_reading": "UNDEFINED",
  "n_settled_today": 0,
  "settlement_rate_per_day": null
}
```

The construct has four settled rows over two dates, so its rate is 4 / 2 =
2.0 per day and `ceil((200 - 4) / 2.0) = 98`. The callback returned 98.
The full fresh-process output is
`docs/evidence/harness/S239_clv_countdown_attempt2_2026-09-04.json` and embeds
the new seal and preregistration commit.

## Contract self-check

- B1/B8/B9: all nonblank ledger rows are retained; there is no fitted
  comparison; the construct rate uses four settled observations over two dates.
- B2/B3/B4/B5/B6/B10: this attempt adds only evidence, changes no schema or
  threshold, has no gate or claim lifecycle, and had no deployment or retired
  route.
- B7/Q7: the two sealed arms are the exhaustive current/CONSTRUCT enumeration.
- Q1: the matching seal was committed before the fresh process opened either
  capture store.
- Q2/Q4/Q5/Q9: neither arm is a charged trial, OOS prediction, ahead result,
  or paired-loss comparison. `walk_forward` and `cpcv_evaluate` are not
  applicable; no manufactured predictive score is reported.
- Q3: the 200 / 2 sports / 7 days bar is unchanged.
- Q6: this evidence uses calibration language only.

Focused tests, run one at a time:

`python -m pytest tests/platformkit/live_edge/test_clv_countdown.py -q -p no:cacheprovider`

`2 passed in 0.40s`

`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider`

`1 passed in 0.62s`

## NOT VERIFIED

- No OOS predictive comparison exists; `walk_forward` and `cpcv_evaluate` are
  not applicable to these reader-only reproduction arms.
- No settlement-rate field exists beyond the dated settled history inspected.
- No future settled reading, multi-sport completion, seven-day completion,
  deployment, or live capture was verified.
- Independent verifier reproduction and register/ledger landing remain pending.

The evidence paths named above exist in this worktree at report time.
