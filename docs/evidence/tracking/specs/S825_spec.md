# S825 -- the sealed scorer refits once per history row; one fit per (fold, arm) instead (2026-10-19)

Owner: paper-desk-improve scheduled run (T3), 2026-10-19 (Opus build lead in worktree lead/s825). Row allocated
2026-10-15 by the paper-desk-improve run from the S824 memo. PAPER ONLY; calibration language only. Seal-day row:
the FREEZE is in force, so the build is PARKED in the worktree and lands only with the next identity step (seal A,
then commit B), never as a night-side patch.

## 1. Premise (fresh reads, master 07c2cd482 / d79117326; the scorer files are identical in both)

- ingame_scoreboard._models passes every validated training row of the sport plus tonight's ticks to
  baseline_four_arm.predict_rows (ingame_scoreboard.py:159) and keeps only tonight's rows afterwards
  (ingame_scoreboard.py:163, `night = [r for r in predictions if ... >= boundary + 3 days]`).
- predict_rows hands one state per row to walk_forward (eval_gate/walkforward.py:124-161). For EVERY row,
  walk_forward builds a fresh train list over all earlier states (fromisoformat + two team-set tests per pair:
  O(N^2)), then `predict` (baseline_four_arm.py:93-129) filters that list again (O(N)), builds the sorted train
  game list (O(N log N)), runs warmup_reason (O(N)) and fits `logistic` for B and C, and on the model subset for
  D (and for NBA three more fits on the lag subset in lagged_subset). Wall grows about quadratically with the S766
  cumulative history: 579 s at 15.9k rows, 1,443 s at 29.2k rows (S824 memo section 2).
- `predict`'s purged train set is a function of the test game's fold boundary alone:
  {s : first[s].date() < first[gid].date() and settled[s] < boundary - 3 days}, boundary = midnight UTC of
  first[gid]. select_rows refuses a tick after its game's close ('tick after close',
  baseline_four_arm_eligibility.py:78-79) and the asserts at baseline_four_arm.py:99-100 hold, so every purged-in
  state was captured before boundary - 3 days <= test tick - 3 days: walk_forward's look-ahead, matchup-embargo and
  team-purge filters never remove one, and the filtered list equals the fold's list in walk_forward's own order.
  `logistic` fits on train only and scores the test row with the fitted coefficients, so one fit per (fold, arm)
  is output-identical by construction.

## 2. The change (identity files; parked)

1. NEW scripts/platformkit/ingame/baseline_four_arm_fit.py: fit_logistic / apply_logistic (the two halves of
   the pre-S825 `logistic` body, arithmetic unchanged); FoldView (per-fold memo of the purged subsets, the sorted
   train game lists, warmup_reason and the fitted coefficients; every hit asserts it was built from the same row
   list object, so two folds or two subsets can never share an entry; key None = no caching); FoldCache (the
   fold train sets in walk_forward order; the fold path is taken only when the row's tick is at or after its
   boundary, the fold's rows all precede boundary - 3 days, and the state_ts string order agrees with the
   instant order -- otherwise the row takes the pre-S825 per-call path with its asserts).
2. baseline_four_arm_features.py: `logistic` delegates to fit_logistic + apply_logistic (one implementation for
   every caller: live_shadow_fit, registry_scorer_e_fit, intel_prior_arm); lagged_subset takes an optional view.
3. baseline_four_arm.py: `predict` reads the fold's train list, games, warmup and fits from the view; the
   per-call purge and both asserts are kept verbatim for the fallback path. 300 LOC (two line joins elsewhere).
4. eval_gate/walkforward.py: keyword `lazy_train=False`. With True, predict_fn receives a zero-argument callable
   that builds (once) the identical train list; predict_rows passes True, so the O(N^2) build runs only on the
   fallback path. Default callers are unchanged (records and n_train_sizes byte-identical).
5. (c) NOT taken: predict_rows' contract is one record per input row (baseline_four_arm.py:132 asserts
   len(result.records) == len(output)) and a history row's evaluation can still decide the sport's outcome (an
   ERRORS raise inside predict_rows -> model_path_refused, ingame_scoreboard.py:159-162; an AssertionError,
   outside ERRORS = ingame_scoreboard_rules.py:16, aborts the step). Skipping history rows would change both;
   with the fold cache a history row costs O(1) amortised, so (c) is not needed for the wall.

## 3. Acceptance

