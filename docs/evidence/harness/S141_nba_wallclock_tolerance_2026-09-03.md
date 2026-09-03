# S141 NBA wall-clock state tolerance

Status: ACCEPT. This records a 300-second state-age rail for the single
NBA wall-clock join.

## Premise and real-input replay

Before the change, `nba_wallclock_join.py:122` performed a backward
`merge_asof` without a tolerance. The replay used every raw Kalshi playoff
event and its cached ESPN state payload from the read-only main data tree.
It enumerated and resolved 53 of 53 games, with 8,294 ticks having a prior
state. State age was p50 18 s, p90 196 s, and maximum 1,026 s. Of 170,307
input ticks, 555 (0.325882%) had a prior state older than 300 s; 162,013
had no prior state. The helper's stale share, which includes both cases, was
95.455853% across all input ticks. The durable summary is
`S141_nba_wallclock_tolerance_2026-09-03_measurement.json`.

## Change and equality check

`join_game_states(..., *, max_staleness_s=300.0)` now delegates to
`asof_join_state`. It exposes `stale_share` and `max_staleness_s` in the
returned DataFrame metadata and logs both the share and rail. Unusable state
columns are nulled by the helper; the join's existing margin-null drop then
excludes those candles from its established output schema.

The pre-change join from base commit `4b7169973ba7de5701942fed14334a2bb77f0b12`
was replayed on the same 53 games and
restricted to rows whose matched state age was at most 300 s. It has 7,739
rows and SHA-256 `839911afd165959248e9cc47e93f8eb9d86e145ef5c80bf4dd66d71a4ae48d9f`.
The changed join produced the same 7,739 rows with the same SHA-256; the
per-game frame equality assertion passed exactly. Evenly spaced game samples
were event 401869406 (2,290 input / 140 retained / 0.938865 stale share),
401871153 (3,164 / 145 / 0.954172), and 401873203 (483 / 142 / 0.706004).

## Verification

`python -m pytest tests/platformkit/venue_history/test_nba_wallclock_join_tolerance.py -q`: 1 passed.
`python -m pytest scripts/platformkit/venue_history/test_nba_wallclock_join.py -q`: 8 passed.
`python -m pytest tests/platformkit/eval_gate/test_asof_join.py -q`: 5 passed.

B1-B10 were checked: the denominator is the one join and all raw ticks are
named; schema remains additive; no unrelated reader was moved; the entire
53-game set was replayed; and the 300-second rail is unchanged. Q1-Q9 were
checked: this is an exhaustive construct, not a scored comparison; no
trial-accounting or corpus claim applies; the premise was remeasured before the edit; and the
artifact uses calibration-only language.

NOT VERIFIED: no data parquet was rebuilt because the data tree is read-only;
no remote execution was required; no deployment action was taken.
