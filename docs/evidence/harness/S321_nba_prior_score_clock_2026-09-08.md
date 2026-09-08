VERDICT: INSUFFICIENT -- binding M0 premise falsified before any scored comparison.

# S321 NBA prior plus score-clock calibration preparation

This memo cites `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Sign convention for any future comparison: improvement = baseline loss minus candidate loss; positive = candidate better.

Input opened locally with `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`:
`data/cache/inplay_odds/nba_checkpoints_full.parquet`, 2,829,826 bytes, tabular 465,249 rows x 13 columns; resolution not applicable.
The column-only binding audit found no `M0` field and no pre-start probability timestamp field. `market_prob` is present only on in-game rows (periods 1-6), so it is not substituted for M0.

| season | games | valid pre-start M0 games | live ML games | active ticks | canonical landmarks | all 7 regular | OT starts |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-25 | 656 | 0 | 656 | 90,245 | 178 / 152 games | 0 | 31 |
| 2025-26 | 937 | 0 | 937 | 130,821 | 257 / 218 games | 0 | 45 |

The binding floor is at least 400 valid M0 games in at least two seasons. Both seasons are zero, so the premise is FALSE and S321 stops as specified.
`active ticks` uses `not (period >= 4 and game_clock_s == 0)`; S309's canonical all-row denominator is otherwise retained. Regular landmarks use total remaining seconds `(4-period)*720+game_clock_s` at 2400, 1800, 1200, 600, 300, 120, 60; each OT start is clock 300. The earliest `(ts, row_index)` per game-landmark is canonical.

Artifact: `docs/evidence/harness/S321_nba_prior_score_clock_2026-09-08/premise_counts.csv` (313 bytes, LF-normalized SHA-256 `766c66c6c80414cdc9c3f8afba3d63cc06eb37689abb6c3900234698762e609f`).
Input raw-byte SHA-256: `5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5`. LF-normalized SHA-256s: S309 route `d37f82965c069348eed65d187712605e6ead3197620c91062fa5795b3f1d9587`; S321 spec `4517722c1fa176fe54f6d9b0587f7d1de0b3d6b848c0f89a3a0b4ac814ad32dd`; verifier contract `63d8d126ea26492a12ecab2e74b48d736d30fc626c1162a338acaae6ddb2c341`.

No preregistration was written or sealed because no scored comparison was permitted after the premise failed. No model, comparer, test, evaluator, bootstrap, shuffle, ablation, or family correction was run. Q1, Q2, Q4, and Q9 therefore have no scored artifact to apply to; no register or ledger was touched. S320 is not landed on master at this audit, but no finisher is dispatched because the prior prerequisite is absent.
The sandbox denied `git add` on this worktree's external index lock. The orchestrator must commit these two evidence paths by explicit pathspec through `lane_commit`; they remain ready on disk.
Self-check: B1-B10 have no changed production schema or score; Q3 is untouched; Q5 has no calibration pass; Q6 calibration language only. No files under `src/`, `data/`, registers, ledgers, or flags changed. Eye check: NONE.

Proposed ledger line (not appended): `2026-09-08 | in-game calibration | S321 | M0 absent in source; 0 valid pre-start M0 games in 2024-25 (n=656) and 2025-26 (n=937) | INSUFFICIENT`
Wall time: approximately 18 minutes local preparation and binding audit; no pod job launched.

## NOT VERIFIED

- Any M0 source outside the specified parquet, model fit, scored comparison, Bar C decision beyond INSUFFICIENT, or proposed integration.
- Per-corpus tick CSVs, bootstrap table, reliability bins, shuffle, and ablation; they are not created after the mandatory premise stop.
- S320 completion, deployment, flags, registers, ledgers, or any broader calibration result.
