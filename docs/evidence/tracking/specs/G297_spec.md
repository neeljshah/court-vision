GAP G297 | sport wnba | worktree a4 | log g297_centre_cross_rater_agreement_clean
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO GPU, NO DECODE, NO RENDERING, NO DISK GUARD, NO HOLD
RULE. START IMMEDIATELY.** Everything is committed: the 72 rendered crops in
`docs/evidence/tracking/g273_detector_precision_blind_sample_artifact/blind_renders/` and G287's verdicts
in `docs/evidence/tracking/g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv`.

**READ FIRST -- AND THIS LIST IS DELIBERATELY SHORT:** the G291 memo and its ledger row, and the G273
memo. **DO NOT READ THE G287 MEMO, THE G288 MEMO, OR ANY `blind_verdicts.csv` UNTIL YOUR OWN VERDICTS ARE
COMMITTED.** **G288's memo names 30 of these 72 crops by their `blind_NNN` identifier and describes what
is in each one; the predecessor row G295 was required to read it and its blinding was destroyed. That
was a defect in the VERIFIER's spec, not the lane's work, and this row exists to redo it cleanly.** **If
any instruction you are given would have you open a file naming `blind_NNN` identifiers before you have
committed your verdicts, DO NOT OPEN IT -- say so in the memo and continue.**

**WHY THIS ROW EXISTS -- G295 ASKED THE RIGHT QUESTION AND ITS BLINDING WAS BROKEN BY MY OWN SPEC.**
**G295 returned centre-cross agreement 37/72, kappa 0.394 (SE 0.069), on-a-player 10/72 against G287's
32/72 -- but it had been required to read the G288 memo first, which names 30 of the 72 crops and
describes their content. Label leakage can only push a rater TOWARD the reference, so that kappa is
INFLATED and the rate gap is unsafely signed.** **YOU ARE A THIRD, FRESH RATER (`gpt-5.6-sol`): unlike
G295 you have never judged these crops, so this is the programme's first clean inter-rater measurement
of the WELL-POSED rule.**

**THE BACKGROUND G291 ESTABLISHED, AND WHY IT MATTERS.**
G291 had an independent rater (`gpt-6-astra`) re-judge G273's 72 crops under **G273's CROP-LEVEL rule**.
Result: **PLAYER 60/72 = 0.833 against G273's 43/72 = 0.597, raw agreement 47/72 = 0.653, Cohen's kappa
0.283 (SE 0.079), exact McNemar p = 0.0000763.** **The second rater never once used NOT A PERSON:** all 15
of G273's NOT A PERSON crops became 10 PLAYER, 4 PERSON-not-player, 1 CANNOT JUDGE.

**And G291 diagnosed the cause in its own words: the second rater "sees recognizable players ELSEWHERE IN
THE CROP", including peripheral legs, players behind officials, and players above graphics.** **That is a
RULE disagreement, not a perception disagreement.** A 512x640 crop covers **26.7 pct x 59.3 pct of a 1080p
frame** and routinely contains several people, so **"what does the crop show" is UNDER-SPECIFIED and
0.597 was never a well-defined quantity.**

**G287's CENTRE-CROSS rule -- what is under the small red cross at the footpoint -- has no such ambiguity,
and it is the rule the programme's real numbers use: 0.208 on a player's feet, about 0.44 on a player at
all, 0.181 on overlay furniture.** **Inter-rater agreement on THAT rule has never been measured.** **If it
is high, those numbers survive G291 and the programme's evidence base is sound. If it is low too, every
eye-labelled figure is in trouble.** **This is the row that decides which.**

THE QUESTION: **does an independent rater reproduce G287's centre-cross content profile?**