(a) Byte-identical scoreboard receipts, OLD code (detached master worktree) vs NEW code (this worktree), same
hard-linked scratch inputs, same recorded argv, on 10-12 (no history file) and 10-13 (training/2026-10-13.jsonl,
29,154 rows): sha256 equal and JSON leaf diff 0 (memo section 4).
(b) The 10-13 argv wall under 600 s with the new code (memo section 4, with the night_running flag).
(c) New per-file tests green (tests/platformkit/ingame/test_baseline_four_arm_fit.py): prediction identity vs the
forced per-call path on five synthetic corpora (MLB, MLB floor, MLB model-optional with a model gap, NBA with the
lag subset, NBA floor), fit/apply bitwise equal to a verbatim copy of the pre-S825 logistic, fit count = distinct
(fold, subset, arm) slots and below the per-row count, fold-key collision refused, walk_forward lazy == eager.
(d) Every behavioural per-file test of the touched modules green; the hash-pin tests red by design (section 5).

## 4. Non-goals / follow-up

- No change to what is scored, the purge, the embargo, the warmup floor, the logistic arithmetic or the receipt
  schema. No history truncation (S766 policy). The S824 deadline (3,600 s) stays until commit B lands; it can be
  tightened afterwards on measured walls (separate row).
- walk_forward's deep copy and per-row redaction/vintage checks stay (O(N)).

## 5. Seal chain (FREEZE rules)

Sealed files touched: scripts/platformkit/eval_gate/walkforward.py, scripts/platformkit/ingame/baseline_four_arm.py,
scripts/platformkit/ingame/baseline_four_arm_features.py; NEW scripts/platformkit/ingame/baseline_four_arm_fit.py
(must be ADDED to the identity file list of the next PREREG, since predict now routes every fit through it).
Untouched: ingame_scoreboard.py, ingame_scoreboard_rules.py.
Seal A (next identity step, beside S721): new PREREG pinning the new hashes; re-pin the hash tests that go red by
design (memo section 7 lists each with the failing assertion). Commit B: two scored nights under seal A before
the receipt is promoted, per the chain rule.

## 6. Tests (one process per file)

tests/platformkit/ingame/test_baseline_four_arm_fit.py (new), test_baseline_four_arm.py,
test_baseline_four_arm_nba.py, test_baseline_four_arm_model_optional.py (spy moved from `logistic` to
fit_logistic; asserts one fit per fold, the same populations), test_baseline_four_arm_eligibility.py,
test_baseline_four_arm_period.py, test_baseline_four_arm_features_nfl.py, test_nba_four_arm_primary_contrast.py
(spy moved from features.logistic to FoldView.logistic; same checks); the walk_forward and logistic callers
listed in memo section 5.

## 7. Tiers

Two Opus tiers (CONTRACT: VERIFIER_CONTRACT A/B/Q + this spec; ADVERSARIAL: probes and mutations). Probes the
tiers must run are in memo section 6.

## AMENDMENT 1 (seal A 2026-10-20)

(a) Identity tuple. scripts/platformkit/execution/ingame_scoreboard_amendment.py IMPLEMENTATION_FILES gains
scripts/platformkit/ingame/baseline_four_arm_fit.py (after baseline_four_arm_features.py): predict routes every
fit through it, so a later edit of the fit module must move the seal. Seven base entries, plus
baseline_four_arm_features_nfl.py because nfl is model-optional: the seal PREREG_2026-10-21.json lists eight.
verify_amendment recomputes the payload from the live tuple, so commit B must carry this tuple change with the
code (it does: the tuple commit is on lead/s825), and every seal hashed under the old six-file list
(PREREG_2026-10-07 and older) refuses amendment_mismatch on the new code -- the disclosed refusal of runbook B2,
never fixed by editing an old seal. Tests that verify old seals pin the pre-S825 list (PRE_S825_FILES in
tests/platformkit/execution/s469_seal_helper.py); no committed old-seal fixture changes.

(b) Tier corrections. Applied (test-only + one annotation, no output change): walkforward.py n_train_sizes
annotated List[Optional[int]]; NEW tests/platformkit/ingame/test_baseline_four_arm_fit_fallback.py (the three
FoldCache fallback branches, key None never memoised, a game settled exactly at boundary - 3 d, distinct
train_games lists across same-fold records); the model-optional spy keyed on train size, not call order.
DECLINED: adversarial (4) cached arrays flags.writeable = False -- it adds a raise path into sealed code that
the byte-identity proof did not cover; the arrays stay read-only by convention (P5 found no writer).

(c) One identity change. No NBA-specific prereg and no ncaaf (S821) in this seal (dispatcher decision 10-19).
