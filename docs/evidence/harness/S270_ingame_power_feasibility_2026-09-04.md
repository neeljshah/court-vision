# S270 in-game power feasibility: attempt 1c

Calibration feasibility and a single-window S82 re-screen only.

## Premise

`git show d7cbf4e34:docs/evidence/harness/S259_ingame_power_audit_v5_2026-09-04.md`
reproduced all eight UNDERPOWERED rows before this work. The register grep found
only the current open S270 successor and no completed later re-screen.

## Real-store feasibility

`S270_ingame_power_feasibility_2026-09-04_v2.json` is the streaming count
record. It lists every exact pool path and byte total; JSONL pools were read one
file at a time using only `game_id`, and CSV pools using only their stated
game-equivalent cluster column. `ingame_eval_cache.parquet` is 35,876,539 bytes
with 1,987 game_id values, but S84 documents it is key/schema incompatible and
it is not pooled. The linked `data/cache/eval_gate/s58_screens` SQLite stores
are screen-result metadata, not event game-id pools, so they cannot enlarge S79
without changing its frozen source.

| screen | required_n_eff | available clusters | feasible |
|---|---:|---:|---|
| S06 | 66914.394 | 227 | no |
| S117 | 148467.824 | 8 | no |
| S119 | 762.529 | 41 | no |
| S58_trial1 | 33840.709 | 227 | no |
| S79 | 2339.082 | 30 | no |
| S80 | 9120.091 | 227 | no |
| S82 | 762.529 | 227 | no |
| S84 | 1368.498 | 284 | no |

S82 was selected because its valid shortfall, 535.529 clusters, is smallest.
The enlarged raw source is `data/cache/ingame_grade_joined/mlb`: 227 JSONL
files and 35,859,254 bytes, with the member inventory in the feasibility JSON.

## Sealed re-screen

The first sealed setup produced no metric artifact and was stopped before
output when its tick-state evaluator construction proved quadratic. The sealed
v2 preregistration is
`S270_attempt_1c_S82_prereg_2026-09-04_v2.md`, commit `b07638248`, with
LF-normalized seal `561246d2d2bd4c6621cbdb96157c36df110a66e74a8295fca3521e357b56c32f`.

The unchanged S82 prediction builder used its existing settlement purge and
one-day embargo. The shared evaluator then scored one canonical median-tick
state per game with its own nonzero symmetric one-day embargo. The paired-loss
archive is `S270_attempt_1c_S82_rescreen_2026-09-04_v2.csv`; it has 127 rows
and 127 game clusters. The result JSON records exercised code identity and
RSS before/after shared scoring: 381.391 MB and 384.625 MB, respectively;
both are below the 600 MB limit.

Census: 178 loaded games = 20 excluded before eligibility
(`NO_FINITE_E4`: 20) + 31 without a finite OOF prediction at the fixed
median tick (`NO_FINITE_CANDIDATE_OR_NULL_OOF_AT_MEDIAN_TICK`: 31) + 127
scored games. The named exclusion table is
`S270_attempt_1c_S82_excluded_games_by_reason_2026-09-04_attempt2.csv`.

| metric | result |
|---|---:|
| Brier null | 0.218938127383 |
| Brier candidate | 0.214406016502 |
| Brier delta | +0.004532110881 |
| MDE80 | 0.008164580827 |

The delta is above the frozen bar, but this is a SINGLE-WINDOW calibration
result: it has no second independent corpus. It is not a deployment or a
generalized calibration claim.

## Attempt 2: B1 denominator correction

The scorer was rerun in a fresh process to
`S270_attempt_1c_S82_rescreen_2026-09-04_attempt2.csv` and
`S270_attempt_1c_S82_rescreen_2026-09-04_attempt2.json`, with the named
excluded-game table above. The census identity is `178 = 20 + 31 + 127`.
The scored Brier values, Brier delta, MDE80, scored tick and game counts, bar,
and fold records are unchanged from the v2 result. The sealed preregistration
file is unchanged; its test reads that file, normalizes CRLF to LF, and hashes
only bytes above the seal line.

## NOT VERIFIED

- An independent verifier has not replayed this attempt-2 result.
- A second independent corpus is not available for this single-window calibration result.
- The 51 named exclusions were enumerated, not repaired or imputed.

## Verification

`python -m pytest tests/platformkit/test_s270_ingame_power_feasibility.py -q -p no:cacheprovider`

The test recomputes S06 required_n_eff, asserts exactly eight rows, and checks
the v2 preregistration by reading the file, normalizing CRLF to LF, and hashing
only bytes above the seal line. No register, ledger, data store, flag, or pod
was modified.
