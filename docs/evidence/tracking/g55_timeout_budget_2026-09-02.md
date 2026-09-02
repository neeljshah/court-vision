# G55 - daemon timeout verdict and budget measurement

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, section B.

## Pod ledger reproduction

The spec path `/workspace/track_daemon_ledger.jsonl` is absent. The real
readable pod ledger is `/workspace/nba-ai-system/data/tracking/track_daemon_ledger.jsonl`.
It contains 397 JSONL rows; all were read. No pod file was copied or changed,
no daemon was restarted, and no process was killed.

Lines 152-155 and 185, 189, 196, and 200 reproduce the eight 2700-second
tennis kills, all `rows=0`: tennis_06 2711 and 2714 s; tennis_07 2711 and
2701 s; tennis_08 2711 and 2704 s; tennis_09 2712 and 2706 s. Line 363 is a
later tennis_06 kill at 3600 s and zero rows. The five pre-budget healthy
tennis completions (lines 49, 60, 71, 73, and 76) took 4827, 6482, 8545, 8575,
and 8773 s. Neither 2700 nor 3600 s would admit any of those five runs.

## Measurement before a threshold decision

The historical window is every append-only ledger row before the first
2700-second kill (lines 1-151), not runs selected for completing under the
current budget. Every `tracked` or `thin` completion in that window is counted;
p95 is linearly interpolated.

| sport | n | median seconds | p95 seconds | max seconds | decoded frames / source resolution |
|---|---:|---:|---:|---:|---|
| baseball | 63 | 867.0 | 4011.0 | 5481 | absent for every row |
| football | 33 | 2074.0 | 6023.4 | 6581 | absent for every row |
| handball | 1 | 20.0 | 20.0 | 20 | absent for every row |
| kbo | 12 | 722.0 | 781.2 | 790 | absent for every row |
| mlb | 9 | 793.0 | 937.4 | 943 | absent for every row |
| ncaa_basketball | 0 | n/a | n/a | n/a | absent for every row |
| soccer | 15 | 3958.0 | 4806.4 | 5365 | absent for every row |
| tennis | 6 | 7513.5 | 8723.5 | 8773 | absent for every row |
| wnba | 1 | 151.0 | 151.0 | 151 | absent for every row |

The entire 397-row ledger lacks `decoded_frames`, `source_resolution`, and
source-duration fields. Therefore it cannot support a frames-versus-time slope,
a clip-length relationship, or a defensible per-clip budget. G56's local writer
has not yet emitted a pod row. A threshold is not proposed: fitting one from
only jobs that survived would be circular. Once new denominator-bearing rows
exist, a frame-derived per-clip budget is preferable to one global constant if
the measured relationship is approximately linear.

## Additive timeout verdict

`track_daemon._finish` now adds `verdict: "TIMEOUT"` only for a killed job;
ordinary writes receive `verdict: null`. The existing lifecycle `status` field
and every existing ledger field retain their names and meanings. No timeout
value, harness threshold, or G15b done-definition changed.

The metric is killed runs identifiable from the new explicit `verdict` alone.
Before is 0.0 because legacy rows lack it. The constructed new timeout write is
identifiable: 1/1 = 1.0. The live ledger's complete count is 397; no new live
row was made because deployment is prohibited before acceptance.

## Test

```text
python -m pytest scripts/platformkit/test_track_daemon_timeout_verdict.py -q
1 passed in 1.13s
```

## Verifier-contract B self-check

- B1: all completed rows in the stated historical window are counted; the
  constructed metric includes every new timeout write.
- B2: `verdict` is additive and no existing reader consumes it.
- B3/B4: claim, quarantine, retention, and done behavior are unchanged.
- B5: there was no deployment, pod copy, daemon restart, or process kill.
- B6: no module moved or retired.
- B7/B8: no render sample or fitted independent result is claimed.
- B9: the metric denominator is timeout writes, not a recycled identifier.
- B10: no timeout, harness threshold, existing field, or done-definition moved.

## NOT VERIFIED

- No historical row has the G56 denominators, so no frame slope or threshold
  proposal is supported.
- The live daemon has not yet written the new verdict field.
