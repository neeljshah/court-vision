# WNBA PBP scope census (read-only, feeds a future stint-keystone decision)

Source: `data/domains/wnba/cdn_backfill/<gameId>/playbyplay.json`, present for
all 168 games backing `player_boxscores.parquet`. Sampled 5 games in depth
(1012600001..1012600005) + a 30-game sweep for counts/edge cases.

## Structure
`{"game": {"gameId": ..., "actions": [...]}, "meta": {...}}`. `gameId` matches
its parent directory name on every sampled game (0 mismatches / 30).

## Fields present (per action)
`actionNumber, actionType, subType, period, clock, personId, teamId,
teamTricode, side, possession, scoreHome, scoreAway, x, y, xLegacy, yLegacy,
timeActual, description` -- plus event-specific fields (`assistPersonId`,
`stealPersonId`, `blockPersonId`, `shotResult`, `shotDistance`, `reboundTotal`,
etc., appear only on the relevant action rows).

## Sample counts (5-game deep sample)
| game_id | n_actions | n_substitution | n_shot(isFieldGoal) |
|---|---|---|---|
| 1012600001 | 546 | 132 | 141 |
| 1012600002 | 539 | 124 | 130 |
| 1012600003 | 539 | 130 | 121 |
| 1012600004 | 454 | 100 | 131 |
| 1012600005 | 486 | 110 | 123 |

30-game sweep: 3,760 substitution actions, **0** with `personId=None`
(NBA's ESPN-backfill "unmapped sub" edge case does not appear here). 3,972
shot actions, **100%** carry non-null `x`/`y`. Max period seen = 5 (1 OT game
in the sweep).

## Field match vs `domains/basketball_nba/lineups/pbp_lineups.py`
The exact fields that module reads on every action --
`actionType=='substitution'`, `personId`, `actionNumber`, `clock`, `period`,
plus `teamId`/`teamTricode`/`subType` used deeper in `build_team_stints`/
`_box_starters` -- are **all present, same names, same shapes** in WNBA PBP.
Shot rows additionally carry `x`/`y` (not consumed by `pbp_lineups.py` today,
but present for a future shot-location claim).

Two seed-side mismatches, not PBP-side:
- `player_boxscores.parquet` (WNBA) has `started: bool` where NBA's box has
  `starter: "1"/"0"` (string) -- `_box_starters` filters `starter == True`, a
  one-line predicate change.
- WNBA box's `team_id` is a numeric-string that matches PBP `teamId` directly
  (`1611661313` style); NBA's `_box_starters` matches on `team` (a tricode
  string against PBP `teamTricode`) -- WNBA can match on the numeric id
  instead, actually simpler than the NBA tricode path.
- WNBA box's `player_id` is stored as `str`; PBP's `personId` is `int` --
  needs a cast at the join, same class of issue NBA already guards against
  cross-source ID mismatches for.

## Verdict
**Portable with adapter.** No missing fields -- every field
`pbp_lineups.py` needs exists under the same name with the same semantics.
The adapter work is the box-score seed join only: swap `starter` (str) for
`started` (bool), swap tricode-match for team_id-match, and cast
`player_id`/`personId` to a common type before the `known_person_ids` set
comparison. No stint-reconstruction code written this wave per scope.
