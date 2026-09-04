# S256 NBA simulator versus line, S255 as-of snapshots

Spec: `docs/evidence/tracking/specs/S256_spec.md`.
Contract self-check: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

## Premise and limit

The exact binding premise was rerun before the CHANGE step. Its output was:

```text
PREMISE cluster_qualification qualifying=355/661
PREMISE archive ticks=79554 games=661
PREMISE market_brier=0.142876712852 recal_null_brier=0.144293050901 market_less_than_null=True
```

The qualification CSV has 355 qualifying game rows. Every one will be joined to the named player and team snapshot dates before the frozen grid is priced; the limit is therefore evaluated on the joined count, not a head sample.

## Preregistration

The preregistration was committed before the first simulator score.

- Path: `docs/evidence/harness/S256_nba_sim_engine_vs_line_v3_asof_2026-09-04/S256_preregistration.md`
- Commit: `afc283a20`
- Embedded LF-prefix seal: `60e3e1d11af2880f7db2dbf4676470af16af6ecc08c402b4608a358928b51721`
- Verification command: `git show HEAD:docs/evidence/harness/S256_nba_sim_engine_vs_line_v3_asof_2026-09-04/S256_preregistration.md | head -n 33 | sha256sum`
- Verification output: `60e3e1d11af2880f7db2dbf4676470af16af6ecc08c402b4608a358928b51721  *-`

The sealed construction fixes six grid targets per joined game (120 through 2520 seconds, spaced by 480), 128 seeded fast-simulator draws, a tied-score remaining-possession limit because the archive has no current score, the 48-hour evaluator purge, and the 3-day nonzero same-matchup embargo.

## Inputs and integrity

The S255 artifact hashes before the run were:

```text
player_rate_snapshots.parquet 0d0697b7402907ed493b429d1f0f44e7afad85ec1aa14019a83e1c24e80f6d6e
team_rate_snapshots.parquet 42932c26f308097afbc1187aed2e9e8e2efb176258f213e1c5e492a270e5c00e
cluster_qualification.csv 826f778104453f75bdf1e7517c2f0650bfa0a322318a346ca3a26df1575f487e
s92_nba_lineup_dynamic_2026-09-03_all.csv f498a7a040201571270183a79a025cd87d91ed5060f244b69964a150eab7d0f6
```

The archive is opened as one bounded 38,630,145-byte store, then released before either snapshot parquet is opened. The three snapshot artifacts are all below 600 KB. The module imports `src.sim.fast_sim` read-only and constructs `TeamModel` directly; it never calls `TeamModel.from_cache` and does not open legacy team-system rate stores.

## Results

The complete selected-tick series, per-game paired-loss series, summary JSON, three-arm table, period table, excluded-cluster census, post-run hashes, and contract self-check are appended after the sealed run completes.
