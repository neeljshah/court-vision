# MLB `asof_bullpen` -- DEFERRED (honest, un-buildable as specified)

**Task 4b** asked for a leak-free as-of bullpen ERA-proxy + load feature
(`diff_bullpen_era_asof`, entity = team, EWMean), built from NON-SP pitchers in
`player_gamelogs.parquet`, with starting-pitcher identity taken from
`pitchers.parquet`, keyed by `event_id`.

**Verdict: DEFER.** The specified join does not map cleanly, and there is no
provable substitute for SP identity in the player_gamelogs era. Per Task-4b's own
instruction ("IF IT DOES NOT map cleanly, DEFER honestly ... do not fabricate the
join"), the bullpen feature is deferred and only the provable component is shipped.

## Join verification (inspected real parquet schemas)

| corpus | key | date span | notes |
|---|---|---|---|
| `player_gamelogs.parquet` | `game_pk` (int64) | **2026-04 .. 2026-06** | has `is_pitcher`, `inningsPitched`, `earnedRuns`; **no SP/RP flag**; `batting_order` null for 8608/8700 pitcher rows |
| `pitchers.parquet` | `event_id` (str) | **2010 .. 2021** | carries SP names/handedness; **zero date overlap with player_gamelogs** |
| `games.parquet` | `event_id` (str) | 2010 .. 2021 | 0/78 player_gamelogs days overlap |
| `games_current.parquet` | `event_id` (str) | 2022 .. present | **77/78 player_gamelogs days overlap** -- the only bridgeable game table |

Three independent blockers, each fatal to the feature as specified:

1. **No shared key.** `player_gamelogs` keys on `game_pk`; `pitchers`/`games` key on
   `event_id`. Neither table carries the other's key, and there is no schedule table
   mapping them.
2. **SP-identity source is era-disjoint.** `pitchers.parquet` (2010-2021) shares **no
   games at all** with `player_gamelogs` (2026). The documented SP source simply does
   not cover the only season for which we have per-pitcher load. So "NON-SP pitchers"
   cannot be defined via `pitchers.parquet`.
3. **No provable SP proxy inside `player_gamelogs`.** Row order within a (game_pk, team)
   is **not** start order: the first pitcher row is the game's max-innings pitcher only
   **~25%** of the time. A unique-max-IP heuristic identifies *a* pitcher 98.7% of the
   time, but that is a *fabricated* SP definition (wrong for openers / bullpen games),
   not the specified `pitchers.parquet` identity -- so using it would fabricate the
   SP/RP split the task forbids.

## What IS provable (shipped instead of fabricating)

The `game_pk -> event_id` bridge for the player_gamelogs era, via
`(date, normalised unordered team-pair)` against `games_current.parquet`
(team-code dialect reconciled: `ARI->AZ`, `SDG->SD`, `TAM->TB`, `KAN->KC`,
`SFO->SF`, `WAS->WSH`, `OAK->ATH`, `CUB->CHC`).

* **1002 / 1031 (97.2%)** game_pks resolve to a unique event_id.
* **14** fall on same-day doubleheader keys -> left **unmapped** (never guessed).
* **15** find no games_current key -> left **unmapped**.
* Leak-free: keys on game identity only; the proof re-derives the same map with the
  outcome columns (`home_runs`/`away_runs`/`target_home_win`) dropped.

Shipped as `domains/mlb/game_pk_bridge.py` with
`scripts/platformkit/proof_mlb/gate_test_bullpen.py` (records the DEFER verdict to the
reject ledger) and `tests/platformkit/test_asof_bullpen.py`.

## How to un-defer (revisitable)

Acquire a `game_pk`-keyed SP-identity source for the player_gamelogs era (MLB Stats API
`gameType`/`probablePitcher`, or a starts table keyed on game_pk). Then: SP per
(game_pk, team) -> mask SP rows -> aggregate the remaining (non-SP) `earnedRuns` and
`inningsPitched` into a 9*ER/IP bullpen ERA-proxy + an IP-load -> `asof_common.EWMean`
prior-only by team -> attach `event_id` via this bridge -> gate against the MLB Elo base.

`DEFER` is honest data-coverage evidence, not a failure (calibration != edge; no $ claim).
