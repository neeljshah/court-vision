# G34 (basketball half): wide-view share on a WNBA broadcast

Date: 2026-09-02. Gap: G34, basketball half (tennis half already landed in
`g34_view_share_and_denominator_2026-09-02.md`). Same method, same script,
different sport. One hand-labelled measurement, no CLIP, no model, no new
dependency.

**Finding.** WIDE (the elevated broadcast camera showing enough court to
calibrate) is **66.3 pct** of this WNBA broadcast (199/300, Wilson 95 pct CI
0.608-0.714). PAN (partial/zoomed elevated court views) is **1.3 pct**
(4/300, CI 0.005-0.034). TIGHT (close-up, crowd, replay, graphic, bench,
picture-in-picture) is **32.3 pct** (97/300, CI 0.273-0.378).

This is markedly higher than tennis's 41.7 pct rally share. A WNBA broadcast
holds its main elevated camera through most live play; tennis cuts away
between every point. But a third of the clip is still structurally
unsolvable by a planar-homography court solver, so no whole-clip
decoded-frame coverage above ~0.66-0.71 is reachable on this broadcast
either.

## 1. Clip and method

Clip `wnba__wnba_01.mp4`, 28,861 frames at 30 fps (ffprobe
`nb_frames=28861, r_frame_rate=30/1`), from
`/workspace/nba-ai-system/data/footage_corpus/` on the pod.

Census built by `/tmp/g34_census.py` on the pod (same script used for the
tennis half; it already existed at that path, unmodified), run as:

```
nohup setsid nice -n 10 python /tmp/g34_census.py \
  /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 300 \
  > /tmp/g34_bb.log 2>&1 &
```

Sampling is deterministic, not randomly seeded: `step = total_frames // 300
= 96`, `indices = [i * 96 for i in range(300)]`, i.e. one frame every 96
frames (~3.2 s at 30 fps), spanning the entire 962 s clip start to finish.
Frames were extracted with a single ffmpeg `select` pass, scaled to width
320, and montaged 25-per-sheet in a 5-wide grid with the frame index burned
into each tile. 12 contact sheets, 300 frames, all read and classified by
eye with the Read tool.

**Frame indices** (300 values, `i*96` for i=0..299):
0, 96, 192, 288, 384, 480, 576, 672, 768, 864, 960, 1056, 1152, 1248, 1344,
1440, 1536, 1632, 1728, 1824, 1920, 2016, 2112, 2208, 2304, 2400, 2496, 2592,
2688, 2784, 2880, 2976, 3072, 3168, 3264, 3360, 3456, 3552, 3648, 3744, 3840,
3936, 4032, 4128, 4224, 4320, 4416, 4512, 4608, 4704, 4800, 4896, 4992, 5088,
5184, 5280, 5376, 5472, 5568, 5664, 5760, 5856, 5952, 6048, 6144, 6240, 6336,
6432, 6528, 6624, 6720, 6816, 6912, 7008, 7104, 7200, 7296, 7392, 7488, 7584,
7680, 7776, 7872, 7968, 8064, 8160, 8256, 8352, 8448, 8544, 8640, 8736, 8832,
8928, 9024, 9120, 9216, 9312, 9408, 9504, 9600, 9696, 9792, 9888, 9984,
10080, 10176, 10272, 10368, 10464, 10560, 10656, 10752, 10848, 10944, 11040,
11136, 11232, 11328, 11424, 11520, 11616, 11712, 11808, 11904, 12000, 12096,
12192, 12288, 12384, 12480, 12576, 12672, 12768, 12864, 12960, 13056, 13152,
13248, 13344, 13440, 13536, 13632, 13728, 13824, 13920, 14016, 14112, 14208,
14304, 14400, 14496, 14592, 14688, 14784, 14880, 14976, 15072, 15168, 15264,
15360, 15456, 15552, 15648, 15744, 15840, 15936, 16032, 16128, 16224, 16320,
16416, 16512, 16608, 16704, 16800, 16896, 16992, 17088, 17184, 17280, 17376,
17472, 17568, 17664, 17760, 17856, 17952, 18048, 18144, 18240, 18336, 18432,
18528, 18624, 18720, 18816, 18912, 19008, 19104, 19200, 19296, 19392, 19488,
19584, 19680, 19776, 19872, 19968, 20064, 20160, 20256, 20352, 20448, 20544,
20640, 20736, 20832, 20928, 21024, 21120, 21216, 21312, 21408, 21504, 21600,
21696, 21792, 21888, 21984, 22080, 22176, 22272, 22368, 22464, 22560, 22656,
22752, 22848, 22944, 23040, 23136, 23232, 23328, 23424, 23520, 23616, 23712,
23808, 23904, 24000, 24096, 24192, 24288, 24384, 24480, 24576, 24672, 24768,
24864, 24960, 25056, 25152, 25248, 25344, 25440, 25536, 25632, 25728, 25824,
25920, 26016, 26112, 26208, 26304, 26400, 26496, 26592, 26688, 26784, 26880,
26976, 27072, 27168, 27264, 27360, 27456, 27552, 27648, 27744, 27840, 27936,
28032, 28128, 28224, 28320, 28416, 28512, 28608, 28704

