# S145 / S149 wallclock LOC and S116 archive

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Premise (Q8)

`wc -l scripts/platformkit/venue_history/nba_wallclock_join.py` was 313; duplicate empty-frame
blocks were lines 117-120 and 125-128. The master S116 CSV had 23 columns and neither raw field.

## Change and reproduction

`_empty_join_frame` owns both empty cases; the module is 282 LOC and its rail is unchanged.
The pre-change four fixtures plus cached event 401869406 (140 rows) were saved at
`C:/Users/neelj/AppData/Local/Temp/cx_s145/prechange_join_outputs.pkl`, SHA-256 `0fd0fd73c8b2498d78a1196cdc722b907a77893abbf028edc15e59fcb76c75d5`; all five inputs remain byte-identical.

The writer appends `model_raw` and `market_raw`; A2 uses those NBA fields and skips a pre-additive archive.
The no-refit scratch CSV is `C:/Users/neelj/AppData/Local/Temp/cx_s145/s116_pooled_ingame_2026-09-03_regenerated.csv`, SHA-256 `8a56e2a94dc2a699f74a4ee259835031f716be86ab7a4c38ae75b3fa2bde1483`:
202,304 rows, 25 columns, and its own raw NBA fields reproduce `n=192635`, `n_informative=78761`.

| Metric | Before | After | n |
|---|---:|---:|---:|
| LOC/equal-output and self-contained count | 0/2 | 2/2 | 2 (CONSTRUCT) |

All four fixtures, the replay, and every scratch NBA row are included. Reproduction uses
`flag_ticks(cluster, ts_utc, market_raw, model_raw)`; no render or landed-data write applies.

## Focused verification

- Wallclock join/tolerance/checkpoints/asof: 8, 1, 10, and 5 passed, respectively.
- S116 synthetic: 8 passed; A2: 1 skipped (no landed `data/` archive in this worktree).
- New wallclock LOC guard: 1 passed.

## Contract self-check

B1 all units are named; B2 is additive and readers checked; B3-B4 add no gate or claim state; B5 no deployment.
B6 no moved module; B7 no sampled render; B8 no fit comparison; B9 has distinct row/event units; B10 preserves rails.
Q1-Q2 are inapplicable and no ledger opened; Q3 unchanged; Q4 no new score or fit; Q5 no AHEAD label; Q6 calibration language.
Q7 constructs two cases; Q8 measured premises first; Q9 archives or reconstructs raw state. NOT VERIFIED: the data-backed A2 path lacks its
read-only junction; the required count was independently reproduced from the scratch CSV.
