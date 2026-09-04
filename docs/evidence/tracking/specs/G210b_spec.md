GAP G210b | sport ncaa_basketball / wnba | worktree a6 | log g210b_court_fit_untruncated_search
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: LOCAL, and NO POD.** 17 small JPEGs, classical geometry, no weights, no downloads, no
build toolchain. The pod is running G203 and must not be disturbed.

**S3 DEPENDENCY -- THIS ROW EXISTS BECAUSE G210's RESULT WAS RETRACTED, AND THE RETRACTION TELLS YOU
EXACTLY WHAT TO FIX.** G210 reported 0/17 and the orchestrator wrote that the classical route was
CLOSED. **That claim was withdrawn.** An adversarial review found:
  - **`scripts/platformkit/tracking/g210_court_model_fit_to_lines.py:37` sets `MAX_GROUPS = 24`**,
    retaining only the 24 LONGEST line groups, while the detector produces **82 to 900 groups per
    frame**.
  - The TRUE paint lines sit **2-30 px** from some group in the FULL set, but **30-230 px** away
    within the top-24. **In 16 of 17 frames the correct hypothesis was not in the search space.**
  - `:38` draws **2,048** samples, about **0.02 pct** of the ~9M distinguishable
    4-group-by-assignment configurations.
  - **Oracle proof:** feeding G210's own `solve_line_pairs` the oracle-nearest real paint lines from
    the UNTRUNCATED set drops median max-corner error from **469 px to about 27 px** and puts
    **1 of 17** under the 12 px bar.

**WHAT ALREADY PASSED REVIEW AND MUST NOT BE "FIXED": the court model** (94x50 ft, 19 ft paint depth,
NCAA 12-ft vs WNBA 16-ft lane, `:79-88`), **the per-frame league assignment** (the `wnba__` prefix
rule, identical to G196's), **the scoring** (model corners inverse-projected to native pixels and
compared to native-pixel labels), and **the absence of any label leak** (`fit_image(image, sport)`
takes no labels). **Change none of those.** Reuse `score_frame` from
`g205_zero_shot_corner_probe.py` unchanged so every number stays commensurable with G205, G208 and
G210.

THE QUESTION: **with the truncation removed and the search actually adequate, what does global
classical court-model fitting score?**

METHOD:
  1. **Remove or greatly raise `MAX_GROUPS`.** If you keep any cap, it must be justified by a measured
     property of the group set, not a round number, and you must report how often the true lines fall
     inside it. **Prefer no cap.**
  2. **Make the search adequate, and say what "adequate" means quantitatively.** Report the size of
     the configuration space and the fraction you sample. If exhaustive search is infeasible, use a
     principled reduction -- for example filtering groups by orientation or by plausible court-line
     geometry BEFORE sampling -- and **state the reduction and the risk that it re-introduces the same
     defect**. Any filter that could discard a true line must be measured for exactly that, the way
     the reviewer measured the top-24.
  3. **Report the oracle bound as a control in the same run.** The reviewer measured 1/17 and ~27 px
     median with oracle-selected lines. **Reproduce that number yourself.** It is the ceiling your
     search can reach with this detector, and reporting your result WITHOUT it is not interpretable.
  4. **Labels stay HELD OUT of the fit.** They may be used for the oracle CONTROL and for scoring, and
     those uses must be clearly separated in the code and in the memo. **If a label reaches the real
     fit, the row is void.**

**HONEST FRAMING you must carry, not discover:** the oracle bound is **1/17**, so **even a perfect
search over these lines is expected to be weak.** A result at or near 1/17 CONFIRMS the reviewer and
is a full success. **Do not present a near-oracle result as vindication of the classical route** -- it
would mean the search was the bug AND the route is still weak, which are both true at once.

ACCEPTANCE RULE:
  metric        = frames with all four roles within 12 px over 17, from the untruncated search;
                  per-corner error distribution; the oracle-control score in the same run; the
                  configuration-space size and the sampled fraction
  before        = G210 scored 0/17 with `MAX_GROUPS=24`, which excluded the true lines in 16/17
                  frames; the oracle bound is 1/17 at ~27 px median; the honest score of an adequate
                  search is unknown
  bar           = NO pass bar. **Matching the 1/17 oracle bound is a FULL SUCCESS** and settles that
                  the truncation was the whole gap. Scoring 0/17 even untruncated is ALSO a full
                  success and would mean the search, not the cap, is the limitation. **Do not tune to
                  beat the oracle -- exceeding an oracle control is a sign of a leak, and you must
                  investigate rather than report it.**
  n             = 17 frames (CONSTRUCT, exhaustive), both leagues handled separately
  eye check     = render the fitted model over the same 5 evenly spaced frames G210 used, so the two
                  are directly comparable. Render even at 0/17.
  must not move = the court model, the league assignment, the scorer, the 12 px protocol, the
                  held-out status of the labels in the fit, every threshold and verdict, `src/`
                  (READ ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g210b_court_fit_untruncated_search_2026-09-03.md with the per-frame
table, the search-space accounting, the oracle control reproduced, the 5 renders, an explicit
statement of how labels were kept out of the real fit, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test, pasted. NEVER a full pytest. **If a commit grows an allowlisted file, raise its
entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit (contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
