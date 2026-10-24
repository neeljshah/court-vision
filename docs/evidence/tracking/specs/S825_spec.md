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

## AMENDMENT 2 (seal A re-cut 2026-10-22)

(a) Why. The laptop was off 05:08Z-15:31Z 10-21 and asleep 20:56Z 10-21 - 14:27Z 10-22; nights 10-20 and 10-21
never ran (no nights/2026-10-20.json or 2026-10-21.json), so the commit-B window of AMENDMENT 1 (10-21, before
05:00Z 10-22) lapsed. Documented default (DESK_STATE section 2, S625 precedent): the whole chain shifts; the
lapsed seal PREREG_2026-10-21.json stays an unreferenced file forever and is never reused; a NEW dated seal A is cut.

(b) The new seal. SEAL A RE-CUT 2ee92e7e9411168429ebbb65ba976617cc3ee9a9 (2026-10-22, the JSON alone):
docs/evidence/forward/scoreboard/PREREG_2026-10-23.json, effective 2026-10-23, generated from the candidate tree
(lead/s825) with --model-optional-sport mlb / nfl / soccer. File sha256
0b86200da126c530ab6c848f228abc9fda233f1fb8298b8b0cf276c262faeab0, payload sha256
2c6689613cef0a5d1bd8c3602e45de5ac5594b76fd62a0bc0199b3500f798bf9. 8 of 8 implementation entries equal the
LF-normalised candidate files and are identical to PREREG_2026-10-21.json; the payload differs from it only in
effective_from and sha256. Commit-B candidate: lead/s825 (SEALS line PREREG_2026-10-23 + pin re-targets).

(c) COMMIT-B GATE (replaces the AMENDMENT 1 / memo section 9 gate):
(1) every night with day < 2026-10-23 that has a served schedule (10-20, 10-21, 10-22) has a terminal scoreboard
step (receipt written, or KILLED / refused recorded in nights/<day>.json) BEFORE commit B, because after commit B
those days refuse amendment_mismatch;
(2) `git diff 2ee92e7e9..master` EMPTY over the 8 hashed files, ingame_scoreboard_night.py,
ingame_scoreboard_amendment.py, scoreboard_history*.py and PREREG_2026-10-23.json;
(3) rebase lead/s825 onto master, `git merge --ff-only lead/s825` on master, push private master:trunk;
(4) the run set green on master one file at a time (test_system_fault_matrix case 11 excepted, pre-existing);
(5) selection rehearsal on master: 10-23 -> PREREG_2026-10-23.json; 10-22 -> PREREG_2026-10-07.json raising
amendment_mismatch (cause invalid_payload); 8 of 8 hashes;
(6) the next tick is tick_ok;
(7) commit B lands BEFORE the tick attempts night 10-23 (06:05Z 10-24 if the box is up); if night 10-23 ever runs
under the old identity first, the seal is re-dated again by this same procedure; never the same night as S721,
S613 or S625.

(d) FINDING 2026-10-22 (not fixed here): master no longer contains cf4dd7d86 or 6f463ebbb as ancestors (a
10-20 15:36Z cherry-pick sequence put a parentless commit 25f9ba76b on master's first-parent line; the tree
kept PREREG_2026-10-21.json byte-identical). Since then `git log -1 HEAD -- <seal>` returns 25f9ba76b
(2026-10-20) for every older seal, so on master code select(day) for any day raises amendment_not_prospective
(PREREG_2026-10-07: effective 10-07 <= commit day 10-20). Expected effect: the scoreboard steps of nights 10-20,
10-21 and 10-22 refuse (terminal, satisfies gate (1) as refused, but scores nothing), and the real-git asserts
in test_s492_landing.py (commit days 09-29 / 10-02 / 10-06) are red on master and the branch. PREREG_2026-10-23
is unaffected (its last commit is the genuine 2ee92e7e9). The old seal commits are kept reachable by the local
branch archive/s825-seal-a-2026-10-21 (6f463ebbb, not pushed). Needs an owner / dispatcher decision.

(e) COMMIT B LANDED 88192a004883d430e6ef36f351941d994b043939 2026-10-23 22:11Z (ff-only of lead/s825 onto master 5aad0526d; gate (c) items 1-5 and 7 verified
before the merge, item 6 at the next tick; run set 34 files on master one per process: 34 files, 1,262 passed, 1 failed, 0 not run (22:12Z-22:25Z; the same set on the candidate tree 21:10Z-21:23Z: 33 files exit 0 + the same single red); reds: test_system_fault_matrix case 14 only (pre-existing: red on master before the merge; its control select hard-codes day 2026-10-03, whose seal no longer matches the post-10-07 identity files; case 11 green on both runs); memo section
11). Finding (d) is RESOLVED by the S832 repair (`git fetch --unshallow private`, 10-22): the old seal commits are
ancestors of master again and select() picks PREREG_2026-10-07 for 10-07..10-22 without raising. Night 10-20 was re-run
by the go session BEFORE the merge (r1 COMPLETE 22:08Z; scoreboard 2,783.9 s with history = the pre-S825 wall). The S824
3,600 s deadline is revisited against the first S825 wall as its own row.