## 2. Class definitions

- **WIDE**: the elevated broadcast camera showing enough court to calibrate
  (the standard diagonal main-broadcast angle, plus the overhead
  "birds-eye"/logo-cam shots that show the full court). Minor ad-banner
  overlays on top of this view do not disqualify a frame.
- **PAN**: an elevated but partial/zoomed court view (e.g. under-basket
  cameras zoomed to one key/paint area) -- shows real court geometry but not
  enough of it, or a moving shot mid-transition.
- **TIGHT**: close-up, crowd, replay, graphic, bench, sideline interview,
  and picture-in-picture layouts (a small court thumbnail inset behind a
  dominant close-up/graphic foreground was scored TIGHT, since the
  dominant image is not calibratable).

## 3. Per-sheet tally

| sheet | frames | idx range | WIDE | PAN | TIGHT |
|---|---|---|---:|---:|---:|
| 00 | 1-25 | 0-2304 | 19 | 0 | 6 |
| 01 | 26-50 | 2400-4704 | 19 | 0 | 6 |
| 02 | 51-75 | 4800-7104 | 13 | 1 | 11 |
| 03 | 76-100 | 7200-9504 | 20 | 0 | 5 |
| 04 | 101-125 | 9600-11904 | 14 | 0 | 11 |
| 05 | 126-150 | 12000-14304 | 20 | 0 | 5 |
| 06 | 151-175 | 14400-16704 | 17 | 2 | 6 |
| 07 | 176-200 | 16800-19104 | 18 | 1 | 6 |
| 08 | 201-225 | 19200-21504 | 22 | 0 | 3 |
| 09 | 226-250 | 21600-23904 | 19 | 0 | 6 |
| 10 | 251-275 | 24000-26304 | 5 | 0 | 20 |
| 11 | 276-300 | 26400-28704 | 13 | 0 | 12 |
| **total** | **300** | | **199** | **4** | **97** |

Sheet 10 (idx 24480-26304) is almost entirely TIGHT: a run of
picture-in-picture segments (analyst/sideline interview full-frame, with a
small court thumbnail inset) that lasts roughly 1,800 frames (~60 s) of
broadcast time. Like tennis's zero-rally sheet, this shows the class is
clustered in broadcast-structure blocks, not uniform noise -- a
non-evenly-spaced sample (e.g. a head slice) would badly misestimate the
share depending on where it landed.

## 4. Shares with Wilson 95 pct CI (n=300, z=1.96)

