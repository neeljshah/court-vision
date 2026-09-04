# S282 Foul Bonus Regime

Verdict: CLOSED AT LIMIT.

## Scope and machine

This premise census ran locally in `C:/Users/neelj/nba-track-a14` on branch
`track-a14`. It opens three small parquet stores read-only, one store at a time,
and retains only the identifier columns needed by the fixed chain. No source is
a raster, so resolution is n/a for every input. No scorer ran: the 30-game rail
was not reached, so no fitting, preregistration, charged trial, evaluator state,
or paired-loss artifact was created.

## Inputs

| Input | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `C:/Users/neelj/nba-track-a14/data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2,829,826 | `5EA6498D88BF7548395C700C7239641DCBD1D641BDADDB5A6B63FCF0EA8909E5` | n/a (parquet) |
| `C:/Users/neelj/nba-track-a14/data/cache/inplay_foul_state.parquet` | 39,429 | `CD3C5CC4714BE7655A9BAF05845C8B32F089090F87594630999A8F606118D5D9` | n/a (parquet) |
| `C:/Users/neelj/nba-track-a14/data/domains/basketball_nba/espn_nba_game_bridge.parquet` | 46,002 | `E0E0AB68D6882BF77987DCA2890A1896376FFE18D8E46D11656338A7EC037F4F` | n/a (parquet) |

The checkpoint path above is the in-worktree resolution of the S226 memo's
other-worktree prefix, as required by the worktree rule.

## Fixed premise reproduction

The fixed, non-widened chain is:

```text
checkpoints.game_id == bridge.event_id == bridge.game_id == foul_state.game_id
```

Verified checkpoint columns:

```text
game_id, game_date, ts, period, game_clock_s, score_home, score_away, margin,
market_prob, traded, market_ticker, outcome_home_win, venue
```

Verified foul-state columns:

```text
game_id, period, home_team_pfs_cum, away_team_pfs_cum, home_max_player_pfs,
away_max_player_pfs, home_starter_fouled_out_indicator,
away_starter_fouled_out_indicator, pf_imbalance
```

Verified bridge columns:

```text
event_id, home_abbr, home_q1, home_q2, home_q3, home_q4, away_abbr, away_q1,
away_q2, away_q3, away_q4, date, home_nba, away_nba, _date, game_id,
match_confidence, season, source_linescores_file, as_of, corpus_id
```

First three identifier values in stored order:

| Side | Values |
|---|---|
| checkpoints.game_id | `401704627`, `401704627`, `401704627` |
| bridge.event_id | `401809243`, `401809244`, `401809235` |
| bridge.game_id | `0022500001`, `0022500002`, `0022500004` |
| foul_state.game_id | `0022200001`, `0022200001`, `0022200002` |

The exact binding before-condition was rerun locally and printed:

```text
BINDING FOUR-WAY CHAIN: checkpoints.game_id == bridge.event_id == bridge.game_id == foul_state.game_id
CHECKPOINT_GAME_CLUSTERS=1593
JOINED_GAME_CLUSTERS=29
RAIL_REQUIRED=30
RSS_BYTES=93790208
```

The complete classification is archived in
`docs/evidence/harness/S282_foul_bonus_regime_join_census_2026-09-04.csv`.
Every one of its 1,593 checkpoint games is represented exactly once; 29 are
`JOINED` and 1,564 are `NAMED-EXCLUDED`. Named exclusions are 958
`NO_BRIDGE_EVENT_ID`, 606 `NO_FOUL_STATE_GAME_ID`, and zero
`NON_UNIQUE_BRIDGE_EVENT_ID`.

| Checkpoint games | Joined game clusters | Named-excluded game clusters | Required rail |
|---:|---:|---:|---:|
| 1,593 | 29 | 1,564 | 30 |

## Limit result

The measured cluster count is below the immutable 30-game requirement. Under
S282, the change and the Brier comparison are therefore not attempted. The
frozen `+0.004` bar is unchanged and has not been evaluated.

The acquisition that would unblock a future attempt is either an ESPN-keyed
foul-state capture or a fuller ESPN-to-NBA `game_id` crosswalk. Neither was
created or modified here.

## Test and contract self-check

```text
python -m pytest tests/platformkit/test_s282_foul_bonus_regime.py -q -p no:cacheprovider
1 passed in 0.59s
```

The focused fixture includes three end-to-end games and one deliberately broken
case at each link. It keeps the exact chain narrow and requires every checkpoint
game to receive either `JOINED` or a named exclusion.

- B1-B10: no metric was computed, no existing schema or route changed, no data
  source was changed, and no threshold moved.
- Q1-Q2 and Q4-Q5: no scored comparison or charged trial occurred.
- Q3: the `+0.004` bar is quoted unchanged.
- Q6: this memo reports a calibration-limit result only.
- Q7-Q9: S282 is an S-row with reproduction instead of an eye check; the
  premise was rerun before work, and no scored differential exists below the
  rail.

## NOT VERIFIED

- Candidate-run RSS of 93,790,208 bytes.
- Historical S226 count of 0/62,465.
- Repository-history claim that no arm previously scored this store.
