GAP G294 | sport wnba | worktree a3 | log g294_gap_conditioned_implausibility
**MEASUREMENT ONLY. `src/` and `domains/` are READ and IMPORT only.** Build in
`scripts/platformkit/tracking/`.

**WHERE THIS ROW RUNS: ENTIRELY LOCAL. NO POD, NO GPU, NO DECODE, NO DISK GUARD, NO HOLD RULE. START
IMMEDIATELY.** The one input is committed and already in your worktree:
`docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv`, which carries
`frame_gap`, `image_displacement_px`, `court_displacement_ft`, `speed_ft_per_s` and `implausible` for all
29,973 steps. **Do not re-derive steps and do not open the video.**

**READ FIRST:** the G289 memo and its ledger row (landed 3f2000f20), and the G290 VERIFIER NOTE row.

**WHY THIS ROW EXISTS -- G289 LEFT A QUANTIFIED LEAD AND DID NOT FOLLOW IT.**
G289's frame-gap table shows implausible steps are **enriched at longer gaps**: gap 1 holds **0.724** of
implausible steps but **0.910** of plausible ones. **The verifier's arithmetic on those published counts:
the implausible rate is 2,961/26,523 = 0.1116 at gap 1 and 1,129/3,450 = 0.327 at gap above 1, nearly 3x
higher; gap-above-1 steps are 3,450/29,973 = 0.115 of all steps but carry 1,129/4,090 = 0.276 of the
implausible ones.** **Reproduce those five figures from `steps.csv` FIRST and paste the check; if any
disagree, STOP and report that as the finding.**

**WHY IT IS STRANGE, AND THIS IS THE POINT OF THE ROW.** `steps()` already **divides by the frame gap**,
so speed is gap-normalised. Under **genuine motion** distance grows LINEARLY with gap and speed is
gap-invariant, giving a FLAT rate. Under a **jump to an unrelated object** the distance is INDEPENDENT of
gap, so speed falls as 1/gap and longer gaps would be LESS implausible. **The observed rate RISES with
gap, which neither model predicts.** **Something about a step that spans a detection dropout makes the
court displacement grow FASTER than linearly in the gap, and nobody has measured it.**

THE QUESTION: **how does displacement scale with frame gap, and how much of the 0.136456 implausible rate
is attributable to gap composition rather than to per-step behaviour?**

METHOD:
  1. **REPRODUCE THE BASELINE AND THE FIVE FIGURES ABOVE** from the committed `steps.csv`. Paste the check.
  2. **REPORT, BY FRAME GAP (1, 2, 3, 4, 5, 6-10, above 10), with the ELIGIBLE denominator in every cell**
     -- steps at that gap -- **name the denominator, never the sample size**: the implausible rate, the
     median `court_displacement_ft`, the median `image_displacement_px`, and the median `speed_ft_per_s`.
     **Report the count in every cell and mark any cell below 30 steps as too small to read.**
  3. **TEST THE SCALING DIRECTLY.** Fit median court displacement against gap on a log-log scale and
     report the **exponent with its standard error**. **Exponent about 1 means linear, consistent with
     genuine motion. About 0 means gap-independent, consistent with a jump to an unrelated object. Above 1
     is SUPER-LINEAR and is what the enrichment implies -- and no current model predicts it.** **Do the
     same for median image displacement.** **State that a log-log fit through 7 medians is a DESCRIPTIVE
     summary on dependent data, not an inferential test, and give no p-value for it.**
  4. **STANDARDISE.** Report the implausible rate the corpus would show **if every step had gap 1's
     rate** -- that is gap 1's rate itself, 0.1116 -- and **the share of the observed 0.136456 that the gap
     composition accounts for: (0.136456 - rate_at_gap_1) / 0.136456.** **Report that share as a single
     number.** **This is a DECOMPOSITION OF THE RATE, NOT A CAUSAL ATTRIBUTION: a step spans a gap because
     the tracker lost the object, and losing the object may be a consequence of the same thing that makes
     the step wrong. Say that; do not call it a cause.**
  5. **MEASURE THE OVERLAP WITH THE KNOWN CANDIDATES so the shares cannot be double-counted.** G289's
     small-image-move bucket is 630/4,090 = 0.154 and the historical bimodal-id set is 185/4,090 = 0.045.
     **Report how many of the gap-above-1 implausible steps also fall in the small-image-move bucket.**
     **The withdrawn bimodal claim was withdrawn precisely because structure was reported without
     magnitude and overlap; do not repeat it.** **If you cannot compute an overlap, say so rather than
     assuming disjointness.**
  6. **ANSWER IN ONE SENTENCE WITH NUMBERS: what share of the implausible rate is carried by steps that
     span a dropout, and does displacement scale super-linearly with gap?** **A large share and
     super-linear scaling makes re-acquisition after a dropout the leading candidate mechanism and it
     should get the next row. A small share leaves the 84.6 pct open. BOTH ARE FULL SUCCESSES.**
  7. **Propose NO filter, threshold, gate, retrain or production change. Do NOT touch `src/`. Do NOT move
     the 40 ft/s bar** -- G279 already showed the finding survives moving it to 60. **Do NOT change any
     G289 count or artifact.**