| class | count | share | Wilson 95 pct CI |
|---|---:|---:|---|
| WIDE  | 199 | 0.6633 | [0.608, 0.714] |
| PAN   | 4   | 0.0133 | [0.005, 0.034] |
| TIGHT | 97  | 0.3233 | [0.273, 0.378] |

(199 + 4 + 97 = 300, each row's CI is a one-vs-rest binomial Wilson
interval, same formula as the tennis rally-share calculation.)

## 5. What this bounds, and a judgment call flagged explicitly

Two sub-populations were folded into WIDE and TIGHT respectively as a
judgment call, matching the discipline the tennis doc used for its
borderline camera cases:

- **5 frames** (idx 3168, 3264, 3360, 20448, 20544) are a fisheye/dome
  overhead effect camera that shows the *entire* court but through a curved
  lens -- a standard planar-homography court solver cannot calibrate a
  fisheye frame without a separate lens model. These were scored TIGHT, not
  WIDE, on the same ground the tennis doc used for the low net-level camera:
  the lock as it exists cannot solve this view even though a human can see
  the whole court in it.
- **16 frames** in the picture-in-picture run on sheet 10 show a small court
  thumbnail behind a dominant close-up/graphic foreground. Scored TIGHT
  because the dominant frame content is not a calibratable court view, even
  though a sliver of court is technically present in the pixels.

If a future solver handles fisheye undistortion or can crop and solve a PIP
inset, the WIDE share would rise by up to (5+16)/300 = 7 pct. As labelled
here, it does not.

## 6. Which existing basketball denominators this changes

- `docs/evidence/tracking/RESULTS_LEDGER.md` row **G04** (2026-09-02) reports
  wnba_01 image_px features on "964/965/965 usable frames of **2,998
  decoded**". That 2,998 is the tracking daemon's own decoded-frame count for
  this same clip (962 s at roughly 3.1 fps effective sampling, not the raw
  28,861-frame file) -- so the daemon already subsamples before this
  census's WIDE/PAN/TIGHT split would apply on top of it. G04's "pan share
  0.0113" is an unrelated computed camera-motion feature, not this doc's PAN
  view-class; the two should not be conflated by name.
- The general rail in `docs/TRACKING.md` and the research plan states
  denominators = decoded frames. This census shows that even a generous
  decoded-frame denominator caps achievable whole-clip coverage at roughly
  0.61-0.71 on this broadcast, because the remaining ~32 pct (TIGHT) can
  never be solved regardless of decode stride, matching the tennis doc's
  point that the ~0.90 coverage bar is unreachable on whole clips by
  construction for camera-cut sports. No basketball clip has a `passing`
  coordinate_contract in the daemon currently (RESULTS_LEDGER row B5/G38:
  all image_px sports fail the contract check by construction), so this
  finding does not flip any live PASS/FAIL verdict today -- it sets the
  ceiling that any future basketball coverage claim must be checked against
  before it is quoted.

## NOT VERIFIED

- One clip, one broadcaster (ESPN), one league (WNBA). Not a per-sport or
  per-broadcast constant; must not be reused for NCAA basketball or a
  different network's broadcast without its own census.
- Labelling was done by one observer, one pass, no blind re-label, so there
  is no inter-rater agreement figure. The fisheye-camera and
  picture-in-picture judgment calls in section 5 are explicit but
  unreplicated.
- The fisheye and PIP frames were scored against "can the existing solver
  calibrate this," not measured against the solver itself -- no court solver
  was run in this task.
- This census is on raw decoded frames from the source file, not on the
  tracking daemon's own decode/stride pattern for this clip -- the G04 row's
  2,998-decoded-frame figure was not reproduced or checked against this
  census's 28,861-frame total; the daemon's actual sampling stride for
  basketball was not measured here.
- No sequential-range check (the tennis doc's section 3/5 addendum) was run
  for basketball -- whether any existing basketball 300-frame range achieves
  a WIDE share materially different from the whole-clip 66.3 pct is unknown.
