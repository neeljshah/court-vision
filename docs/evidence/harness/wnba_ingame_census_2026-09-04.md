# WNBA in-game state census, 2026-09-04

Verdict: ACCEPT. This is an unscored offline census. It does not evaluate a
prediction or publish a calibration comparison.

## Reproduction

Run `python -m scripts.platformkit.ingame.wnba_wallclock_join` from the
repository root. The command reads only the five local sources named in
`wnba_ingame_census_2026-09-04_summary.json`, calls the existing backward
`asof_join_state` rail at `max_staleness_s=300.0`, and writes the additive
checkpoint parquet. The summary JSON and the 85-row per-game CSV are the
durable rows behind each number below.

| Measure | Before | After |
| --- | ---: | ---: |
| WNBA in-play ticks with an action-derived as-of state | 0 | 18,650 |
| Intersect games | 0 | 85 |
| In-play denominator over those 85 games | 186,736 | 186,736 |
| In-span ticks | n/a | 19,456 (10.42 percent) |

The before value is the established S80/S82 closed evidence: no settled WNBA
ticks in a state-joined store, and no WNBA in-game tick with player or lineup
state. No register or ledger was changed for this census.

## Premise reproduction

- Price source: 967,102 rows and 287 events. Its market breakdown is spread
  484,729/130, total 264,671/59, and moneyline 217,702/98. There are 217,408
  in-play moneyline ticks over all 98 events, median 2,380 per event, with all
  98 at or above 100 ticks.
- The existing resolver labels 95 of 98 priced events. The ticker-side local
  settlement label resolves all 98 and agrees on all 95 comparable events,
  with zero disagreements.
- Cached play-by-play has 168 games and 84,143 actions; all 84,143 have the
  required timestamp, score, clock, period, and person fields. Its wallclock
  range is 2026-04-25T19:03:10Z through 2026-07-04T04:31:59Z.
- Checkpoint state has 504 rows across 168 games: 168 each at end_q1, half,
  and end_q3. Both lineup fields are non-null on all 504 rows. These are only
  three checkpoints per game, not a lineup series.
- The two bridge maps reproduce 95 priced events to ESPN event ids and
  166 state games to line scores; their intersection is 85 games. Those games
  hold 186,991 moneyline rows, of which exactly 186,736 are in-play.

## Census result

All 186,736 intersect in-play ticks remain in the denominator. The 167,280
ticks outside their game-specific play-by-play span are reported unjoined;
they were not removed before computing the 18,650 joined-tick result. Of the
19,456 in-span ticks, every one of 85 games has at least one, the median is
250, p90 is 274, 84 games have at least 100, and 67 have at least 150.

The joined rows have state-age median 15 seconds, p90 132 seconds, and zero
share above 300 seconds. The per-game CSV records each game's denominator,
in-span count, and joined count. Reloading the checkpoint parquet gives
18,650 rows across 85 event keys and 85 game ids, with the same state-age
distribution.

## Exclusions and limits

The 13 priced events excluded from `n` have no state counterpart:

`KXWNBAGAME-26JUL03CHILV`, `KXWNBAGAME-26JUL03MINNY`,
`KXWNBAGAME-26JUL04GSATL`, `KXWNBAGAME-26JUL04PDXSEA`,
`KXWNBAGAME-26JUL05DALTOR`, `KXWNBAGAME-26JUL05INDLV`,
`KXWNBAGAME-26JUL06CONNMIN`, `KXWNBAGAME-26JUL06GSWSH`,
`KXWNBAGAME-26JUL06SEALA`, `KXWNBAGAME-26JUL07DALNY`,
`KXWNBAGAME-26JUL08GSTOR`, `KXWNBAGAME-26JUL08INDLA`, and
`KXWNBAGAME-26JUL08MINCONN`.

The 83 state games excluded from `n` have no priced-event counterpart. Their
complete ids are in `excluded_state_games` in the committed summary JSON;
the two state-to-linescore failures are `1022600148` and `1022600149`.
The three resolver-unbridged priced events are also named in that summary.
These exclusions are bridge absences, not quality filters.

## Not verified

- No player or continuous lineup state was derived; the source lineup data has
  only its three stated checkpoints.
- No price or outcome quality metric was evaluated.
- No state can be recovered for the 167,280 ticks outside cached play-by-play
  wallclock spans.
- No network call, deployment, feature-flag change, register write, or ledger
  write occurred.

## Contract self-check

B1 is satisfied because every in-play tick stays in the denominator and all
unbridged sets are named. B2-B6 are satisfied: the change is additive, has no
gate behavior, claim loop, deployment, moved module, or changed reader. B7-B9
do not apply to a render or scored comparison; the unit is unique price ticks.
B10 is satisfied by using the unchanged 300-second shared rail. Q1-Q6 and Q9
do not apply because this is not scored; Q7 is satisfied by the exhaustive
85-game intersection and Q8 by the premise measurements above.
