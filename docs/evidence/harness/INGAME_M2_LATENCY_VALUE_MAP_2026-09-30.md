# Value of state-feed latency for the Model 2.0 staleness backstop (M4, 2026-09-30)

For the CAPTURE-LATENCY lead (S592 census, S593 MLB push socket, S595 NFL clock, S596 NBA pbp primary).
Calibration language only.

Every number below is printed by one of two scripts. The stdout copies sit beside the scripts in
`ingame_model_2_probes/`:
- `ingame_model_2_probes/m4_latency_value_map.py`, which reads the sealed S542 replay JSON.
- `ingame_model_2_probes/probe_mlb_latency.py`, which streams the MLB state archive with a psutil cap
  (peak 22 MB).

## What the map says

The market-anchored projection (PROJ, S542) has one job: a staleness backstop. When our copy of the price is
stale and the state has changed, PROJ moves the stale price through the state change.
- The sealed replay verdict is ACCEPT_STALENESS_BACKSTOP_ONLY (S542, 429a8e271).
- PROJ never gets ahead of a FRESH price. At an 18 s state delay, all ticks:
  - 2024-25: PROJ-FRESH +0.00046 [+0.00026, +0.00066];
  - 2025-26: PROJ-FRESH +0.00017 [-0.00046, +0.00066].
- So the durable fix for staleness is capture cadence and state latency, not a model. The model only
  recovers part of what latency costs.

## Recovery of the staleness loss by state delay

Source: NBA, Polymarket per-minute points, 1,593 games. STALE is the previous point. R = the share of the
STALE-minus-FRESH Brier gap that PROJ recovers. The replayed lags carry sealed CIs; the 5 / 10 / 21 s rows
are linear interpolations and have no CI.

| subset | lag | 2024-25 R | 2024-25 PROJ-STALE | 2025-26 R | 2025-26 PROJ-STALE |
|---|---|---|---|---|---|
| all ticks | 0 s | 0.989 [0.876, 1.099] | -0.00148 | 1.201 [0.887, 1.623] | -0.00181 |
| all ticks | 5 s (interp) | 0.906 | -0.00136 | 1.114 | -0.00168 |
| all ticks | 10 s (interp) | 0.823 | -0.00123 | 1.026 | -0.00155 |
| all ticks | 18 s | 0.691 [0.555, 0.829] | -0.00104 | 0.886 [0.565, 1.301] | -0.00134 |
| all ticks | 21 s (interp) | 0.636 | -0.00095 | 0.844 | -0.00127 |
| all ticks | 31 s | 0.453 [0.324, 0.578] | -0.00068 | 0.703 [0.388, 1.097] | -0.00106 |
| all ticks | 60 s | 0.018 [-0.017, 0.051] | -0.00003 | 0.299 [0.060, 0.631] | -0.00045 |
| state-changed (projected) | 0 s | 1.021 [0.902, 1.148] | -0.00211 | 1.302 [0.954, 1.764] | -0.00255 |
| state-changed (projected) | 18 s | 0.729 [0.582, 0.885] | -0.00157 | 0.970 [0.625, 1.426] | -0.00200 |
| state-changed (projected) | 31 s | 0.519 [0.373, 0.669] | -0.00112 | 0.814 [0.453, 1.268] | -0.00174 |

Reading:
- Each second of state delay costs recovery.
- In 2024-25, R falls from about 0.99 at 0 s to 0.69 at 18 s, 0.45 at 31 s and about 0 at 60 s.
- 2025-26 falls more slowly, but in the same direction.
- Cutting the MLB feed delay from about 21 s to 5-10 s would move PROJ's recovery from about the 21 s
  row to the 5-10 s rows. That is roughly +0.2 to +0.3 of the staleness gap on this corpus. The table
  measures NBA; applying it to MLB is a transfer, not a measurement.

## Measured state delays (per sport)

MLB (statsapi state in capture_view_v2; `probe_mlb_latency.py`; 9,532 plays at the 00:0xZ run (the live archive grows); each game's first observed play
skipped):

| measure | p10 | p50 | p90 |
|---|---|---|---|
| capture_ts - last_play_ts (our receipt - play end) | 13.1 s | 21.8 s | 33.4 s |
| source_ts - last_play_ts (feed timestamp - play end) | -1.6 s | -1.0 s | -0.3 s |
| capture_ts - source_ts | 14.0 s | 22.8 s | 34.6 s |
| mlb_live.receipt_utc - last_play_ts (S432 block) | 13.2 s | 22.3 s | 36.7 s |

- Our per-game live poll gap (same script, 24,743 gaps under 600 s) is p10 10.0 s, p50 10.0 s, p90 47.5 s.
- About 5 s of the delay is the expected wait inside a 10 s poll.
- The rest, about 17 s, is between the feed's own timestamp and our receipt. That is a publication or
  fetch delay, not play timing.
- The S432 mlb_live block is no faster.
- For comparison, the execution lead's S550 receipt reports a median of 21.4 s from play to our receipt.

Other sports:
- NBA / WNBA / NFL: NO_DATA. There are no live rows in capture_view_v2: the NBA offseason, WNBA pre rows
  only, and 2 NFL games.
- Soccer: repricing is complete within one tick at a p50 29 s cadence (P6), so there is nothing to recover.

## For the capture-latency rows

- **S593 (MLB push socket).** Target a play-to-receipt delay under 10 s. The table above prices the
  backstop's recovery at each delay, but the first-order effect is the fresh book itself: a fresh anchor
  needs no projection.
- **S596 (NBA pbp primary).** NBA recovery is highest below about 18 s. Any delay above 60 s makes PROJ
  worthless as a backstop in 2024-25.
- **S595 (NFL clock).** No NFL model exists yet (S546 is specced after this map). The value is unmeasured.
