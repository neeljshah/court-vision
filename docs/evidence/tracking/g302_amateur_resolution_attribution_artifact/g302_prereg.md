# G302 attempt 2 preregistration -- amateur-vs-resolution attribution

Sealed before any crop was rated and before any category count existed. Measurement only.
No production change, filter, threshold, gate or retrain is proposed by this row.
Spec: `docs/evidence/tracking/specs/G302_spec.md`, VERSION 2026-09-07 plus VERSION 2026-09-07b.

## Question

At MATCHED source resolution, how much of the G273 -> G280b 0.597 -> 0.347 PLAYER gap survives?

## Why there is an attempt 2

Attempt 1 (`ebdd44ab3`, worktree a5) was REJECTED on exactly two findings
(`docs/evidence/tracking/G302_VERIFY_2026-09-07.md`): the spec's named sources were lost in the
2026-09-07 pod rebuild so SUBSTITUTE clips were measured, and the live verdict sheet was added AFTER
unblinding. Attempt 2 fixes both. Everything the verifier passed is reused unchanged.

## Sources (A9) -- RE-ACQUIRED, and qualified before this prereg was sealed

Both sources named by the spec were RE-ACQUIRED from the same YouTube ids at the original
resolutions, and each was qualified against what master records for it BEFORE this prereg was sealed
and before any detector ran. The qualification is `scripts/platformkit/tracking/g302_source_identity.py`
and its two committed reports.

BROADCAST (the G273 population), pod `/workspace/g302_attempt2/g302_broadcast_1080.mp4`, shipped from
`C:/Users/neelj/nba-ai-system/data/videos/bridge/wnba_01.f137.mp4`, the retained bridge partial
download of `https://www.youtube.com/watch?v=1zPhldjbJnU` (the recorded `source_url` for `wnba_01`):
2,841,750,689 bytes, 1920x1080, 30 fps, 174,430 frames, 5814.333 s, SHA-256
`f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3`. Master records G273's source as
2,931,985,407 bytes, 1920x1080, 30 fps. The byte hash is DIFFERENT and is reported as DIFFERENT: the
recovered file is the 1080p H.264 VIDEO stream, the lost file was that stream muxed with its audio
track, so the two cannot share a hash. Resolution and fps are EQUAL. The decisive check is
CONTENT REPRODUCTION: re-rendering all 72 of G273's committed blind crops from this file at G273's
recorded source frames and footpoints with the same 512x640 geometry gives mean absolute pixel
difference 1.5446 mean / 2.5103 max / 0.4765 min over 72 of 72 crops, marker patch excluded --
JPEG-requantization distance. This file IS G273's population, frame for frame, over G273's own span.

AMATEUR (the G280 population), pod `/workspace/g302_attempt2/g302_amateur_720p.mp4`, re-fetched with
G245's committed command (`-f '232+233' --download-sections '*00:20:00-00:22:00'` on
`https://www.youtube.com/watch?v=jh3fnwMi7dM`, `docs/evidence/tracking/g245_amateur_footage_acquisition_2026-09-04.md`):
24,523,745 bytes, 1280x720, 30 fps, 3,729 frames, SHA-256
`773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`. Every recorded fact matches:
BYTE HASH IDENTICAL to the value G245 committed, byte size identical, frame count identical,
resolution identical, and duration equal to the 124.3 s the G280 run manifest recorded. Content
reproduction of all 72 of G280b's committed blind crops gives 1.4117 mean / 2.1334 max / 0.6685 min
MAD over 72 of 72 crops. This file IS G280's population, byte for byte.

## Transport

Both qualified files were shipped whole to pod scratch `/workspace/g302_attempt2/` as `.part` and
then renamed, never into the daemon's `data/footage_bridge` stage. The identity above was measured on
the LOCAL files; the pod copies are md5-verified transfers of exactly those bytes -- broadcast
`62ff0c41c20576fb5f5c399b0ceca94a`, amateur `b1613abde31994781e9e18dd1effc991`, checked on both
sides. The same identity check is additionally re-run ON THE POD COPIES, on the files the detector
actually opens, and both reports are committed under
`g302_amateur_resolution_attribution_artifact/identity/`.

## Identity thresholds, declared here before scoring

A source qualifies as a prior row's population when its resolution equals the recorded resolution AND
it reproduces ALL of that row's committed blind crops at mean absolute pixel difference below 3.0
(marker patch 48x48 px excluded), with the byte hash and the duration reported as measured whatever
they are. A source that fails reproduction is NOT the population and the row STOPS CLOSED AT LIMIT.
No frame offset is applied to either source: both were shipped whole, so offset = 0 for both arms.

## Design: three arms, one blind pool, one rater

- ARM 1 `arm1_broadcast_1080_native` -- broadcast decoded at native 1920x1080.
- ARM 2 `arm2_broadcast_720_downscaled` -- the SAME decoded frames from the SAME decode pass,
  downscaled to 1280x720 with `cv2.INTER_AREA` before the detector sees them. The ONLY difference
  from ARM 1 is source resolution.
