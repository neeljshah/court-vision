GAP G287 | sport wnba | worktree a5 | log g287_unconditioned_footpoint_content
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO DECODE, NO DISK GUARD, NO HOLD RULE. START IMMEDIATELY.**
Committed inputs, all already in this worktree:
  - **G273's 72 blind crops**:
    `docs/evidence/tracking/g273_detector_precision_blind_sample_artifact/blind_renders/`
  - **G273's committed verdicts and unblind map** in the same artifact directory.

**READ THE G286 MEMO, THE G286-CONSEQUENCE ROW AND THE G273-VS-G285b-RECONCILED ROW FIRST.**

**WHY THIS ROW EXISTS -- G286 FOUND THE MECHANISM ON A CONDITIONED SAMPLE, AND THE UNCONDITIONED VERSION
IS ONE RE-JUDGE AWAY.**
G286 classified what lies under the footpoint for **79 detections that already had a player nearby** and
found: **bare floor 0.506, broadcast graphics or tickers 0.367, different person 0.089, player's body
0.038, and the player's FEET 0.000.** **Zero of seventy-nine.**

**But those 79 were conditioned on a player being in the crop.** The unconditioned share of graphics is
unknown, and **G273's 0.208 NOT A PERSON category lumped "floor marking, equipment, scoreboard, graphic,
shadow, artifact" into one bucket**, so it cannot be split after the fact.

**G273's 72 crops are committed, each already marked with a small red centre cross at the footpoint.**
Re-judging them with G286's finer categories gives the **unconditioned** answer on an **already-sealed,
unconditioned sample** -- no new sampling, no new rendering, no pod.

THE QUESTION: **on an unconditioned sample, what is actually at the detector's footpoint, and how much
does G273's 0.597 overstate "the detection is on a player"?**

METHOD:
  1. **RE-JUDGE ALL 72 COMMITTED G273 CROPS in a FRESH randomised order, committing the order and the
     verdicts BEFORE un-blinding or joining anything.** **Do not re-render, re-sample or re-crop** -- use
     the committed JPEGs exactly as they are.
  2. **JUDGE WHAT IS UNDER THE CENTRE CROSS**, not what is in the crop. **State that distinction in the
     memo** -- it is the entire difference between this row and G273. Categories:
     **(a) a PLAYER'S FEET; (b) a PLAYER'S BODY but not feet; (c) BARE COURT OR FLOOR; (d) a BROADCAST
     GRAPHIC OR SCORE TICKER; (e) a PERSON who is not a player in play; (f) SOMETHING ELSE, with a free-text
     description; (g) CANNOT JUDGE.** **Keep (g) separate. Keep the free text on (f)** -- the graphics
     category only exists because G286 had one.
  3. **REPORT THE SEVEN COUNTS AND FRACTIONS**, and specifically **(a) as the fraction of unconditioned
     detections whose footpoint is actually on a player's feet.**
  4. **BUILD THE CROSS-TAB AGAINST G273's OWN COMMITTED VERDICTS.** For each crop, G273 recorded PLAYER /
     PERSON-not-player / NOT A PERSON / CANNOT JUDGE. **Report the full contingency table of G273's verdict
     against your finer category.** **The cell that matters is: of G273's 43 PLAYER verdicts, how many are
     (a) feet, how many (b) body, how many (c) floor, how many (d) graphic.** **That single row of the
     table quantifies exactly how much "0.597 precision" overstates "the detection is on a player".**
  5. **STATE THE OVERSTATEMENT IN ONE SENTENCE** with both numbers.
  6. **COMPARE YOUR (d) GRAPHIC SHARE WITH G286's 0.367** and say plainly whether the unconditioned share
     is similar or much lower. **G286's sample was conditioned on a player being nearby, so a LOWER
     unconditioned share is expected; a HIGHER one would be surprising and worth flagging.**
  7. **THIS IS A RE-JUDGE BY THE SAME LABELLER, SO IT MEASURES CATEGORY REFINEMENT, NOT INDEPENDENT
     CORRECTNESS.** Say so in those words. **If your (a)+(b)+(e) total disagrees sharply with G273's
     0.597+0.125, that is a finding about label stability and must be reported, not reconciled away.**
  8. **Do NOT re-detect, re-render, re-sample, or touch `src/`. Propose no filter, threshold, gate or
     retrain, and do not move any bar.**

**LIMITS to state:** 72 crops from ONE shot of ONE clip, ONE labeller, one non-deterministic detector
draw. **Same labeller as G273, so agreement is repeatability plus refinement, not validation.** **A
footpoint is a POINT: this row observes what is at it and can only infer box geometry, never measure it.**
**Per G278 the span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078): NOT
clip-wide.** The population is detector-box observations, not authenticated players.

ACCEPTANCE RULE:
  metric        = the committed fresh randomised order and verdicts; seven counts and fractions with (g)
                  separate and (f) free text retained; **the full cross-tab against G273's committed
                  verdicts, with the PLAYER row broken out**; the one-sentence overstatement statement;
                  and the comparison of the (d) share against G286's 0.367
  before        = G286 found 0/79 footpoints on a player's feet and 0.367 on graphics, but on a sample
                  CONDITIONED on a player being nearby; G273's 0.208 lumped floor, graphics and artifacts
                  together and its 0.597 is localisation-blind
  bar           = **NO pass bar.** **A near-zero (a) would confirm G286 unconditionally and would mean the
                  detector essentially never marks a player's feet.** **A substantial (a) would mean
                  G286's conditioned sample was unrepresentative and is the more interesting outcome.**
                  **A large (g) would mean the crops cannot answer it.** All are full successes.
  n             = 72 crops, 1 clip, 1 shot, 1 labeller -- name every denominator in the verdict line
  eye check     = the blind re-classification IS the measurement; it is a coarse categorical judgement at
                  full crop resolution, where the centre cross and its surroundings are both plainly
                  visible
  must not move = G273's committed crops, verdicts, unblind map and category definitions; G286's counts;
                  every threshold and verdict; `src/` and `domains/`
EVIDENCE: `docs/evidence/tracking/g287_unconditioned_footpoint_content_2026-09-04.md` with the committed
order and verdicts, the seven counts, the cross-tab, the overstatement sentence, the G286 comparison, and
a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.**
TEST: one per-file test for any harness added, pasted. **NEVER a full pytest.**
COMMIT: explicit pathspec, no push, report the sha. **Commit verdicts before un-blinding; make EVERY
commit before you finish.** ASCII stdout. **NEVER PARK.**
