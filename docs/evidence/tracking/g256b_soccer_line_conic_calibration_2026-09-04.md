**GATE: FAIL BEFORE FIT (n=1 clip, 1 inspected near-miss frame, 0 fitted frames, 1 labeller).** The clearest surveyed midpoint image has the centre circle and halfway line but no penalty-area or goal-area geometry; using a touchline for the second line would require the prohibited unknown pitch width. There is no legal two-line-plus-conic input for the unchanged G253 harness, so no homography, self-fit residual, withheld projection, or pixel-offset result is presented.

# G256b: Pod Soccer Line-and-Conic Calibration

**Verdict: CLOSED AT LIMIT (feature configuration; full success).** This measurement-only re-issue follows [the verifier contract](VERIFIER_CONTRACT.md). It changes no production module, `IMAGE_SPACE`, coordinate contract, label, threshold, pitch model, corpus source, daemon, `src/`, or `domains/` file. The named soccer source was reached over SSH on the pod; the local Windows corpus was neither opened nor compared.

## Lane check, source identity, and disk guard

At 2026-09-04T07:44:36-05:00 America/Chicago, I checked processes by executable and complete argument while excluding this checker, its parent, and this G256b row's launcher. G257 was active in `C:/Users/neelj/nba-track-a6`; it was the permitted other pod measurement lane and was not interrupted. No resident process was touched.

The source was confirmed on the pod before any decode. Its full, read-only path and measured identity are:

