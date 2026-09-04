# G250: Amateur Court Feature Inventory and Conditioning Stop

**VERDICT: NO NON-DEGENERATE FOUR-POINT SET EXISTS.** Denominator: 1 clip,
61 fixed-stride survey frames, 20 named physical features, and 0 same-frame
four-point candidates. The largest usable same-frame set is 3 points, all on
the centre line. Consequently no label, fit, identity crop, render, or gate
was run. This is a full measurement result, not a calibration.

This row follows `docs/evidence/tracking/VERIFIER_CONTRACT.md` and the
requirements in `docs/evidence/tracking/specs/G250_spec.md`. It changes no
production code, label file, threshold, coordinate contract,
`court_points_for_sport` key, corpus source, `src/`, or `domains/` file.

## Preconditions, source, lane check, and disk guard

I began on 2026-09-04 America/Chicago in
`C:\Users\neelj\nba-track-a6`, branch `track-a6`. Before beginning, an exact
executable-and-argument process check for `--tag g248` excluded the current
PowerShell process and the checker itself and returned no matching process.
No process was interrupted. (A G248 lane on `a5` would have been permitted
and would not have been interrupted.)

The sole source opened through the already-committed G249 remote-survey and
G243c frame-exact helpers was:

| Field | Independently measured value |
|---|---|
| Exact source path | `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4` |
| Bytes | 24,523,745 |
| SHA-256 | `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea` |
| Video identity | 1280x720; 30/1 fps; 120.100000 s; 3,601 decoded frames |

`df` was not used. Before writing temporary local review products, the remote
binding guard
`dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g250_disk_probe.bin bs=1M count=1 conv=fsync status=none`
passed, wrote 1,048,576 bytes, and the probe was removed. `du -sm
/workspace/nba-ai-system/data` was 33,076 MB. The two abandoned bridge
partials were observed but not changed: `baseball__npb_05.mp4.part`
(2,490,710,544 bytes) and `football__football_m8UWuQoflJo.mp4.part`
(4,999,500,276 bytes).

G249's committed [61-frame whole-clip sheet](g249_amateur_court_corner_seed_2026-09-04_artifact/whole_clip_court_corner_survey_stride_60.jpg)
is the survey basis: zero-based frames `0, 60, ..., 3600`, no input-side
seek. I did not reacquire footage or rerun that survey. Three new exact,
no-seek spot inspections (frames 540, 2220, and 3300) only resolved the best
feature-set identities; none became a label or evidence artifact.

## Feature identity and full 61-frame inventory

`far` is the bleacher-side sideline and `near` is the scorer-table-side
sideline. `in frame` means the named physical location is within the image;
`unoccluded` is its subset. Thus an omitted near sideline is out of frame,
not player-occluded. A circle or arc row counts the location where its named
extremum would lie, not any arbitrary visible curve segment.

The final column is decisive. A painted crossing is hand-identifiable when
both named markings visibly meet. The centre-circle longitudinal extrema are
also marked centre-line/circle crossings. In contrast, a transverse circle
extremum and a three-point apex are unmarked tangent locations on curves;
their mathematical names do not make them hand-identifiable image pixels.

| Feature | In frame | Unoccluded | Out of frame | In-frame but occluded | Human-identifiable world point? |
|---|---:|---:|---:|---:|---|
| far-left court corner | 19/61 | 19/61 | 42/61 | 0/61 | Yes - baseline/sideline crossing |
| far-right court corner | 31/61 | 31/61 | 30/61 | 0/61 | Yes - baseline/sideline crossing |
| near-left court corner | 0/61 | 0/61 | 61/61 | 0/61 | Yes, but never shown |
| near-right court corner | 0/61 | 0/61 | 61/61 | 0/61 | Yes, but never shown |
| centre line x far sideline | 38/61 | 38/61 | 23/61 | 0/61 | Yes - painted crossing |
| centre line x near sideline | 0/61 | 0/61 | 61/61 | 0/61 | Yes, but never shown |
| centre-circle longitudinal-left extremum (centre-line crossing) | 38/61 | 30/61 | 23/61 | 8/61 | Yes - painted crossing |
| centre-circle longitudinal-right extremum (centre-line crossing) | 38/61 | 31/61 | 23/61 | 7/61 | Yes - painted crossing |
| centre-circle far transverse extremum | 38/61 | 34/61 | 23/61 | 4/61 | No - unmarked curve tangent |
| centre-circle near transverse extremum | 38/61 | 33/61 | 23/61 | 5/61 | No - unmarked curve tangent |
| left-end far lane/baseline intersection | 20/61 | 0/61 | 41/61 | 20/61 | Yes - painted crossing |
| left-end near lane/baseline intersection | 20/61 | 0/61 | 41/61 | 20/61 | Yes - painted crossing |
| right-end far lane/baseline intersection | 21/61 | 0/61 | 40/61 | 21/61 | Yes - painted crossing |
| right-end near lane/baseline intersection | 21/61 | 0/61 | 40/61 | 21/61 | Yes - painted crossing |
| left-end far free-throw/lane intersection | 20/61 | 0/61 | 41/61 | 20/61 | Yes - painted crossing |
| left-end near free-throw/lane intersection | 20/61 | 0/61 | 41/61 | 20/61 | Yes - painted crossing |
| right-end far free-throw/lane intersection | 21/61 | 0/61 | 40/61 | 21/61 | Yes - painted crossing |
| right-end near free-throw/lane intersection | 21/61 | 0/61 | 40/61 | 21/61 | Yes - painted crossing |
| left-end three-point arc apex | 20/61 | 14/61 | 41/61 | 6/61 | No - unmarked curve tangent |
| right-end three-point arc apex | 21/61 | 15/61 | 40/61 | 6/61 | No - unmarked curve tangent |

