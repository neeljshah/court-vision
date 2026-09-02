# G132: additive original-plus-CLAHE candidate union

## Preregistered method (written before scoring)

This measurement retains the frozen G115 30-frame, 68-visible-line population,
its three pre-existing G110 picture-divergence exclusions, its hand marks, and
its role vocabulary. No visibility decision, correspondence tolerance, G84
seed, or sample identity is changed or replaced.

For each retained reconstructed 640x384 tile, the baseline proposal set is
`detect_lsd_segments(image, 28.0)`. The enhanced proposal set is the same call
on G123's already committed whole-frame CIELAB-L CLAHE image: `clipLimit=2.0`
and `tileGridSize=(8, 8)`, with A/B channels retained and no ROI. This reuses
G123's parameters exactly; no G132 variant selection is permitted.

The segment union is deterministic. Baseline LSD segments are inserted first,
then enhanced LSD segments in detector order. A later enhanced segment is a
near-duplicate only when its endpoints can be paired, in either direction,
within 1.0 image pixel per paired endpoint; it is then discarded in favour of
the already-retained baseline segment. Every other enhanced segment is kept.
The 1.0-pixel rule is an endpoint quantisation guard, not a geometry merge:
no collinear, orientation, length, or offset-based collapse is applied.
`candidate_line_group_details(union, 5.0, 10.0)` runs once over the resulting
union. This is deliberately not separate grouping followed by a union of
candidate groups.

Recall is evaluated under the frozen G93/G115 rule: 12-degree orientation,
12-pixel perpendicular distance, and 20-pixel endpoint extension. The
baseline and union both score all 120 role records, with the same 68 visible
role records as their recall denominator. Wilson 95% intervals and per-role
counts are calculated from those fixed units.

The direct additive check is per visible role: every baseline-detected role
must also have at least one union group satisfying the unchanged correspondence
rule. Candidate precision is the preregistered fixed-label proxy on the 30
same-picture frames: for both baseline and union candidates, transfer
`court_line` only if the candidate matches at least one G84 audited
`court_line` endpoint pair using that same frozen correspondence rule; all
other candidates are `other`. Candidate volume is the count of unique
`(clip, frame_index, group_index)` records in each variant. The historic full
G84 33-frame audit is reported only as context and is not substituted into the
30-frame paired calculation.

All 30 union candidate-plus-hand-mark overlays will be rendered. The eye check
will inspect six evenly distributed positions in the lexically sorted
30-frame decision set (1, 6, 11, 16, 21, and 26), including both NCAA and
WNBA identities, before a verdict is stated.

The normal read-only pod rebuild populated the complete 30-tile local cache,
but its launcher did not reach the artifact-write phase through this session's
execution channel. After checking all 30 fixed non-divergent manifest tile
identities, the cache-only writer scored those same tiles and avoided a second
pod request; this does not alter, select, or reconstruct any pixel input.

## Result

**REJECT: the single-grouping union is not additive.** On the frozen 30 frames
and 68 visible physical paint lines, the reproduced baseline is **25/68 =
36.76%** (Wilson 95% **[26.30%, 48.64%]**). The union reaches **28/68 =
41.18%** (**[30.26%, 53.04%]**), but only **24/25** baseline matches survive.
Because one previously matched physical line is lost, the mechanism's required
additive property fails and the apparent three-line recall increase is not an
accepted additive gain.

| role | baseline detected / visible | union detected / visible |
|---|---:|---:|
| baseline | 1 / 17 (5.88%) | 1 / 17 (5.88%) |
| free throw | 2 / 17 (11.76%) | 4 / 17 (23.53%) |
| lane left | 8 / 17 (47.06%) | 8 / 17 (47.06%) |
| lane right | 14 / 17 (82.35%) | 15 / 17 (88.24%) |
| **overall** | **25 / 68 (36.76%)** | **28 / 68 (41.18%)** |

The lost baseline match is `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p`,
frame `11760`, `lane_right`. Baseline groups 4 and 24 match its fixed hand
line; no union group does. The closest union replacement for baseline group 24
is group 19, whose endpoint span shifts from `[[258,225],[582,250]]` to
`[[258,230],[582,251]]`; it falls outside the frozen correspondence rule.
This is the expected remaining failure mode: original LSD fragments survive,
but a once-only grouping fit changes when enhanced fragments join its group.
The G132 design therefore does not supply a true superset of candidate groups.

