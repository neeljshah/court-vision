# Deep feature program -- NBA pregame (preregistered 2026-07-17)

Declared BEFORE testing. Each family is tested alone vs the plain-feature
sweep baseline (Brier 0.2065, n=743, 4 WF folds), then forward-selected
combinations of survivors. Gate: paired bootstrap CI vs plain features must
exclude zero. Honest REJECTs go to the reject ledger. No family's definition
may be edited after its first scored run (a changed definition = a NEW
prereg entry with a version suffix).

The gap to the close is 0.023 Brier. Hypothesis ranking below reflects what
the close plausibly knows that our features cannot see. Team-grain
aggregates are largely saturated (enriched-GBM REJECT 2026-07-17;
live_edge memory: player-grain = remaining signal).

## Family P -- player-grain availability + value (THE core bet)
P1 roster_value_asof: walk-forward per-player value v_p (EW per-minute
   margin contribution from player_boxscores, shrunk to position mean by
   minutes played); team feature = sum of v_p over players active in the
   team's PREVIOUS game (expected-available proxy; late scratches are
   honest noise, NEVER same-game participation -- that leaks).
P2 star_absence_delta: drop in roster_value_asof vs the team's trailing-10
   max (captures "the star just went out" faster than Elo losses can).
P3 continuity: minutes-weighted Jaccard overlap of last-game rotation vs
   trailing-5 rotation (roster churn / trade shock).
P4 top_heavy: share of roster_value in top-2 players (fragility to
   single-absence; interacts with P2).

## Family M -- motivation / season phase
M1 tank_gradient: late-season (post trade deadline) feature = playoff-race
   distance (games back from 8th seed as-of) x days-remaining decay --
   teams far out of the race underperform market-neutral baselines.
M2 seeding_stakes: late-season games where one side is locked (seed
   clinched) vs fighting -- asymmetric effort.
M3 season_phase: game-number spline (early-season prior instability,
   post-all-star intensity).

## Family S -- schedule micro (beyond rest days)
S1 three_in_four, S2 road_trip_position (game # within trip), S3 timezone
   delta from previous game, S4 b2b_asymmetry (home-b2b vs road-b2b as
   separate features, not one flag).

## Family V -- variance / luck regression
V1 fg3_luck: trailing-10 3P% minus season-to-date 3P% (mean-reverting;
   the market discounts hot streaks, naive form features don't).
V2 pythag_gap: trailing win% minus pythagorean expectation from points
   (close-game luck regresses).
V3 garbage_mov: recompute Elo MOV update with margins capped at 20
   (blowout tails are noise) -- an ALTERNATE Elo, tested as a swap.

## Family X -- matchup interactions
X1 pace_product interaction, X2 style: rim-pressure vs rim-protection
   percentile differential (from own profiles asof), X3 size_spacing.

## MLB (parallel, separate lane): SP1 as-of starter quality from statcast
   (EW xwOBA-against last 6 starts, walk-forward) -- kills pitcher-blindness
   with data already on the pod. SP2 bullpen fatigue (relief IP last 3 days).

Execution: harness runs family-by-family on the pod GPU (each ~2 min),
then greedy forward selection over CI-surviving families, then the final
composed candidate vs close. Everything logged, every null recorded.