This confirms G249's important distinction: all 50 within-frame court
corner observations are unoccluded. The paint-line crossings fail for a
different reason: every within-frame observation is occupied. A visible arc
or circle contour is not silently converted into a point label.

## Best simultaneous-feature frames

The highest usable count is three. The best rows are below; each has the
same three clearly marked, unoccluded crossings and no fourth. The visible
paint-end crossings are occupied in every one. The apparent circle/arc curve
locations are listed separately above but excluded here because they are not
hand-identifiable point correspondences.

| Exact frame | Unoccluded, human-identifiable set | Count | Why no fourth point enters |
|---:|---|---:|---|
| 480 | far centre-line/sideline; both centre-line/circle crossings | 3 | left painted-end crossings are player-occupied; near sideline is outside image |
| 540 | far centre-line/sideline; both centre-line/circle crossings | 3 | left painted-end crossings are player-occupied; near sideline is outside image |
| 600 | far centre-line/sideline; both centre-line/circle crossings | 3 | left painted-end crossings are player-occupied; near sideline is outside image |
| 2220 | far centre-line/sideline; both centre-line/circle crossings | 3 | right painted-end crossings are player-occupied; near sideline is outside image |

The three listed points are collinear on the physical centre line. Far court
corners occur in other pan states; no such corner co-occurs with a fourth
unoccluded, nameable point in this 61-frame survey.

## Conditioning before fitting

A candidate here is exactly what a homography needs: four distinct,
same-frame, human-identifiable, unoccluded correspondences. There are zero
such candidates. The complete pre-fit conditioning enumeration is therefore:

| Candidate four-point set | Number of sets | Quadrilateral area / image area | Minimum point-to-line distance | Result |
|---|---:|---:|---:|---|
| Every valid same-frame four-subset of the inventory | 0 | N/A - no fourth point exists | N/A - no fourth point exists | No set to fit; do not manufacture a fourth curve point |

This is stronger than a near-collinearity finding: every surveyed usable set
has cardinality at most three. At the best frames the sole three-point set is
collinear, so a hypothetical fourth point placed on the same centre line
would have zero quadrilateral area fraction and zero minimum perpendicular
distance by construction; it is not a permissible correspondence. The two
far corners and far centre-line/sideline crossing similarly lie on the far
sideline when observed. No cross-frame combination is a candidate because
the camera pans between frames.

No homography was fitted. In particular, no self-fit residual is reported:
with four fitted inputs it would be 0.000000000 px even for a bad,
near-collinear construction and would not measure correctness.

## Gates deliberately not run

No non-degenerate candidate exists, so G243c's unchanged post-selection
protocol is not entered: there are no committed point-identity crops, no
three independent labellings, no label spread, no high-school 84x50-ft /
12-ft-lane gate, no existing `ncaa_basketball` 94x50-ft / 12-ft-lane gate,
and no render. `court_points_for_sport` was not changed or extended.
Repeatability is not correctness; inventing repeatable curve placements or
adjusting a label after a gate would repeat the G246 failure and void the row.

## Acquisition criterion

For this footage class to be calibratable, a source camera must show in one
frame at least four distinct, named, painted intersections that are not
occluded and span two dimensions of the court. Practically, it must include
some near-side geometry (a near corner or visible near painted-end crossing)
as well as far-side/centre geometry, rather than only a far sideline and
centre line. Before any fit, the acquisition review must report the actual
four-point image quadrilateral area fraction and minimum point-to-other-three
line distance, and reject a near-zero-spread set. This is an acquisition
criterion, not a newly invented calibration threshold.

## Cleanup, limitations, and verifier self-check

Temporary local grouped review sheets and the three exact spot decodes totalled
8,102,914 bytes. The host command policy rejected two exact-path deletion
attempts, and the local patch mechanism cannot delete binary files; they remain
untracked in `docs/evidence/tracking/g250_amateur_feature_inventory_2026-09-04_artifact_temp/` and are not evidence or part of this commit. Bytes freed: 0.
No corpus source, bridge partial, committed G249 artifact, or label was
deleted or modified.

Limitations: one clip, one camera, one labeller, 120.1 seconds, and a
61-frame stride-60 survey. A feature may be available in an unsurveyed frame.
This consumes no hand label and is not automatic calibration, which remains
0/17. Eye-label reliability has not cleared 80 percent blind agreement on
the programme's measured criteria. The court model is assumed, not measured.
G242, G244, and G247 remain controlling: match counts, inliers, ratio, RMS,
and quadrilateral shape do not establish a correct court; only independent
renders could do so, and none is permissible here.

Verifier self-check: A7: the linked G249 contact sheet exists at report time.
B1: every inventory denominator is the named 61-frame whole-clip survey; no
failed row was excluded. B2-B6: no schema, lifecycle, deployment, production
code, or module move occurred. B7: fixed stride covers frames 0 through 3600,
not a head slice. B8: no fitted residual or input point is represented as
independent evidence. B9: all counts use distinct survey frames. B10: no
threshold, bar, matcher, coordinate contract, or court-model key changed. Q
does not apply to this tracking eye-measurement row. No harness was added, so
there is no new per-file test or A12 allowlist adjustment.

## NOT VERIFIED

- A four-point seed in an unsurveyed frame, another source interval, camera,
  clip, or labeller review.
- Any hand-labelled calibration, high-school or NCAA gate verdict, render,
  propagation, detector projection, or in-court calculation.
- Physical 84-versus-94-foot dimensions, lane width, arc radius, camera-model
  adequacy, or any automatic calibration result.
- Whether a different camera framing can meet the stated acquisition
  criterion; this row establishes only the limitation of this one camera and
  61-frame survey.
