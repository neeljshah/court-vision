# Soccer Analytics Playbook

Read [README.md](README.md) first for the pipeline and rules -- this file
covers the club-league domain (`domains/soccer`); international/national-team
data lives in a separate `soccer_intl` corpus not covered by this registry.

## Data on disk

| Corpus | Path | Rows | Coverage |
|---|---|---|---|
| StatsBomb events | `data/cache/statsbomb/events/<mid>.json` | 4,235 match event files | 2015-2021 open data |
| Match stats | `data/domains/soccer/match_stats.parquet` | 25,834 | 2015-2026 |
| Odds | `data/domains/soccer/odds.parquet` | 16,322 | O/U open/close -- **raw decimal odds**, needs devig before use as a probability |
| ESPN player stats | `data/domains/soccer/espn_player_stats.parquet` | 1,290 | current |
| Referee card/foul profiles (verified claims) | `data/domains/soccer/referee_card_foul_profiles.parquet` (10,251 rows) + `data/cache/intel_claims/soccer_referee_card_foul_profiles*` | 2,736 claims, 2,736/2,736 verified | 2015-2026, per-year + per-league (E0/E1) |
| Compiled profiles | `data/cache/profiles/soccer_team_profiles.parquet` | 16,098 | rolling |
| Market | `data/cache/line_history/soccer/` | 839,128 rows; in-play tick history is an empty stub | 2026-06/07 through 07-08 |

Biggest known gap: event data (the only corpus with possession-level detail)
covers only 4,235 StatsBomb match event files ending 2021 -- none of the 25,834-match
odds corpus has matching events, so attribute-to-market joins are limited to
the event-covered window. Closed class (do not re-attempt): `home_sot_replication`.

## Attribute catalog (25 attributes, `domains/soccer/profiles/attribute_registry.py`, team-only)

The original 7: `counter_threat` (counter-attack goal threat, weighted by
danger, **VALIDATED_MECHANISM**), `buildup_quality` (regular-play attacking
output per possession, **VALIDATED_CLAIM**), `set_piece_threat` (share of a
team's total xG from set-piece-derived possessions, **VALIDATED_CLAIM**),
`formation_flexibility` (1 - share of matches on the primary formation,
**VALIDATED_CLAIM**), `defensive_solidity` (xG conceded per opponent
possession, DESCRIPTIVE, lower is better), `finishing_overperformance`
(goals minus a shots-based proxy xG, DESCRIPTIVE), `home_strength` (home
points-rate normalized 0-1, DESCRIPTIVE).

The 07-08 expansion added 18 more (all DESCRIPTIVE unless separately
replicated): `away_goal_rate`, `away_strength`, `clean_sheet_rate`,
`comeback_rate`, `corner_rate`, `defensive_counter_threat`,
`defensive_set_piece_threat`, `discipline_rate`, `first_half_xg_share`,
`foul_rate`, `formation_primary_xg`, `formation_secondary_xg`,
`home_goal_rate`, `possessions_per_match`, `second_half_xg_share`,
`shot_accuracy`, `shot_conversion_rate`, `shots_per_possession` -- full list
via the `--list` command below.

All corpus="statsbomb_event" attributes floor at >=30 team-matches;
`finishing_overperformance`/`home_strength` (corpus="footballdata_season")
floor at 20/10 team-season(-home)-matches respectively.

## Replicated mechanisms (from `prereg_hypothesis_ledger.jsonl`)

- **Counter-attack xG premium.** Counter-attack possessions carry a higher
  xG-per-possession than regular play. SURVIVES_PREREG on the full corpus
  (n=31,395, p=8.09e-34, effect=+0.0435), and independently on both
  within-corpus year splits: matches through 2018 (n=20,317, p=1.60e-21,
  effect=+0.0398) and 2019 onward (n=11,078, p=9.72e-14, effect=+0.0511) --
  same sign, both well past alpha, giving a **REPLICATED** verdict via
  within-corpus year-split replication (no independent second source is
  currently available). This is the mechanism directly behind
  `counter_threat`.

## Honest NULLs and kills

No NULL or FAILED_REPLICATION hypotheses are logged for soccer in the
current ledger -- the one preregistered hypothesis tested so far
(counter-attack xG premium) replicated. The honest gap here is what was
never testable at all -- three attributes are **BLOCKED**, registered but
not built:

- **`press_resistance`** (possessions lost in a team's own defensive third)
  -- StatsBomb's `location` field is pitch-absolute (0-120 x 0-80), not
  normalized to attacking direction, and attacking direction flips at
  half-time and period boundaries. No attacking-direction resolver exists
  anywhere in this codebase. A wrong-sided proxy would silently invert the
  attribute (a team's "own-third" losses would read as the opponent's), so
  this was BLOCKED rather than shipped wrong.
- **`lead_trail_score_state`** -- same class of silent-wrong-side risk:
  attaching a running score state correctly needs per-period end-swap logic
  (extra-time periods 3-5 must continue the running score, not reset it)
  that is not cheap or safe to improvise here.
- **`late_goal_share`** -- the season-level `footballdata_season` corpus
  only carries match-level goal columns (fthg/ftag/hthg/htag, shots, cards),
  never a per-goal minute. StatsBomb does carry per-event minutes but is a
  different (4,235-match-event-file) corpus than the one this attribute was
  asked against, so this was BLOCKED rather than silently substituting a
  different corpus's window.

## Try these

```
python -m scripts.platformkit.profiles.ask "Manchester City counter threat" --sport soccer
```
```
Entity:     Manchester City WFC  (soccer team)
Attribute:  counter_threat
Window:     statsbomb_2015_2021
Raw value:  0.0011893359221132897
n:          36
Status:     VALIDATED_MECHANISM -- built on a mechanism replicated on independent corpora
```

- `python -m scripts.platformkit.profiles.ask "Arsenal defensive solidity" --sport soccer`
- `python -m scripts.platformkit.profiles.ask "Chelsea formation flexibility" --sport soccer`
- `python -m scripts.platformkit.profiles.ask --list --sport soccer` (all 25 attributes)

## What would make this deeper

- An attacking-direction resolver for StatsBomb's pitch-absolute
  coordinates -- the blocker on `press_resistance` and `lead_trail_score_state`,
  and on any future own-third / final-third attribute.
- Extending event coverage past 2021 -- the 4,235-match-event-file StatsBomb
  open-data corpus is the only source with possession-level detail, and it stops
  there while the 25,834-match season corpus runs through 2026.
- A proper devig of `odds.parquet` (currently raw decimal odds, not
  probabilities) before any attribute-to-market comparison.
- Club in-play tick history is an empty stub -- no in-game conditioning
  attribute is buildable for soccer until that lands.
