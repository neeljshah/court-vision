# S203 replication wiring -- FALSIFIED at premise

## Scope and verdict

S203 required a step-0 re-measurement before any implementation. The stated premise
was that `scripts/platformkit/hedge_trial_runner.py` was the one existing caller of
`replication_verdict`, making the baseline one of six writers. That premise is false
in this worktree: the current hedge-trial runner has no import or call to either
`replication_verdict` or `replication_fields`. A repository-index search found the
only current callers in two unrelated S58 modules:

    scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py:110
    scripts/platformkit/eval_gate/s58_t2_first_trial.py:145

This memo is the required S203 STOP artifact. Verdict: **FALSIFIED**. No code,
artifact schema, threshold, ledger, register, or data file was changed.

## Clean-source preflight

The preflight source survey was performed against the current `track-a15` worktree.
The only pre-existing reported tracked state was the S203 specification with no text
diff (`git diff` emitted only the repository's LF-to-CRLF warning). The six source
files below had no changes. The isolated `.planning/s203-replication-wiring/` records
are ignored local working notes and are not part of this commit.

## Exhaustive six-writer survey

| Writer | Current raw AHEAD source and output line | AHEAD branch reachability | Replication call in current source | Result |
|---|---|---|---|---|
| `scripts/platformkit/hedge_trial_runner.py` | `verdict_of` begins line 100; its raw verdict is written at line 206 | Reachable when its existing paired calibration conditions hold | No | The claimed single pre-existing call site is absent; this falsifies the premise. |
| `scripts/platformkit/ingame/mlb_winprob_v6.py` | paired AHEAD line 105; final assignment line 186; raw output line 195 | Reachable when paired CI conditions and `val_helps` hold | No | Unwired. |
| `scripts/platformkit/ingame/mlb_winprob_v7.py` | AHEAD assignment line 179; raw output line 184 | Reachable when its paired result is AHEAD | No | Unwired. |
| `scripts/platformkit/frontend/slate.py` | AHEAD return line 80; row output line 221 | Reachable when incoming predictor text contains the matching AHEAD condition | No | Unwired. |
| `scripts/platformkit/pm_trading/clv_daily_readout.py` | AHEAD branch line 117; raw output line 129 | Reachable with sufficient settled rows and positive median CLV units | No | Unwired. |
| `scripts/platformkit/eval_gate/stacker.py` | raw AHEAD/BEHIND branch line 224; single-window fields line 244 | Reachable when its existing paired calibration conditions hold | No | Unwired; it still uses `min_corpora_eff(1, k)` and `single_window=True`. |

The denominator has not been narrowed: all six paths named by S203 were opened and
surveyed. The table deliberately does not count a subset of reachable writers.

## Required construct cases -- not run

S203's 12 cases belong to step 2 and are conditional on the stated step-0 premise.
The premise is false, and the specification explicitly says: "If falsified, STOP,
memo, commit, FALSIFIED." Therefore no case was run and no S203 test file was added.
This is not a 0-of-12 score and is not a claim about the intended wiring; it is the
required precondition stop. No live artifact was regenerated.

| Cases | Status | Reason |
|---|---|---|
| n_corpora=1 downgrade cases | Not run | Step 2 is prohibited after the FALSIFIED premise. |
| n_corpora=2 unchanged cases | Not run | Step 2 is prohibited after the FALSIFIED premise. |

## Reader survey and self-check

No artifact field, status, or key was changed, so A5/B2 reader checks have no touched
schema to inspect. The `replication_verdict` repository-index search above is the
relevant premise check: it names every current caller and proves none is the claimed
hedge-trial writer. The raw verdict keys, all calibration bars, `min_corpora_eff`, and
the standing MLB hedge-trial BEHIND artifact remain untouched.

Section B/Q self-check: no circular metric was produced; no schema was changed; no
absent evidence was quarantined; no claim loop, deployment, source move, scored
sampling, self-fit comparison, denominator, or threshold change occurred. Q1-Q4 and
Q9 are not applicable because no score was run. Q5 is the subject of the unmodified
construct proposal, and Q7 permits the FALSIFIED premise stop rather than a sampled
claim. Q8 is satisfied by the source re-measurement recorded above. Q6 is satisfied:
this memo reports calibration labels only.

## NOT VERIFIED

- The intended six-writer wiring and 12 construct cases were not performed because
  S203 required STOP once its one-wired-writer premise was falsified.
- No live AHEAD was exercised or downgraded.
- No artifact-reader schema audit is applicable because no artifact key changed.
