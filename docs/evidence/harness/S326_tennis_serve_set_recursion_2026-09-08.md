VERDICT: INSUFFICIENT (PREMISE FALSIFIED)

# S326 Tennis Serve/Set Recursion

Machine: LOCAL, conda `basketball_ai`; this is a bounded premise read, so no pod job
was needed. Interpreter: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (Q1-Q9 and B1-B11 checked).

## Binding before-condition

The required re-measurement was run before a preregistration, model, scorer, or
comparison. `domains/tennis/ingest_ingame_states.py:9` defines `p0` as the
pre-match walk-forward Elo win probability; its builder imports the Elo routine at
line 241 and assigns `win_prob_p1` at line 274. Thus `p0` is a rating for both tours.
The price archive was scanned one row group at a time: 10 groups, 1,854,100 rows,
986 event keys, `moneyline` only, and game-date span 2026-05-24..2026-07-08.
The state archives end in 2025, yielding zero overlapping game dates and zero
joinable matches for each tour. This is the exact S326 stop condition: no
market-implied pre-match probability can join at least 500 matches in two seasons.

| tour | matches | states | p0 matches | date span | seasons | server columns | joinable prices |
|---|---:|---:|---:|---|---:|---:|---:|
| ATP | 29,572 | 40,516 | 29,572 | 2015-01-04..2025-12-17 | 11 | 0 | 0 |
| WTA | 11,016 | 14,559 | 11,016 | 2015-01-19..2025-11-01 | 11 | 0 | 0 |

Retirements were excluded before state generation at
`domains/tennis/ingest_ingame_states.py:243-245`; no retirement state was scored.
No state schema carries the server, so a future eligible run would use the sealed
game-grain alternation rule. The target would be match-winner calibration, not a
total-games line; no quoted total line join was available. Eye check: NONE.

## Inputs and archive

| source opened (local resolved path) | bytes | rows |
|---|---:|---:|
| `C:\Users\neelj\nba-track-a11\data\cache\ingame\tennis_states__atp.parquet` | 783216 | 40516 |
| `C:\Users\neelj\nba-track-a11\data\cache\ingame\tennis_states__wta.parquet` | 285269 | 14559 |
| `C:\Users\neelj\nba-track-a11\data\cache\ingame\tennis_gamestate__atp.parquet` | 557856 | 48512 |
| `C:\Users\neelj\nba-track-a11\data\cache\ingame\tennis_gamestate__wta.parquet` | 196262 | 14559 |
| `C:\Users\neelj\nba-track-a11\data\cache\ingame\tennis_setdetail__atp.parquet` | 4319245 | 30616 |
| `C:\Users\neelj\nba-track-a11\data\cache\ingame\tennis_setdetail__wta.parquet` | 1240709 | 11270 |
| `C:\Users\neelj\nba-track-a11\data\cache\inplay_odds\tennis_price_series.parquet` | 4948107 | 1854100 |

`premise_audit.csv` is the per-tour archive; integer cells are zero-padded.
Its LF-normalized SHA-256 is
`7ebc3f40e96b4d6e5c9d2038ab05b8f430d0c7d00d1d2dcfd2996dd15a190af6`.
Producer SHA-256: `ingest_ingame_states.py` `ff7b197d188a5958a485f50dc0e129562ef0890ad73ddea68f2227ac112f98cf`.
Wall time: 6.4 s for the row-group premise/date scan (local).

No scored delta exists; for any future scored comparison, improvement means baseline loss minus candidate loss, positive means the candidate has lower loss.
No preregistration, model, comparer, audit beyond the premise archive, test, or
ledger/register write was made because scoring is blocked by the binding condition.
Proposed ledger line only (not appended):
`2026-09-08 | in-game calibration | S326 | rating p0; zero eligible price joins | INSUFFICIENT`
Landing: sandbox denied the worktree index lock; the orchestrator must commit these two paths by explicit `lane_commit` pathspec.

## NOT VERIFIED

- A serve/set recursion, ablations, leakage audit, bootstrap intervals, and bar C were not run.
- No market-implied pre-match calibration comparison is supported by these disjoint periods.
