# MLB Analytics Playbook

Read [README.md](README.md) first for the pipeline and rules -- this file is
sport-specific detail only.

## Data on disk

| Corpus | Path | Rows | Coverage |
|---|---|---|---|
| Statcast pitch-level | `data/cache/statcast/statcast_fuller__{2022,2023}.parquet` | ~721k/season | 2022-2023 |
| Pitch states | `data/cache/ingame/mlb_pitch_states__{2022..2026}.parquet` | ~70k/season | 2022-2026 |
| At-bat states | `data/cache/ingame/mlb_{atbat_,}states__*.parquet` | 13k-42k/season | 2021-2026 |
| Hit coordinates (spray angle) | `data/cache/statcast/savant_hitcoords__{2023,2024}.parquet` | 27,625 (2023); 2024 pending | 2023 landed 07-08 |
| Games/odds/pitchers | `data/domains/mlb/{games,odds,pitchers}.parquet` | ~28k | 2010-2021 |
| Starter table | `data/cache/statcast/starter_table__*.parquet` | ~1,048/season | 2022-2023 |
| Injuries/box/framing | `data/domains/mlb/{injuries,espn_boxscores,catcher_framing_index}.parquet` | 113-3,837 | current era |
| Bullpen fatigue chains (verified claims) | `data/cache/intel_claims/mlb_bullpen_fatigue_chains.jsonl` | 9,060 claims, 9,060/9,060 verified | 2022-2026 |
| Live GUMBO | `data/domains/mlb/gumbo_live/<pk>.jsonl` | 47 games x ~104 ticks | 2026 live |
| Compiled profiles | `data/cache/profiles/mlb_player_profiles.parquet` | 146,262 | rolling |

Biggest known gap: the pre-2022 odds corpus (2010-2021) and the pitch-level
Statcast corpus (2022-2026) are disjoint -- no historical odds exist for the
statcast era, so pitch-derived families cannot be market-joined historically.
Closed classes (do not re-attempt): `ingame_sp_velo_fatigue`,
`mlb_pregame_stack_L3`.

## Attribute catalog (17 base attributes / 121 total incl. grid expansions, `domains/mlb/profiles/attribute_registry.py`)

Batter (8): `platoon_resilience` (on-base delta same-hand vs opposite-hand
pitcher, **VALIDATED_MECHANISM**), `clutch_baseout` (GB-rate delta with RISP
vs not, **VALIDATED_MECHANISM**), `pull_tendency`, `contact_quality` (barrel
share), `discipline_by_count` (swing-rate delta behind vs ahead in count),
`K_avoidance`, `BB_rate`, `chase_rate` (flat out-of-zone swing rate) -- the
other six DESCRIPTIVE.

Pitcher (8): `mix_by_leverage` (breaking-pitch-share delta ahead vs not
ahead in count, **VALIDATED_MECHANISM**), `velo_band`, `TTO_durability`
(xwOBA delta 3rd-time-through vs 1st -- DESCRIPTIVE **by design**: the
closest causal mechanism, starter velo-band x TTO, was tested and failed
replication, see below), `platoon_split`, `whiff_rate`, `gb_tendency`,
`edge_zone_rate` (flat zone-11-14 pitch share), `release_spin_rate` (mean
release spin rate) -- the other seven DESCRIPTIVE.

Catcher (1): `framing` (borderline called-strike rate, **VALIDATED_CLAIM**,
reused verbatim from the already-verified `mlb_framing_claims.jsonl`).

Uniform floor rule: `n` = min of the two compared cell counts for every
split metric (no per-attribute special-casing). Exact ingredient columns and
formulas are in the registry file.

## Replicated mechanisms (from `prereg_hypothesis_ledger.jsonl`)

- **Platoon (pitcher-hand x batter-stand) x pitch type**
  (`platoon_same_hand:is_breaking`). Same-handed matchups shift a pitcher's
  breaking-ball usage. SURVIVES_PREREG (n=366,080, p=1.30e-7,
  effect=-0.0768), **REPLICATED** on an independent 2024 season
  (n=182,220, p=0.000276, effect=-0.0755) -- note an earlier, smaller
  replication attempt (n=50,424) initially came back FAILED_REPLICATION
  (p=0.094); the larger 2024 sample replicated cleanly. Backs
  `platoon_resilience`.
