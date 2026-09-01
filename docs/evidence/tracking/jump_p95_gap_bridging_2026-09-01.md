# jump_p95 has been measuring player MOVEMENT across gaps, not tracker error

## The mechanism

Two facts combine badly.

`domains/tennis/tracking/adapter.py:_track_ids` labels players with
`enumerate(order, start=1)` -- track ids are ALWAYS 1 and 2, for the entire
video, and are never re-issued. Even `_reset_temporal_calibration`, which clears
`_centroids`, re-seeds the SAME two labels.

`scripts/platformkit/tracking_harness.py:157-159` computes
`players.sort_values(["track_id","frame"]).groupby("track_id")` then `.diff()`.
Consecutive EMITTED rows of one id, with NO frame-gap normalisation.

The adapter emits only on frames where calibration solved fresh. So when a
player is emitted at frame 100 and not again until frame 1000 -- a cutaway, a
replay, a changeover -- the harness sees ONE step whose length is however far
the player actually walked. An end change is up to 78 ft on a 78 ft court.

## Measured on three real games

Observed maximum emission gap: 2,898 frames.

| game | jump_p95 as-is | jump_p95 split at gaps > 30 frames | gate |
|---|---:|---:|---:|
| tennis_01 |  2.780 ft |  2.486 ft | 8.0 |
| tennis_03 | 34.362 ft | 28.755 ft | 8.0 |
| tennis_04 | 10.033 ft |  4.906 ft | 8.0 |

tennis_04 goes from FAILING to PASSING purely by not asserting identity across a
gap. tennis_01 was already passing. tennis_03 still fails badly at 28.755, so it
carries genuine within-run defects -- identity swaps or calibration blow-ups --
that this does not touch.

CAVEAT ON PROVENANCE: these CSVs were produced by the OLD propagating adapter
(they carry thousands of rows; the current fail-closed adapter emits far fewer).
They demonstrate the MECHANISM reliably. They are not a claim about what the
current producer scores.

## Why splitting is the HONEST choice, not a workaround

Identity across a thirty-second replay is genuinely unknown. Asserting that the
player emitted before the cutaway is the same track as the one after it is the
unsupported claim; issuing a new id is the truthful statement. This is the same
principle that removed carried-over calibration: state what was observed, not
what was assumed.

It must be done on real evidence of discontinuity -- a detected camera cut, or a
gap long enough that continuity cannot be claimed -- and NOT by resetting on
every missed frame, which would drive jump_p95 to near zero at any accept rate
and would be gaming the metric rather than reporting it.

## What this reorders

Calibration ACCURACY was not the binding constraint it appeared to be. A
back-solve of the tennis gates against the measured 5.28 ft held-out error puts
modelled oob at 0.014 against a 0.08 gate -- satisfied with roughly 5.7x margin
-- and the historical oob of 0.09-0.59 came from the old carried-over
homographies rather than from fresh solves. Coverage needs both players found on
about 88.6% of emitted frames, and is unaffected by the accept rate because
non-solving frames leave the denominator entirely.

jump_p95 binds hardest, and a large part of it was never a tracking failure.
