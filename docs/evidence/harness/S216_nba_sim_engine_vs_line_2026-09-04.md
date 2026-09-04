# S216 NBA simulator versus line - ATTEMPT 2 premise memo

Row: `docs/evidence/tracking/specs/S216_spec.md` (S216).

Verdict: **FALSIFIED at Step 0.** The S92 archives are now visible and the
S123 Brier ordering reproduces, but their measured corpus does not match the
S86 corpus premise required by S216. The stop rule therefore applies before
rate qualification, simulator pricing, or tick scoring.

## ATTEMPT 2: Attempt 1 store-visibility artefact

Attempt 1 reported the S92 archive paths absent. The orchestrator ruled that
finding a store-visibility artefact. For Attempt 2, the paths are read-only
hard links and were opened successfully. Attempt 1's missing-store finding is
superseded; it is not evidence about the archive contents.

Attempt 2 independently finds a different failed premise: the visible S92
archives do not contain the stipulated S86 denominator, game count, or end
date. This is the operative FALSIFIED result.

## Step 0 premise re-measurement

| premise | required value | Attempt 2 measurement | result |
|---|---|---|---|
| `scripts/platformkit/` imports `src.sim` | no imports | 0 executable imports; the import census printed no file list | CONFIRMED |
| S86 corpus | 465,249 ticks / 1,593 games / 2024-10-22 through 2026-06-13 | full S92 archive: 79,554 ticks / 661 games / 2024-10-25 through 2026-04-06 | **FALSIFIED** |
| S123 incumbent market default | unchanged | `apply_incumbent(rows, "market") is rows`; CSV bytes identical | CONFIRMED |
| S123 archive ordering | `market < recal_null < ladder_base` | reproduced on each visible S92 archive below | CONFIRMED |

The S123 module exists at
`scripts/platformkit/foundry/ingame_incumbent_nba.py`, with SHA-256
`476ed9fdfb714b93c5b722f8e99fb1266cdb5987a729495f12e84d2b62ea08ed`.

### S123 ordering reproduced from the visible archives

These are premise measurements only, not S216 simulator scoring. Each Brier
value is the mean of the archive's stored per-tick loss column on every row in
that archive.

| archive | denominator ticks | games | raw line Brier | recal_null Brier | ladder_base Brier | order |
|---|---:|---:|---:|---:|---:|---|
| `s92_nba_lineup_dynamic_2026-09-03_all.csv` | 79,554 | 661 | 0.142876712852 | 0.144293050901 | 0.146849530547 | CONFIRMED |
| `s92_nba_lineup_dynamic_2026-09-03_rated.csv` | 33,713 | 284 | 0.144100776926 | 0.146842905353 | 0.153323943143 | CONFIRMED |

The full archive's 79,554-tick denominator is 385,695 ticks short of the
stipulated 465,249. Its 661-game count is 932 games short of the stipulated
1,593. Its final game date is 68 days before the stipulated 2026-06-13 end
date. The premise cannot be substituted with this smaller archive without a
new specification.

## Stop boundary and required S216 output table

Step 1 and Step 2 were not reached. No qualification count was calculated,
and `src.sim` was not imported by new code. The requested S216 arms therefore
have no scored tick denominator, Brier, ECE, clustered interval, effective
cluster count, or tail share.

| S216 arm | Brier | ECE | scored ticks | clusters | eventual-loser p > 0.8 |
|---|---:|---:|---:|---:|---:|
| raw line | NOT SCORED | NOT SCORED | 0 | 0 | NOT SCORED |
| S123 incumbent / recal_null | NOT SCORED | NOT SCORED | 0 | 0 | NOT SCORED |
| possession simulator | NOT SCORED | NOT SCORED | 0 | 0 | NOT SCORED |

LIMIT verdict: **NOT ASSESSED.** This is not a CLOSED AT LIMIT determination:
the required earlier premise failed first.

## Inputs and bounded reader procedure

| full path | bytes | resolution | use |
|---|---:|---|---|
| `C:\Users\neelj\nba-track-a13\data\cache\eval_gate\s92_nba_lineup_dynamic_2026-09-03_all.csv` | 38,630,145 | n/a (CSV) | one 50,000-row chunk at a time for denominator, dates, and stored-loss means |
| `C:\Users\neelj\nba-track-a13\data\cache\eval_gate\s92_nba_lineup_dynamic_2026-09-03_rated.csv` | 16,420,946 | n/a (CSV) | one 50,000-row chunk at a time for ordering reproduction |
| `C:\Users\neelj\nba-track-a13\data\cache\team_system\player_rates.parquet` | 71,906 | n/a (tabular parquet) | Step 1 input schema inspection only; no qualification calculation |
| `C:\Users\neelj\nba-track-a13\data\cache\team_system\team_rates.json` | 378,935 | n/a (JSON) | Step 1 input schema inspection only; no qualification calculation |

The archives were processed sequentially, never concurrently. No archive over
300 MB was opened. Nothing was written below `data/cache/eval_gate/`; the
FWER ledger and hypotheses database were neither opened nor modified.

## Integrity and contract self-check

- `git diff --quiet -- src` passed: no file under `src/` differs from HEAD.
- `ingame_screen.BAR` was not edited; its value remains 0.004.
- No files were added under `scripts/platformkit/ingame/`, so the S216 named
  test has no target to run after the required Step 0 stop.
- No rates snapshot was used, no flag was changed, and no external action was
  taken.
- B1, B7-B9: no scored metric or selected scoring subset exists. B2, B5, B6,
  and B10: no production or shared-rail code changed. Q1-Q5 and Q9 do not
  apply because no S216 comparison was scored. Q6: calibration language only.

## NOT VERIFIED

- The stipulated 465,249-tick / 1,593-game S86 corpus is not represented by
  the supplied S92 archives; no substitute corpus was authorized.
- Strictly-prior rate-snapshot coverage and excluded games were not assessed
  because Step 1 was not reached.
- The possession simulator was not priced on any tick.
- No S216 three-arm Brier/ECE result, clustered confidence interval, tail
  share, paired-loss series, preregistration, or ledger charge exists.
