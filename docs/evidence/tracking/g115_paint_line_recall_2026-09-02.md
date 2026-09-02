# G115: paint-line detection recall on the G110 same-picture subset

## Result

The frozen G93 detection-recall protocol was run on the **30** G110
same-picture rebuilt tiles. Of **68 visible physical paint lines**, the fixed
candidate detector returned a corresponding group for **25**, giving overall
recall **36.76%** with Wilson 95% interval **[26.30%, 48.64%]**.

This is a detector-limit measurement. It does not tune a detector, make a
solver claim, or change any production behavior. G84's precision result stays
the paired context: 198/1,764 candidate groups were court lines (11.22%), and
none of its 33 frames had all four paint lines co-present. G87's 11/12
perspective-gate result is unchanged, so this recall result locates the loss
upstream of that gate.

## Fixed population and exclusions

The source population remains G84's seeded 33-frame sample (`84092026`). G110
identified the following three current-stream content divergences in
[`pixel_triage.csv`](g110_tiles/pixel_triage.csv), so G115 excludes them and
does not replace them:

| clip | frame index | G110 reason |
|---|---:|---|
| `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss` | 2483 | current timeline has different picture |
| `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss` | 2865 | current timeline has different picture |
| `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss` | 16235 | current timeline has different picture |

The remaining 30 identities are the exact fixed, low-delta same-picture set:
G110 established seek/sequential raw-pixel equality for all 33 and a
same-picture reconstruction for these 30. The unannotated rebuilt inputs were
read from the pod only; G84's candidate-overlay renders were not detector
input.

## Frozen protocol and eye marks

The G93 protocol committed at `98b7d6974` is used without modification:
`detect_lsd_segments(image, 28.0)`, then
`candidate_line_group_details(..., 5.0, 10.0)`, with 12-degree angle,
12-pixel perpendicular-distance, and 20-pixel endpoint-extension matching.
The seven-value miss vocabulary is also unchanged.

I reviewed every retained unannotated rebuilt tile by eye and recorded every
role as visible or not visible in [`hand_marks.json`](g115_recall/hand_marks.json).
An off-frame or fully occluded role is not a miss. The role-level output,
including every non-visible mark, matching candidate indices, and endpoint
marks, is [`line_measurements.csv`](g115_recall/line_measurements.csv). All
30 final candidate-plus-hand-mark overlays are in
[`renders/`](g115_recall/renders/).

## Recall by role

| role | detected / visible | recall | Wilson 95% |
|---|---:|---:|---:|
| baseline | 1 / 17 | 5.88% | [1.05%, 26.98%] |
| free throw | 2 / 17 | 11.76% | [3.29%, 34.34%] |
| lane left | 8 / 17 | 47.06% | [26.17%, 69.04%] |
| lane right | 14 / 17 | 82.35% | [58.97%, 93.81%] |
| **overall** | **25 / 68** | **36.76%** | **[26.30%, 48.64%]** |

The machine-readable table is
[`recall_summary.csv`](g115_recall/recall_summary.csv). Each role has the same
17-line visible denominator because the retained hand-reviewed frames expose
the four marked paint edges together; the 13 remaining retained frames expose
none sufficiently to count under the G93 rule.

## Miss reasons

Each of the 43 missed visible lines has one fixed-vocabulary reason in
[`miss_reasons.json`](g115_recall/miss_reasons.json), and the complete histogram
is [`miss_reason_histogram.csv`](g115_recall/miss_reason_histogram.csv).

| miss reason | count |
|---|---:|
| low contrast | 17 |
| split into fragments | 14 |
| occluded partial | 12 |
| merged with neighbour | 0 |
| painted over by court logo | 0 |
| too short | 0 |
| other | 0 |

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g115_paint_line_recall --rebuild
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g115_paint_line_recall --write
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g115_paint_line_recall.py -q
```

The first command pulls only the retained 30 source frames from the read-only
pod corpus. It does not copy to the pod or deploy anything. The focused test
passed: `1 passed`.

## Verifier-contract self-check

- A2: headline counts are directly reproducible from the committed
  role-level measurement CSV; the 25/68 aggregate and Wilson interval were
  independently recomputed before this memo.
- A3: I reviewed final overlays at sorted positions 1, 6, 11, 16, 21, and 26
  of 30, spanning NCAA and WNBA sources, instead of a head slice.
- A4: `line_measurements.csv` has 120 unique `(clip, frame_index, role)`
  records over 30 unique frame identities; its visible subset has 68 unique
  records.
- A5: G115 adds a new evidence module and files; it changes no existing field
  or reader. Repository search finds no reader of a pre-existing changed
  field.
- A7: at self-check time every evidence path named in this memo exists: this
  memo, G110 triage CSV, marks, miss reasons, measurement CSV, summary CSV,
  histogram CSV, all 30 renders, module, and focused test.
- B1: the three excluded identities are named above and are G110's
  pre-established content divergences, not outcomes excluded after scoring;
  no replacement was drawn.
- B2-B6: additions only; no existing schema, reader, gate, claim lifecycle,
  deploy, pod file, module movement, or feature flag changed.
- B7: final overlay review is distributed across the complete ordered 30-frame
  set, not a head slice.
- B8: correspondence values and miss vocabulary predate G115 in `98b7d6974`;
  no fit or detector adjustment is offered as validation.
- B9: the denominator is 68 unique visible `(frame, role)` observations, not
  candidate IDs or recycled track IDs.
- B10: the G84 seed/sample, G93 28.0/5.0/10.0 detector inputs, correspondence
  values, `line_calibration.py`, G87 result, and harness thresholds are
  untouched.

## Not verified

- Generalization beyond this frozen, 30-frame same-picture subset and its
  68 visible line roles.
- An independent second reviewer or inter-rater agreement for the eye marks.
- Whether a replacement detector, contrast method, ROI, candidate cleaner, or
  downstream solver would improve this measurement.
- Exact historic provenance of the three excluded WFl source frames; G110
  establishes current-picture divergence, not a unique acquisition cause.
