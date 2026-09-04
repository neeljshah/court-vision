# G249: Amateur Court-Corner Survey and Probe Stop

**VERDICT: CLOSED AT LIMIT.** No frame with all four identifiable, unoccluded
court corners exists in the 61-frame whole-clip survey or in 48 evenly spaced
probe samples. The blocking limitation is camera framing, not player
occlusion: both near-side baseline-sideline intersections are outside the
image in every surveyed source frame. Denominator: 1 existing clip, 61
whole-clip survey frames, 4 corners, 4 same-source short probes with 12
contact-sheet samples each, 0 eligible frames, 0 labels, and 0 gates.

This measurement-only row follows
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. No production code, threshold,
coordinate contract, `court_points_for_sport` key, label file, matcher,
corpus clip, `src/`, or `domains/` file changed. No probe video was uploaded
or retained.

## Lane check, source identity, and disk guard

I began 2026-09-04 05:57:11 America/Chicago in
`C:\Users\neelj\nba-track-a6`, branch `track-a6`. The exact process check
matched only `pythonw.exe` processes carrying an argument of the form
`--tag g248`; it returned absent. This excludes the G249 launch wrapper, whose
prompt text merely mentions G248. No process, including permanent residents,
was interrupted.

Before the survey, the remote source was independently read and measured:

| Field | Measured value |
|---|---|
| Exact source path | `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4` |
| Bytes | 24,523,745 |
| SHA-256 | `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea` |
| Resolution | 1280x720 |
| FPS | 30/1 |
| Duration | 120.100000 s |
| Decoded video frames | 3,601 |

`df` was not used. Before any probe download, the required remote guard
`dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g249_disk_probe.bin bs=1M count=1 conv=fsync status=none`
wrote 1,048,576 bytes, which was then removed. `du -sm
/workspace/nba-ai-system/data` was 33,065 MB. The existing amateur corpus
source and both abandoned bridge partials were not changed.

## Existing-clip court-corner survey

The [whole-clip contact sheet](g249_amateur_court_corner_seed_2026-09-04_artifact/whole_clip_court_corner_survey_stride_60.jpg)
contains all 61 zero-based frames `0, 60, ..., 3600`, decoded from the source
without input-side seek and scaled only for review. `far` is the bleacher-side
sideline; `near` is the scorer-table-side sideline. A corner was counted as
within frame only when the painted baseline and sideline visibly meet at that
physical intersection. `unoccluded` is a subset of within-frame. Thus a
corner outside the image is not counted as player-occluded.

| Physical corner | Within field of view | Unoccluded | Out of frame | In-frame but occluded |
|---|---:|---:|---:|---:|
| far-left | 19/61 | 19/61 | 42/61 | 0/61 |
| far-right | 31/61 | 31/61 | 30/61 | 0/61 |
| near-left | 0/61 | 0/61 | 61/61 | 0/61 |
| near-right | 0/61 | 0/61 | 61/61 | 0/61 |

No source-survey frame has four corners in frame, so none can have four
unoccluded corners. The near-corner zeros are a permanent framing limitation
of this camera position during this clip, not a waiting-for-players problem.
The far corners that entered frame were unobstructed; no otherwise usable
corner was rejected because a player, coach, or official covered it.

## Conditional same-source probes

Because the existing clip had no eligible frame, I used the established
explicit-HLS pair `-f '232+233'` with `--download-sections` against only
`https://www.youtube.com/watch?v=jh3fnwMi7dM`. Four separate 30-second probes
targeted the opening and later stoppage/quarter-boundary portions of the same
source. Each was sampled into its linked 12-frame contact sheet before any
retention decision.

