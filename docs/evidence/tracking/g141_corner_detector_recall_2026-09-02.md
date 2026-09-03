# G141 basketball direct corner detector recall

## 1. Preregistered tolerance (before measurement)

The native-image Euclidean match tolerance was fixed at **12.0 pixels** before
this detector ran. G140's blind re-labelling measured a 10.971927 px median and
11.392950 px p90 displacement. A tolerance below roughly 11 px would measure
target-placement noise rather than detector error, so 12.0 px is the smallest
whole-pixel tolerance above that measured floor. It was not changed after the
zero-match result. The preregistration and fixed Harris parameters are in
[`g141_corner_recall/protocol.md`](g141_corner_recall/protocol.md).

## 2. Fixed proposal and denominator

The direct proposal is a native-image grayscale Harris `goodFeaturesToTrack`
response only (`maxCorners=100`, `qualityLevel=0.01`, `minDistance=10`,
`blockSize=5`, `k=0.04`). It is not learned and does not use line detection,
grouping, role assignment, homography, `line_calibration.py`, or a production
module. It generated 100 generic local proposals on each of 17 fixed G140
frames: 1,700 total in
[`g141_corner_recall/proposals.csv`](g141_corner_recall/proposals.csv).

The denominator is every G140 target: 68 unique `(clip, source_frame, role)`
keys from 17 frames, 17 for each physical role, unchanged from
[`g140_corner_targets/corner_pixel_targets.csv`](g140_corner_targets/corner_pixel_targets.csv).
A target is available only if a generic local proposal is within the fixed
12.0 px tolerance. The detector has no role assignment, so recall is measured
against the named targets without a post-hoc role mapping.

## 3. Recall and availability

| G140 physical corner role | available / denominator | recall | Wilson 95 percent interval |
|---|---:|---:|---:|
| `paint_near_baseline_left_corner` | 0 / 17 | 0.00 percent | 0.00 to 18.43 percent |
| `paint_near_baseline_right_corner` | 0 / 17 | 0.00 percent | 0.00 to 18.43 percent |
| `paint_near_free_throw_left_corner` | 0 / 17 | 0.00 percent | 0.00 to 18.43 percent |
| `paint_near_free_throw_right_corner` | 0 / 17 | 0.00 percent | 0.00 to 18.43 percent |
| **all fixed target roles** | **0 / 68** | **0.00 percent** | **0.00 to 5.35 percent** |

The complete per-target result, including nearest generic-proposal distance and
rank, is [`g141_corner_recall/target_scores.csv`](g141_corner_recall/target_scores.csv).
The summary is [`g141_corner_recall/summary.json`](g141_corner_recall/summary.json).

## 4. Proposal precision

Each of the 1,700 generic proposals was scored once against the four committed
targets on its own frame. A proposal is precise only if it lies within 12.0 px
of any target; nearby proposals were not removed or deduplicated. **0 / 1,700**
proposals land on a real target: **0.00 percent** precision, Wilson 95 percent
interval **0.00 to 0.23 percent**. Candidate-level scores are in
[`g141_corner_recall/proposal_scores.csv`](g141_corner_recall/proposal_scores.csv).

## 5. Like-for-like comparison and decision

G138's line route made 1 of 84 reviewed role units independently available;
this corner route makes **0 of 68** fixed G140 target role units available.
The review sets differ, but both quantities are independently available named
physical constraints divided by all named physical constraint units reviewed.

**One-sentence decision:** No - this corner-first local-response route makes
materially fewer of the four constraints available than the line route and is
not worth a production row.

## 6. Pixel-to-court scale context

For these clips, 12 px converts to **0.214 to 1.976 ft** (median **0.514 ft**)
along the labelled baseline-to-free-throw paint depth. Each frame has left and
right local estimates using the committed 19-foot paint depth, rather than a
single assumed full-court scale; see
[`g141_corner_recall/scale_conversion.csv`](g141_corner_recall/scale_conversion.csv).
This is descriptive tolerance context only, not court-coordinate output,
calibration, or a detector input.

## 7. Eye check

Before output review, the protocol fixed lexically sorted G140 audit-ID
positions 0, 3, 5, 8, 10, 13, and 16. I inspected all seven overlays in
[`g141_corner_recall/renders/`](g141_corner_recall/renders/), spanning NCAA and
WNBA wide and closer broadcasts. Yellow circles/red crosses mark targets; grey
crosses are the 100 local Harris proposals. The proposals visibly land on crowd,
players, basket apparatus, broadcast graphics, and unrelated court texture;
none falls inside a target circle. This agrees with both zero recall and zero
precision rather than exposing a score/render disagreement.

## 8. Ceiling and scope

This is a small 17-frame / 68-target feasibility result. Its denominator is
conditioned on G136's 46.2 percent four-corner census, which has a 28/42 =
66.7 percent blinded reachability-agreement caveat. A good recall here would
not have solved basketball: it would only show recoverable constraints before
G135's external-validation requirement. This route did not reach that step.

## Verifier-contract self-check

- **A1:** ran exactly one new per-file test, `python -m pytest
  tests/platformkit/test_g141_corner_detector_recall.py -q`; it passed (1
  passed). Master-side rerun and archive landing remain verifier work because
  this lane is committed in worktree `a2`, not landed to master.
- **A2:** independently recomputed from immutable G140 targets and raw G141
  proposals: 68 unique target keys, 17 unique frames, 1,700 proposals, 0 target
  hits, and 0 proposal hits at 12.0 px. This reproduces the tables.
- **A3:** inspected all seven predeclared evenly spaced overlays, positions
  0, 3, 5, 8, 10, 13, and 16, not a head slice.
- **A4:** G140 has 68 unique `(clip, source_frame, role)` keys; each proposal
  is unique by `(audit_id, rank)` and no denominator unit is recycled.
- **A5:** all scored fields are additive G141 evidence fields. A repository
  reader grep for `nearest_proposal_distance_px`, `nearest_proposal_rank`,
  `on_any_target`, and `tolerance_feet_along_paint_depth` found no existing
  readers to update.
- **A6:** this lane is committed with explicit paths in worktree `a2` and does
  not archive or land to master; the contract assigns landing to the verifier.
- **A7:** at self-check, this memo, protocol, all four score/proposal CSVs,
  scale CSV, summary JSON, and all seven predeclared render files exist.
- **B1:** clear. All fixed targets are retained; zero matches remove neither a
  target nor a proposal.
- **B2:** clear. Only additive evidence files and an additive platformkit
  module/test were created; no existing schema, field, or reader changed.
- **B3-B4:** clear. No gate, claim state, or failure lifecycle changed.
- **B5:** clear. No pod or deployment file was written.
- **B6:** clear. No module, import, caller, or test was moved or retired.
- **B7:** clear. The render set was fixed before output and spans the decision
  set rather than its first frames.
- **B8:** clear. The detector is not fitted to G140 targets; targets only score
  generic local proposals after generation.
- **B9:** clear. Metrics use unique named physical target roles and unique
  proposal ranks, not tracker IDs or repeated frames.
- **B10:** clear. G140 targets/displacement, G136 census, existing detector and
  grouping parameters, line calibration, coordinate contract, and rung ladder
  are untouched. The new local parameters and 12.0 px tolerance were
  preregistered before measurement.

## NOT VERIFIED

- Any learned or neighbourhood-intersection corner detector, alternative
  parameter set, or post-result tuning.
- Homography, court-feet output, calibration, tracking, coordinate-contract
  change, or production integration.
- Generalisation beyond G140's fixed 17-frame target set or a more precise
  basketball four-corner visibility rate than G136's caveated census.
- G135's required external court-distance validation.
