# G213 footage visual census - 2026-09-03

## Scope and result

This is a measurement-only visual characterisation of the live POD corpus
snapshot. It changes no production code, thresholds, coordinate contract, or
verdict. It ran no full decode, `ffprobe -count_frames`, `run_clip.py`, model
inference, or GPU work, and did not alter the corpus, daemon, keeper, bridge,
or watchdog.

**Eligible denominator: 13 of 13 complete corpus clips.** The construct is
every top-level `*.mp4` under
`/workspace/nba-ai-system/data/footage_corpus` at enumeration time. This is
two clips more than G209's then-current 11-clip snapshot: KBO 08 and WNBA 02
are now present.

The construct excludes every item outside that root: local `g130_recensus`
archive/cache copies, local reference/demo/tmp files, and the current POD
`data/footage_bridge` staging/bridge files
`soccer__soccer_Z6NTDyxcODs.mp4`,
`ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`,
`mlb__mlb_gDv5xF2AA2E.mp4`, plus its two `.log` files. The corpus root itself
had no top-level non-MP4 files or subdirectories, so there were no exclusions
within the root construct.

## Fixed visual rubric

Each row is a **single-labeller eye judgement** from five sampled stills. There
was no second labeller, no agreement measurement, and no unsupported confidence
score. An observation that could not be made from the stills is marked
ambiguous; capture style is never inferred from the sport or league name.

- **Camera style:** broadcast pan/zoom (moving multi-camera production),
  fixed-wide (static elevated game camera), handheld, or non-game/ambiguous.
  A fixed-wide component inside a multi-camera broadcast is not called a
  fixed single-camera capture.
- **Production tier:** visually professional broadcast, amateur/home-produced
  presentation, or ambiguous. This is a label of the presentation seen, not
  a claim about league status.
- **Graphics:** none, light, or heavy. Record separately whether graphics
  substantively cover the playing surface.
- **Playing-surface visibility:** low (<25%), medium (25-74%), or high
  (>=75%) of the surface in a typical sampled frame. "Typical" is the
  visual tendency across the five stills, not a decoded-frame percentage.
- **Surface appearance:** standard sport surface/markings, or unusual
  colour/markings. A colour treatment can be unusual while the physical
  sport surface remains standard.
- **Lighting:** well-lit venue, dim gym/venue, or ambiguous.

## Sampling and committed evidence

For a clip of duration `D`, seeks used timestamps `D * {1, 3, 5, 7, 11}/12`.
They are evenly spaced by `D/6` while avoiding the title/credits endpoints.
Each was exactly one `ffmpeg -ss <timestamp> -i <clip> -frames:v 1` seek. The
remote command streamed a JPEG directly to this worktree; it created no POD
file. JPEGs were downscaled to 480 pixels wide (`scale=480:-2`, quality 5).

The committed evidence is 65 source-derived JPEGs plus 13 five-panel contact
sheets (78 JPEGs, 2,715,887 bytes total). The contact sheet in each clip folder
is only a concatenation of its five committed frames; frame filenames encode
their timestamp in seconds.