- **Count leverage (ahead/behind) x pitch-mix**
  (`pitcher_ahead:is_breaking`). SURVIVES_PREREG (n=1,177,944, p=1.29e-22,
  effect=-0.0803), **REPLICATED** at two independent sample sizes
  (n=162,383, p=6.37e-7; n=584,705, p=1.55e-17, effect=-0.0989). Backs
  `mix_by_leverage`.
- **Base-out state x contact type (GB/FB)** (`is_risp:two_outs`). Initially
  BLOCKED for lack of base-runner columns; once savant_2024 unblocked those
  columns, SURVIVES_PREREG (n=124,127, p=2.70e-5, effect=-0.116),
  **REPLICATED** on savant_2023 (n=124,280, p=0.0409, effect=-0.056). Backs
  `clutch_baseout`.

## Honest NULLs and kills

- **Starter velo-band x TTO** (`above_avg_velo:tto3`) -- the natural causal
  mechanism behind `TTO_durability`: SURVIVES_PREREG (n=366,080,
  p=2.56e-6, effect=-0.1014), then **FAILED_REPLICATION twice**
  (n=182,220, p=0.067; n=50,424, p=0.686). `TTO_durability` stays
  DESCRIPTIVE because of this explicit kill.
- **Pitch-mix diversity x TTO**: NULL (n=366,080, p=0.195).
- **Fielding alignment (shift) x batter stand x BABIP**: NULL (n=236,633,
  p=0.0516).
- **Pull-tendency x infield alignment**: NULL on the unblocked test
  (n=52,334, p=0.521), then FAILED_REPLICATION (n=51,894, p=0.175) -- the
  2023 test never survived prereg, so the 2024 replication was not
  attempted on the merits.
- **Launch-angle tightness x park factor**: NULL on both 2023 (p=0.371) and
  2024 (p=0.837).
- **Catcher framing x count leverage**: NULL (n=111,713, p=0.885), then
  FAILED_REPLICATION (n=107,528, p=0.0021).
- **BLOCKED**: bullpen fatigue-chain x leverage (no `leverage_index`
  column, no proxy invented), catcher framing x pitch location (isolating
  called-strikes needs a separate leak-safe build, not run this pass),
  sprint-speed x infield-alignment (`sprint_speed` is a Statcast
  *leaderboard* stat, not a per-pitch column -- not obtainable from this
  endpoint).
- **Composed PA-outcome model** (`pa_outcome_v2_composed`): logged as
  `SHIP_PROVISIONAL_RETROSPECTIVE` but adjudicated NOT deployable -- the
  lift is almost entirely `count_leverage_mix_share`, a rollup of the plate
  appearance's own realized pitch sequence (hindsight relative to the first
  pitch). The pregame-only analogue (`pa_outcome_v2b_pregame`, using an
  as-of pitcher mix-while-ahead profile) came back **NULL** (candidate log
  loss 1.41297 vs league 1.40231).

## Try these

```
python -m scripts.platformkit.profiles.ask "Charlie Blackmon platoon resilience" --sport mlb
```
```
Entity:     Charlie Blackmon  (mlb player)
Attribute:  platoon_resilience
Window:     season_2024
Raw value:  -0.005308726361357929
n:          114.0
Status:     VALIDATED_MECHANISM -- built on a mechanism replicated on independent corpora
```

- `python -m scripts.platformkit.profiles.ask "Charlie Blackmon contact quality" --sport mlb`
- `python -m scripts.platformkit.profiles.ask "Justin Turner discipline by count" --sport mlb`
- `python -m scripts.platformkit.profiles.ask --list --sport mlb` (all 17 base attributes)

## What would make this deeper

- `fielding_alignment_conditioning` -- if/of alignment x batter stand ->
  BABIP/xwOBA descriptive splits. Data is already on disk, this is an
  unbuilt (`leverage_rank: 3`) family, not a data gap.
- A `leverage_index` derivation for bullpen-fatigue x leverage: no
  win-probability or leverage column exists, and no coarse late-inning +
  close-score proxy has been declared acceptable.
- A leak-safe catcher framing x pitch-location split: `description` now
  exists to isolate called strikes, but the leak-safe build itself hasn't
  been run.
- Ingesting `sprint_speed` from the Statcast leaderboard endpoint (it is not
  a per-pitch column, so the current pitch corpus can't carry it).
- Bridging the 2010-2021 odds corpus to the 2022-2026 pitch-level corpus --
  currently disjoint, so no pitch-derived family can be market-joined
  historically.
- `pitch_arsenal_profiles` and `batted_ball_quality_profiles` are PARTIAL
  builds; `count_leverage_transitions` is PARTIAL.