METHOD:
  1. **RE-JUDGE ALL 72 COMMITTED CROPS IN A FRESH RANDOMISED ORDER. Commit the order and your verdicts in
     their OWN commit BEFORE you open G287's verdicts.** **Do NOT read G287's verdict file until that
     commit exists**; report the sealing sha. **Do NOT re-render, re-crop or re-sample.**
  2. **APPLY G287's CENTRE-CROSS RULE AND ONLY THAT RULE: judge WHAT IS UNDER THE SMALL RED CROSS, NOT
     WHAT IS ANYWHERE IN THE CROP.** **This is the entire point of the row.** **A recognizable player
     elsewhere in the crop is IRRELEVANT: if the cross sits on the floor, the verdict is BARE COURT OR
     FLOOR even when a player is plainly visible two metres away.** **State in the memo, in your own
     words, that you applied the centre-cross rule and not the crop-level rule.**
  3. **CATEGORIES ARE G287's, UNCHANGED AND NOT REDEFINED**: (a) a PLAYER'S FEET; (b) a PLAYER'S BODY but
     not feet; (c) BARE COURT OR FLOOR; (d) a BROADCAST GRAPHIC OR SCORE TICKER; (e) a PERSON who is not a
     player in play; (f) SOMETHING ELSE, free text; (g) CANNOT JUDGE, kept separate. **FREE TEXT MANDATORY
     ON EVERY ROW.**
  4. **THEN un-blind and build the 7x7 CONFUSION MATRIX against G287's committed verdicts**, both
     marginals shown. **Report raw agreement, Cohen's kappa with its standard error, and per-category
     agreement.** **A category one rater never uses is the single most informative cell -- G291's
     zero-count NOT A PERSON column is what exposed the rule problem -- so REPORT EVERY ZERO EXPLICITLY
     rather than omitting empty rows.**
  5. **REPORT YOUR SEVEN RATES AGAINST G287's** and use **McNemar's exact test on the paired
     "footpoint is on a player at all", meaning (a)+(b)** -- **the crops are THE SAME CROPS, so a paired
     test is correct and an unpaired two-proportion test would be WRONG here.** Nominal p, said to be
     nominal.
  6. **COMPARE THE TWO KAPPAS DIRECTLY AND SAY WHAT THE COMPARISON MEANS: G291's crop-level kappa was 0.283 (SE 0.079)
     and G295's leak-inflated centre-cross kappa was 0.394 (SE 0.069).** **If your centre-cross kappa is materially higher, the well-posed rule is
     reproducible and the ambiguity was the crop rule -- which would mean the programme should quote
     centre-cross numbers and RETIRE crop-level ones. If it is similarly low, the problem is not the rule
     and every eye-labelled number in the programme carries this uncertainty.** **Say which, bluntly.**
     **Do NOT test the difference between the two kappas for significance** -- they come from overlapping
     judgements on the same 72 crops by partly the same raters, and no valid test is specified here.
     **Compare them descriptively with both standard errors shown.**
  7. **NAME EVERY DISAGREEING CROP** with both categories and your free text, and **describe any
     SYSTEMATIC pattern in words** -- a pattern is more informative than the scalar.
  8. **DO NOT CHANGE, RE-OPEN OR CORRECT ANY G287, G288, G273 OR G291 VERDICT.** Your disagreement is the
     measurement, not an error to fix. **Do NOT converge toward G287's numbers -- you have not seen them
     when you judge, and your independence IS the measurement.** **Propose no filter, threshold, retrain
     or production change. Do NOT touch `src/`. Do NOT move any bar.**

**HONEST LIMITATIONS to state, not discover:** **TWO MODEL RATERS AGREEING IS NOT GROUND TRUTH.** This
measures REPRODUCIBILITY ACROSS RATERS, never CORRECTNESS -- **both raters can be wrong in the same
direction, and high agreement would NOT establish that either is right.** **Say that in those words.**
Neither rater is a human and no human has checked these 72 crops. **You are the same model that produced
G291's crop-level verdicts on these SAME crops, so you may carry over an impression of them; say so, and
say that this makes your agreement with G287 a CONSERVATIVE test of rule-clarity rather than a fully
independent one.** **A footpoint is a POINT: this row says what is AT it, never what a bounding box
contained.** 72 crops, ONE clip, ONE span, ONE shot, ONE draw of a non-deterministic route. **Per G278 the
span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078), so nothing may be quoted
clip-wide.** The population is detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the sealing sha; an explicit statement that the centre-cross rule was applied; the 7x7
                  confusion matrix with both marginals and every zero shown; raw agreement; Cohen's kappa
                  with SE and per-category agreement; the seven rates against G287's; exact McNemar on the
                  paired on-a-player judgement; the descriptive comparison against G291's 0.283 kappa with
                  both SEs; and every disagreeing crop named with free text and any systematic pattern
  before        = G291 measured crop-level kappa at 0.283 and traced the disagreement to an
                  under-specified crop rule; agreement on the well-posed centre-cross rule -- which is what
                  the programme's 0.208 / 0.44 / 0.181 figures use -- has never been measured
  bar           = **NO pass bar.** **A materially higher kappa means the centre-cross rule is reproducible
                  and crop-level figures should be retired. A similarly low kappa means every eye-labelled
                  number in the programme carries this uncertainty. Too imprecise to separate at n = 72 is
                  an honest result. ALL are full successes and I want whichever is true stated bluntly.**
  n             = 72 crops, 2 raters, 1 clip, 1 span, 1 shot, 1 draw -- name every denominator in the
                  verdict line, name both raters, and name the detector-box population
  eye check     = the re-judge IS the measurement. A COARSE categorical judgement at the centre cross, not
                  a geometric one. **Say that distinction.**
  must not move = G287's, G288's, G273's and G291's verdicts, crops, sealed orders and category
                  definitions; every threshold and verdict; `src/` and `domains/` (READ and IMPORT ONLY)
EVIDENCE: `docs/evidence/tracking/g297_centre_cross_rater_agreement_clean_2026-09-04.md` with the sealing sha,
the rule statement, the confusion matrix, agreement and kappa with SE, the rate comparison, McNemar, the
kappa-versus-kappa comparison, the named disagreements and pattern, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator owns it.
TEST: a per-file test for any harness added, pasted -- **pin kappa 1.0 on identical verdict vectors, 0.0
at chance, and that a category with a ZERO column is retained in the matrix rather than dropped.**
**NEVER a full pytest.** **If a commit grows an allowlisted file, raise its entry in
`tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
