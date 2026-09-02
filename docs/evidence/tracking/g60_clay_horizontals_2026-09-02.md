# G60: clay horizontal clutter limit measurement

Date: 2026-09-02. Gap G60. Read-only limit measurement. No solver, harness
threshold, camera lock, coordinate contract, pod file, daemon, or deployment was
changed.

**VERDICT: CLOSED AT LIMIT for above-court-horizontal exclusion alone.** The
leading mechanism is real, but it is not sufficient: removing every measured
above-court horizontal produces **0/40 full solver accepts** on clay. This is a
limit result, not a solver fix.

## 1. Premise first

The G57 premise was reproduced before any G60 measurement. The existing
`g57_look.py` diagnostic was re-run unchanged on the six named pristine
`tennis__tennis_06.mp4` frames. The richest evidence pass gave these horizontal
counts: frame 0: 260; 536: 261; 1610: 265; 4332: 263; 5942: 257; 7093: 252.
All six are in the required 250-265 range.

G57's production baseline remains 10/200 = 5.0% [2.7%, 9.0%] clay solver
acceptance. A fresh 400-frame full-clip gate scan was 28/400 = 7.0% [4.9%,
9.9%]. These are different evenly-spaced grids, not a moved threshold or a
before/after claim.

## 2. Definition and procedure

**Above the court region means that a horizontal segment's midpoint is strictly
above the median upper endpoint row of the five vertical clusters already
selected by the unchanged solver's cross-ratio match; the solver-derived horizon
starts the court region and no hand-drawn clip rectangle is used.**

The production gate was evaluated on `np.linspace` grids spanning each complete
clip. The named decision set is every grid frame whose unfiltered production
gate is `horizontal_roles`; all other gates are retained and counted in the raw
gate census rather than silently excluded. Clay has 102 such frames in 400 grid
positions; seed 60 selected one frame from each of 40 equal-size ordered strata.
The hard control scans 1,400 positions each from `tennis_09` and `tennis_10`;
they contain 8 and 32 decision-set frames, respectively, so all 40 are used.
This is not a head slice.

For each selected frame, the count uses the richest unchanged contrast pass
(45 or 60) that itself reaches `horizontal_roles`. The counterfactual then
re-runs `select_court_lines` and `solve_corners` at both unchanged production
contrasts after removing only the above-court horizontals. The raw per-frame
records, gate counts, selection method, and field schema are committed in
`g60_clay_horizontals_2026-09-02.json` (SHA-256
`B524348EFEC8DE8369970B3AA2EA13822E39F0B051B14F7B8F4304D509DA4497`).

## 3. Result

Wilson 95% intervals apply to every reported fraction. Segment fractions use
unique Hough segments from the recorded frames, not track IDs or a recycled
unit. The counterfactual denominator is the 40 unique frames in each named
decision set.

| measure | clay: tennis_06 | hard control: tennis_09 + tennis_10 |
|---|---:|---:|
| fresh production acceptance, full grid | 28/400 = 7.0% [4.9%, 9.9%] | 877/2800 = 31.3% [29.6%, 33.1%] |
| `horizontal_roles` frames available | 102/400 = 25.5% [21.5%, 30.0%] | 40/2800 = 1.4% [1.0%, 2.0%] |
| measured decision-set frames | 40 unique | 40 unique |
| horizontals above derived court region | 7,806/9,454 = 82.6% [81.8%, 83.3%] | 1,872/14,624 = 12.8% [12.3%, 13.4%] |
| role assignment passes after only that exclusion | 4/40 = 10.0% [4.0%, 23.1%] | 4/40 = 10.0% [4.0%, 23.1%] |
| full solver accepts after only that exclusion | 0/40 = 0.0% [0.0%, 8.8%] | 0/40 = 0.0% [0.0%, 8.8%] |

Above-court clutter is strongly concentrated in this clay decision set: 82.6%
of its measured horizontal segments versus 12.8% on the hard control. It can
let role assignment pass on 4 clay frames, but it never clears the downstream
corner solve. Therefore excluding above-court horizontals alone changes full
clay acceptance by 0.0 percentage points on the specified 40-frame decision
set. It does not establish a deployable exclusion rule.

## 4. Mandatory eye check

I rendered and viewed all 10 seeded-evenly-spaced clay decision-set positions:
0, 726, 1740, 2944, 3136, 4092, 4838, 5985, 7094, and 7457. Files are in
`g60_renders/`; red is above, green is at/below the derived horizon, yellow is
the horizon, and blue is the recovered vertical evidence.

Nine renders are wide court views. Their red segments visibly run through the
crowd tiers and sponsor-band region above the yellow horizon, while the green
segments remain at or below it. The important contradiction is frame 4838: it
is a crowd cutaway, yet it reaches `horizontal_roles` with a spurious vertical
guide; it has 739 horizontals but only 4 above the derived horizon. It remains
in the denominator. The diagnosis is therefore not that every
`horizontal_roles` reject is a pristine full-court frame; it is a conditional
mechanism measured on the whole named decision set.

## 5. Scope and NOT VERIFIED

- This is venue-scoped to Roland Garros `tennis_06`. Clay is one existing clip,
  one venue, one camera, and one match; no second clay source exists in the
  corpus, and none was acquired. Do not generalize this result to clay broadly.
- The red/green partition identifies Hough evidence by a solver-derived image
  boundary. It is not pixel-level semantic labeling of every crowd or sponsor
  origin.
- This does not test a contrast change, a different line detector, a new court
  ROI, or any other solver intervention. It only falsifies the hypothesis that
  removing above-court horizontals alone yields full solver acceptance.
- The full-court acceptance metric is a solver gate, not geometry accuracy.
- Seven clay and twelve hard scan positions were unreadable after seek and are
  named as `read_failed` in the raw gate censuses; none was deleted or recoded.

## 6. Reproduction and contract self-check

Run the focused test only:

```
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g60_clay_horizontals.py -q
```

It passes: 1 passed. `scripts/platformkit/g60_clay_horizontals.py` is an
additive evidence script. It was streamed to a one-off remote Python process to
read the existing corpus; no module or file was copied to the pod, and no pod
state changed.

Section B self-check before report:

- B1: The conditional decision set is named (`horizontal_roles`), all other
  gate counts are reported, and frame 4838 is retained rather than excluded.
- B2: No schema, field, or reader changed; evidence files and a standalone
  script are additive.
- B3/B4: No production gate or claim path changed.
- B5: No file was copied to or deployed on the pod before this verdict.
- B6: No module was moved or retired.
- B7: Both the metric grid and the 10-render check span the complete decision
  sets; neither is a head slice.
- B8: No fitted residual is presented as independent evidence.
- B9: The fraction denominator is unique Hough segments within unique frames,
  and the frame denominators are 40 unique source frames per group.
- B10: The diff does not change a harness threshold, solver constant, camera
  lock, or coordinate contract.
