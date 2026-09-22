GAP S355 | sport mlb + soccer_intl (+ nba checkpoints) | worktree harness-h13 (master-based) | log cx_s355_four_arm_eligibility
# Four-arm scorer: eligibility instead of stop-on-missing-state, three reviewer guards, and a counts-only census mode

AUTHORITY: docs/evidence/ingame/S347_PREREG_REVIEW_2026-09-21.md (orchestrator review of the unsealed S347 prereg draft).
SINGLE PROBLEM: scripts/platformkit/ingame/baseline_four_arm.py (landed by row S347, nothing scored) STOPS THE RUN when a row lacks
a mandatory state field. Measured on the real corpus (counts only): 52,646 of 78,986 mlb_clean rows carry a stated game state and
soccer_intl has 696 partial rows (7.7 pct), so the scorer would halt on its first real file. Three reviewer notes are also open.

BINDING BEFORE-CONDITION (re-run, quote): build a 3-row synthetic corpus under a temp dir where one row's state_summary lacks a
declared feature and show that the current loader / eligibility path raises (quote the exception).

CHANGE (EDIT the row-owned modules scripts/platformkit/ingame/baseline_four_arm.py and baseline_four_arm_features.py; the module
change is REQUIRED; add a NEW module baseline_four_arm_eligibility.py if needed to stay <= 300 LOC per file; edit no other
pre-existing module):
1. ELIGIBILITY, NOT ABORT. A tick is ELIGIBLE only if it has a finite market_prob strictly inside (0, 1) after the existing EPS
   clipping rule, a finite model_prob, an outcome, a parseable timestamp, and EVERY declared state feature for its sport. An
   ineligible tick is excluded from ALL FOUR arms identically and COUNTED by reason (missing_state:<feature>, missing_model_prob,
   missing_market_prob, nonfinite_value, unparseable_time) per file and per game. INTEGRITY failures still stop the run: manifest
   hash mismatch, unparseable JSON line, inconsistent outcome within a game, duplicate stable tick key, unknown corpus name.
   A game whose every tick is ineligible is reported as an excluded game with its reason histogram.
2. `--census-only` MODE: reads the corpus through the SAME loader and eligibility code and writes a JSON census -- per sport:
   files, games, ticks; eligible ticks and games; excluded ticks by reason; state-transition ticks; games per first-tick UTC date;
   number of warmup folds implied by the declared embargo; and whether eligible games >= 30. It computes NO loss, reads NO
   outcome beyond the presence and within-game consistency check, fits nothing, and therefore does NOT require a sealed prereg
   (it still requires the hash-matching manifest). The census JSON states `"scored": false` and lists every field it read.
3. GUARDS from the independent review of S347: (a) a --corpus-dir that does not resolve under the gate DATA_ROOT is a hard error
   (today the reused loader would return an EMPTY frame and the run would report every cell UNDERPOWERED); (b) assert per key
   that the output outcome equals the evaluator record outcome; (c) report the training-set size (games and ticks) for every
   fold, because rows carry no home/away and the shared same-team purge is degenerate.
4. Scoring mode keeps EVERY refusal it has today (manifest, sealed prereg, committed prereg). Bars, seeds and the verdict rule stay
   byte-identical to the inherited GATE A0 lines.
5. tests: NEW tests/platformkit/ingame/test_baseline_four_arm_eligibility.py -- ineligible ticks are dropped from all four arms
   identically and counted by reason; an all-ineligible game is reported, not fatal; each integrity failure still raises;
   --census-only runs WITHOUT a prereg, writes scored=false, and computes no loss (assert the loss functions are never called,
   e.g. by monkeypatching them to raise); the DATA_ROOT guard; the outcome-equality assertion; per-fold training sizes present.
   The existing tests/platformkit/ingame/test_baseline_four_arm.py must still pass; where an existing test encoded
   "missing state aborts", rewrite it to the new rule and say so in the memo.
6. Memo docs/evidence/harness/S355_four_arm_eligibility_2026-09-21.md + an UPDATED unsealed draft
   docs/evidence/ingame/S347_PREREG_DRAFT_r2_2026-09-21.md (ADD a new file; leave the first draft in place -- superseded evidence is
   never removed) whose text replaces the stop-on-missing rule with the eligibility rule and adds a placeholder section
   "Pre-seal eligibility census (filled by the orchestrator)". The builder does NOT seal and does NOT run on a real corpus.

