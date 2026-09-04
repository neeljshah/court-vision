# G233b: Matched NCAA Seed Gate

## FAIL - the distance-zero projected court does not land on the painted court; propagation and player-foot projection were not run.

This measurement follows [the verifier contract](VERIFIER_CONTRACT.md). It is
the supplied identifier-matched NCAA pairing, not G233's mismatched WNBA pair.

## Premise, scheduling, and source

The shared pod was used because it hosts the read-only source. At
`2026-09-04T01:33:13-05:00`, the pre-dispatch slot check found no active G232
or G235 measurement process. A prior local census had observed G232 and no
G235; no permanent resident, daemon, keeper, or unrelated process was waited
on, stopped, restarted, or changed.

The only opened video was
`/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`:
3,580,059,573 bytes, 1920x1080, 205,444 frames, and `30000/1001` fps, recorded
in the committed [pod context](g233b_seed_gate_artifact/context.txt). The
completed guarded run began at `2026-09-04T06:35:18Z`.

The exact zero-based source-frame index was 28171. It was decoded by sequential
`cv2.VideoCapture.read` calls from index 0 through 28171 inclusive; no keyframe
seek was used. The decoded image was 1920x1080. The committed [seed
record](g233b_seed_gate_artifact/measurement/seed_gate_record.json) contains
the complete decode contract and matrix.

## Fixed seed construction

The labels are 640x360 and the video is 1920x1080, so the applied scale factor
is exactly 3.0. The four labels and scaled native-frame coordinates are:

| Role | Label px | Native-video px |
|---|---:|---:|
| Near baseline left corner | `(38, 223)` | `(114, 669)` |
| Near baseline right corner | `(39, 289)` | `(117, 867)` |
| Near free-throw left corner | `(274, 224)` | `(822, 672)` |
| Near free-throw right corner | `(273, 282)` | `(819, 846)` |

The unchanged G196 `court_points_for_sport("ncaa_basketball")` supplies the
NCAA 12-foot-lane points `[(19, 0), (31, 0), (19, 19), (31, 19)]`; the WNBA
16-foot lane was not used. The image-to-court matrix is:

```text
[[-0.003363616984280291, 0.056501292359316474, -19.294683312439012],
 [ 0.022472194145923066, -0.0003404877900897448, -2.3340438010651896],
 [-0.00016425748617990242, -0.000041144626323545014, 1.0]]
```

## Required distance-zero render gate

The [seed render](g233b_seed_gate_artifact/measurement/seed_render_source_frame_28171.jpg)
was inspected at original resolution. Its yellow inverse-projected court model
does not follow the visible painted near-court geometry: extrapolated boundary
and lane/arc geometry run through the seating and baseline lettering rather
than the painted court. The four red markers are fitted input points, not
independent validation. Therefore the gate is **FAIL** at distance 0.

Per the hard gate, G222 propagation, direct detector calls, projected player
feet, in-court fraction, outside-distance distribution, later-distance renders,
and a labels-per-hour horizon were not computed. The useful eye-checked horizon
is 0 frames, so `ceil(108000 / 0)` is undefined and no finite labels-per-hour
number is supported.

## Disk guard, code identity, and cleanup

Before the completed run wrote a measurement artifact, `du -sm
/workspace/nba-ai-system/data` recorded 31,961 MiB. The binding 4 MiB `dd`
probe with `conv=fsync` completed and was removed; `df` was not used. The pod
temporary tree measured 714,204 bytes before its 25-byte accounting file was
written, and the trap removed it at command exit. Thus the completed run freed
4,908,533 bytes: 4,194,304-byte probe plus 714,229-byte temporary tree. The
first staging-only attempt produced no render and its 826-byte local extraction
was removed after confirming the pod temporary paths were absent. No corpus
source was deleted or changed. The retained committed evidence artifact is
714,232 bytes and is not temporary.

The pod exercised only the streamed measurement files, whose SHA-256 values are
recorded in the [context](g233b_seed_gate_artifact/context.txt):
`g196_homography_from_labelled_corners.py` is
`f9655c338c92be6bcf90be998eac8b2904aaee52346b2f1593a2814458c737a3`, and
`g233b_ncaa_seed_gate.py` is
`19660d292917664dde6e8f02978e9cf78e4fed16bba532c04f5f91dd0b105f74`.
No `src/` or `domains/` file was edited, copied to the pod, or executed.

## Verifier self-check and NOT VERIFIED

Section B was self-checked before reporting. B1 does not apply: there is no
post-gate metric or excluded set. B2-B6 do not apply: this is an additive
measurement harness with no schema, lifecycle, deployment, or retired-module
change. B7 is not applicable because the decision set contains only the required
distance-zero gate, not a head-slice selection. B8 is explicitly avoided: the
exact four-point fit is not presented as independent evidence. B9 does not
apply because no detector-row metric was computed. B10 holds: no fixed threshold,
bar, court model, coordinate contract, or production route was changed. A7
holds: the context, record, and seed render linked above exist in this commit.

- This consumes one hand label and does not change automatic calibration, which
  remains 0/17.
- The visual judgement is one seed, one clip, and one camera. It is a decisive
  gate result for this supplied pairing, not a corpus-wide conclusion.
- No ground truth, label repeatability beyond G140's reported 11.39-pixel p90,
  player semantics, tracking-route behavior, detector behavior, or later-frame
  coordinate plausibility was measured.
- Plausibility is necessary, never sufficient; it was not used as a substitute
  for the failed render gate.
