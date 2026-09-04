# S255 AS-OF Rate Snapshot Producer

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

Machine: local Windows worktree `C:\Users\neelj\nba-track-a16` on branch
`track-a16`. This run is local and writes only the documentation-side artifact
directory named below. No file under `data/` was written.

## Step 0 premise re-measurement

The premise is confirmed. The two existing rate stores are each a single,
undated snapshot and their shared file-system date is after every game in the
S247 archive construct.

| full path | bytes | mtime UTC | schema date/as-of fields | SHA-256 | result |
|---|---:|---|---|---|---|
| `C:\Users\neelj\nba-track-a16\data\cache\team_system\player_rates.parquet` | 71,906 | 2026-06-07T03:04:43.608791Z | none in 28 columns | `60ba3e717ffd9b434fa0783ca17c774f9265be9a6109d536533e785fc97d0c68` | CONFIRMED undated |
| `C:\Users\neelj\nba-track-a16\data\cache\team_system\team_rates.json` | 378,935 | 2026-06-07T03:04:43.649789Z | none in 6,244 recursively inspected key occurrences | `12d1f13c911df9e300e70a775efa341cc3fdc9b85870c19d3c311663b5ff70fa` | CONFIRMED undated |

The fixed S247 archive is
`C:\Users\neelj\nba-track-a16\data\cache\eval_gate\s92_nba_lineup_dynamic_2026-09-03_all.csv`.
It is 38,630,145 bytes and was read in sequential 50,000-row chunks. The
exhaustive `(game, cluster_id)` construct has 661 unique clusters dated
2024-10-25 through 2026-04-06.

## Named dated inputs and snapshot rule

| full path | bytes | resolution | rows | date span | fields used |
|---|---:|---|---:|---|---|
| `C:\Users\neelj\nba-track-a16\data\intelligence\built_signals_sidecar.parquet` | 399,511 | n/a (tabular parquet) | 101,765 | 2022-10-18 through 2026-05-24 | `player_id`, `game_date`, `ft_rate_q50`, `ft_rate_spread`, `ft_n_prior` |
| `C:\Users\neelj\nba-track-a16\data\intelligence\team_tempo_spacing.parquet` | 24,255 | n/a (tabular parquet) | 210 | 2025-10-22 through 2026-04-12 | `team_id`, `game_date`, and seven `team_*_z` rate fields |

The additive producer is
`scripts/platformkit/ingame/asof_rate_snapshot_producer.py` (171 physical
lines). It reads one source store at a time. For every dated source snapshot
date D through the S247 archive end date, it drops missing rate values, then
computes each entity's arithmetic-mean rate fields from only source rows whose
`game_date < D`. The player source also requires `ft_n_prior > 0`.

For every one of the 661 archive clusters dated G, the qualification artifact
selects the latest available player snapshot date and team snapshot date with
each date strictly before G. Therefore all rows feeding a selected rate table
obey `source_game_date < snapshot_date < G`.

## Qualifying fraction and leakage assertion

| construct | qualifying clusters | non-qualifying clusters | fixed denominator | fraction | fixed bar | verdict |
|---|---:|---:|---:|---|---|---|
| every S247 `(game, cluster_id)` | 355 | 306 | 661 | 355/661 | at least 30/661 | MET |

The 306 non-qualifying clusters are retained with `qualifies=false`; none is
removed from the denominator. The exact exhaustive mapping is
`docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv`.

Independent artifact recomputation found 661 rows and 661 unique
`(game, cluster_id)` pairs, with 355 qualifying rows. Both assertions passed
on every qualifying row:

```text
player_snapshot_date < game_date: True
team_snapshot_date < game_date: True
```

The focused test includes a planted future source row. It asserts that the
selected snapshot for a target game uses the earlier snapshot date and retains
only rates formed from strictly earlier source rows. This test passed. No
future snapshot date is attached to any qualifying archive cluster.

## Archived artifacts and reproduction

| artifact | rows | bytes | SHA-256 |
|---|---:|---:|---|
| `S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet` | 76,820 | 565,095 | `0d0697b7402907ed493b429d1f0f44e7afad85ec1aa14019a83e1c24e80f6d6e` |
| `S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet` | 1,434 | 22,677 | `42932c26f308097afbc1187aed2e9e8e2efb176258f213e1c5e492a270e5c00e` |
| `S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv` | 661 | 36,282 | `826f778104453f75bdf1e7517c2f0650bfa0a322318a346ca3a26df1575f487e` |
| `S255_asof_rate_snapshot_producer_2026-09-04/summary.json` | n/a | 1,101 | `74074077f7df81350126ce7bd6a21587f9b93a239adda99a85eaff78ff107cad` |

Both snapshot tables have zero duplicate `(entity_id, as_of_date)` keys.
Reproduce the tables and exact count with:

```text
python -m scripts.platformkit.ingame.asof_rate_snapshot_producer --archive data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv --player-source data/intelligence/built_signals_sidecar.parquet --team-source data/intelligence/team_tempo_spacing.parquet --output-dir docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04
```

The original `player_rates.parquet` and `team_rates.json` SHA-256 values were
rechecked after production and are byte-identical to the Step 0 values.

## Limit verdict, test, and self-check

LIMIT verdict: **MET.** The unchanged 30-cluster bar is exceeded by the
construct result of 355/661. This producer does not re-run S247 or make a
calibration comparison; it supplies the strictly-prior snapshot prerequisite.

```text
python -m pytest scripts/platformkit/ingame/test_s255_asof_rate_snapshot_producer.py -q
1 passed in 2.06s
```

- B1: the mapping enumerates all 661 fixed clusters, including all 306 that do
  not qualify.
- B2, B5, B6, B10: all changes are additive under `scripts/platformkit/ingame/`
  and documentation; no production reader, deployment, flag, register, or
  ledger changed.
- B3 and B4: this is an opt-in artifact with no claim/reclaim path.
- B7 through B9: no render, fitted comparison, or recycled denominator exists.
- Q1 through Q5 and Q9: no scored comparison, preregistration, or interval is
  claimed. Q6: calibration language only. Q7: the 661-row construct is fully
  enumerated. Q8: the named undated-rate premise was re-measured before
  construction.

## NOT VERIFIED

- The new snapshots are an additive prerequisite and have no production caller.
- This row does not establish rate compatibility with the legacy simulator
  schema, player lineups for an individual archive cluster, or any calibration
  outcome; those require a separately specified S247 rerun.
- The team source begins on 2025-10-22, which is why the early archive dates
  remain represented but non-qualifying.
