# G120: preregistered basketball paint-line fragment merge

## Preregistered merge rule (recorded before scoring)

This diagnostic-only pass inserts one fragment-merge step between the frozen
G93 LSD output and the frozen `candidate_line_group_details(..., 5.0, 10.0)`
call. It does not change `line_calibration.py`, the LSD minimum length (28.0),
the grouping settings, the G93 correspondence rule, any labels, or any
sampling rule.

The constants are fixed before any G120 recall or precision measurement:

| rule component | preregistered value |
|---|---:|
| unsigned orientation difference | at most 4.0 degrees |
| perpendicular midpoint distance | at most 8.0 pixels |
| unoccupied along-line gap | at most 24.0 pixels |
| minimum emitted merged-fragment length | 28.0 pixels |

The 28.0-pixel output floor deliberately equals the frozen G115 LSD input
floor, so the rule adds no separate length filter. A merge replaces two or
more compatible fragments with their fitted endpoint span; a singleton is
preserved. Compatibility is recomputed against the current merged span, so a
transitive chain cannot bridge an incompatible pair.

These values were selected as a conservative image-space join rule, not by
examining G120 outcomes: 4 degrees is stricter than the existing frozen
5-degree grouping tolerance, 8 pixels is smaller than its 10-pixel offset
tolerance, and 24 pixels allows one short unobserved break without joining
visibly separated structures.

## Fixed scope

The fixed G115 population is the 30 G110 same-picture frames with 68 visible
physical paint-line roles. The G84 candidate-precision source is its seeded
33-frame audit. Its three pre-established G110 picture-divergent identities
cannot be reread from their original contact sheets in this worktree, so the
paired precision calculation uses the other 30 identities only: the fixed G115
same-picture subset on which G110 establishes that the G84 annotations apply.
The three rows were excluded before scoring because of picture divergence, not
their detection outcome; no replacement was drawn.

## Recall result: REJECT

The frozen G93 detector and correspondence protocol were rerun exactly: LSD
minimum length 28.0, grouping 5.0 degrees/10.0 pixels, and correspondence 12
degrees/12 pixels/20 pixels. The before row reproduces G115 exactly. The
preregistered fragment merge loses one free-throw-line detection, so it is a
REJECT, not a detector improvement claim.

| role | before detected / visible | before Wilson 95% | after detected / visible | after Wilson 95% |
|---|---:|---:|---:|---:|
| baseline | 1 / 17 (5.88%) | [1.05%, 26.98%] | 1 / 17 (5.88%) | [1.05%, 26.98%] |
| free throw | 2 / 17 (11.76%) | [3.29%, 34.34%] | 1 / 17 (5.88%) | [1.05%, 26.98%] |
| lane left | 8 / 17 (47.06%) | [26.17%, 69.04%] | 8 / 17 (47.06%) | [26.17%, 69.04%] |
| lane right | 14 / 17 (82.35%) | [58.97%, 93.81%] | 14 / 17 (82.35%) | [58.97%, 93.81%] |
| **overall** | **25 / 68 (36.76%)** | **[26.30%, 48.64%]** | **24 / 68 (35.29%)** | **[25.00%, 47.16%]** |

Role-level rows and candidate matches are in
[`recall_measurements.csv`](g120_merge/recall_measurements.csv), with
machine-readable Wilson summaries in
[`recall_summary.csv`](g120_merge/recall_summary.csv).

## Candidate precision cost: REJECT

The published full G84 input baseline remains **198 / 1,764 = 11.22%**. The
paired G120 calculation is intentionally narrower: it uses all current
candidates from the frozen 30-frame same-picture subset and carries an old G84
audit label forward only with the frozen G93 correspondence rule. A candidate
is positive only if every applicable G84 label is `court_line`; unmatched or
mixed-label candidates are conservatively `other`. This avoids claiming that a
new merged span is a court line merely because it looks plausible or because
it contains a prior fragment.

| paired current 30-frame measure | court-line candidates / candidates | precision | Wilson 95% |
|---|---:|---:|---:|
| before merge | 94 / 1,581 | 5.95% | [4.88%, 7.22%] |
| after merge | 72 / 1,311 | 5.49% | [4.38%, 6.86%] |

