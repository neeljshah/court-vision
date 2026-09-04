# S256 attempt 1d construct result

Verdict: BEHIND

| arm | Brier | ECE |
|---|---:|---:|
| market | 0.180282739 | 0.108594444 |
| recal_null | 0.178516136 | 0.115852521 |
| simulator | 0.255904134 | 0.135156250 |

Improvement vs recal_null: -0.077387998
Game-clustered 95 pct CI: [-0.156878092, 0.002102095]
Seed: 2561001; denominator: 30 games / 180 ticks.
Q9 series: S256_per_game_paired_loss_series_construct.csv; tick archive: S256_selected_tick_series_construct.csv.
Successor after ACCEPT: the 355-cluster S256 run on the pod. No attempt file reached the pod before ACCEPT.
NOT VERIFIED: construct results do not establish the 355-cluster measurement.

## Construct contract and identity checks

Preregistration: `docs/evidence/harness/S256_nba_sim_engine_vs_line_v3_asof_2026-09-04_prereg_attempt1d.md`.
Its pre-scoring staged-byte seal, verified from `HEAD`, is
`1be7b77791e8b422f1e1a1c4711ef6dec3720090199c28cd34235e8e6f003acf`.

The fixed selection was seed 2561001 from all 355 strict S255 qualifying
clusters, with 30 whole games and six fixed elapsed targets per game
`[120, 600, 1080, 1560, 2040, 2520]`. Every target selected the nearest S92
tick, ties by timestamp then streaming source order. S92 was streamed in
5,000-row CSV chunks and filtered to those games before grid or simulator state
construction. The two S255 parquets were predicate-read only on the selected
games' strict snapshot dates. They contain no game_id field, so the date
predicate is the reconstructible game-to-snapshot join.

The shared `cpcv_evaluate` callback emitted all 180 simulator probabilities:
8 chronological groups, one test group per split, strict redaction, symmetric
3-calendar-day embargo, shared 48-hour same-team purge, and shared 3-day
same-matchup purge. The frozen calibration bar is +0.004. The observed
improvement is below zero, so this is BEHIND; no larger claim is made.

RSS BEFORE SCORING 484.73 MB. RSS AFTER SCORING 489.68 MB. Peak callback RSS
was 489.72 MB, below the 600 MB rail. The CPU route used 32 draws per retained
state after the CUDA route ended without a flushed diagnostic; this did not
change the sealed games, grid, arms, bar, or CPCV scheme.

S255/S92 SHA-256 before equals after:

| input | SHA-256 |
|---|---|
| S92 archive | f498a7a040201571270183a79a025cd87d91ed5060f244b69964a150eab7d0f6 |
| S255 player snapshots | 0d0697b7402907ed493b429d1f0f44e7afad85ec1aa14019a83e1c24e80f6d6e |
| S255 team snapshots | 42932c26f308097afbc1187aed2e9e8e2efb176258f213e1c5e492a270e5c00e |
| S255 qualification | 826f778104453f75bdf1e7517c2f0650bfa0a322318a346ca3a26df1575f487e |

The aggregate tracked `src/` SHA-256 was identical before and after:
`ca212a89b0dcef6936c0b66ada99c4cba1389ef1f6b83f4d2d81062e2886c260`.
The assertion passed. No file reached the pod before ACCEPT.

The strict-date qualification remainder is 306 excluded clusters: 306 lack a
team snapshot date; 4 also lack a player snapshot date; 0 have both dates but
fail strict-prior ordering. No selected game was excluded after selection.

Snapshot `ft_rate_q50` is the only player rate in S255. The output summary's
`fills` enumerates every date and fast-simulator field filled from that date's
league mean through the named `date_mean_ft_rate_q50_scaled_baseline` transform.
Team pace is the selected snapshot date's `team_tempo_z` mean. The distinct
fill field list is `ast_per_min, blk_per_min, dreb_per_min, fg3_pct, fg_mid,
fg_paint, fg_rim, ft_pct, ft_share, height, int_d, oreb_per_min, perim_d,
pf_per_min, self_create, stl_per_min, supp, tov_share, use_per_min, z_3,
z_mid, z_paint, z_rim`.

The Q9 files are below 50 MB: `S256_selected_tick_series_construct.csv`
(53,203 bytes) and `S256_per_game_paired_loss_series_construct.csv` (2,970
bytes). `S256_summary_construct.json` is 87,556 bytes. The per-game series
names cluster_id, timestamp, tick count, both losses, and their paired
difference; its test recomputes one selected game's paired loss from the tick
archive and checks the 30-cluster denominator.

The successor, after an ACCEPT decision on this row, is the full 355-cluster
run on the pod. This construct result is not that successor run.

Validation lines:

`python -m pytest scripts/platformkit/ingame/test_s256_nba_sim_engine_v3.py -q -p no:cacheprovider` -> 1 passed.

`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed.
