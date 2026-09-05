GAP G291 | sport wnba | worktree a4 | log g291_independent_second_rater_agreement
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO GPU, NO DECODE, NO RENDERING, NO DISK GUARD, NO HOLD
RULE. START IMMEDIATELY.** Everything is committed and already in your worktree:
`docs/evidence/tracking/g273_detector_precision_blind_sample_artifact/` -- 72 rendered JPEG crops in
`blind_renders/`, G273's committed verdicts, and its unblind map.

**READ FIRST:** the G273 and G287 memos and their ledger rows, and `VERIFIER_CONTRACT.md`.

**WHY THIS ROW EXISTS -- EVERY EYE-LABELLED NUMBER IN THIS PROGRAMME RESTS ON ONE RATER AND NOBODY HAS
MEASURED WHETHER A SECOND ONE AGREES.**
G273's **0.597 PLAYER / 0.208 NOT A PERSON**, G280b's amateur **0.347 / 0.514**, G287's **0.181 graphic**
and G286's content split are ALL single-labeller eye judgements. **Verified from the dispatch logs: G273,
G280b, G285b and G287 every one ran on `gpt-5.6-terra`. They are the SAME RATER, so their agreement with
each other measures REPEATABILITY, never independence -- both memos say so.**

**YOU ARE RUNNING ON `gpt-6-astra`. You are a DIFFERENT rater, and this is the programme's first genuine
inter-rater measurement.** Every downstream comparison -- broadcast against amateur, 1080p against 720p,
conditioned against unconditioned -- inherits whatever labeller variance is measured here, **and that
variance is currently UNQUANTIFIED.**

THE QUESTION: **how much of G273's 0.597 survives an independent rater?**

METHOD:
  1. **RE-JUDGE ALL 72 COMMITTED CROPS IN A FRESH RANDOMISED ORDER. Commit the order and your verdicts in
     their OWN commit BEFORE you open G273's verdicts or its unblind map.** **Do NOT read G273's verdict
     file until that commit exists** -- report the sha of the sealing commit in the memo. **Do NOT
     re-render, re-crop or re-sample. Use the committed JPEGs exactly as they are.**
  2. **G273's FOUR CATEGORIES, UNCHANGED AND NOT REDEFINED**: (a) a PLAYER on the court of play; (b) a
     PERSON who is not a player in play; (c) NOT A PERSON; (d) CANNOT JUDGE. **Keep (d) separate; never
     fold it into another bucket.** Judge by G273's own rule -- **what the CROP shows**, which is the rule
     G273 used, NOT G287's centre-cross rule. **State which rule you applied; mixing the two would make
     the comparison meaningless.**
  3. **CARRY A FREE-TEXT LINE ON EVERY CROP.** The graphics category only exists at all because an earlier
     row carried free text.
  4. **THEN un-blind and build the 4x4 CONFUSION MATRIX against G273's committed verdicts**, both
     marginals shown.
  5. **REPORT RAW AGREEMENT and COHEN'S KAPPA with its interpretation.** **Report kappa's standard error
     and say plainly that at n = 72 it is imprecise.** Report per-category agreement too -- **overall
     kappa can hide a category that never agrees.**
  6. **REPORT YOUR OWN FOUR RATES AND COMPARE EACH TO G273's** (0.597 / 0.125 / 0.208 / 0.069). **Use
     McNemar's test on the PAIRED PLAYER-versus-not judgements -- the crops are the same crops, so an
     unpaired two-proportion test is the WRONG test here. Report the nominal two-sided p and say it is
     nominal.**
  7. **ANSWER IN ONE SENTENCE: does an independent rater reproduce 0.597, and within what margin?**
     **HIGH agreement means every landed precision figure carries less labeller risk than feared and I
     want that said. LOW agreement means the programme's eye-labelled numbers carry an uncertainty that
     was never quantified, every downstream comparison inherits it, and I want THAT said just as bluntly.
     BOTH ARE FULL SUCCESSES. Do not converge toward G273's numbers -- you have not seen them when you
     judge, and your independence IS the measurement.**
  8. **NAME EVERY CROP WHERE YOU AND G273 DISAGREE, with your category, G273's, and your free text.** A
     systematic disagreement (for example G273 calling a distant blurred shape a PLAYER where you call it
     CANNOT JUDGE) is more informative than the scalar and **must be described in words.**
  9. **DO NOT CHANGE, RE-OPEN OR CORRECT ANY G273 VERDICT.** G273's verdicts are the reference; your
     disagreement is the measurement, not an error to be fixed. **Propose no filter, threshold, retrain or
     production change. Do NOT touch `src/`. Do NOT move any bar.**

**HONEST LIMITATIONS to state, not discover:** **TWO MODEL RATERS AGREEING IS NOT GROUND TRUTH.** This row
measures REPRODUCIBILITY ACROSS RATERS, never CORRECTNESS -- **both raters can be wrong in the same
direction, and high agreement would NOT establish that either is right.** **Say that in those words.**
Neither rater is a human and no human has checked these 72 crops. **A 512x640 crop is not the detector's
box, and a crop-level judgement cannot say where in the crop the detection actually fell** -- that is why
G287's centre-cross re-judge found G273's 43 PLAYER verdicts split 13 feet / 15 body / 12 floor / 2 graphic
/ 1 basketball. **This row inherits that limit and does not touch it.** 72 crops, ONE clip, ONE span, ONE
shot, ONE draw of a non-deterministic route. **Per G278 the span is measurably friendlier than the clip
(0.836 against 0.656, p = 0.0078), so nothing here may be quoted clip-wide.** The population is
detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the sealed randomised order and verdicts committed BEFORE un-blinding, with that sha
                  reported; the 4x4 confusion matrix with both marginals; raw agreement; Cohen's kappa with
                  its standard error and per-category agreement; your four rates against G273's; McNemar's
                  paired test with nominal p; the one-sentence answer; and every disagreeing crop named
                  with both categories and your free text
  before        = 0.597 PLAYER and 0.208 NOT A PERSON from a SINGLE rater (`gpt-5.6-terra`), with
                  inter-rater agreement entirely unmeasured across every eye-labelled row in the programme
  bar           = **NO pass bar.** **High agreement lowers the labeller risk on every landed precision
                  figure. Low agreement means those figures carry an unquantified uncertainty that every
                  downstream comparison inherits. A kappa too imprecise to call at n = 72 is an honest
                  result. ALL are full successes and I want whichever is true stated bluntly.**
  n             = 72 crops, 2 raters (`gpt-5.6-terra` for G273, `gpt-6-astra` for you), 1 clip, 1 span,
                  1 shot, 1 draw -- name every denominator in the verdict line and name both raters
  eye check     = the re-judge IS the measurement. It is a COARSE categorical judgement at full crop
                  resolution, not a geometric one. **Say that distinction.**
  must not move = G273's crops, sealed order, verdicts, unblind map and category definitions; G287's
                  verdicts; G280b's and G286-G288's counts; every threshold and verdict; `src/` and
                  `domains/` (READ and IMPORT ONLY)
EVIDENCE: `docs/evidence/tracking/g291_independent_second_rater_agreement_2026-09-04.md` with the sealing
sha, the confusion matrix, agreement and kappa with its standard error, the rate comparison, McNemar's
test, the one-sentence answer, the named disagreements with free text, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted -- **pin that kappa on identical verdict vectors is
1.0 and that it is 0.0 on chance-level agreement.** **NEVER a full pytest.** **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