## Candidate cost

The paired fixed-label transfer against G84's audited `court_line` endpoints
uses the same 30 current same-picture identities for both variants. Baseline
candidate volume is 1,581 groups with 212 transferred court-line candidates
(**13.41%**, Wilson **[11.82%, 15.18%]**). The union is 2,014 groups with 225
transferred court-line candidates (**11.17%**, **[9.87%, 12.62%]**): 433 more
groups (+27.4%) for 13 more transferred positives, while precision declines
2.24 percentage points. The historic full G84 audit remains the separate
33-frame context of 198/1,764 = 11.22%; it is not substituted for this paired
current-tile calculation.

The independent-line implication rises from `(25/68)^4 = 1.8269%` (the stated
1.83% baseline) to `(28/68)^4 = 2.8747%`. That implication is descriptive
only: it cannot support a solve or an acceptance when the proposed additive
property has failed.

## Eye check

All 30 union overlays are in `g132_union/renders/`. I inspected lexical
positions 1, 6, 11, 16, 21, and 26:

- `...IB-_u4gW3ds__f16704.jpg`
- `...IB-_u4gW3ds_1080p__f5160.jpg`
- `...tiUvyvWOCxo__f25728.jpg`
- `...wnba_01__f11904.jpg`
- `...wnba_01_1080p__f360.jpg`
- `...wnba_04__f23424.jpg`

They span NCAA and WNBA sources and include both visible-paint and
not-visible-role frames. The union visibly blankets court texture, crowd and
broadcast areas with many more indexed groups. It does recover plausible
marked free-throw and lane lines, but the candidate density and lower fixed
label-transfer precision agree that the three extra matches are not evidence
of a clean additive route.

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g132_additive_candidate_union --write
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g132_additive_candidate_union --write --reuse-local-tiles
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g132_additive_candidate_union.py -q
```

The first command performs the read-only pod tile pull; the second is the
cache-only scoring mode used here and does not write to the pod. The sole new
focused test passed: `1 passed`.

## Verifier-contract self-check

- A2: independent CSV recomputation gives 120/120 unique role rows, 68/68
  unique visible roles, baseline/union recall 25/68 and 28/68, direct
  survival 24/25, and paired precision 212/1,581 and 225/2,014. Wilson values
  and co-occurrence are recomputable from the artifacts.
- A3: reviewed positions 1, 6, 11, 16, 21, and 26 of the lexical 30-render
  decision set, not a head slice.
- A4: role records are unique `(clip, frame_index, role)` units; both
  candidate-transfer files have unique `(clip, frame_index, group_index)`
  units; the direct additive file has all 25 unique baseline-detected roles.
- A5: G132 adds isolated fields and artifacts only; no pre-existing reader,
  schema, production caller, or detector module changed.
- A7: all named paths exist at self-check time: this memo; G132's seven CSV
  artifacts and preregistration JSON; all 30 renders; the isolated module;
  and its one focused test.
- B1: every frozen G115 role record remains, with its original 68-visible
  denominator and the three pre-existing named G110 picture exclusions only.
- B2-B6: additions only; no existing field, reader, gate, lifecycle, pod file,
  deployment, feature flag, module move, import, or caller changed.
- B7: the eye check is evenly distributed across the 30 renders.
- B8: the transform, deduplication, grouping, correspondence, precision
  transfer, and render selection were preregistered before G132 scoring.
- B9: recall and survival use unique frame-role units; precision uses unique
  frame-candidate units, not recycled identifiers.
- B10: G93/G115 protocol, G84 sample and seed, hand marks, detector parameters
  28.0/5.0/10.0, `line_calibration.py`, coordinate contract, and every harness
  threshold are untouched.

## Not verified

- Generalisation beyond the frozen 30-frame / 68-visible-line decision set.
- A fresh independent human relabelling of union candidates; candidate
  precision is the preregistered G84 fixed-label transfer proxy.
- A different grouping architecture that preserves baseline groups separately,
  a parameter sweep, a detector change, a court-coordinate solve, or any
  `court_feet` declaration. None was attempted.
