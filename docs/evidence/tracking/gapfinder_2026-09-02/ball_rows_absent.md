# 127 of 135 gated pod tables carry zero ball rows (2026-09-02)

Read-only on the pod. Every `data/tracking/*/tracking_data.csv` loaded with
pandas; per table we counted distinct `track_id`, distinct `frame`, and rows by
`cls`. Raw rows: `pod_trackid_ball_census.json` (182 game dirs; 173 have a csv,
9 have none).

## The number

165 of 173 tables (95.4 pct) contain zero rows with `cls == "ball"`. Only 8
tennis tables emit any ball row at all.

`scripts/platformkit/tracking_harness.py:160` computes
`ball_valid = df[df["cls"] == "ball"]["frame"].nunique() / n_frames` whenever
`schema.ball_telemetry_available` is true, and the `normalized` schema these
tables resolve to sets that flag True (`tracking_schema.py:54`). Football is the
only sport whose config sets `ball_valid_min = 0.0` (the FootballAdapter
deliberately has no ball detector). Excluding football's 38 exempt tables:

| sport | tables | zero-ball | config ball_valid_min |
|---|---:|---:|---:|
| kbo | 35 | 35 | 0.10 |
| mlb | 32 | 32 | 0.10 |
| soccer | 24 | 24 | 0.20 |
| npb | 23 | 23 | 0.10 |
| wnba | 7 | 7 | 0.30 |
| ncaa_basketball | 4 | 4 | 0.30 |
| tennis | 10 | 2 | 0.20 |
| **total gated** | **135** | **127 (94.1 pct)** | |

So `ball_valid` evaluates to 0.00 and the gate fails by construction on 127 of
the 135 tables it is applied to. The eight tennis tables that do carry ball rows
(tennis_01..05, tennis_08, tennis_3x3eEWCZmWQ, tennis_nyYk2nPZAwY) are the only
evidence in the corpus that a ball detector runs anywhere, and every landed
`ball_valid` number in the results ledger (G05: 0.6889, 0.4828) comes from them.

## Why it is a gap, not a known-limitation

The failure is silent and indistinguishable from a real miss: a sport with no
ball detector attached and a sport whose ball detector performs badly both
report `ball_valid 0.00 < 0.30`. Football is handled honestly (threshold 0.0
plus a comment naming the reason); the other six sports are not.

## Achievable limit

Either attach a ball detector per sport, or -- the lazy correct move -- have
each producer declare `ball_telemetry_available=False` when it emits no ball
class, so `ball_valid` returns None and the gate is honestly skipped instead of
silently failed. That makes the remaining harness failures readable. No
threshold is loosened by this; the 0.30 basketball bar stays 0.30 for the day a
detector exists.
