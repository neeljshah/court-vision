# S223 intelligence-pool AS-OF census (2026-09-04, attempt 2c)

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Machine: local Windows worktree `C:\Users\neelj\nba-track-a15`. This is a
read-only parquet census; no producer, deployment, or data write ran.

## Attempt 1 visibility artifact

Attempt 1 (commit `1a2c19d2d443db0606bef711425342cc214096bd`) saw neither
the atlas nor intelligence stores and emitted two no-match rows. That was a
worktree-visibility artifact, not a census of the intended stores.

## Attempt 2 visibility artifact

Attempt 2 (commit `430010aeb080133095f913c5c0af7394d4ef13d8`) saw the 99
intelligence stores through the junction but no atlas files. Its 0-of-45 atlas
result was also a visibility artifact. The verifier rejected that result.

## Attempt 2b row-group-0 defect

Attempt 2b (commit `fa85c108438ee597a4d1c6eacf605d071b9d012a`) inspected only
row group zero for each selected temporal column. A synthetic two-row-group
store measured one distinct date instead of two. The verifier rejected that
sampling defect; it was not a store or producer action.

## Attempt 2c observed census and construct

The construct for this census is EVERY `data/cache/atlas_*.parquet` file
present when it runs: 59 files today, plus every 99 present intelligence files.
All 59 atlas files were enumerated. The frozen specification's n=45 is not used
as a selector and no visible file is omitted.

The current 59-file count is reconciled against the specification numeral by a
deterministic alphabetical addendum only. Positions 46 through 59 below are the
14 names beyond the first 45 sorted paths; this is not a substitute 45-file
construct or a filter on the census:

- `atlas_wnba_player_clutch_margin.parquet`
- `atlas_wnba_player_defense_activity.parquet`
- `atlas_wnba_player_ft_profile.parquet`
- `atlas_wnba_player_playmaking.parquet`
- `atlas_wnba_player_rotation.parquet`
- `atlas_wnba_player_shooting_profile.parquet`
- `atlas_wnba_player_shot_zones.parquet`
- `atlas_wnba_player_usage_volume.parquet`
- `atlas_wnba_team_bench_hustle.parquet`
- `atlas_wnba_team_defense_allowed.parquet`
- `atlas_wnba_team_lineup_exposure.parquet`
- `atlas_wnba_team_officials_venue.parquet`
- `atlas_wnba_team_pace_shooting.parquet`
- `atlas_wnba_team_rotation.parquet`

The sampled premise is falsified on the full temporal-column scan: 55 of 59
atlas files are SNAPSHOT-ONLY and four are AS-OF SAFE. Their whole-store
cardinalities are 2, 8, 70, and 146. The checkpoint recount reproduces 5 of
1,593 distinct games and 915 of 465,249 ticks strictly after `2026-05-31`.

## Read discipline and labels

Each target was size-checked before inspection and opened one file at a time.
The helper reads parquet schema and row metadata, then streams only the selected
temporal column with `iter_batches(columns=[column], batch_size=1000)`. No
target exceeds the 300 MiB rail; the checkpoint recount is a separate
2,829,826-byte exact scan of `game_id` and `game_date`. No producer ran and no
file under `data/` was written.

`AS-OF SAFE` means the selected temporal field has more than one distinct date
across its full batched scan. `SNAPSHOT-ONLY` requires a true AS-OF field with
exactly one distinct date across that scan. A singleton `game_date` does not
become a snapshot: `as_of_column = asof_column or date_column` preserves that
field for disclosure, while `if asof_column and n_distinct == 1` leaves it
UNDATED.

| group | AS-OF SAFE | SNAPSHOT-ONLY | UNDATED | total |
|---|---:|---:|---:|---:|
| every present atlas file | 4 | 55 | 0 | 59 |
| present intelligence | 45 | 0 | 54 | 99 |
| all emitted rows | 49 | 55 | 54 | 158 |

The deterministic per-store output is
`docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.json`. Every row
names its path, size, metadata row count, schema/grain fields, temporal fields,
classification field, whole-column date cardinality and bounds, label, producer
or `NONE`, and error. There are zero unreadable present rows.

Q6 handling: source basenames are opaque identifiers quoted verbatim under the VERIFIER_CONTRACT Q6 NOTE (orchestrator ruling 2026-09-04).

## Premise denominators and NOT VERIFIED

| premise | observed result | status |
|---|---:|---|
| census atlas construct | every present atlas file | 59 files, fully enumerated |
| frozen specification numeral | n=45 without a named roster | preserved, not used as a filter |
| singleton atlas AS-OF finding | 55 snapshot-only, 4 safe of 59 | falsified for observed mount |
| checkpoint dates after `2026-05-31` | 5 of 1,593 games; 915 of 465,249 ticks | reproduced |

## NOT VERIFIED

- The frozen n=45 specification does not provide a named membership roster, so
  the historical 45-file membership cannot be reconstructed from its numeral.
- No atlas join, walk-forward evaluation, or predictive conclusion was run.
- Temporal cardinality alone does not establish the provenance or availability
  timing of any row beyond the observed selected field.
- The artifact date follows the S223-required evidence filename; execution was
  performed on 2026-09-03.

## Reproduction and checks

```text
C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m scripts.platformkit.intel_pool_asof_census --root C:\Users\neelj\nba-track-a15 --output docs\evidence\harness\S223_intel_pool_asof_census_2026-09-04.json --atlas-as-of 2026-05-31
observed counts: AS-OF SAFE=49 SNAPSHOT-ONLY=55 UNDATED=54 total=158
observed groups: atlas=59 intelligence=99
checkpoint: 5 of 1593 games, 915 of 465249 ticks after 2026-05-31

C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_intel_pool_asof_census.py -q
4 passed in 0.62s

C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests\platformkit\test_loc_rail_scope.py -q
1 passed in 2.06s
```

The module measured 251 physical lines and the focused test measured 70 lines;
both remain below the 300-LOC rail. Source SHA-256:
`294FFC7500A441DE2227A9C42C83959239296E2FE095572EA41EC0D34CB765CE`.
JSON SHA-256:
`237C9E831D12BBDD1B557853D64D6763D84EC0EC71DA0945CEA001CDED256F7D`.

Section B self-check: every visible path has an emitted row (B1, B7), field
semantics remain additive (B2), no producer or deployment ran (B5), no reader
was removed (B6), and the 300 MiB rail is unchanged (B10). This construct
census has no fitted comparison, threshold change, or launch claim. Calibration
language only.
