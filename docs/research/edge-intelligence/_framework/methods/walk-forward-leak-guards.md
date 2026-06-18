# METHOD: Walk-forward + leak guards -- expanding window, purge/embargo, vintage, DM, 2-corpus
_Part of the edge-intelligence method library (B). Reusable recipe. ASCII only.
Code pointers: scripts/platformkit/eval_gate/walkforward.py (the harness +
assert_vintage + purge/embargo constants), scripts/platformkit/eval_gate/dm_test.py
(cluster-robust Diebold-Mariano), scripts/platformkit/eval_gate/scoring.py (Brier/BSS),
scripts/platformkit/eval_gate/run_gate.py (the orchestrator/ratchet)._

## Why (the principle)
To claim an edge we must score predictions OUT OF SAMPLE with ZERO lookahead. In-sample
scoring and random K-fold both leak the future and make noise look like skill. The harness
ENFORCES leak-freeness rather than assuming it (walkforward.py module docstring).

## Expanding window (the split)
Sort all states by event timestamp. For each test state at time t, train ONLY on states
strictly before t -- an EXPANDING window (every prediction uses only its own past).
  - predict_fn(train_states, test_state, select_inside) -> p in [0,1]. The harness never
    trains a model; it orchestrates the leak-free split and collects per-state p for scoring.
  - Tie-safe: states with ts >= t are skipped (walkforward.py lines 60-65).
This is strictly causal -- no future state ever enters a training set.

## Purge + embargo (kill autocorrelation across the boundary)
Even a correct time split leaks via correlated nearby events. Two guards (walkforward.py
lines 21-23, 66-70):
  - PURGE: drop same-TEAM games within PURGE_HOURS = 48h of the test game -> kills
    back-to-back autocorrelation (a team's two halves of a B2B are not independent).
  - EMBARGO: drop the same MATCHUP within EMBARGO_DAYS = 3 days of the boundary -> kills
    rolling-window / repeated-matchup spillover.
Without these, a model can "learn" the test outcome from a near-duplicate adjacent game.

## assert_vintage (the per-feature leak guard)
Every feature used to predict event E must have been KNOWN strictly before E.
assert_vintage(state) iterates state["feature_avail"] and asserts each feature's
availability timestamp < state["state_ts"], raising "LEAK: feature {f} availability {avail}
>= state_ts" otherwise (walkforward.py lines 41-48; called as defense-in-depth at line 71,
the schema also checks). This catches the season-FINAL-aggregate-as-feature class of leak
(never use end-of-season totals as a feature for a mid-season game) and the silent
train/inference parity bug (a new feature that reads 0.0 at inference because it was only
wired on the train side -- the most expensive bug class).

## select_inside (no tuning leak)
Feature selection / hyperparameter tuning MUST happen INSIDE the window, on the train
slice only. The harness records the select_inside flag; a caller that selects on the FULL
history (select_inside=False) is surfaced so the GATE FAILS the run (walkforward.py
docstring + WalkForwardResult.select_inside, lines 49-52). Selecting on the full history is
a subtle, common leak that inflates OOS scores.

## Cluster-robust Diebold-Mariano (honest significance)
To test "does the model beat the close?", form per-state loss differences
  d_t = loss_close(t) - loss_model(t)   (POSITIVE mean => model better)
and test the mean with diebold_mariano(d, cluster_ids) clustering by game_id
(dm_test.py). The SE clusters by game because many states within one game are highly
correlated; a naive i.i.d. SE runs ~3x too NARROW and manufactures fake significance (this
is a real QA-caught bug in the in-game blueprint). The estimator uses a cluster-sum
variance with a G/(G-1) finite-cluster correction (dm_test.py lines 46-57). Always cluster;
never report a naive t-test on correlated states.

## Proper scoring (what to compute)
Brier + ECE (PAIRED with a sharpness check so collapse-to-0.5 isn't read as "calibrated") +
log-loss, and Brier-Skill-Score vs the devigged close: BSS > 0 means sharper than the
market on that market (the north-star metric). Each test record carries p_model, p_close
(devig_close_prob) and y so the close is the baseline (walkforward.py lines 72-78).

## >= 2-corpus accept (the anti-selection rule)
A single good fold of four is usually a SELECTION ARTIFACT. Require agreement on >= 2
INDEPENDENT corpora / folds before promoting (proof-standards.md bar 4). Project history:
many single-fold "lifts" reverted (17 feature-add reverts in one loop). Also run multi-seed
/ larger-N stability for any big jump driven by one seed or tiny N (small-N ROI is noise).

## The recipe (apply in order)
  1. Build states with event timestamps + feature_avail per feature + devig_close_prob + y.
  2. walk_forward(states, predict_fn, select_inside=True) -- expanding window + purge +
     embargo + assert_vintage. select_inside=False fails the gate.
  3. Score with scoring.py: Brier/ECE/log-loss + BSS vs the devigged close (+ sharpness).
  4. diebold_mariano(d, game_id) for significance; require the clustered SE.
  5. Replicate on >= 2 independent corpora/folds + multi-seed stability for big jumps.
  6. Ratchet (run_gate.py): SHIP only if it does NOT regress vs the frozen baseline AND
     beats it beyond tolerance OOS; only-improve-or-hold. Record rejects. < ~60 settled
     outcomes -> INSUFFICIENT_DATA (accrue before judging).

## Failure modes (each maps to a guard above)
  - LOOKAHEAD: training on >= t states -> expanding window forbids it.
  - B2B / repeated-matchup autocorrelation -> purge + embargo.
  - FEATURE FROM THE FUTURE (season-final aggregates, train/inference 0.0) -> assert_vintage.
  - TUNING ON FULL HISTORY -> select_inside guard fails the run.
  - FAKE SIGNIFICANCE from i.i.d. SE on correlated states -> cluster by game_id.
  - SINGLE-FOLD SELECTION / single-seed jump -> >= 2 corpora + seed/N stability.
  - MIRROR-NOT-STUB: tests must call the REAL gate, never a parallel stub that can drift
    (feedback-tests-mirror-real-not-parallel).

## Evidence-tier reminder
Passing this harness with BSS > 0, clustered-significant, on >= 2 corpora is the
CALIBRATION-PROVEN tier (sharper than the devigged close) -- NOT a $-edge. CLV
(clv-computation.md) is the separate, later bar for real money. A clean NULL/REJECT here is
a SUCCESS: it tells us where to STOP.
