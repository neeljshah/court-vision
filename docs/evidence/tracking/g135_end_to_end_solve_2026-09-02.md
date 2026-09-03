# G135: end-to-end basketball solve attempt

## Qualifying frame count: 0 of 30 frozen frames

Under G134's unchanged stable grouping plus G132 union, **zero** frozen G84
frames contain matched candidates for all four declared paint roles. The
recomputed role-level output has 120 unique `(clip, frame_index, role)` rows,
30 stable matched roles total, and zero unique frames marked
`qualifying_frame=true`.

This is G135's explicit terminal outcome. No four-line correspondence set
exists, so no homography was attempted. Consequently there is no solve status,
external distance error in feet, or reprojected-court overlay to report. Zero
is a sample-size result, not evidence that the unchanged correspondence solver
failed.

## Frozen measurement

The runner calls `g134_grouping_stability.measure()` unchanged, which in turn
uses the frozen 28px LSD threshold, G132 segment union, G134 immutable-baseline
grouping at 5 degrees and 10px, G115 hand marks, and the exact 30-frame G115
subset. It does not edit or call any production calibration path.

| quantity | result |
|---|---:|
| frozen frames | 30 |
| unique role rows | 120 |
| stable matched roles | 30 |
| all-four qualifying frames | **0** |
| homographies attempted | 0 |
| external distance measurements | 0 |
| reprojection renders | 0 |

The durable artifacts are:

- [`frame_role_matches.csv`](g135_solve/frame_role_matches.csv): all 120 scored role rows and the per-frame qualifier flag.
- [`qualifying_frames.csv`](g135_solve/qualifying_frames.csv): header-only because there are no qualifiers.
- [`summary.json`](g135_solve/summary.json): machine-readable count and zero-result status.

## External validation and eye check

The specified independent check would have been a separately visible
three-point arc or centre circle, because baseline-to-free-throw distance and
lane width are already encoded by the solve correspondences and would be
self-fit. With no H, no physical distance is projected, so there is no
independent quantity or feet error to measure. No solve-line residual is
reported as validation.

Likewise, the required visual check has an empty decision set: no solved court
model exists to reproject, so no overlay can honestly be rendered or reviewed.
This is not replaced by a head slice or an unrelated image review.

## Court-standard caveat

No clip reached a solve. If a future qualifier occurs, the existing library's
declared standard is `ncaa_legacy` for `ncaa_basketball__*` clips (19 ft
baseline-to-free-throw spacing and 12 ft lane width) and `nba_wnba` for
`wnba__*` clips (19 ft and 16 ft). Any future three-point-arc measurement must
verify the clip's governing court standard; a court-standard discrepancy alone
can contribute to an apparent feet error, and an error below that discrepancy
must not be called calibration accuracy. This row has no feet error to compare
against that caveat.

## Coordinate status

Nothing declares `court_feet`, promotes a table, writes a coordinate space, or
changes the rung ladder. A validated frame solve would only show reachability,
not calibrate a clip; G135 has not reached even that frame-level evidence.

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g115_paint_line_recall --rebuild
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g135_end_to_end_solve --write
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g135_end_to_end_solve.py -q
```

The rebuild reads source frames only; no pod file, process, daemon, detector,
grouping parameter, calibration module, threshold, label, coordinate contract,
or feature flag changed.

## Verifier-contract self-check

- A2: independently parsed `frame_role_matches.csv`: 120 unique role rows,
  30 unique frames, 30 stable matched roles, and zero qualifying frames.
- A3: no solved-frame decision set exists, so there are no renders to sample;
  no head-slice proxy was used.
- A4: the artifact has unique `(clip, frame_index, role)` units and zero
  qualifying-frame units.
- A5: only new isolated G135 files are added; no existing field or reader
  changed.
- A7: every evidence path named above exists at this commit; no render path is
  named because zero solves produced zero renders.
- B1: every one of the fixed 30 frames and all four role rows remains in the
  artifact; none was excluded after scoring.
- B2-B6: no existing schema, reader, gate, lifecycle, pod file, deployment,
  module, import, caller, or flag changed.
- B7: no render claim is made; the render decision set is empty.
- B8: no same-line residual is presented as external validation.
- B9: frames and role rows are unique, non-recycled artifact units.
- B10: the frozen detector, grouping, correspondence, calibration, manifest,
  seed, labels, thresholds, coordinate contract, and rung ladder are unchanged.

## Not verified

- A four-line basketball solve on this fixed sample.
- Any external physical-distance error in feet.
- A reprojected court-model eye check.
- Court-feet calibration for any frame or clip.
- Generalization beyond the frozen 30 frames.

## Verdict

**NOT VALIDATED -- terminal zero-qualifier outcome.** The all-four frame count
was measured exactly as required, but this sample supplies no correspondence set
from which a solve or independent validation could be made.