| Clip | Duration (s) | Five seek times (s) | Committed evidence |
|---|---:|---|---|
| `baseball__kbo_06.mp4` | 887.494 | 73.958, 221.874, 369.789, 517.705, 813.536 | `g213_footage_visual_census_2026-09-03/frames/baseball__kbo_06/` |
| `baseball__kbo_07.mp4` | 903.934 | 75.328, 225.984, 376.639, 527.295, 828.606 | `g213_footage_visual_census_2026-09-03/frames/baseball__kbo_07/` |
| `baseball__kbo_08.mp4` | 1,193.474 | 99.456, 298.369, 497.281, 696.193, 1094.018 | `g213_footage_visual_census_2026-09-03/frames/baseball__kbo_08/` |
| `baseball__npb_02.mp4` | 13,706.368 | 1142.197, 3426.592, 5710.987, 7995.381, 12564.17 | `g213_footage_visual_census_2026-09-03/frames/baseball__npb_02/` |
| `baseball__npb_03.mp4` | 14,345.714 | 1195.476, 3586.429, 5977.381, 8368.333, 13150.238 | `g213_footage_visual_census_2026-09-03/frames/baseball__npb_03/` |
| `football__football_Z8Ezd95NnjM.mp4` | 9,617.314 | 801.443, 2404.329, 4007.214, 5610.1, 8815.871 | `g213_footage_visual_census_2026-09-03/frames/football__football_Z8Ezd95NnjM/` |
| `football__football_yahhMkUWd7c.mp4` | 10,129.594 | 844.133, 2532.399, 4220.664, 5908.93, 9285.461 | `g213_footage_visual_census_2026-09-03/frames/football__football_yahhMkUWd7c/` |
| `mlb__mlb_nLoG6gvC-Nk.mp4` | 7,354.174 | 612.848, 1838.544, 3064.239, 4289.935, 6741.326 | `g213_footage_visual_census_2026-09-03/frames/mlb__mlb_nLoG6gvC-Nk/` |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 6,855.014 | 571.251, 1713.754, 2856.256, 3998.758, 6283.763 | `g213_footage_visual_census_2026-09-03/frames/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds/` |
| `soccer__soccer_dnR5C6WLJI4.mp4` | 8,340.034 | 695.003, 2085.009, 3475.014, 4865.02, 7645.031 | `g213_footage_visual_census_2026-09-03/frames/soccer__soccer_dnR5C6WLJI4/` |
| `tennis__tennis_02.mp4` | 8,101.714 | 675.143, 2025.429, 3375.714, 4726, 7426.571 | `g213_footage_visual_census_2026-09-03/frames/tennis__tennis_02/` |
| `wnba__wnba_01.mp4` | 5,814.354 | 484.53, 1453.589, 2422.648, 3391.707, 5329.825 | `g213_footage_visual_census_2026-09-03/frames/wnba__wnba_01/` |
| `wnba__wnba_02.mp4` | 3,146.874 | 262.24, 786.719, 1311.198, 1835.677, 2884.635 | `g213_footage_visual_census_2026-09-03/frames/wnba__wnba_02/` |

## Per-clip classifications

| Clip | Camera style | Production tier | Graphics / surface occlusion | Surface visibility | Surface appearance | Lighting |
|---|---|---|---|---|---|---|
| KBO 06 | Broadcast pan/zoom with close-up cuts | Professional broadcast | Heavy, margin-confined; no substantive field occlusion | Medium | Standard green-and-dirt baseball field | Well-lit |
| KBO 07 | Broadcast pan/zoom with close-up cuts | Professional broadcast | Heavy, margin-confined; no substantive field occlusion | Medium | Standard green-and-dirt baseball field | Well-lit |
| KBO 08 | Broadcast pan/zoom with close-up cuts | Professional broadcast | Heavy, margin-confined; no substantive field occlusion | Medium | Standard green-and-dirt baseball field | Well-lit |
| NPB 02 | Broadcast pan/zoom with close-up/wide cuts | Professional broadcast | Light margin score bug/watermark; no substantive field occlusion | Low | Standard green-and-dirt baseball field | Well-lit |
| NPB 03 | Broadcast pan/zoom with close-up/wide cuts | Professional broadcast | Light; one small analytical inset partly covers field | Medium | Standard green-and-dirt baseball field | Well-lit |
| Football Z8Ezd95NnjM | Broadcast pan/zoom with cutaways | Professional broadcast | Light score bug; one larger analysis graphic partly covers field | Medium | Standard marked green gridiron | Well-lit |
| Football yahhMkUWd7c | Broadcast pan/zoom with cutaways | Professional broadcast | Light margin score bug; no substantive field occlusion | Medium | Standard marked green gridiron | Well-lit |
| MLB nLoG6gvC-Nk | Non-game screen capture; embedded segments use broadcast pan/zoom | Amateur/home-produced commentary livestream | Heavy UI/chat/webcam/desktop layout; substantial embedded-field occlusion | Low | Standard field when visible | Ambiguous |
| NCAA basketball | Broadcast pan/zoom with close-up cuts | Professional broadcast | Light lower-margin score/network graphics; no substantive court occlusion | Medium | Standard marked hardwood court | Well-lit |
| Soccer | Broadcast pan/zoom with close-up/wide cuts | Professional broadcast | Light score bug; occasional lower panel partly covers pitch | Medium | Standard marked green pitch | Well-lit |
| Tennis | Fixed-wide elevated play camera plus broadcast cutaways | Professional broadcast | Light score bug; no material court occlusion | Medium | Standard blue hard court | Well-lit |
| WNBA 01 | Broadcast pan/zoom with close-up cuts | Professional broadcast | Light lower-margin score/network graphics; no substantive court occlusion | Medium | Standard marked hardwood court | Well-lit |
| WNBA 02 | Broadcast pan/zoom with close-up cuts | Professional broadcast | Light lower-margin score graphics; no substantive court occlusion | Medium | Standard markings, unusual dark/lavender-white colour treatment | Well-lit |

