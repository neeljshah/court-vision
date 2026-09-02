# G123: low-contrast paint-line contrast-normalisation measurement

## Preregistered method (written before scoring)

This feasibility measurement uses a single fixed, simple local-contrast
operator before the unchanged candidate-segment detector. For every frozen G115
input tile, convert BGR to CIELAB; apply OpenCV CLAHE to the L channel only;
merge the untouched A and B channels; and convert back to BGR before passing
the result to the detector. CLAHE settings are fixed at `clipLimit=2.0` and
`tileGridSize=(8, 8)`. The operator applies to the entire 640x384 input tile,
not a court ROI. These settings were chosen before any G123 recall, candidate
precision, or post-method miss-reason result was computed. No method variants
will be selected on the frozen sample.

The detector and correspondence contract remain G115's frozen calls:
`detect_lsd_segments(image, 28.0)` followed by
`candidate_line_group_details(..., 5.0, 10.0)` and its 12-degree, 12-pixel,
20-pixel matching rule. The G84 seed, labels, G115 valid 30-frame subset,
visibility labels, and G87 result remain unchanged.

Candidate precision uses no new post-contrast hand labels. Its before count is
the pre-existing G84 audited candidate-label table restricted to the same
30 current same-picture identities. For each post-contrast candidate, transfer
`court_line` only when it matches an existing G84 `court_line` endpoint pair
under that same frozen correspondence rule; every unmatched post-contrast
candidate is counted as `other`. This deliberately conservative, fixed-label
transfer keeps amplified texture in the denominator and will be reported as a
fixed-label precision proxy, not a fresh human relabelling exercise.

## Result

The fixed method is rejected as a low-contrast remedy on this frozen sample.
It detected **23/68** visible physical paint lines (**33.82%**, Wilson 95%
**[23.71%, 45.66%]**) versus the independently recomputed G115 baseline of
**25/68** (**36.76%**, **[26.30%, 48.64%]**). The method therefore loses two
net line detections; it does not recover any of G115's 17 pre-existing
`low_contrast` misses.

| measurement | detected / visible | recall | Wilson 95% |
|---|---:|---:|---:|
| G115 unchanged baseline | 25 / 68 | 36.76% | [26.30%, 48.64%] |
| G123 CLAHE L only | 23 / 68 | 33.82% | [23.71%, 45.66%] |

The same 30 G115 current same-picture identities have four roles recorded on
every frame (120 unique `(clip, frame_index, role)` records); the visible
denominator is 17 for each role and 68 overall. Per-role values are committed
in [recall_summary.csv](g123_contrast/recall_summary.csv), and all role-level
outcomes are in [line_measurements.csv](g123_contrast/line_measurements.csv).

## Post-method miss reasons

The post-method histogram has 45 misses, versus 43 in G115. All 17 original
low-contrast misses remain misses. Five old misses were recovered (2 formerly
`split_into_fragments`, 3 formerly `occluded_partial`), but 7 formerly found
lines are now misses and are recorded as `other`; the latter is a detector
instability label, not a new visual taxonomy.

| miss reason | G115 before | G123 after |
|---|---:|---:|
| low contrast | 17 | 17 |
| split into fragments | 14 | 12 |
| occluded partial | 12 | 9 |
| other | 0 | 7 |
| merged with neighbour | 0 | 0 |
| painted over by court logo | 0 | 0 |
| too short | 0 | 0 |

The machine-readable after histogram is
[after_miss_reason_histogram.csv](g123_contrast/after_miss_reason_histogram.csv).

## Candidate precision cost

The direct G84 audit recount reproduces its full frozen baseline: 198 court
line candidates among 1,764 (11.22%, Wilson [9.83%, 12.78%]). Restricted to
the 30 current same-picture identities that pair with G115, its unchanged
audited labels are 180/1,584 = 11.36% [9.89%, 13.02%]. CLAHE yields 191
fixed-label court matches among 1,654 candidate groups = 11.55% [10.10%,
13.18%]. Thus the proxy precision rises 0.18 percentage points while candidate
volume rises by 70 groups (4.4%) and recall falls.

