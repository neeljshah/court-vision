# Tennis Analytics Playbook

Read [README.md](README.md) first for the pipeline and rules -- this file is
sport-specific detail only.

## Data on disk

| Corpus | Path | Rows | Coverage |
|---|---|---|---|
| Matches | `data/domains/tennis/matches.parquet` | 30,616 | 2015-2025 ATP+WTA |
| Match stats (serve lines) | `data/domains/tennis/match_stats.parquet` | 59,312 | per-match |
| Odds | `data/domains/tennis/odds.parquet` | 33,952 | 2015-2025 |
| Point-by-point | `data/cache/sackmann_pbp/{slam_points,charting_points}.parquet` | 543,772 + 1,853,115 = 2,396,887 | slam 2011-15; charting broader, per-match charted points |
| Fatigue / schedule density (verified claims) | `data/cache/intel_claims/tennis_fatigue_schedule_density.jsonl` | 10,914 claims, 10,914/10,914 verified | 2015-2026, career-to-date + per-year x surface |
| Compiled profiles | `data/cache/profiles/tennis_player_profiles.parquet` | 67,244 | rolling |
| Market | `data/cache/{line,inplay,depth}_history/tennis/` | 39k+ lines / 119k+ ticks / 4 depth-days | 2026-07-03 through 2026-07-15 |

Biggest known gap: point-by-point data is now on disk in bulk, but true
pressure-point splits (deuce points, break-point-as-actually-played
sequences, tiebreak sequencing) are still unbuilt -- no claim family reads
`sackmann_pbp` for those yet. No closed classes for tennis.

## Attribute catalog (`domains/tennis/profiles/attribute_registry.py`)

`serve_dominance` and `return_strength` (mean of charting service/return-point
win rate and match-aggregate serve/return strength where both are available,
DESCRIPTIVE), `pressure_serve` (break-point serve-win delta vs the player's
own baseline, **VALIDATED_MECHANISM** -- the only attribute at this status
in tennis), `second_serve_reliability` (second-serve point win rate,
DESCRIPTIVE), `rally_tolerance` (**BLOCKED**, see below), and
`surface_splits_{serve,return}_{Hard,Clay,Grass}` -- 6 concrete DESCRIPTIVE
attributes (career serve/return win rate per surface, generated from one
family spec, not hand-duplicated).

Note the registry's status enum is deliberately narrow: only `pressure_serve`
carries `VALIDATED_MECHANISM` (its sign/significance replicated across two
independent point corpora); no attribute currently qualifies for
`VALIDATED_CLAIM` (reserved for a future straight passthrough of an
already-verified claims family under a different name).

## Replicated mechanisms (from `prereg_hypothesis_ledger.jsonl`)

- **H1: break-point serve dip** (`delta_bp_minus_nonbp`). A player's serve
  win rate drops on break points relative to their own baseline.
  SURVIVES_PREREG on `slam_points_2011_15` (n=5,345, p=1.74e-17,
  effect=-0.0211) **and** on `charting_points_2016plus` (n=12,910,
  p=2.51e-35, effect=-0.0213) -- same sign, both p<alpha, giving a combined
  **REPLICATED** verdict (n=18,255). This is the mechanism directly behind
  `pressure_serve`.

## Honest NULLs and kills

- **H2: serve-return interaction** (`serve_str:return_str`) -- does serve
  strength x return strength jointly predict the point outcome beyond
  either alone? NULL on the smaller `slam_points_2011_15` corpus (n=8,336,
  p=0.897), but SURVIVES_PREREG on `charting_points_2016plus` (n=727,737,
  p=9.93e-36, effect=-17.77) -- same sign in both, but the combined verdict
  is **FAILED_REPLICATION** because the slam leg does not clear alpha.
  Adjudicated note: the failing leg is the much smaller slam corpus
  (n=8,336 vs n=727,737, same sign both) -- this reads as power-limited,
  not a clean kill, and should be re-tested at equal power once post-2015
  slam point-by-point data lands.
- **`rally_tolerance`** -- **BLOCKED**, registered but not built:
  `charting_points.rally_length` is 100% null by design in the charting
  corpus, and `slam_points.rally` is 78.9% null with missingness that is
  not declared random -- neither clears a usable floor.

## Try these

```
python -m scripts.platformkit.profiles.ask "Carlos Alcaraz pressure serve" --sport tennis
```
```
Entity:     Carlos Alcaraz  (tennis player)
Attribute:  pressure_serve
Window:     career_to_2026
Raw value:  -0.0385406456172398
n:          1206
Status:     VALIDATED_MECHANISM -- built on a mechanism replicated on independent corpora
```

- `python -m scripts.platformkit.profiles.ask "Carlos Alcaraz serve dominance" --sport tennis`
- `python -m scripts.platformkit.profiles.ask "Andre Agassi surface splits serve Hard" --sport tennis`
- `python -m scripts.platformkit.profiles.ask --list --sport tennis` (all 73 attributes: 72 concrete, 1 BLOCKED)

## What would make this deeper

- Real pressure-point splits (deuce points, break-point-as-actually-played
  sequences, tiebreak sequencing) from `sackmann_pbp` -- the raw data
  exists, the build does not.
- A usable rally-length signal in either point corpus, to unblock
  `rally_tolerance` -- both existing rally-length columns are unusable
  (100% null / 78.9% null non-randomly).
- Post-2015 slam point-by-point data, to re-test H2 (serve-return
  interaction) at a sample size comparable to the charting corpus instead
  of the current 88x power imbalance between the two legs.