## Counts and direct gap answer

| Rubric category | Count (n=13) |
|---|---:|
| Professional broadcast presentation | 12 |
| Amateur/home-produced presentation | 1 |
| Broadcast pan/zoom primary camera | 11 |
| Fixed-wide primary play camera within a multi-camera broadcast | 1 |
| Non-game screen capture | 1 |
| Handheld game camera | 0 |
| Fixed single-camera game capture | 0 |
| Heavy graphics | 4 |
| Light graphics | 9 |
| No graphics | 0 |
| Graphics with substantive/partial surface occlusion | 4 |
| Medium surface visibility | 11 |
| Low surface visibility | 2 |
| High surface visibility | 0 |
| Standard physical sport surface when visible | 12 |
| Unusual surface colour/markings (but standard physical surface) | 1 |
| Visibly non-standard physical sport surface | 0 |
| Well-lit venue | 12 |
| Dim gym/venue | 0 |
| Ambiguous lighting | 1 |

The blunt answer is that this corpus is **mostly professional, multi-camera,
well-lit broadcast footage with persistent graphics**. It is not completely
monolithic: one clip is an amateur/home-produced desktop-commentary livestream
with heavy UI occlusion, and tennis has a fixed-wide *broadcast* play view.
Those exceptions do not supply the missing game-camera classes.

The following categories have **zero representation** in this 13-clip visual
census:

- Handheld game-camera footage.
- Fixed **single-camera** game footage. Tennis is a multi-camera broadcast that
  happens to use a fixed-wide primary play view, not a continuous single-camera
  source.
- Amateur/high-school direct field/court camera acquisition. The one
  amateur/home-produced item is a desktop-commentary screen capture, not an
  amateur game camera.
- Graphics-free footage.
- High playing-surface visibility under the stated typical-frame rubric.
- Dim-gym or otherwise visibly poor-lighting footage.
- Visibly non-standard physical playing surfaces. WNBA 02 supplies one unusual
  court colour treatment only; its markings and physical court remain standard.

No tracking outcome, performance claim, proposed fix, model recommendation, or
robustness conclusion is made here. This row only states the visual coverage
and its holes.

## NOT VERIFIED

- Any independent second labeller, inter-rater agreement, self-agreement, or
  confidence for these visual labels.
- Capture provenance, league level, or production ownership beyond what is
  visually apparent in the five stills.
- Continuous-time prevalence of a camera, overlay, lighting state, or surface
  view outside the five samples per clip.
- Current technical metadata distributions; G209 measured those separately on
  an earlier snapshot and they were not remeasured here beyond duration needed
  to place the seeks.
- Any tracking, detection, calibration, or other system outcome.
- The G203 completion marker: its historical log path was absent on this POD
  snapshot. The task's stated active-G203 constraint was honoured regardless.
- Future corpus membership after this point-in-time enumeration.

## Evidence-path check

This memo and all 78 named JPEG evidence files exist in this worktree under
`docs/evidence/tracking/g213_footage_visual_census_2026-09-03*` before commit.
