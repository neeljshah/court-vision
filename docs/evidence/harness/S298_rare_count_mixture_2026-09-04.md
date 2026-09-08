> SUPERSEDED: attempt-1 memo, archived as evidence only. It records the
> NOT VALIDATED state before the pod scorer ran. The landed attempt-2
> result is `S298_rare_count_mixture_2026-09-07.md` (BEHIND).

# S298 rare-count mixture comparison

## Verdict: NOT VALIDATED

The prerequisite premise holds, but the required pod-only scorer did not
launch. No scored comparison was run locally.

## Preregistration

The sealed preregistration is
`docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg.md` with
LF-normalized bytes-above-seal SHA-256
`906ef129f74c860192046e1c60d21fffb2dd9c98a780efc766f2b30597be082b`.
The worktree sandbox denied creation of the Git index lock, so this is the
committed-byte-equivalent hash rather than a `git show :<path>` hash. The
orchestrator must make the preregistration its own explicit-path `lane_commit`
before any future score run.

## Binding premise re-measurement

The exact source paths opened, byte sizes, and resolution were:

| Path | Bytes | Resolution | First three `(game_id, player_id)` keys |
|---|---:|---|---|
| `C:/Users/neelj/nba-track-a10/data/domains/basketball_nba/player_boxscores.parquet` | 1118538 | tabular; not applicable | `('0022300001', 202684)`, `('0022300001', 1627747)`, `('0022300001', 1627777)` |
| `C:/Users/neelj/nba-track-a10/data/cache/omni_box_refresh/nba_player_box_extension.parquet` | 34147 | tabular; not applicable | `('0042500121', 203468)`, `('0042500121', 203903)`, `('0042500121', 1626157)` |

Binding output:

```text
S298_BINDING_ZERO_COUNTS data/domains/basketball_nba/player_boxscores.parquet STL=40520 BLK=53267
S298_BINDING_ZERO_COUNTS data/cache/omni_box_refresh/nba_player_box_extension.parquet STL=669 BLK=799
```

The premise is not falsified. It authorizes the pre-registered Poisson, NB2,
hurdle-NB2, and ZINB comparison, but does not itself provide a calibration
result.

## Required score and archive status

The frozen primary sign convention is improvement = Poisson log score minus
candidate log score; positive means lower candidate loss. The six planned
comparisons are STL and BLK against NB2, hurdle-NB2, and ZINB. The fixed bar is
Holm-adjusted paired 95 percent lower bound greater than 0, with all families
published. RPS, zero reliability, and randomized PIT are secondary.

| Metric table item | Status |
|---|---|
| Discrete log-score means and paired confidence intervals | NOT PRODUCED: scorer did not launch |
| RPS, zero reliability, randomized PIT | NOT PRODUCED: scorer did not launch |
| RSS before and after scorer | NOT PRODUCED: scorer did not launch |
| PMF CSV archive through tail cutoff 20 | NOT PRODUCED: scorer did not launch |
| Evaluator-derived paired-loss CSV and JSON summary | NOT PRODUCED: scorer did not launch |

The route is `scripts/platformkit/s298_rare_count_mixture.py` (264 lines). It
uses `cpcv_evaluate_vector_distributional`, which applies shared purging and a
symmetric one-day embargo; it emits one stable player-game state per scored
tick and rejects non-finite integer PMFs before scoring. The planned pod
dispatch was exactly one invocation of `/c/Users/neelj/bin/pod_run a10` with
the preregistration shipped and the three dated result files fetched. It failed
before the runner began, with `CreateFileMapping ... Win32 error 5` from both
Git Bash launch paths. `wsl.exe` reported that WSL is not installed. A plain
process check returned no running `wt/a10` job. No deployed pod tree, source
store, data path, register, or ledger was written.

## Test

`python -m pytest tests/platformkit/test_s298_rare_count_mixture.py -q -p
no:cacheprovider` -> `1 passed in 1.51s`. The test reads the preregistration
file, normalizes CRLF to LF, verifies the seal above its seal line, and checks
finite PMFs, PMF sums, zero support, tail finiteness, and strict-prior feature
availability.

## NOT VERIFIED

- Any discrete log-score, RPS, zero reliability, or randomized PIT comparison.
- Any confidence interval, Holm decision, family ranking, or calibration
  conclusion.
- The PMF archive, paired-loss archive, JSON summary, scorer RSS, and pod route
  reproducibility; no pod process launched.
- The required preregistration-only Git commit and final explicit-path commit;
  the sandbox denied Git index writes and files are ready for `lane_commit`.
