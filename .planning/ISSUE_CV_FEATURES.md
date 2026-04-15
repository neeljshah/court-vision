# ISSUE: CV Features Null — defender_distance, spacing, fatigue

**Status:** BLOCKED  
**Opened:** 2026-04-15  
**Source:** Task 6, backlog sweep

## Diagnosis

Scanned all 26 tracking dirs with tracking data. Results:

| Column | Non-null games | Notes |
|---|---|---|
| `defender_distance` | 0/26 | Never populated — BLOCKED |
| `team_spacing` | 26/26 | Present but already in player_props |
| `handler_isolation` | ~22/26 | Present, could be added |
| `fatigue` | 0/26 | Not written anywhere in pipeline |
| `cvb_avg_defender_dist` | 0/26 | Needs full-game CV run |
| `cvb_fatigue_score` | 0/26 | Needs full-game CV run |

`defender_distance` is tracked by the pipeline as `nearest_opponent` in
`feature_engineering.py`, but the `cv_avg_defender_distance` field in
`player_props.py` requires joining shot-moment tracking data with player
gamelogs — a join that is not implemented.

## Root Cause

1. `defender_distance` in tracking_data.csv stores nearest opponent distance
   **per frame**, not aggregated per player per game.
2. `player_props.py` expects `cv_avg_defender_distance` as a player-game
   aggregate (mean over shot frames).
3. The aggregation pipeline (`scripts/build_cv_features.py` or equivalent)
   does not exist.

## Resolution Required

1. Write `scripts/build_cv_features.py`:
   - For each game in `data/tracking/`, join `shot_log.csv` with
     `tracking_data.csv` on `frame` to get defender_distance at shot moment.
   - Aggregate: `cv_avg_defender_distance = mean(nearest_opponent where shot_event=True)`.
   - Output: `data/nba/cv_player_features_{season}.json` keyed by player_id.
2. Update `player_props.py` `_load_cv_features()` to read this new file.
3. Retrain 7 prop models after CV features are non-null.

## Current workaround

`player_props.py` already zero-fills `cv_avg_defender_distance = 0.0` when
not available (line 845), so models degrade gracefully. No action needed until
CV features are built.

## Do NOT force-add to prop models while null.