- ARM 3 `arm3_amateur_720_native` -- the amateur clip decoded at its native 1280x720.

ARM 1 vs ARM 2 isolates RESOLUTION on identical content. ARM 2 vs ARM 3 isolates
AMATEUR-vs-BROADCAST at matched resolution. No fourth difference is added.

FRAME GRID. Every arm uses the identical grid SHAPE -- stride 3, 1152 processed frames, 72
equal-width bins of 16 processed frames -- over its own row's span. ARMS 1 and 2 start at source
frame 19599 and end at 23052, inside G273's own inherited span [19599, 23399]. ARM 3 starts at source
frame 0 and ends at 3453, inside the G280 clip's 3,729 frames, on the same stride-3 lattice the G280
production tracker emitted. One crop geometry (512x640 in that arm's own source pixels) and one
detector call (`yolov8n`, `imgsz=640`, `classes=[0]`, `conf=0.3`) imported unedited from the
human-gated `src/tracking/player_detection.py` serve all three arms.

## Denominators

72 crops per arm; 216 pooled blind crops; 1152 processed frames per arm; 3 arms; 2 source clips plus
1 in-memory downscale of one of them; 1 rater; 1 draw per arm.

## Sampling and seal

One uniformly random class-0 `conf>=0.3` detector box from each of 72 equal-width processed-frame
bins per arm, conditioned on nothing downstream. Sample seed 30220260907; blind seed 30220907. The
216 crops are interleaved into one shuffled presentation order. No arm label, filename, path or image
dimension distinguishes an arm: every render is `blind_NNN.jpg` at 512x640. The unblind map stays
outside the committed packet until the completed verdict sheet is committed BY ITSELF; its canonical
SHA-256 is declared in `blind_packet/blind_order_commitment.json`.

## Rating protocol -- fixed here, before any crop is viewed

All 216 crops are rated ONCE, in the committed presentation order, with the four G273 categories
UNCHANGED and in committed order:

- (a) PLAYER on the court of play -- a person at the marker who is a uniformed player of one of the
  two competing teams AND is on the marked playing court, apart from any bench, chair, huddle,
  timeout or scorer's-table cluster.
- (b) PERSON NOT PLAYER IN PLAY -- a person at the marker who is not that: referee, coach, staff,
  broadcast or camera crew, cheerleader, spectator, scorer's-table crew, a seated or huddled bench
  player, or a uniformed player off the court of play.
- (c) NOT A PERSON -- no person at the marker: floor, seat, wall, equipment, broadcast graphic.
- (d) CANNOT JUDGE -- a person is at the marker but the crop does not allow deciding on-court-of-play
  status.

The rater is a MODEL, not a human, and no human will check any crop. G291 measured two raters at
kappa 0.283 on this exact task, so ARM 1's counts are a second rater's reading of G273's population
and are NOT a correction of G273. The completed verdict sheet is committed BY ITSELF BEFORE the
unblind map exists on disk. THERE IS NO RERATE: any rating produced after unblinding would be
non-blind and is excluded by construction. If fewer than 216 ratings can be completed the row reports
CLOSED AT LIMIT with the completed count, and no arm is rated more thinly than another.

## Declared analysis, fixed before scoring

1. Per-arm counts in all four categories over 72, plus the (b)+(c) grouping.
2. Two pooled two-proportion tests, nominal two-sided p, explicitly with NO multiplicity correction:
   ARM 1 vs ARM 2 (resolution) and ARM 2 vs ARM 3 (amateur at matched resolution), on PLAYER and on
   NOT A PERSON.
3. Per-arm total detection count and detections per processed frame.
4. The ARM 1 determinism check: ARM 1 run twice in one session, both detection-row draws retained as
   committed CSVs and their canonical hashes compared; if they differ, every arm is ONE draw.
5. One sentence decomposing the 0.597 -> 0.347 PLAYER gap.

## Acceptance arithmetic, fixed before scoring

With `a1`, `a2`, `a3` the PLAYER counts of the three arms out of 72 each:

    player_drop_resolution        = (a1 - a2) / 72
    player_drop_amateur_matched   = (a2 - a3) / 72
    player_drop_total_arm1_arm3   = (a1 - a3) / 72 == the sum of the two terms, exactly
    unresolved_remainder          = 0.250000 - player_drop_total_arm1_arm3

`0.250000` is the prior G273 -> G280b PLAYER gap, `(43 - 25) / 72`. The remainder is reported as
UNRESOLVED and is attributed to NOTHING: it is the part of the prior gap that this row's own two
terms do not span, and rater difference (kappa 0.283), span difference and one-draw sampling are all
inside it. NO percent-of-gap survival figure is claimed.

## Acceptance rule

NO pass bar. This is an ATTRIBUTION row. A large resolution effect, a large residual amateur effect,
and a null that refuses to decompose are ALL full successes and will all be reported as measured.

<!-- SEAL -->
sha256_of_lf_normalized_bytes_above_this_seal = f7028693dfdae4c428d2599a4723ff93673fb1c82faef51e04596f6b6e1c1aa2
