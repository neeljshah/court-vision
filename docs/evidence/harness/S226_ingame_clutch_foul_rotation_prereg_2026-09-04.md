# S226 In-Game Clutch Foul Rotation Preregistration

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a13` on branch `track-a13`.
The source stores are read-only and no file under `data/` will be written. No
atlas store will be joined: those inputs are SNAPSHOT-ONLY at as_of 2026-05-31
and are reported BLOCKED-ON-S223. This is a SCREEN-only calibration measurement:
no register or FWER ledger is read or written, no feature flag changes, and no
serving route is used.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Fixed inputs and premise method

Open one store at a time, each below the 300 MB rail:

```text
C:\Users\neelj\nba-ai-system\data\cache\inplay_odds\nba_checkpoints_full.parquet (2,829,826 bytes)
C:\Users\neelj\nba-ai-system\data\cache\inplay_foul_state.parquet (39,429 bytes)
C:\Users\neelj\nba-ai-system\data\cache\ingame\possession_states_2024_25.parquet (249,491 bytes)
C:\Users\neelj\nba-ai-system\data\cache\ingame\possession_states_2025_26.parquet (247,926 bytes)
```

The fixed clutch population is `period == 4`, `abs(margin) <= 5`, and
`game_clock_s <= 300`. Reproduce its stated tick/game counts before any arm.
Report the exact foul and possession join keys, coverage against all clutch
ticks, duplicate-key handling, and every named reason for a non-scored row.
No game is removed because it has no clutch tick; report the count of the
1,593 period-4 games that contribute none.

If any required source or stated count is unavailable or fails to reproduce,
write the evidence memo with verdict FALSIFIED and do not score an arm.

## Fixed scored method if the premise reproduces

Before evaluating the sibling grammar, print market and S123-incumbent clutch
Brier and ECE, effective sample size, and the 80 percent-power MDE. If MDE is
above 0.004, report CLOSED AT LIMIT and do not evaluate hypotheses.

The only candidate family is a new additive sibling of
`scripts/platformkit/foundry/ingame_grammar_nba.py`. It exposes exactly
`TRANSFORMS`, `build_state`, `build_grid`, `enumerate_hypotheses`, and
`hypothesis_column`, using only the foul-state and possession-state columns
available as-of each tick. The original grammar is not edited. The enumerated
family is frozen before the run and is evaluated with the shared
`scripts.platformkit/eval_gate/walkforward.py::walk_forward`, including its
48-hour purge and symmetric nonzero 3-day embargo. Every scored probability is
produced by that evaluator callback; no direct fitted or in-sample probability
is reported.

For every enumerated hypothesis, archive a per-tick paired-loss CSV containing
game cluster, timestamp, market loss, incumbent loss, candidate loss, and the
probabilities used. Report Brier improvement against the S123 leak-free
incumbent, DM p, game-clustered 95 percent CI, effective sample size, and
Benjamini-Hochberg adjusted p at q=0.05 across the complete family. Require at
least 30 game clusters, name every dropped tick, and use the fixed +0.004 bar.
No bar or family member may change after this seal. `SCREEN_NULL` is the
expected valid result; all prose is calibration language only.

Seal SHA-256 of the pre-seal content above: `4DB9F6F9E92440C9949B39AC8BC0327F651693F9D09764841DC218A98A01FB82`.
