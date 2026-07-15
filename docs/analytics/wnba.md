# WNBA Analytics Playbook

Read [README.md](README.md) first for the pipeline and rules -- this file is
sport-specific detail only.

## Data on disk

| Corpus | Path | Rows | Coverage |
|---|---|---|---|
| Player boxscores | `data/domains/wnba/player_boxscores.parquet` | 4,697 | built 2026-07-08 |
| Play-by-play | `data/domains/wnba/cdn_backfill/<gid>/playbyplay.json` | 507 game dirs | built 2026-07-08 |
| Lineup keystone (stints/on-off/gravity/spacing/matchups) | `data/cache/team_system/lineups/*_wnba_2026.parquet` | 8,324 stints / 320 on-off rows / 104 gravity-proxy players / 2,195 spacing rows / 4,972 matchup rows | built 2026-07-08, at parity with NBA |
| CDN checkpoint states (legacy) | `data/domains/wnba/cdn_backfill_states.parquet` (+168 raw game dirs) | 504 | 3 checkpoints/game |
| Scoreboard/linescores | `data/domains/wnba/{espn_scoreboard,linescores}.parquet` | 776 | 2024-05..2026-07 |
| Context (injuries/referee/schedule/attendance) | `data/domains/wnba/{injuries,referee_crew_foul_rate,schedule_density,arena_attendance_context}.parquet` | 35-1,540 | current |
| Compiled profiles | `data/cache/profiles/wnba_{player,lineup}_profiles.parquet` | 3,476 / 1,246 | rolling |
| Market | `data/cache/{line,inplay,depth}_history/wnba/` | 20k+ lines / 200k+ ticks / 4 depth-days | 2026-07 through 07-08 |

Biggest known development: player boxscores and full play-by-play landed
2026-07-08, and the complete lineup keystone (reconstruction, on/off,
gravity, spacing, matchups) is now built at parity with the NBA pipeline --
the old 3-checkpoint-per-game `cdn_backfill_states` corpus is superseded as
the lineup source. `lineup_exposure_descriptors` (built on the old
checkpoint-string recipe) has not yet been re-derived from the new
stint-level `lineup_key`. No closed classes for WNBA yet.

## Attribute catalog (31 attributes: 28 player + 3 lineup, `domains/basketball_wnba/profiles/attribute_registry.py`)

Player (28): the original 8 -- `on_court_impact` (team net rating on-court,
**VALIDATED_CLAIM**), `gravity` (teammate eFG lift on vs off,
**VALIDATED_CLAIM**), `scoring_per36` / `reb_per36` / `ast_per36` / `efg` /
`usage_proxy_per36` (box-derived rates, all **VALIDATED_CLAIM** --
independently re-verified by `wnba_player_form_claims.jsonl` via a genuinely
different recompute path), `recent_form` (last-10-games minus full-season
pts/36, DESCRIPTIVE -- a window *delta* is not expressible in the shared
claims grammar's single-window aggregate, so it stays DESCRIPTIVE regardless
of the other claim families) -- plus 20 added in the attribute expansion:
zone shooting (10, DESCRIPTIVE: rim/paint/mid/corner3/above-break-3 share and
eFG%), `assisted_share` (1, DESCRIPTIVE), defensive on/off zone-allowed
deltas (4, DESCRIPTIVE: rim share/eFG allowed and three share/eFG allowed,
on-court minus off-court), and last-10 variants (5, DESCRIPTIVE:
`scoring_per36_last10` / `reb_per36_last10` / `ast_per36_last10` /
`efg_last10` / `usage_proxy_per36_last10`).

Lineup (3): `spacing` (mean pairwise shot distance, **VALIDATED_CLAIM**),
`matchup_net` (net pts/48 vs overlapping lineups, melted from both matchup
sides, DESCRIPTIVE), `minutes_together` (total shared floor time,
DESCRIPTIVE).

Important nuance specific to this registry: `VALIDATED_CLAIM` here means the
formula's arithmetic was independently re-verified against source data by a
separate claims-store validator -- it is **not** a claim that the attribute
causally predicts anything. No WNBA attribute currently carries
`VALIDATED_MECHANISM`.

## Replicated mechanisms

None yet. Unlike NBA (stint-continuity x DREB, spacing x transition, spacing
x late-clock) and the other three sports, no prereg hypothesis for WNBA has
been logged in `prereg_hypothesis_ledger.jsonl` -- the lineup keystone data
needed to run those same tests (stint continuity, spacing, gravity) only
landed 2026-07-08, at parity with the NBA corpus that produced its own
replicated mechanisms. Running the same preregistered hypothesis battery
against the new WNBA keystone is the natural next step, not yet done.

## Honest NULLs and kills

None logged -- because no hypothesis has been tested against WNBA data yet
(see above). This is an honest gap, not a hidden one: do not assume WNBA
attributes carry the same causal backing as their NBA analogues just because
the underlying keystone pipeline is now built at parity.

## Try these

```
python -m scripts.platformkit.profiles.ask "Breanna Stewart gravity" --sport wnba
```
```
Entity:     Breanna Stewart  (wnba player)
Attribute:  gravity
Window:     season_2026
Raw value:  0.0040999999999999925
n:          321.0
Status:     VALIDATED_CLAIM -- claims re-verified against source data
```

- `python -m scripts.platformkit.profiles.ask "Sabrina Ionescu usage proxy per36" --sport wnba`
- `python -m scripts.platformkit.profiles.ask "Jonquel Jones on court impact" --sport wnba`
- `python -m scripts.platformkit.profiles.ask --list --sport wnba` (all 31 attributes)

## What would make this deeper

- Run the same preregistered mechanism battery already validated on NBA
  (stint continuity x DREB, spacing x transition, spacing x late-clock)
  against the new WNBA lineup keystone -- the data now exists at parity, the
  tests have not been run.
- Re-derive `lineup_exposure_descriptors` from the new stint-level
  `lineup_key` instead of the stale 3-checkpoint-based recipe.
- True `usage_proxy_per36` -> real USG% needs a per-game team on-court join
  the shared claims grammar can't currently express -- same documented
  limitation as its MLB/NBA analogues.
- `matchup_net` and `minutes_together` have no independent claims-store
  corroboration yet (their two-sided melted-lineup aggregates aren't
  expressible in either existing claim family's grammar) -- both stay
  DESCRIPTIVE until that changes.
