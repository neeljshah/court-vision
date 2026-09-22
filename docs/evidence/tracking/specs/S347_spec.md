GAP S347 | sport mlb + soccer_intl (+ nba checkpoints) | worktree harness-h5 | log cx_s347_baseline_scorer
# Four-arm calibration baseline scorer + preregistration DRAFT (astra round 10 rank 7) -- PREPARE ONLY, NO SCORING

SINGLE PROBLEM: scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:271 defaults to the contaminated mlb_clean corpus and
PHASE_FN (:107) has no keys for the segmented corpora, so a repointed run silently reports NO_DATA by phase; and the repo has
never scored, on IDENTICAL observations, the four arms that isolate what the model adds: (A) current mid, (B) recalibrated mid
(walk-forward logistic on logit(mid) only), (C) mid + state residual (logit(mid) + state features, no model_prob), (D) mid +
state + model_prob.

BINDING BEFORE-CONDITION (re-run, quote): `grep -n "mlb_clean" scripts/platformkit/ingame/gate_a0_ingame_vs_market.py` hits the
default; `grep -n "PHASE_FN" -A 6` shows no *_segmented keys.

CHANGE (NEW files only; gate_a0_ingame_vs_market.py is NOT edited -- supersede by ADDING):
1. scripts/platformkit/ingame/baseline_four_arm.py (<= 300 LOC; numpy + stdlib; reuse the row loader and the game-clustered
   bootstrap from gate_a0 by import; split helpers into baseline_four_arm_features.py if needed): CLI
   `--corpus-dir <dir> --manifest <json> --prereg <path> --out <dir>`. REFUSES to run unless (1) the manifest exists, lists the
   files with SHA-256, and every hash matches, and (2) the prereg file exists, its seal verifies (SHA-256 of LF-normalized bytes
   above the seal line) and `git log --format=%H -- <prereg>` is non-empty (committed BEFORE scoring, contract Q1).
   Walk-forward by game first-tick date through the shared evaluator under scripts/platformkit/eval_gate/ (walkforward) with
   purge + a symmetric nonzero embargo; ONE evaluator state per scored tick with a stable key; equal-game weighting AND tick
   weighting both reported; all-tick and state-transition-tick populations reported separately; paired Brier and log-loss deltas
   vs arm A with game-clustered CIs; leave-one-game-out range; largest single-game and single-week share of each delta; n >= 30
   games per scored cell else UNDERPOWERED; phase mapping covers the *_segmented and *_segmented_r3 corpus names and any unmapped
   corpus name is a hard error, never NO_DATA. State features come ONLY from the row state_summary string via a pure parser with
   a declared feature list per sport (mlb: score diff, inning, half, outs, base state; soccer: score diff, minute, red cards if
   present).
2. docs/evidence/ingame/S347_PREREG_DRAFT_2026-09-21.md: an UNSEALED draft prereg (hypotheses with both signs named, arms,
   populations, folds, embargo, bars copied byte-identical from GATE_A0 where they exist, the single-game concentration rule,
   the stop rule). The orchestrator reviews, seals and commits it; the builder does not seal and does not score.
3. tests/platformkit/ingame/test_baseline_four_arm.py: synthetic corpora under tmp_path -- refuses without manifest, refuses on a
   hash mismatch, refuses on an unsealed or uncommitted prereg (monkeypatch the git check), truncation-invariance (dropping
   future games never changes a past fold prediction), arm D equals arm C when model_prob is constant, unmapped corpus -> error.

CONTROLS: NO number is computed on any real corpus in this row. ACCEPTANCE: per-file test passes; `--help` works; diff = NEW
files only. Vocabulary follows contract Q6; automated scan required. Memo docs/evidence/harness/S347_baseline_scorer_2026-09-21.md
ends with a NOT VERIFIED list. The pod is OFF.