| Field | Value |
|---|---|
| Source | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4` |
| Bytes | 2,341,768,743 |
| SHA-256 | `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e` |
| Mtime | 2026-09-04 02:21:30 UTC |
| Video stream | 1920x1080, 30/1 fps, 179,250 declared frames, 5,975.000000 seconds |

`df` was not used. Before streamed decoding, `du -sm /workspace/nba-ai-system/data` was 33,144 MB. The required `dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g256b_disk_probe.bin bs=1M count=1 conv=fsync status=none` wrote 1,048,576 bytes; its size was checked and it was removed successfully. No corpus source or either abandoned `footage_bridge` partial was changed. The pod probe freed 1,048,576 bytes; discarded local inspection JPEGs freed 181,671 bytes; total temporary bytes freed were 1,230,247.

## Survey and pre-fit identity decision

The measurement utility [g256b_soccer_line_conic_calibration.py](../../../scripts/platformkit/tracking/g256b_soccer_line_conic_calibration.py), SHA-256 `4893847f50096aa4d8b2d9dd73b636839efc6e7b248908c42b9c94bfae9f6cdb`, streamed a no-input-seek, whole-clip ffmpeg survey: one 384x216 sample every 60 seconds, tiled as ten by ten panels. Thus the committed [survey](g256b_soccer_line_conic_calibration_2026-09-04_artifact/survey_60s.jpg) covers 100 chronologically even samples from the 5,975-second clip; no full decode was written on the pod.

The survey supplied no image with the ideal one penalty area plus halfway line and centre circle. The strongest midpoint near-miss was exact zero-based frame 5,400, sequentially decoded from the start and retained as [the native frame](g256b_soccer_line_conic_calibration_2026-09-04_artifact/best_available_frame_5400.jpg). Its [selection crop](g256b_soccer_line_conic_calibration_2026-09-04_artifact/near_miss_centre_circle_halfway_zoom.jpg) shows the painted centre circle and vertical halfway line: players partially cover the circle centre, but no penalty-area, goal-area, goal-line, or penalty-mark feature is in frame. This crop is explicitly a pre-fit near-miss, not a fitted-feature identity crop. There are no fitted lines or conic, so G246's required per-fitted-element crops do not exist and none is represented as evidence.

## Standard geometry and unchanged-harness stop

The only observed standard-dimensional marking eligible in frame 5,400 was the centre circle, for which the eligible dimension is radius 9.15 m. The halfway line is identifiable as the line through that circle's centre, but it supplies only one line correspondence. No touchline length, pitch width, or any other non-standard dimension was fitted or assumed.

The full eligible standard list remains centre-circle radius 9.15 m; penalty-area depth 16.5 m and width 40.32 m; goal-area depth 5.5 m and width 18.32 m; and penalty-mark distance 11 m from the goal line. None of the penalty- or goal-area features was available in the selected near-miss. Any non-standard pitch-size assumption would invalidate a result.

The landed G253 solver was held unchanged at SHA-256 `d3eb9daa4196c4c25dbf9aacca819d38fbfeecf1ff979988c18fb0adf9aa07df`. Its `fit_line_conic` precondition is exactly two line correspondences plus one conic. Here the available centre-circle conic plus one halfway line supplies seven constraints for an eight-degree-of-freedom homography; a second line from the touchline would introduce prohibited unknown width. This is an underconstrained configuration, reported rather than fitted.

| Required degeneracy diagnostic | Result |
|---|---|
| Image-space angle between fitted lines | NOT MEASURED: only one legal line is visible. |
| Observed fraction of fitted conic circumference | NOT MEASURED: no conic was admitted to a fit. |
| Final-objective Jacobian condition number | NOT MEASURED: the unchanged two-line-plus-conic solver was not invoked. |

## Independent gate and withheld pixel measurement

The leading gate line is a pre-fit FAIL, not a residual verdict. No projection exists to render against withheld penalty-area or goal-area geometry, and fabricating such a render would falsely imply a fitted map. The configuration defeated the experiment before the independent-geometry gate: the broadcast view provides the circle and halfway line together, but no second legally dimensioned line in the same frame. This is a full negative result; it is not evidence against the source, the G253 method, or a different frame configuration.

Because the gate did not pass, G252's withheld-geometry normal-search measurement was not run. Consequently soccer median, p90, censored maximum, and no-candidate count are NOT MEASURED. The fixed comparison definition would have searched Canny strong-edge candidates on local normals through 24 pixels, retained no-candidate samples without imputing them, and treated a found 24-pixel offset as right-censored. G252's WNBA reference is median 5 px and p90 19 px under that definition; no soccer number is comparable here.

## Verification and limitations

Focused tests run:

```text
python -m pytest scripts/platformkit/tracking/test_g256b_soccer_line_conic_calibration.py -q -p no:cacheprovider
4 passed in 2.19s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed in 0.84s
```

The added utility is 88 lines and below the 300-line rail, so A12 requires no allowlist change. A7: every linked on-tree artifact exists: [survey](g256b_soccer_line_conic_calibration_2026-09-04_artifact/survey_60s.jpg), [native near-miss frame](g256b_soccer_line_conic_calibration_2026-09-04_artifact/best_available_frame_5400.jpg), [selection crop](g256b_soccer_line_conic_calibration_2026-09-04_artifact/near_miss_centre_circle_halfway_zoom.jpg), unchanged solver, and utility. B1: no metric omits failures; the one clip and 100 evenly spaced survey samples are named. B2-B6: no schema, reader, lifecycle, deployment, production module, or move changed. B7: the complete 100-panel chronological decision survey, not a head slice, is committed. B8: no self-fit residual or fitted geometry is offered as independent evidence. B9: no denominator is recycled. B10: no bar, threshold, coordinate contract, `IMAGE_SPACE`, pitch model, or G253 solver setting changed. Q does not apply to this tracking measurement row.

**NOT VERIFIED:** whether a different unsampled camera instant has the required legal configuration; a soccer homography; feature identity for any fitted input (none was fitted); line angle, conic visibility fraction, or condition number of a valid two-line-plus-conic configuration; an independent penalty- or goal-area render; any G252 pixel offset; propagation; coverage; detection; tracking; coordinate output; pitch length or width; manual-label reliability; automatic calibration (still 0/17); or any production change. Hand-fitting lines remains no more automatic than hand-fitting points.
