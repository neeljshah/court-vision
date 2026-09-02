# G44B tennis ball spatial gate -- attempt 3 label-grounded limit

Date: 2026-09-02. Gap: G44B. Worktree: a2. Contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A7 and B1--B10.

**VERDICT: REJECT -- no detector or gate change is justified.** The G65
per-frame labels now exist and are the only ground truth used here. They make
the previous missing-artifact blocker go away, but they do not support fitting
or independently scoring a new spatial rule: only 41 of 150 rally-window
frames have a resolved ball centre and the remaining 109 are explicitly
uncertain, rather than labelled non-balls. Thus neither a complete recall
denominator nor a precision denominator for emitted candidates exists. No code
was changed, and no candidate was generated or treated as truth.

## Step 0 -- premise review

The existing G44 source record reports 32 visible balls in 50 confirmed
live-rally frames (64%) and 16 of 31 classified sightings inside the old
`y < 2/3 * height` rule (52%). It also documents 6--8 px balls near the net
and 15--30 px cutaway balls, so the premise remains a coverage/discrimination
problem, not a sub-pixel resolution wall. Those old aggregates are reproduced
as documentary values from
`g44_ball_detectability_limit_2026-09-02.md`; the original G44 per-frame
labels did not survive, so they cannot be independently recomputed.

G39's false-candidate finding does reproduce from the retained per-frame
record and renders: 0 of 12 emitted candidates was the ball (Wilson 95% CI
0.0%--24.2%). Nine are player/body/racket motion and three are
crowd/staff/scoreboard motion; a real ball is visible elsewhere in four
frames. This is the current baseline precision result, not a claim about G65.

## G65 remeasurement and denominator discipline

`g65_ball_labels/labels.csv` has 150 unique `(clip, source_frame)` decisions:
50 evenly spaced frames in each of three continuous rally-view windows. The
ground-truth counts recompute as follows.

| Ground-truth quantity | Count | Rate | Wilson 95% CI |
|---|---:|---:|---:|
| Resolved visible ball | 41 / 150 | 27.3% | 20.8%--35.0% |
| Explicitly uncertain | 109 / 150 | 72.7% | 65.0%--79.2% |
| Resolved visible ball inside old y-gate | 32 / 41 | 78.0% | 63.3%--88.0% |

The 41/150 rate is **not comparable** with G44's 64%: G44 used 50 confirmed
live-rally frames, while G65's denominator is all sampled rally-window frames
and carries 109 unresolved visibility calls. Do not difference these rates.

The spatial results disagree. G44 reports about 52% in gate (16/31
classified sightings); G65 reports 78% (32/41 resolved sightings). The
numbers in the durable G65 per-frame file support **78%**, but its wide 95%
interval and high uncertainty do not resolve the disagreement with G44. On
this evidence the row threshold may be a minor rather than main recall loss,
so widening it would be an ungrounded trade of one error for another.

## Why no decision boundary was fitted

The required replacement needs a signal beyond image row, such as a
label-derived blob size plus motion magnitude and local brightness. A
hand-drawn clip rectangle was not considered. The available labels cannot
size such a rule:

- A 50:50 fit/held-out split would leave only 20 and 21 resolved positives.
  At 20 positives, even an observed 50% recall has an approximately
  30%--70% Wilson 95% interval; this cannot establish a material gain over the
  33% historical ceiling.
- The 109 uncertain rows are neither negative examples nor known false
  candidates. Counting a candidate there as false would fabricate precision;
  excluding it would be B1. Therefore held-out precision is not measurable.
- No boundary was selected, so there is no independent held-out recall,
  precision, tolerance, candidate decision record, or candidate-marked render
  to claim. The mandatory 15-render eye check cannot be performed honestly
  without an emitted-candidate rule.

Minimum next data requirement: resolve all **109 existing uncertain frames**
to a binary visibility decision (with image-pixel centre/radius for every
visible ball), then collect or resolve enough evenly spaced frames to reach
at least **100 resolved positive labels** across the three clips: 50 fit and
50 held out. That is at least **59 additional resolved visible-ball labels**
beyond today's 41; if resolving the 109 does not yield them, sample additional
rally frames. This still must preserve known non-ball frames so precision is
scored rather than inferred.

## No-change and downstream status

No player detection, court solver, camera lock, harness threshold, detector,
or coordinate contract moved. There are no new ball rows; the existing ball
row contract remains image-pixel candidate input followed by its declared
projection path. No pod file was copied, deployed, or run.

No rally-tempo, serve-speed, or contact-frame teacher may be built. This gate
did not pass.

## Durable per-frame evidence

The durable ground-truth and per-frame spatial decisions are the existing
`g65_ball_labels/labels.csv`: each resolved row contains the image-pixel
centre, frame shape, and radius needed to recompute `y < 2/3 * height`; every
other row explicitly records why a binary decision is unavailable. The new
focused test recomputes the 150, 41, 109, and 32 counts directly from that
file. There is intentionally no detector-output decision artifact because no
candidate rule was fitted or run.

## A7 and B self-check

All evidence paths named here exist at write time:

- `docs/evidence/tracking/VERIFIER_CONTRACT.md`
- `docs/evidence/tracking/g44_ball_detectability_limit_2026-09-02.md`
- `docs/evidence/tracking/g39_ball_projection_diagnosis_2026-09-02.md`
- `docs/evidence/tracking/g39_renders/`
- `docs/evidence/tracking/g44b_g39_per_frame_decisions_2026-09-02.csv`
- `docs/evidence/tracking/g65_ball_label_set_2026-09-02.md`
- `docs/evidence/tracking/g65_ball_labels/labels.csv`
- `docs/evidence/tracking/g65_ball_labels/renders/`
- `tests/platformkit/tracking/test_g44b_label_ground_truth.py`

- B1: all denominators include the stated uncertainty; no uncertain row is
  silently excluded from a claimed recall or precision value.
- B2--B4: no schema, reader, gate, or claim path changed.
- B5: no pre-verification pod deployment occurred.
- B6: no module or test was moved or retired.
- B7: G65 is seeded and evenly spaced over three rally-view windows; G39's
  12 decisions are retained evenly spaced renders, not a head slice.
- B8: no rule was fit, and no same-sample result is represented as independent.
- B9: the G65 check asserts 150 unique `(clip, source_frame)` decisions.
- B10: no harness threshold or gate value changed.

## NOT VERIFIED

- Independent per-frame recomputation of G44's old 32/50 and 16/31 aggregates.
- A new spatial decision boundary, fit/held-out split, pixel tolerance, or
  held-out recall and precision with Wilson intervals.
- Fifteen candidate-marked held-out renders; no candidate rule exists to mark.
- Resolution of the 52% versus 78% in-gate disagreement.
