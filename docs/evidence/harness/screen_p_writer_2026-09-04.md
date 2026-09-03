# S175 screen p writer

## Verdict: ACCEPT

The premise remains confirmed on the historical S85 store: it has 1,302 result rows (958 T0 and 344 T1), 20 result columns without `screen_p`, and every historical T1 artifact carries `archive.screen_p`.

The additive writer copies `result.archive["screen_p"]` into the top-level record row when present. No existing result field, SQL path, archive content, ledger, register, or production data changed.

## ATTEMPT 2 -- complete reproducible rerun

The required five-family S85 screen population was seeded into a fresh worktree scratch SQLite and drained with `foundry_runner`, `--predictor real`, charges off, `--screen-rows 800`, and `--idle-exit`. The runner reached its idle pass. Its scratch ledger path was not created.

The rerun recorded 344 T0 rows, 344 T1 rows, and 0 T2 rows. Every recorded T1 row is included: 344/344 top-level `screen_p` values equal that row's artifact JSON `archive.screen_p` within 1e-12. The required family counts are `nba_opp_allowed` 120, `soccer_style_fingerprints` 112, `nba_player_adv` 48, `nba_player_value_features` 32, and `mlb_bullpen_relief_chains` 32.

Committed reproduction artifacts:

- `docs/evidence/harness/S175_screen_p_rerun_2026-09-03.json` contains the scratch SQLite location, runner settings, result counts, and all 344 row-level hash/tier/family/screen_p/artifact-path/archive-parity records.
- `docs/evidence/harness/S175_screen_p_family_values_2026-09-03.json` contains the five ordered `ResultsDB.family_p_values(family, tier='T1')` lists with their result IDs in ascending order.

## Before and after

| Check | Before | ATTEMPT 2 rerun |
|---|---:|---:|
| Result `screen_p` column | absent in historical S85 store | present in scratch schema |
| T1 values matching artifact `archive.screen_p` | 0/344 | 344/344 |
| Required T1 denominator | 344 | 344 |
| Scratch ledger rows | n/a | 0 |

## NOT VERIFIED

- The historical S85 database is evidence for the original missing column, not a replacement for the ATTEMPT 2 scratch rerun.
- No charged tier, FWER conclusion, or claim beyond the storage/indexing reproduction was evaluated.

## Verifier self-check

- B1: every T1 result the rerun recorded is in the 344-row denominator; none is excluded.
- B2: the writer is additive, the existing field/status set remains intact, and the original untiered `family_p_values` SQL is unchanged.
- B3-B6: no gate, absent-evidence behavior, claim path, deployment, module move, register, or ledger changed.
- B7/B9: this is a complete database reproduction, not a sampled render or fitted residual.
- B10/Q3: the 344/344 bar is unchanged and met.
- Q1-Q5/Q9: this is a storage/indexing reproduction, not a new scored comparison or AHEAD claim.
- Q6: wording is calibration and storage only.
- Q7: the reproduction artifact enumerates all recorded T1 rows.
- Q8: the premise was re-measured before the additive writer change.