| Requested source section | Contact sheet | Eligibility result |
|---|---|---|
| `00:00:00-00:00:30` opening | [sheet](g249_amateur_court_corner_seed_2026-09-04_artifact/probe_opening_contact_sheet.jpg) | 0/12; near corners remain out of frame |
| `00:35:00-00:35:30` | [sheet](g249_amateur_court_corner_seed_2026-09-04_artifact/probe_q1_break_contact_sheet.jpg) | 0/12; near corners remain out of frame |
| `00:50:00-00:50:30` | [sheet](g249_amateur_court_corner_seed_2026-09-04_artifact/probe_q2_break_contact_sheet.jpg) | 0/12; near corners remain out of frame |
| `01:10:00-01:10:30` quarter-boundary probe | [sheet](g249_amateur_court_corner_seed_2026-09-04_artifact/probe_halftime_contact_sheet.jpg) | 0/12; near corners remain out of frame |

Exact acquisition command template, run once per listed section with its
corresponding output basename, was:

```text
yt-dlp --quiet --cookies data/videos/youtube_cookies.txt --merge-output-format mp4 --no-part --no-playlist -f '232+233' --download-sections '*<section>' -o data/videos/bridge/g249_probe_<name>.%(ext)s https://www.youtube.com/watch?v=jh3fnwMi7dM
```

The local probe video sizes were 7,371,777, 4,861,613, 5,574,561, and
6,127,134 bytes. All four were deleted after the contact-sheet decisions,
freeing 23,935,085 bytes. No section qualified for corpus upload, so there is
no new corpus identity or `ls -la` presence proof to report; retaining a
non-eligible section would repeat G245's limitation.

## Unrun seed protocol

The hard prerequisite for G243c's unchanged seed protocol never occurred.
Accordingly there are no frame-exact seed decode, committed identity crops,
hand labels, label-spread calculation, high-school gate, NCAA gate, fit,
render, or propagation result. No label was adjusted after a gate because no
gate was run. RMS is not reported: four fitted points would make it
identically zero and it would not be independent geometry.

The local survey helper is
`scripts/platformkit/tracking/g249_court_corner_survey.py` (SHA-256
`f5c5fce105451641bc051af0f1fa67651f31d4dc66989efb414be6732d86fd90`);
its focused test is
`scripts/platformkit/tracking/test_g249_court_corner_survey.py` (SHA-256
`bc88d9238bd8284a901e1bcb148d1d0e7522c1f7d17cf5f5a19a8e64b5060c91`).
It reads the pod video through `ssh config.pod` and writes only local evidence;
it did not deploy or alter a pod route.

Focused tests:

```text
python -m pytest scripts/platformkit/tracking/test_g249_court_corner_survey.py -q -p no:cacheprovider
3 passed
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed
```

## Verifier-contract self-check

A7: every memo-linked contact sheet exists in this commit. B1: the denominator
names every surveyed frame and each probe sample; no failures were excluded.
B2-B6: no schema, lifecycle, deployment, or module move occurred. B7: the
existing-clip sheet spans frames 0 through 3600 at fixed stride, and every
probe sheet is evenly spaced rather than a head slice. B8: no self-fit result
is offered as evidence. B9: each count is over distinct decoded survey frames
or explicitly named probe samples. B10: no bar, threshold, model key, or
matcher setting changed. Q does not apply to this tracking eye-measurement
row. A12: both new Python files are below 300 LOC and no allowlisted file
grew; the shared LOC rail passed.

## NOT VERIFIED

- An eligible frame in another camera, source interval, or labeller's review.
- Any hand-labelled calibration, which remains 0/17; this row consumed no
  label and did not run automatic calibration.
- Physical 84-versus-94-foot dimensions, lane width, camera-model adequacy,
  detection, tracking, or projected court coordinates.
- Eye-label reliability beyond this one labeller; it has not cleared 80
  percent blind agreement on the programme's measured criteria.
- Whether the original source has an unprobed interval with a different camera
  framing. This result is limited to the one clip plus the four listed probes.

G246 remains controlling: repeatability is not correctness. G242, G244, and
G247 remain controlling: matches, inliers, ratios, RMS, and quadrilateral
shape do not establish a correct court; only independent-geometry renders
could do so, and none is permissible without four identity-safe corners.