| scope | court-line candidates / candidates | precision | Wilson 95% |
|---|---:|---:|---:|
| G84 full audited baseline (33 frames) | 198 / 1,764 | 11.22% | [9.83%, 12.78%] |
| G84 audited labels, G115-valid 30 | 180 / 1,584 | 11.36% | [9.89%, 13.02%] |
| CLAHE fixed-label transfer, same 30 | 191 / 1,654 | 11.55% | [10.10%, 13.18%] |

The final row is deliberately a fixed-label precision proxy: a post-CLAHE
candidate is counted as a court line only if it matches an existing G84
`court_line` label under the frozen correspondence rule; all unmatched
candidates count as other. The complete non-relabelled transfer rows are in
[candidate_label_transfer.csv](g123_contrast/candidate_label_transfer.csv),
and its summary is in
[candidate_precision_summary.csv](g123_contrast/candidate_precision_summary.csv).

## Co-occurrence implication

Treating the measured line recall as independent, the implied all-four-line
co-occurrence is `(23/68)^4 = 1.31%`, below G115's `(25/68)^4 = 1.83%`. This
single fixed contrast treatment moves the estimated four-line availability in
the wrong direction and is not a viable standalone solve.

## Eye check

All 30 enhanced candidate overlays are committed in
[g123_contrast/renders/](g123_contrast/renders/). I reviewed evenly distributed
lexically sorted positions 1, 6, 11, 16, 21, and 26, spanning NCAA and WNBA
sources. The overlays visibly amplify crowd, bench, player-silhouette,
broadcast-graphic, score-bar, reflection, and court-texture segments. The
sampled low-contrast baselines remain missed; the added structures are not
credible court-line recoveries. This visual result agrees with the added
candidate volume and the recall decline.

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g123_low_contrast_lines --write
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g123_low_contrast_lines.py -q
```

The first command reads only the fixed 30 source tiles through the existing
read-only pod recipe and writes local evidence. The sole new focused test
passed: `1 passed`.

## Verifier-contract self-check

- A2: independently recomputed from the committed artifacts: 23/68 recall,
  191/1,654 transferred court candidates, 120/120 unique role records,
  1,654/1,654 unique candidate records, 45 post-method misses, 30 renders,
  and 1.308807% implied co-occurrence.
- A3: reviewed renders at sorted positions 1, 6, 11, 16, 21, and 26, not a
  head slice.
- A4: the role metric uses 68 unique visible `(clip, frame_index, role)`
  observations within 120 unique all-role records. Candidate precision uses
  1,654 unique `(clip, frame_index, group_index)` observations.
- A5: the new CSV field names and module symbols have no existing readers;
  the change is additive evidence only.
- A7: every named local evidence path exists at self-check time: this memo,
  preregistration, four CSV artifacts, 30 renders, G123 module, and focused
  test.
- B1: all 30 frozen G115 identities and all four recorded roles remain in the
  artifact; the three named G110 divergences remain G115's pre-existing
  exclusions with no replacement.
- B2-B6: no pre-existing schema, reader, gate, claim lifecycle, deployment,
  pod file, module movement, caller, or feature flag changed.
- B7: the visual review is evenly distributed; no result is based on a head
  slice.
- B8: the method and precision-transfer rule were written before scoring;
  detector, correspondence, labels, and visibility marks predate G123.
- B9: neither recall nor precision reuses candidate or track identifiers as
  its denominator.
- B10: `line_calibration.py`, all detector parameters (28.0 / 5.0 / 10.0),
  correspondence values, G84/G115 identities and labels, coordinate contract,
  G87 finding, and every harness threshold are untouched.

## Not verified

- A fresh independent human audit of post-CLAHE candidate labels; the reported
  post-method precision is the preregistered fixed-label proxy, not a relabel.
- Generalization beyond this frozen 30-frame / 68-visible-line decision set.
- A different contrast operator, CLAHE parameterization, court ROI, learned
  detector, fragment merge, or corner-first route. None was selected or built
  here.
- Any court-coordinate solve or `court_feet` declaration for a clip.
