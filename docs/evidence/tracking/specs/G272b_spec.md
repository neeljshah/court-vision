GAP G272b | sport wnba | worktree a5 | log g272b_box_jump_visual_classification
**READ `docs/evidence/tracking/specs/G272_spec.md` IN FULL AND FOLLOW IT EXACTLY. This file changes ONE
thing: what gets rendered.** Every other requirement in G272 -- the sampling, the blind randomised
classification with verdicts committed before un-blinding, the four fixed categories, the consequence
statement, the limitations, the disk guard, the ledger row -- **applies unchanged.**

**HELD UNTIL A POD LANE IS FREE** (N=2 is optimal). **Check first, do NOT interrupt a running row, and
EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**WHY THIS RE-ISSUE EXISTS -- A RETENTION GAP, AND THE LANE WAS RIGHT TO REFUSE.**
G272 **reproduced the required count exactly: 1,454 / 2,507 = 0.580** of retained both-endpoints-on-court
strict-over-40-ft/s same-ID steps have bottom-centre image displacement above 83 px. **But G267's landed
artifact retains only each detection's bottom-centre FOOTPOINT, not a drawable bounding box.** G272
therefore could not draw the boxes its render step required, and **correctly refused to invent them.**

**THE FIX IS NOT TO RE-DETECT.** G241 established the detector is non-deterministic (808 of 1,201 records
differed on an exact re-run), so a fresh pass would produce different records and **break comparability
with G267, G269, G270 and G271** -- the whole chain this row exists to complete.

**THE FIX IS THAT A BOUNDING BOX WAS NEVER NEEDED.** The question is *"is this the same person in both
frames?"* **A fixed-size crop CENTRED ON THE RETAINED FOOTPOINT answers it completely**, uses only landed
data, fabricates nothing, and keeps every number comparable.

**THE ONE CHANGE, replacing G272 step 3:**
  - **Render each sampled step as a before/after pair of fixed-size crops centred on that id's retained
    bottom-centre footpoint** in the frame before and the frame after, at full source resolution.
  - **State the crop size and say why you chose it** -- large enough to show a whole person and some
    surroundings, small enough to commit.
  - **Draw NO bounding box and infer none.** Mark the footpoint itself if that aids judgement, and **say
    that the crop is centred on the retained footpoint and that no box geometry exists in the artifact.**
  - **Annotate each pair with its image displacement and court speed**, as G272 required.
  - **If the two crops overlap heavily because the displacement is small, say so** rather than presenting
    them as clearly distinct views.

**EVERYTHING ELSE IS G272's**, and in particular:
  - **Reproduce the 1,454 count first** and confirm it matches; G272 already did, so a mismatch would be a
    significant finding.
  - **Sample at least 40, spread across the span AND across distinct ids**, not a head slice; report id
    coverage.
  - **Classify BLIND in randomised order, committing the order and verdicts in their own commit BEFORE
    un-blinding**, into exactly: **(a) SAME PERSON, real fast movement; (b) DIFFERENT PERSON; (c) NOT A
    PERSON in one or both crops; (d) OCCLUDED / CANNOT JUDGE.** **Keep (d) separate and never merge it.**
  - **State the consequence**: (b)-dominant makes it a tracker identity problem; (c)-dominant moves the
    defect upstream of association entirely; **a substantial (a) would mean part of the 10.5 pct is not an
    error and my "physically impossible" framing needs qualifying -- say so directly.**
  - **An eye check is appropriate here** because *"same person?"* is a **coarse categorical** judgement,
    not the sub-pixel geometric one G257 bounded at 20 px. **Say that distinction in the memo.**
  - **Do NOT propose a production change, filter, gate or threshold; do NOT touch `src/`; do NOT
    re-associate or re-detect.**
  - **The population is detector boxes, not authenticated players** (G225: 19 boxes, 2 visibly on-court
    people). **Name the denominator; never say "players" unqualified.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** (last about
**36,400 MB**, roughly 13.6 GB free). **`dd conv=fsync` probe before writing, STOP and report if it
fails.** **Crops are the bulk -- keep them modest and report committed bytes.** **Do NOT delete any corpus
source or the two abandoned partials in the bridge directory.** Report bytes freed.

**ADDITIONAL LIMITATION beyond G272's:** **a crop centred on a footpoint is not the detector's box** -- it
shows the neighbourhood the detection claimed, not the extent it claimed. **A judgement that two crops show
different people is about what is at those two locations, which is exactly the question, but it cannot
confirm what the detector actually bounded.** Say so.

ACCEPTANCE RULE, EVIDENCE, TEST and COMMIT: **as in G272_spec.md**, with the memo at
`docs/evidence/tracking/g272b_box_jump_visual_classification_2026-09-04.md` and the crop-size and
no-box-inferred statements added to the required evidence. **ADD A RESULTS_LEDGER.md ROW IN THE SAME
COMMIT AS THE MEMO.** Commit BEFORE reporting (A7). Explicit pathspec, no push, report the sha. Per-file
tests only, never a full pytest. ASCII stdout. **NEVER PARK.**
