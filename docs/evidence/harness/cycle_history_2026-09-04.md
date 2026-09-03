# S186 Cycle History

This memo follows [the verifier contract](../tracking/VERIFIER_CONTRACT.md), sections B and Q for the S-row.

## ATTEMPT 2

Verdict: ACCEPT.

The earlier FALSIFIED statement is replaced. The now-visible premise store was measured without exclusions: 34 files (mlb 9, tennis 13, wnba 12), 24,612 rows, 24,612 exact-unique rows, and 0 rows with `no_live_state`, `bridge_date_mismatch`, or an `error:` reason. The spec-order reason vector is `[13733, 5135, 3694, 1027, 724, 245, 37, 17]`.

The overwritten heartbeat was also remeasured: 866 bytes, 18 keys, `as_of=2026-09-02T22:04:36Z`, `n_live=0`, `n_pairs=0`, and `grade_write_fail_by_reason={"no_live_state":1}`. `poll_once` already constructs every required counter and failure map. The heartbeat writer and its key/value construction were not changed.

`scripts/platformkit/ingame/cycle_history.py` appends one compact, size-bounded JSON record per completed tick to `data/cache/ingame_cycle_history/<date>.jsonl`. The call is inside the existing fail-open shadow-history block. When a temporary heartbeat is injected, its parent also supplies the temporary cycle-history directory; the reproduction never writes the live store.

| Measurement | Before | After |
| --- | --- | --- |
| Persistent driven cycles | 0 of 30 | 30 of 30 |
| Denominator | Every offline-driven cycle, none sampled or dropped | Every offline-driven cycle, none sampled or dropped |
| Required fields per retained row | Not retained after the next heartbeat replace | `ts`, all six counters, and the full failure-reason map |
| Cycle 1 `no_live_state` after cycle 30 | Not readable | Readable as 1 |

The reproduction ran `serve_forever(max_ticks=30, clock=<no-op>, heartbeat_path=<tmp>)` with injected live-state, model, and in-play fetch functions. It made no network request and no real sleep. Each tick supplied one liquid two-leg game whose bridge had no live state, so every row retained the full `{"no_live_state":1}` map. The focused test collected and ran: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/ingame/test_cycle_history.py -q` -> `1 passed`.

Scope: `no_home_leg` and `error:*` are set after the shadow block, so their absence in the existing shadow store is empirical. Only `no_live_state` and `bridge_date_mismatch` are unrecordable by construction there.

### 30 appended temporary records

```jsonl
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
{"cycle_duration_sec":0.0,"grade_write_fail_by_reason":{"no_live_state":1},"n_429_total":0,"n_bets":0,"n_live":0,"n_pairs":0,"n_requests_total":0,"ts":"2026-09-03T19:05:32Z"}
```

## NOT VERIFIED

- Live-daemon writes are not exercised; only the required offline temporary reproduction ran.
- No deployment or register/ledger action was performed.

## Verifier self-check

- B1: every premise and reproduction row is counted; no row was excluded.
- B2: the history file is additive; existing heartbeat fields and readers are unchanged.
- B3: the new append is observability only and fail-open.
- B4: no claim lifecycle changed.
- B5: no deployment occurred.
- B6: no module was moved or retired; the new test imports its package path.
- B7: Q7 replaces visual sampling with the complete 30-cycle reproduction.
- B8: no fitted residual is presented.
- B9: the denominator is every independently driven cycle.
- B10: the 30 of 30 bar is unchanged.
- Q1, Q2, Q4, Q5, Q9: no scored comparison, charged trial, or model comparison is presented.
- Q3: the acceptance bar is unchanged.
- Q6: calibration language only.
- Q7: the complete required reproduction ran, including its first retained record check after tick 30.
- Q8: the premise was remeasured before implementation and confirmed.
