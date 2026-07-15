# NBA Analytics Playbook

Read [README.md](README.md) first for the pipeline and rules -- this file is
sport-specific detail only.

## Data on disk

| Corpus | Path | Rows | Coverage |
|---|---|---|---|
| Player boxscores | `data/domains/basketball_nba/player_boxscores.parquet` | 77,744 | 2024-10..2026-04 |
| Games/odds/linescores | `data/domains/basketball_nba/{games,odds,linescores}.parquet` | 1.3k-4.8k | 2022-10..2026-04 |
| Possessions | `data/cache/team_system/{pbp_possessions,legacy_possessions}.parquet` | 39.5k + 508.9k | multi-season |
| Full play-by-play | `data/cache/team_system/pbp/*.json` | 1,192 files | 2025-26 only |
| Quarter box | `data/cache/quarter_box/<gid>_q{1-4}.json` | 4,925 files | 2024-25 + 2025-26 |
| Lineup keystone (stints/on-off/gravity/spacing/matchups) | `data/cache/team_system/lineups/*.parquet` | 10,124 stints / 550 on-off rows / 43 gravity-proxy players / 3,043 lineup-shot rows | 196-game full-pbp subset only |
| Defender matchup states | `data/domains/basketball_nba/defender_matchup_states.parquet` | 37,395 | prior + realized |
| Compiled profiles | `data/cache/profiles/nba_{player,lineup,team}_profiles.parquet` | 58,472 / 40,408 / 2,908 | rolling |

Biggest known gap: the lineup keystone (reconstruction, on/off, gravity,
spacing) only covers the 196-game full-sub-PBP subset -- that corpus has not
grown, so `gravity` is a thin 43-player sample. In-play tick and depth-history
market data are empty stubs for NBA (offseason).

## Attribute catalog (110 attributes, `domains/basketball_nba/profiles/attribute_registry.py`)

Player (11): `gravity` (teammate eFG lift on vs off court, VALIDATED_CLAIM),
`usage_absorption`, `creation` (eFG lift for assisted teammates),
`spacing_contribution`, `rim_pressure_def` (own on/off defensive-points
swing; team rim-defense context carried as ingredients only, not blended),
`shot_zone_three_rate_per36` / `shot_zone_three_efg` / `shot_zone_two_rate_per36`
/ `shot_zone_two_fg_pct` (three vs two-point split -- no rim/mid zone split
exists on disk), `stint_stamina_avg_s`, `stint_minutes_load`. All
DESCRIPTIVE except `gravity`.

Team (5 families, 19 concrete columns): `shot_diet` (6 zone-share columns,
DESCRIPTIVE), `concession` (10 zone-eFG/share-allowed columns, DESCRIPTIVE,
lower is better defense), `transition_rate_allowed` (opponent-mixed proxy,
DESCRIPTIVE), `lineup_continuity_avg_stint_s` (team-level stint-continuity
mechanism, **VALIDATED_MECHANISM**), `pace_proxy_fga_per_game` (shot-volume
proxy, not true possessions, DESCRIPTIVE).

Lineup (4): `spacing` (mean pairwise shot distance, DESCRIPTIVE),
`synergy_residual` (actual net rtg/48 minus talent-sum expectation,
VALIDATED_CLAIM), `continuity_s` (total seconds together, DESCRIPTIVE),
`matchup_net` (net pts/300s vs overlapping lineups, DESCRIPTIVE).

All floors, formulas, and exact source columns are declared per-attribute in
the registry file -- read it directly rather than trusting a summary for
anything you plan to cite precisely.

## Replicated mechanisms (from `data/cache/intel_claims/prereg_hypothesis_ledger.jsonl`)

- **Stint continuity x defensive rebound rate** (`continuity_s`). Longer
  intact 5-man stints predict a higher DREB rate. SURVIVES_PREREG on
  2025-26 (n=94,766, p=1.10e-16), **REPLICATED** on 2024-25 (n=116,960,
  p=1.95e-17, effect=+0.00057) and again on 2023-24 (n=114,948, p=2.87e-16,
  effect=+0.00054) -- three independent seasons, same sign. This backs
  `lineup_continuity_avg_stint_s`'s VALIDATED_MECHANISM status.