CONTROLS: construct tests only; no real-corpus run; no calibration number. ACCEPTANCE: both per-file test runs pass; `--help`
shows --census-only; the self-check still passes. Vocabulary follows contract Q6; automated scan required; assemble any
retracted-figure literal from single digits. Memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (orchestrator, 2026-09-21; binding; found by feeding the REAL corpora through the candidate, counts only).
The candidate raised `duplicate stable tick key` on the first real corpus. MEASURED duplicate (game_id, ts) keys:
  mlb_clean 1,588 keys (1,659 extra rows; 1,500 IDENTICAL repeats, 88 CONFLICTING -- state_summary differs in 86, market_prob in 1,
  model_prob in 1; 87 games); mlb_segmented 50 keys, all CONFLICTING (state_summary differs); soccer_intl 203 keys (200 identical,
  3 conflicting on model_prob); soccer_intl_segmented 5 keys, all identical. So "duplicate stable tick key stops the run" (CHANGE
  item 1, integrity list) would halt on every real corpus. It is REPLACED by this outcome-blind rule:
  (a) IDENTICAL REPEATS (every field equal) collapse to ONE row; counted as duplicate_identical per file and per game.
  (b) A CONFLICTING KEY (same game_id and ts, any field differing) is AMBIGUOUS: EVERY row of that key is excluded from ALL FOUR
      arms identically, counted as conflicting_duplicate_key per file and per game. Never keep-first, keep-last or an average:
      any such choice would be an unregistered analyst decision.
  (c) The rule is applied BEFORE eligibility and before state-transition detection, so a dropped key never creates a transition.
  (d) A game where more than 10 pct of its keys are conflicting is reported in the census as high_conflict_game (it stays in the
      population; the census makes it visible so the prereg can name a threshold before sealing).
  The remaining integrity failures still stop the run: manifest hash mismatch, unparseable JSON line, inconsistent outcome within a
  game, unknown corpus name.
Required tests: identical repeats collapse with a count; a conflicting key removes all of its rows from every arm and from the
transition population; the census reports both counters and high_conflict_game; the old duplicate-key abort test is rewritten.

AMENDMENT 2 (orchestrator, 2026-09-21; binding; found by running the candidate's eligibility step over the REAL corpora, counts only).
RESULT OF THAT RUN: mlb_clean 78,986 rows -> 0 eligible ticks; mlb_segmented 27,351 -> 0; the dominant reason is
missing_state:base1 / base2 / base3 (77,239 rows). The declared MLB feature names do not exist in the data. MEASURED key census of
the real state_summary strings (mlb_clean): 43,915 rows carry {home_score, away_score, inning, half, outs, base, bos, re, count,
pitch_count, tto}; 7,318 carry the same without pitch_count and tto; 1,313 lack half; 26,340 are the bare word "live" (state-less).
The base field is ONE integer with eight observed values 0..7 (0: 33,142; 1: 8,729; 3: 3,190; 2: 3,073; 5: 1,462; 7: 1,114;
4: 954; 6: 882). Example: home_score=0.0 away_score=0.0 inning=1 half=top outs=1 base=1 bos=4 re=0.509 count=1-2.
BINDING CHANGE to the declared MLB features (this supersedes "base1/base2/base3" in the S347 draft and in the features module):
  (e) MLB declared features are: score_diff (home_score minus away_score), inning, half (top = 0, bottom = 1), outs (0, 1, 2), and
      BASE AS A ONE-HOT OVER ITS EIGHT VALUES 0..7 (seven indicator columns, value 0 as the reference). No bit order is assumed and
      none is decoded: the one-hot is encoding-agnostic. A base value outside 0..7, or a non-integer, makes the tick ineligible with
      reason missing_state:base. The fields bos, re, count, pitch_count and tto are NOT features in this baseline (re is itself a
      model output); the memo lists them as available-but-excluded.
  (f) Scores arrive as decimal strings such as 2.0; parse them as numbers and require them finite.
  (g) Soccer declared features stay score_diff and minute; the red-card inputs stay optional exactly as drafted (absent -> zero with
      indicator zero). MEASURED soccer keys: 2,524 rows {home_score, away_score, minute}; 1,134 with half as well; 696 without minute;
      4,649 state-less. half is NOT required for soccer.
  (h) The census must show the eligible-tick and eligible-game counts AFTER this change on synthetic fixtures shaped like the real
      strings above; the orchestrator re-runs it on the real corpora.
Required tests: the exact example string above is eligible and yields the right one-hot; base=8 and base=1.5 are ineligible with
reason missing_state:base; a row without half is ineligible for MLB and eligible for soccer; decimal-string scores parse.
Also update docs/evidence/ingame/S347_PREREG_DRAFT_r2_2026-09-21.md: the MLB feature list per (e), and a sentence that a sport with
fewer than 30 eligible games in the pre-seal census is declared UNDERPOWERED in the sealed text and reported descriptively only.