Thus the merge removes 270 candidates but removes 22 of 94 applicable audited
court-line candidates. Precision declines by 0.45 percentage points. The
complete candidate-level pairing, including applicable audited G84 group
indices, is in
[`precision_measurements.csv`](g120_merge/precision_measurements.csv), and
its summary is in
[`precision_summary.csv`](g120_merge/precision_summary.csv).

## Implied all-four co-occurrence

Using the same independent-line implication used by G115, the reproduced
before recall gives **0.367647^4 = 1.8269%**, consistent with the stated 1.83%
baseline. The after recall gives **0.352941^4 = 1.5517%**. The merge moves the
implied all-four probability down by 0.2752 percentage points, so it makes the
precondition for a four-line solve less likely rather than more likely. See
[`implied_cooccurrence.csv`](g120_merge/implied_cooccurrence.csv).

## Render eye check

All 30 G115 after-merge candidate-plus-role overlays are committed in
[`recall_renders/`](g120_merge/recall_renders/); all 30 paired precision
overlays, with green conservatively-court and red other candidates, are in
[`precision_renders/`](g120_merge/precision_renders/). I inspected sorted
recall positions 1, 6, 11, 16, 21, and 26 of 30, spanning NCAA and WNBA,
including visible and non-visible paint frames. I also inspected paired
precision overlays at positions 1 and 16. The sample showed no cross-court
bridge that would create a plausible false paint line, but it showed no repair
of the free-throw fragmentation either. The result remains REJECT on measured
recall and precision, regardless of this qualitative check.

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g115_paint_line_recall --rebuild
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g120_fragment_merge
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g120_fragment_merge.py -q
```

The rebuild reads only the fixed 30 source frames from the read-only pod. The
new focused test passed; no full test suite was run.

## Verifier-contract self-check

- A2: aggregate counts and Wilson intervals are recomputable from the two
  measurement CSVs; the module regenerates them from the frozen inputs.
- A3: render positions 1, 6, 11, 16, 21, and 26 span the sorted 30-frame
  decision set; the precision render review covers both NCAA and WNBA.
- A4: `recall_measurements.csv` has 240 unique `(variant, clip, frame_index,
  role)` rows: 120 unique frame-role units per variant and 68 visible per
  variant. `precision_measurements.csv` has 2,892 unique candidate rows over
  the fixed 30-frame same-picture subset.
- A5: G120 adds an isolated evidence module and files only. It changes no
  existing field, reader, detector, or production caller.
- A7: every evidence path named here exists at self-check time: this memo; the
  three CSV summaries/detail files; 30 recall renders; 30 precision renders;
  the G120 module; and its focused test.
- B1: the three excluded identities are G110's named picture divergences,
  fixed before G120 scoring; all other 30 frames and all 68 visible roles are
  retained.
- B2-B6: additions only; no schema, existing reader, claim lifecycle, pod
  deployment, feature flag, module move, or production code changed.
- B7: renders were reviewed across the ordered set, not as a head slice.
- B8: the merge constants are recorded at the top of this memo before any
  G120 score. G84 label carry-over uses the already frozen G93 correspondence,
  not a fitted or reselected threshold.
- B9: recall uses unique visible `(frame, role)` observations; precision uses
  unique `(frame, candidate)` observations. No track or candidate identifier is
  recycled across rows.
- B10: G93/G115 correspondence and detector/grouping settings, G84 seed,
  visibility labels, the coordinate contract, G87 finding, and every harness
  threshold remain untouched.

## Not verified

- Generalization beyond the frozen 30-frame same-picture subset or the
  G84-labeled content that geometrically applies to it.
- The three G110-divergent G84 frames under current reconstructed pixels; their
  original contact-sheet inputs are absent from this worktree and they were not
  substituted or scored.
- A new independent human audit of every current candidate; this row reuses
  applicable G84 audit geometry under its already frozen correspondence rule.
- Court-coordinate recovery, role naming, a homography, a detector parameter
  change, or deployment.