- **Lineup spacing x transition frequency** (`spacing_mean_dist:is_transition`).
  Wider-spaced lineups play fewer transition possessions. SURVIVES_PREREG on
  2025-26 (n=213,696, p=8.69e-10, effect=-0.0099), **REPLICATED** on 2023-24
  (n=219,629, p=1.56e-5, effect=-0.0082). Derived `is_transition` label:
  precision 0.172 / recall 0.905 vs the real CDN fastbreak qualifier -- a
  broad early-clock-shot proxy, not a 1:1 fastbreak match.
- **Spacing x late-clock (<=7s) shot efficiency**
  (`spacing_mean_dist:is_late_clock`). SURVIVES_PREREG on 2025-26 (n=213,696,
  p=0.00013, effect=+0.0057), **REPLICATED** on 2023-24 (n=219,629,
  p=0.0098, effect=+0.0039). Shot-clock proxy label: 0.968 agreement with
  the real clock (n=108,614).
- **endQ1 x star_minutes_load** (in-game conditioning). **REPLICATED** on
  2023-24 (n=486, p=0.0028, effect=+0.0040) after first surviving on
  2025-26 -- the in-game state at end of Q1 conditions on how many minutes
  the team's top-3 usage players have already logged.
- **H3_onoff_talent_diff** (lineup-matchup net rating vs on/off talent
  differential) -- a sanity-check mechanism, not novel: **REPLICATED** on
  2024-25 (n=27,958, p=2.93e-150) and 2023-24 (n=27,086, p=1.16e-130).

## Honest NULLs and kills

- **H2_continuity_diff, controlled**: raw continuity-differential effect on
  lineup matchup net rating REPLICATED at the raw level (2024-25 p=0.00028,
  2023-24 p=8.46e-6) but is **CONTROL_KILLED** once talent differential
  (`x3_talent_diff`) is controlled for in both seasons -- the raw signal was
  talent, not continuity.
- **endQ1 x floor_quality_now**: FAILED_REPLICATION on 2023-24 (n=486,
  p=0.1322).
- **Lineup-vs-lineup net rating x rest differential**: NULL (n=22,339,
  p=0.844).
- **Spacing x clutch (<=5pt, <=5min)**: NULL (n=213,002, p=0.343).
- **H1_spacing_diff** (raw and talent-controlled): NULL both variants.
- **BLOCKED** (no usable label exists in the PBP corpus, no proxy invented):
  gravity x drop coverage, ball-handler usage x screen coverage (both need a
  switch/drop coverage-type label that doesn't exist), on-court gravity x
  opponent help-rate (no help-defense rate), gravity x paint touches allowed
  (concession has zone eFG-allowed, not touch frequency), lineup size x
  opponent post-up rate (no player-height column, no post-up shot subtype).

## Try these

```
python -m scripts.platformkit.profiles.ask "Luka Doncic gravity" --sport nba
```
```
Entity:     Luka Doncic  (nba player)
Attribute:  gravity
Window:     season_2025_26
Raw value:  0.0619
Percentile: 99.0888
n:          2282.47
Status:     VALIDATED_CLAIM -- claims re-verified against source data
```

- `python -m scripts.platformkit.profiles.ask "Luka Doncic spacing contribution" --sport nba`
- `python -m scripts.platformkit.profiles.ask "Lakers concession rim efg allowed" --sport nba`
- `python -m scripts.platformkit.profiles.ask "Celtics lineup continuity avg stint" --sport nba`
- `python -m scripts.platformkit.profiles.ask --list --sport nba` (see all 110 attributes)

## What would make this deeper

- `rim_pressure_def` wants per-player on/off rim-attempt-share and rim-eFG
  allowed -- doesn't exist (concession is team-level only, no player split).
- A real shot-zone profile (rim/mid/three per-36) -- no per-player shot-chart
  parquet exists; `atlas_player_shot_profile.parquet`'s own `zones` field
  says "DEFER: no per-zone shot-chart parquet in repo."
- `pace_proxy` as true possessions/48 -- `pace_possession.parquet` exists but
  has no on-disk tricode<->team_id bridge to join it.
- `transition_rate_allowed` opponent-only (current column is ~50%
  opponent-mixed, both teams' transition possessions).
- Coverage-type (switch/drop), help-defense rate, shot-clock field on raw
  PBP, player height, and post-up shot subtype -- none exist anywhere in the
  corpus; five BLOCKED mechanism hypotheses are waiting on these.
- The lineup keystone corpus itself: 196 full-sub-PBP games is thin for
  `gravity` (43 players) -- growing that corpus is the highest-leverage
  single fix for every lineup-level attribute in this registry.
