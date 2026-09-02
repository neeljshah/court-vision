# In-game signal wave -- verdict (Fable, 2026-09-03 ~16:45 CDT)

User directive: in-game signal quality first, slowly, try new things, use the pod. Twenty-four register
rows (S79-S105) ran as SCREEN-side lanes, uncharged, calibration language only. The FWER ledger stayed at
18 rows; no bar moved; every result reproduces from its archived per-tick series (Q9).

## What was measured (all SCREEN side, walk-forward, purged, game-clustered CIs)

| lane | surface | result vs the in-play line |
|---|---|---|
| S82 | MLB 14 state features through the new in-game factory tier | 0/14 clear +0.004 (41 games; CI half-width ~0.005 -- unresolvable) |
| S80 S83 | MLB player grain (pitcher as-of residual) | +0.0036 below bar; store join fixed |
| S86 | NBA every tick scored (465,249 ticks / 1,593 games) | state prior -0.0049 pooled; matches in 16/27 cells |
| S94 | NBA early-phase shrinkage on a measured market miscalibration | -0.0028; the miscalibration does not survive walk-forward |
| S96 | NBA overreaction after scoring events | direction FALSIFIED: the line UNDER-reacts and drifts; drift arm still behind |
| S97 | NBA two-sensor Kalman fusion | +0.000003; the line is a martingale at tick resolution |
| S98 S103 | better as-of prior / fitted sigma | no better prior exists on disk; fitted sigma closes half the gap (-0.0021, CI includes 0) |
| S101 | conformal coverage | static bands 0.94-0.98 (Gaussian 0.08); online ACI is label-consuming |
| S99 | rest-of-game distribution vs moneyline + total | BEHIND both markets with CIs excluding zero |
| S100 | order-book microstructure | premise falsified: depth captured pre-game only |
| S102 | 576 NBA derived-state hypotheses swept on the pod | 0/564 clear; best +0.00025; 3,267 screens/hour |

## The honest conclusion

With the data on disk, the in-play line is efficient at tick resolution within the +0.004 Brier bar in
every direction we tested: state, player grain, phase recalibration, overreaction, fusion, prior quality,
distributional consistency and a 576-form sweep. Three findings hold across lanes: (1) a recalibration
of the line fit on the past is itself BEHIND the raw line out of sample; (2) blending a state price into
the line never beats the line (four confirmations); (3) the line drifts after events (slow mid) but the
drift is too small to convert.

This is the Renaissance-level property: the process found the limit rigorously and recorded it.

## What still moves the in-game number (none is a modelling row)

1. MLB game STATE for the 3,780 priced events -- Neel's S62 row 3 (MLB Stats API backfill).
2. Depth capture DURING scored games (S105, capture cadence) -- reopens microstructure.
3. In-play ticks for a second sport with state (soccer captures are structured from 2026-06-28).
4. The tracking teacher (Phase M): features the line cannot see, which is the only class of
   information no test above could reach.
