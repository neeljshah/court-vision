GAP G208 | sport ncaa_basketball / wnba | worktree a6 | log g208_zero_shot_corner_probe_learned
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. Build any harness
in `scripts/platformkit/tracking/`.

**S1 MACHINE: LOCAL, and NO POD.** 17 small JPEGs. The pod is running G203 (byte identity) and must
not share the machine. Do not launch the `run_clip.py` route.

**NETWORK FETCH AND PACKAGE INSTALL ARE EXPLICITLY AUTHORISED FOR THIS ROW.** G205 correctly skipped
every learned candidate because my spec did not say whether it could fetch them; that ambiguity was
mine. You MAY `pip install` and download official checkpoints. **Conditions, all binding:**
  - Install into the environment; **do NOT vendor third-party source into this repo**, and **never
    add a GPL-licensed dependency**.
  - **Verify and record the licence of both the CODE and the WEIGHTS separately.** G205 flagged that
    weight licences were not independently verified for any candidate; that is the gap to close.
    **If a weight licence cannot be established, run the candidate but mark the result
    LICENCE-UNVERIFIED and say it cannot be shipped on that basis.**
  - Record exact package versions and checkpoint URLs plus sizes, so this is reproducible.
  - **If a fetch fails, report the failure and move to the next candidate.** Do not spend the row
    fighting an install.

**S3 DEPENDENCY, and read G205's numbers before you start.**
  - **G205** (landed `fb1ae4c6d`) ran ONE candidate, G134 stable-LSD intersections:
    **0/17 all-four frames, 22/68 corner recall, 80/32,777 proposal precision hits (0.24 pct).**
    ELSED, DeepLSD, HAWP, M-LSD and KpSFR were excluded, not measured, so **the zero-shot route is NOT
    closed** -- G205's STOP condition required 0/17 for EVERY candidate.
  - **G141**: a naive local-response corner detector scored **0/68 recall**. **So G205's 22/68 is a
    real improvement and line-based methods clearly carry signal** -- they simply never get all four
    roles right in the same frame.
  - **G196**: a homography from four hand-labelled corners projects correctly, so the geometry is
    recoverable and the ceiling is DETECTION.
  - **G192b**: the production Hough solver returns `None` on 17 of 17.
  - **G31**: closed a LEARNED, TRAINED calibration path AT LIMIT for tennis. **This row trains
    NOTHING** -- every candidate is run zero-shot on released weights -- so it does not reopen G31. If
    you find yourself wanting to fine-tune, stop: that is a different row that must cite G31.

THE QUESTION, unchanged from G205 and still open: **does any licence-clean zero-shot primitive propose
the four paint corners on these frames?**

**THE PRECISION CONSTRAINT, which G205 makes concrete and you must report against:** 32,777 proposals
across 17 frames is about **1,928 proposals per frame**. Any method that proposes on that scale is
unusable even if recall improves, because a homography solver cannot consume it. **Report proposals
per frame for every candidate**, and treat a candidate with high recall and unusable precision as a
negative result, not a success.

CANDIDATES, in this order (cheapest first; stop only when you run out of time or candidates):
  1. **ELSED** (Apache-2.0, no weights needed) -- cheapest, do this one first.
  2. **M-LSD** (Apache-2.0 code) and **HAWP** / **DeepLSD** (MIT code, Wireframe-trained weights).
  3. **KpSFR** (MIT, soccer weights) -- run purely to see whether the architecture proposes anything
     on a basketball court. **A null result here is expected and is still informative.**

PREMISES, VERIFIED BY THE ORCHESTRATOR OVER THE WHOLE SET (S2):
  - `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv` holds 68 rows, all
    `status = target`; **all 17 frames carry all FOUR distinct roles** (17 each).
  - All 68 `source_decode` JPEGs exist. Resolutions are **MIXED**: 12 at 1920x1080, 4 at 1280x720, 1
    at 640x360. **Handle that explicitly; do not assume 1080p.**

METHOD -- G141's protocol EXACTLY, and G205's scorer already implements it: reuse
`scripts/platformkit/tracking/g205_zero_shot_corner_probe.py`'s `score_frame` rather than writing a
second scorer, so the numbers are commensurable. One fixed configuration per candidate across all 17
frames, stated; **no per-frame tuning**.

**THE HONEST LIMITATION you must state rather than discover:** G140's p90 label repeatability is
**11.39 px**, so the 12 px match threshold sits AT the label noise floor. A candidate that passes at
12 px has been shown to propose something in roughly the right place -- it has NOT been shown accurate
enough for production.

ACCEPTANCE RULE:
  metric        = frames with all four roles within 12 px over 17; per-corner recall over 68;
                  precision over proposals; **and proposals per frame**; per candidate
  before        = G141 0/68 with a naive detector; G205 0/17 frames, 22/68 recall, 0.24 pct precision
                  with classical LSD intersections; five named candidates unrun
  bar           = **>= 1 of 17 for any candidate.** **STOP: 0 of 17 for every candidate run here,
                  taken together with G205, closes the ZERO-SHOT corner route AT LIMIT** -- a FULL
                  SUCCESS that saves a large investment. **It does NOT close labelling, and must not
                  be written as closing it.** Do not tune, do not lower the bar, do not add a
                  candidate after seeing results to rescue the row.
  n             = 17 frames (CONSTRUCT, exhaustive) x every candidate you obtain; name every exclusion
  eye check     = for the best-scoring candidate, render proposals against labels on 5 evenly spaced
                  frames and say what a human sees. If all score 0, render the closest anyway so the
                  failure mode is visible.
  must not move = every threshold, every bar and verdict, the 12 px protocol, G205's scorer contract,
                  the coordinate contract, `src/` (READ ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g208_zero_shot_corner_probe_learned_2026-09-03.md with the
per-candidate per-frame table, **separate CODE and WEIGHT licences with how each was established**,
package versions and checkpoint URLs, proposals per frame, the renders, the 11.39 px label floor
stated, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).** Note master's rail entry for `tracking_harness.py` is **425** as of G204; if your
worktree shows 416 you are behind master, not looking at a failure.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
