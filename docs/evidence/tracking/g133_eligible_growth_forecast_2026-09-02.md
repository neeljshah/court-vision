# G133: tennis eligible-growth forecast

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including section A
(especially A7) and section B. Verdict: **NOT VALIDATED** for a time-to-10
forecast; the measured terminal rate and descriptive conversion are recorded.
This is a read-only snapshot. It changes no queue, bridge, cookie jar,
threshold, 10-table bar, coordinate contract, pod file, or pod process.

## Measurement window and units

The window is **2026-09-02T21:44:56Z to 2026-09-02T23:43:37Z**: 7,121
seconds, or **1.978056 hours**. The start is commit
`03a34eef84a599005d9fd785c8ea892528bff6a6`; the end is the read-only pod UTC
snapshot. A unit is one distinct tennis `game_id`, never a retry, frame, row,
or a repeated bridge-log line.

The per-identity timing evidence is
[post_repair_observations.csv](g133_forecast/post_repair_observations.csv).
The source of terminal time is the append-only pod ledger
`/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`; the two
included ledger rows are `tennis_06` at 22:22:22Z and `tennis_07` at
22:39:07Z. Their table write times corroborate the result. The bridge log and
bridge ledger are read-only sources in the main checkout, but neither records
per-event time. They therefore cannot establish a time-bounded local download
count.

## Pipeline rate

| Stage | Distinct count in window | Rate per hour | What the count means |
|---|---:|---:|---|
| Successful local acquisition | Not measurable | Not measurable | Neither the bridge log nor its JSONL ledger timestamps a download-complete event. Counting their 272 `staged` messages would recycle retries and include pre-repair work. |
| Directly timestamped pod stage | At least 1 | At least 0.506 | `tennis_08` was a 279,257,080-byte completed stage file at 23:38:38Z. The two terminal games must have staged earlier, but their stage time was not retained, so they are not silently added to this time-bounded count. |
| Terminal tracked | 2 | 1.011 | `tennis_06` and `tennis_07` are the only tennis ledger rows whose `finished_at` is at or after the repair time. This is the only complete, timestamped throughput measurement and is the rate that matters for growth. |

The derivation, numerator, denominator, and precision are in
[measurement_summary.csv](g133_forecast/measurement_summary.csv). The bridge
had a current staged-only `tennis_08` at the snapshot, so the observed stage
and terminal counts are not interchangeable.

## Conversion that reaches the jump statistic

Of the **2** distinct post-repair terminally tracked tennis games, **2/2
(100%)** reach the G107/G131 jump-statistic eligibility definition. This is
not a harness-pass rate: both terminal ledger rows are `passed=false`. It is
specifically the frozen jump-input test: at least 30 distinct frames, all rows
declared `court_feet`, usable player fields, and a unique positive modal
same-track stride.

[tracked_to_jump_gate.csv](g133_forecast/tracked_to_jump_gate.csv) preserves
the terminal fields beside G131's independent census rows, input hashes, and
modal-stride counts. G131's full census was at 23:36:56Z to 23:37:03Z and
listed both tables as `eligible_reaches_jump_statistic`; see
[current_jump_gate_census.json](g131_policy2/current_jump_gate_census.json).
No failed table is excluded from the terminal denominator: there were exactly
two terminal tennis rows in this time window.

## Time to ten

The current frozen eligible count is **8** ([G131](g131_jump_statistic_policy_attempt2_2026-09-02.md)), so two more tables are required. The deliberately conditional arithmetic is:

`2 tables needed / (2 eligible tables / 1.978056 h) = 1.978056 h`.

That is **not a forecast**. It assumes every future terminal game is a new
table, terminal throughput remains 1.011 per hour, the observed 2/2 conversion
persists, no source is overwritten or duplicated, and the current queue and
pod conditions remain unchanged. Two outcomes cannot estimate conversion or
the stage-to-terminal delay, and acquisition cannot be separately timed. The
honest result is therefore **forecast refused: n=2 is too small and the
upstream timing denominator is incomplete**.

