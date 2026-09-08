# S287 route repeatability preregistration

Spec: `docs/evidence/tracking/specs/S287_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.
Answering the verifier correction in `docs/evidence/harness/S287_VERIFY_2026-09-08.md`:
"establish route repeatability and regenerate the three S287 artifacts without moving the bar".

Sealed before any repeatability comparison was read.

## Question

The S287 row reproduces every deterministic column of the S266 thirty-cluster
restriction bit for bit and differs only on the Monte Carlo arm. This design
measures whether the route is repeatable inside one environment, so that the
replay miss can be attributed from measurement instead of guessed.

## The three runs, frozen

The route is identical in all three runs:
`python -m scripts.platformkit.ingame.s287_sim_full_pod --game-ids <the thirty S266 clusters> --out-dir <scratch>`,
entrypoint SHA-256 `b0eec530328e84272060e32f6b1f87e0dfa3d2f11db182608879ff3fad832118`,
importing `s256_nba_sim_engine_v3` SHA-256
`757b2bd9f88a85fe68da97c6fcb275b1b44e5f4926a801265eb7f6c7cc951e12` unchanged.
The per-state seed is a pure function of tick identity, so identical seeds follow
from the same thirty clusters and the same six frozen targets.

A. POD-1 then POD-2, run sequentially in that order on the pod scratch worktree
   `/workspace/wt/a13` (python 3.12.3, torch 2.8.0+cu128, numpy 2.1.2, torch
   threads 128), detached, writing only under `/workspace/wt/a13/repeat/`. No
   deployed-tree path is written and no running daemon is touched.
B. LOCAL-1, one run in `C:/Users/neelj/nba-track-a13` with
   `C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe` (python 3.10.20,
   torch 2.1.2+cu121, numpy 1.26.4, torch threads 6), the environment the landed
   S266 memo names for its own run, writing only to a scratch directory outside
   the repository. It is abandoned and reported as skipped if it passes sixty
   minutes of wall time or 1.5 GB of peak resident memory.

## Comparison rule, frozen before any comparison

Every comparison joins the two tick series one-to-one on `state_key` and requires
thirty clusters and 180 rows on both sides. A pair AGREES only when the maximum
absolute difference is at or below `1e-9` on both of:

- per metric: Brier and ten-bin ECE for market, recal_null and simulator; the
  improvement; and both game-clustered interval bounds;
- per tick: `outcome_home_win`, `market_prob`, `p_null`, `p_simulator`,
  `loss_market`, `loss_recal_null`, `loss_simulator` and
  `paired_loss_recal_null_minus_simulator`.

`n_train` is excluded from the per-tick rule only in the comparison against the
full-scale S287 rows, where the fold sizes legitimately differ between 180 and
2,130 evaluator states; it is compared everywhere else.

Each pair reports the maximum absolute difference per metric, the count of ticks
differing by more than `1e-9`, and the first differing `state_key` in ascending
order.

Pairs compared, all four:

1. POD-1 against POD-2.
2. POD-1 and POD-2 against the archived S287 full-scale rows restricted to the
   same thirty clusters.
3. LOCAL-1 against the archived S266 tick series and summary.
4. POD-1 against LOCAL-1.

## Decision table, frozen

- POD-1 agrees with POD-2, and LOCAL-1 agrees with S266, and the pod disagrees
  with local: the route is repeatable within an environment and the difference is
  cross-environment, so the S266 replay condition is unmet for an attributed
  cause and S287 closes at that limit.
- POD-1 disagrees with POD-2: the route is not repeatable on the pod. The first
  differing state key and metric are named and no cause beyond the measurement is
  offered.
- LOCAL-1 disagrees with S266: the S266 archive is not reproducible in its own
  environment. That is recorded as an S266 finding.
- LOCAL-1 skipped: the local arm is reported as not run and no conclusion that
  depends on it is drawn.

## What does not move

The frozen `+0.004` bar, the S266 module bytes, the S255 artifacts, the S92
archive, `recal_null` defaults, and every file under `src/`. No ledger, register,
K value, feature flag, `data/` path, deployed pod file, or charged trial is
involved. No S287 metric is recomputed or restated by this design; the measured
full-scale numbers stand exactly as they were archived, and nothing here can turn
a BEHIND result into any other result.

Vocabulary follows contract Q6; automated scan required.

## Seal

SHA-256 of every LF-normalised byte above the seal line:

SEAL sha256 acc0c31dd04a0ae3785169f80e668dd7378bbee95f300313eea59835cca60673