**HONEST LIMITATIONS to state, not discover:** ONE clip, ONE span, ONE draw of a NON-DETERMINISTIC route
(G241: 808 of 1,201 records differed), though G282 reproduced the RATE at 0.136978 on an independent draw.
**Per G278 the span is measurably friendlier than the clip (0.836 against 0.656, p = 0.0078), so nothing
here may be quoted clip-wide.** **There is NO ground truth and NO eye check in this row** -- say that
rather than implying validation. **A gap is a property of the RETAINED records: a step spans a gap because
intervening detections were absent or dropped, and this row cannot tell those two apart.** **The population
is detector-box observations, not authenticated players** -- only about 0.208 of footpoints sit on a
player's feet, so a step may connect two things that are not players at all.

ACCEPTANCE RULE:
  metric        = the reproduced baseline and five published figures; the per-gap table with eligible
                  denominators, counts and small-cell marks; the log-log exponents with standard errors
                  for court and image displacement; the standardised rate and the gap-composition share as
                  a single number; the overlap with the small-image-move bucket; and the one-sentence
                  answer
  before        = implausible steps are enriched at longer gaps (gap 1 holds 0.724 of them against 0.910
                  of plausible steps) and the enrichment is unexplained and unquantified; 84.6 pct of
                  implausible steps have no mechanism
  bar           = **NO pass bar.** **A large share with super-linear scaling makes dropout re-acquisition
                  the leading candidate and earns the next row. A small share leaves the residue open. A
                  scaling exponent near 1 or 0 would match an existing model and is equally informative.
                  ALL are full successes and I want whichever is true stated bluntly.**
  n             = 29,973 steps, 4,090 implausible, 1 clip, 1 span, 1 draw -- name every denominator in
                  the verdict line and name the detector-box population
  eye check     = NONE. Arithmetic on a committed CSV, no ground truth. **Say that rather than implying
                  validation.**
  must not move = the 40 ft/s bar; G289's steps.csv, partition, gap table and counts; `steps()` and its
                  definition; G267's retained records and span; every threshold and verdict; `src/` and
                  `domains/` (READ and IMPORT ONLY)
EVIDENCE: `docs/evidence/tracking/g294_gap_conditioned_implausibility_2026-09-04.md` with the reproduction
check, the per-gap table, the scaling exponents, the standardised share, the overlap, the one-sentence
answer, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit
BEFORE reporting (A7). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the
orchestrator owns it and a lane edit collides with concurrent id allocation.
TEST: a per-file test for the harness, pasted -- **pin the reproduction of 0.136456 and of gap 1's
0.1116, and pin that the gap bucketing is exhaustive.** **NEVER a full pytest.** **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **Make EVERY commit before you finish.** ASCII stdout.
**NEVER PARK.**