## Levers, without changing them

1. **Refresh the tennis cookie (largest immediate acquisition lever).** The
   bridge records repeated tennis HTTP 403 download failures. A user-performed
   refresh could turn those blocked attempts into sources, but it costs a
   human credential refresh and does not establish that a source will track or
   reach the jump statistic.
2. **Add local memory or wait for running lanes to release it.** About 2.3 GB
   of 15.1 GB is free, so higher download parallelism is unsafe while the
   lanes run. More memory or an idle interval has hardware/opportunity cost;
   moreover, current pod staging demonstrates that acquisition alone is not a
   guarantee of faster terminal tracking.
3. **Do not treat the 3,600-second tennis duration floor as a speed lever.**
   It is already long. Reducing it would change the queue and could admit less
   useful source material; increasing it cannot make a finished source arrive
   sooner. G133 forbids either change.

## Bar versus corpus

The corpus should move before the bar. The fixed bar asks for ten independent
tables and the current census has eight; reducing it would make a policy
decision from an even smaller cross-table basis rather than repair the blocked
source flow. The post-repair snapshot supplies two encouraging eligible
outcomes but is far too short to show a stable route to two more. If a cookie
refresh and ordinary corpus growth still fail to produce timestamped new
terminal tables on a useful horizon, reconsidering the bar is an orchestrator
adjudication, not a lane action; this memo does not change it.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code or test was added, so no per-file test exists to run.
- **A2:** Recomputed from the two CSV artifacts: 7,121 seconds is 1.978056
  hours; `2 / (7121 / 3600) = 1.011094` terminal tables/hour; the two G131 rows
  both have `eligible_reaches_jump_statistic`.
- **A3:** Not applicable. This is an exhaustive two-row, timestamp-filtered
  terminal ledger measurement; no render or visual decision set exists.
- **A4:** Both artifacts contain two unique terminal `game_id` values.
  Bridge retries and rows/frames are never used as units.
- **A5:** Evidence only; no field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in `track-a5` only.
  It does not archive-land, append a results ledger/register row, deploy, or
  modify a pod.
- **A7:** Before commit/report, the named repository evidence paths were
  checked: this memo; all three `g133_forecast/` CSV files; G131; its census
  JSON; G109; G133 spec; and `VERIFIER_CONTRACT.md`. The external pod ledger,
  two terminal CSV paths, and staged file were also confirmed at the read-only
  snapshot time cited above.

### B

- **B1 CIRCULAR METRIC:** Clear. The terminal denominator is every tennis
  ledger row after the timestamp cutoff; eligibility is joined afterward, and
  the missing acquisition count is named rather than filtered away.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No schema, field, status, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Staged-only and untimeable acquisition
  evidence are explicit states, not failures or exclusions.
- **B4 RE-CLAIM LOOP:** Clear. No queue, claim, retry, or ownership behavior changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. Pod operations were read-only shell
  and Python reads; no file was copied, created, restarted, or killed.
- **B6 ORPHANS:** Clear. No module, import, command, or test was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The terminal measurement filters the
  complete ledger by sport and time; it is not a log head or tail slice.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. A unit is a unique game ID/table, not a
  repeated staging event, frame, or track ID.
- **B10 MOVED BAR:** Clear. No harness threshold, coordinate contract, or
  10-table bar changed.

## NOT VERIFIED

- The exact post-repair local acquisition or full staging rate: the bridge
  sources do not timestamp those events.
- A time-to-ten forecast or durable conversion rate: only two terminal games
  exist in the measured window.
- Whether staged-only `tennis_08` will finish, create a new table, or reach the
  jump statistic.
- Whether a cookie refresh, more memory, or any queue change would improve the
  terminal or eligible rate. None was performed.
- Any policy score, recommendation, threshold change, deployment, or pod
  process state beyond the one read-only snapshot.
