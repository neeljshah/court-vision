GAP S394 | sport nba | worktree harness-h53 (master-based) | log cx_s394_nba_trial_runner
# NBA charged-trial runner: sibling of S359 with the period-first cell as PRIMARY (design: ASTRA_ROUND14 row 12)

SINGLE PROBLEM: the landed trial runner (row S359) is MLB-specific (family ingame_four_arm_mlb_r3, MLB census keys, the scorer's
tick / equal-game cells as the verdict source). The NBA prereg draft (row S382) declares a PERIOD-FIRST primary computed by the
landed S383 module over saved paired rows, with arm D descriptive on its paired subset (rows S385 / S387). Nothing can charge and
run an NBA trial today, and nothing must run one before the draft is sealed.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ingame/nba_four_arm_trial.py` fails. Read on master and quote: s359_four_arm_trial.py
(the nine-step launch order: sealed prereg SHA-256 + committed check, manifest pin BEFORE any corpus byte, canonical ledger guard,
output + attempt guards, census against frozen denominators, manifest re-read mutation guard, charge via backtest_runner._charge_ledger
with K read at launch, charge.json, then prediction; checkout-independent hashing; strict-int census typing), baseline_four_arm.py
(predict_rows / summarize after S387: d_eligible, d_subset, d_subset_warmup_keys), baseline_four_arm_period.py (stratified_cells;
--show-values gate), docs/evidence/ingame/S382_NBA_PREREG_DRAFT_r1_2026-09-21.md (populations, primary, bars, do-not-seal list),
backtest_runner's canonical helpers. The S347 result directory is NOT an input.

CHANGE (NEW files only):
1. scripts/platformkit/ingame/nba_four_arm_trial.py (<= 300 LOC; a NEW helper nba_four_arm_trial_guards.py is allowed): the same
   nine-step launch order, same refusals (occupied output, repeated attempt, non-canonical ledger, absent or empty ledger, wrong
   pin, checkout-dependent bytes), family ingame_four_arm_nba_r1, tier read from the sealed prereg text, K read at launch; the
   frozen denominators are parsed from the SEALED NBA prereg (which does not exist yet: the runner must refuse an UNSEALED prereg --
   no `SHA256: ` seal line, or a seal that does not match the normalized content, or a prereg not committed -- and a test proves the
   S382 draft is refused). After the charge: predict_rows on the corpus; write paired_rows.json and summary.json exactly as S359;
   THEN run the landed stratified_cells on the SCORED rows as the PRIMARY (primary.json: period-first C-minus-A Brier and log-loss
   with the four M[p], game counts, discarded draws, interval, verdict; secondaries labelled: tick, equal_game, game_first, D on
   its subset marked DESCRIPTIVE); trial_summary.json carries the primary verdict first and every secondary after it with the word
   SECONDARY. Nothing is printed to stdout except accounting lines (ledger path, prior max K, k_at_launch, attempt, counts).
2. tests/platformkit/ingame/test_nba_four_arm_trial.py: the nine-step recording test (each failure point leaves later steps
   unreached); an unsealed prereg refused; LF / CRLF identity equality; a synthetic sealed prereg + tiny synthetic corpus run end to
   end against a TEST ledger (the canonical guard mocked to a temp path ONLY through the landed test hook the S359 tests use);
   primary.json shape; D descriptive; strict-int census; no metric in stdout.
3. Memo docs/evidence/harness/S394_nba_trial_runner_2026-09-22.md.

CONTROLS: PREPARE only, NEW files only, construct tests, NO real corpus, NO real ledger, no network; the real NBA trial is NOT run
by anyone until the prereg is sealed. ACCEPTANCE: per-file test passes; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary
(assemble retracted-figure literals from single digits); the memo ends with a NOT VERIFIED list. The pod is OFF.
