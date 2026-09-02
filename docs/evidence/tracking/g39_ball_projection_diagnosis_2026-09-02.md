# G39: why the tennis ball projects to 106,853 ft

Date: 2026-09-02. Gap: G39 (filed by G38 section 5). Read-only diagnosis over
four pod tracking tables plus two instrumented re-runs of the current adapter.
No code changed, no threshold moved, no clamp added, nothing re-tracked into
`data/tracking/`.

**VERDICT: CAUSE ESTABLISHED, and the leading hypothesis is FALSIFIED.** The
homography is not near-singular. The cause is a detection failure amplified by
an unguarded plane projection: `MotionDiffDetector` is not detecting the ball at
all -- in 12 of 12 renders it has locked onto the far player's body or onto
crowd/scoreboard motion -- and `ball_rows` then pushes that image point through
the GROUND-PLANE homography with no plane-membership check and no bound. Court
`x` is exactly proportional to `1 / (distance to the ground plane's vanishing
line)`, so a pixel picked near the horizon goes to five and six figures.

---

## 1. Reproduction of the premise (contract A2, Q8)

The G38 section-5 numbers reproduce exactly from
`/workspace/nba-ai-system/data/tracking/<clip>/tracking_data.csv`, `cls=="ball"`
(`track_id` 99), sorted by frame:

| clip | ball rows | ball x min | ball x max | max abs step | player x min | player x max |
|---|---:|---:|---:|---:|---:|---:|
| tennis_02 | 1,831 | -113,676.5 | 226,046.5 | 253,397.4 | -4.79 | 82.48 |
| tennis_03 | 2,630 | **-126,835.5** | **106,853.7** | **126,001.0** | -4.96 | 82.93 |
| tennis_04 | 2,946 | -34,542.6 | 168,015.5 | 168,914.4 | -4.89 | 82.99 |
| tennis_05 | 2,395 | -85,003.7 | 395,650.8 | **760,419.9** | -4.81 | 82.96 |

G38's "max x = 106,853 ft", "transitions of 126,001 ft and 760,419 ft" and
"players within 82.93 ft" all reproduce. PREMISE HOLDS.

It is not a handful of outliers. Ball rows inside a generous court rectangle
(x in [-6, 84], y in [-4, 40] ft): tennis_02 **24.5%**, tennis_03 **64.6%**,
tennis_04 **53.4%**, tennis_05 **35.3%**. Rows strictly inside the real court
(x in [0, 78]): 495 / 1,607 / 1,756 / 891 of 1,831 / 2,630 / 2,946 / 2,395.

**One G38 sentence needs correcting.** "players in the SAME frames stay within
82.93 ft" is not what the tables say: 82.93 ft is the clip-wide player maximum.
In the frames where the ball exceeds 500 ft there are **zero** player rows on
tennis_02, _03 and _05, and two on tennis_04. See section 5.

---

## 2. The projection law, measured (contract A2)

`domains/tennis/tracking/ball.py:246` is the whole projection:

```python
court = cv2.perspectiveTransform(np.float32([[[point[0], point[1]]]]), homography)[0, 0]
```

No gate on the input, no gate on the output. `homography` maps the image to the
78x36 ft **ground plane**, so `court_x = X/w` with
`w = h20*u + h21*v + h22`, and `w = 0` is exactly the ground plane's vanishing
line (the horizon) in the image. The prediction is that `1/|court_x|` is linear
in the ball pixel's distance to that line. Measured on two instrumented re-runs
of the current adapter (probe records the raw detection, `H`, `w` and the
vanishing line per evaluated frame):

| clip re-run | emitted ball rows | corr(dist to vanishing line px, 1/abs(court_x)) |
|---|---:|---:|
| tennis_nyYk2nPZAwY_720p (1280x720, 6,000 source frames) | 188 | **0.9654** |
| tennis_3x3eEWCZmWQ (640x360, 8,000 source frames) | 191 | **0.8853** |

The law also shows on the four premise clips without any image data. A point
approaching the horizon of a court seen from behind the baseline runs off along
the court LENGTH axis, so the blow-up direction should hug the +/-x axis.
Folded angle of `(x-39, y-18)` to the x axis on rows with `|x| > 500`:

| clip | n | median angle | p90 angle |
|---|---:|---:|---:|
| tennis_02 | 315 | 2.35 deg | 35.45 deg |
| tennis_03 | 220 | **1.34 deg** | 5.46 deg |
| tennis_04 | 258 | 2.18 deg | 9.01 deg |
| tennis_05 | 275 | 1.50 deg | 23.35 deg |

And `|y|/|x|` on `|x| > 1000` rows has median 0.013 to 0.039 across the four
clips: `x` diverges 25x to 75x harder than `y`. That is the horizon signature.

---

## 3. The leading hypothesis is FALSIFIED

"A near-singular homography maps a ball detection close to the horizon toward
infinity." The second half is right; the first half is wrong. `cond(H)` on the
instrumented runs, split by how badly the row blows up:

| clip | band | n | median cond(H) | median abs(w) | median ball row v | v / image height |
|---|---|---:|---:|---:|---:|---:|
| nyYk 720p | abs(x) <= 84 | 85 | 44,665 | 2.882 | 442.8 | 0.615 |
| nyYk 720p | 84-500 | 103 | **44,707** | 1.641 | **149.9** | **0.208** |
| 3x3 360p | abs(x) <= 84 | 11 | 21,550 | 2.370 | 150.8 | 0.419 |
| 3x3 360p | 84-500 | 180 | **21,550** | 1.662 | **71.2** | **0.198** |

`cond(H)` is flat to four significant figures across the well-behaved and the
blown-up rows (nyYk overall: median 44,683, p95 45,346, max 45,998). It does not
discriminate at all. What changes is the ball pixel's **image row**: the
misbehaving rows sit high in the frame. On nyYk the far baseline back-projects
to image row ~232 and the near baseline to ~619; the `|x| <= 84` rows sit at
median row 443 (on court) and the blown-up rows at median row 150 (**above the
far baseline, in the backdrop wall and crowd**).

Stale calibration is also ruled out: every emitted ball row carries provenance
`solved` (150) or the drift-checked reuse `camera_lock_drift_checked` (38) on
nyYk, 101 / 90 on 3x3. `CameraLock.resolve` fails closed when it cannot find
>= 2 current-frame court intersections, so these frames really do show the court.

---

## 4. What the renders show (contract A3, B7)

12 frames sampled EVENLY across the offending set (`|court_x| > 84`, 103 of 188
emitted rows on nyYk 720p, ordered by frame, `np.linspace` over the index -- not
a head or tail slice of that set). Each render draws the ball pixel, the
back-projected 78x36 court, the ground plane's vanishing line and the
detector's own 2/3-height cap. Files: `docs/evidence/tracking/g39_renders/`.

| frame | ball pixel | court x | what is actually at that pixel |
|---|---|---:|---|
| 5501 | (1196, 73) | 161.4 | speed-gun / scoreboard graphic, top right, above the backdrop |
| 5561 | (1054, 97) | 148.8 | crowd and standing staff behind the backdrop wall |
| 5644 | (387, 149) | 115.5 | far player's head, against the "Emirates" banner |
| 5662 | (367, 164) | 106.7 | far player's head and racket |
| 5687 | (320, 178) | 100.5 | far player's legs -- real yellow ball visible at (325, 238) |
| 5711 | (329, 209) | 86.9 | far player's leg / shoe -- real yellow ball visible at (305, 430) |
| 5727 | (368, 150) | 113.3 | far player's head -- real yellow ball visible at (308, 411) |
| 5767 | (415, 155) | 112.1 | far player's head and racket |
| 5794 | (451, 150) | 115.4 | far player's head -- real yellow ball visible at (920, 215) |
| 5870 | (1030, 156) | 111.1 | crowd / staff beside the speed display (court y = 44.2, off court) |
| 5888 | (580, 122) | 131.1 | far player's head and racket hand |
| 5902 | (597, 148) | 115.8 | far player's torso and racket |

**Tally: 0 of 12 are the tennis ball.** 9 of 12 are the far player's body, head
or racket; 3 of 12 are crowd, staff or a scoreboard graphic beyond the court. In
4 of the 12 the real yellow ball is plainly visible elsewhere in the same frame
and was not chosen.

This is structural, not bad luck. `MotionDiffDetector.detect`
(`domains/tennis/tracking/ball.py:33-77`) takes the highest-scoring 4-120 px
motion blob subject to one spatial rule, `if y >= upper_limit: continue` with
`upper_limit = height * 2/3`. On nyYk that cap is row 480, which **excludes the
entire near half of the court** (rows 480-619) while **including** the far
backdrop wall, the players' box, the crowd and the scoreboard. There is no
court-region gate, no plane gate and no ball-appearance gate. The detector is
pointed at the part of the frame that contains the horizon.

Two further amplifiers, both visible in the renders:

- A player's **head** is 6 ft off the ground plane. Even a "correct" detection
  of an off-plane object is projected by a ground-plane homography onto the
  point where the camera ray meets the grass, which runs away up-court and
  diverges as the ray flattens. The projection is wrong before any detection
  error is counted.
- In all 12 renders the far edge of the back-projected 78x36 rectangle sits on
  the **far service line**, not the far baseline. The solver has labelled the
  60 ft line as `far` (78 ft), so the length scale is off by ~78/60 = 1.3x and
  every `court_x` is inflated before the horizon effect is applied. Filed below.

---

## 5. Why 1e5 ft there and only ~200 ft here

The magnitude is set by one thing: whether the horizon is inside the frame. On
both clips I could re-run it is not. The vanishing row at the ball's column is
**-239.6** (median) on nyYk 720p and **-109.4** on 3x3 360p -- above the top of
the frame -- so no pixel can get near `w = 0`, and the worst court values are
184.7 and 200.8 ft. Wrong, but bounded.

On tennis_02-05 the values reach 1e5, and 34 to 70 rows per clip sit at
`x < -1000 ft`:

| clip | x < -1,000 | x > 1,000 | abs(x) > 10,000 |
|---|---:|---:|---:|
| tennis_02 | 60 | 119 | 21 |
| tennis_03 | 34 | 80 | 19 |
| tennis_04 | 64 | 101 | 11 |
| tennis_05 | 70 | 129 | 21 |

Large NEGATIVE x is only producible by an image point on the FAR side of the
vanishing line (`w` changes sign). So on those four broadcasts the horizon lies
inside the ball detector's 2/3-height search window -- a lower, flatter camera.
This is INFERRED from the sign flips, not measured, because the source videos
are gone (section 7).

A clean secondary association, mechanism not established: the share of ball rows
whose frame also carries a player pair collapses as the ball blows up.

| clip | abs(x) <= 84 | 84-500 | 500-5,000 | > 5,000 |
|---|---:|---:|---:|---:|
| tennis_02 | 18.9% | 0.8% | 0.0% | 0.0% |
| tennis_03 | 34.6% | 13.9% | 0.0% | 0.0% |
| tennis_04 | 64.6% | 20.3% | 0.0% | 3.2% |
| tennis_05 | 29.9% | 2.3% | 0.0% | 0.0% |

Across all four clips **1 of 727** rows with `|x| > 500` shares a frame with a
player pair. The blow-up frames are frames where `detect_players` emitted no
complete pair. Why the two co-occur is NOT established here.

---

## 6. The harness does not catch any of this

`scripts/platformkit/tracking_harness.py:169`:

```python
ball_valid = float(df[df["cls"] == "ball"]["frame"].nunique() / n_frames)
```

`ball_valid_pct` is a **presence** metric. It counts frames that have a ball row
and never looks at the coordinate. tennis_03 scores `ball_valid_pct` 0.7754
against a `ball_valid_min` of 0.20 and that gate PASSES, while only 61% of the
same coordinates are inside 0-78 ft and 19 of them exceed 10,000 ft. G38 was
right that the jump and oob gates filter to `cls == "player"`; the ball gate that
does exist measures the wrong thing. Nothing downstream is wrong today because
no consumer reads ball coordinates, but the name asserts a validity that is not
measured.

---

## NOT VERIFIED

- **No image-space measurement or render exists for tennis_02-05.** Their source
  videos have been deleted from the pod; only `logs/dl_tennis_0*.log` and
  450-frame 960x540 overlay demos remain. Every image-space number and all 12
  renders come from two SIBLING clips (`tennis_nyYk2nPZAwY_720p`,
  `tennis_3x3eEWCZmWQ`) run through the same current adapter. The premise clips
  contribute the magnitudes, the angle signature and the sign-flip counts only.
- The two sibling clips were tracked by the CURRENT master code; tennis_02-05
  were tracked 2026-09-01 and their CSVs carry the older 5-column schema with no
  `calibration_provenance`. Code drift between the two is not ruled out.
- "The horizon lies inside the frame on tennis_02-05" is INFERRED from the
  `x < -1000` counts. Not measured.
- The 12-render tally is evenly spaced over the offending set, but that set for
  this run is concentrated in frames 5501-5902 (103 of 103 offending rows). It is
  not a sample across the whole clip, and it is one clip and one camera.
- The 1/x-linear-in-frame test across each blow-up peak on the premise clips gave
  median R^2 of only 0.33 / 0.33 / 0.45 / 0.71. That test is weak and is NOT part
  of the verdict; the verdict rests on the 0.9654 / 0.8853 correlations measured
  with real image coordinates.
- Per-clip frame rate was not read. Stride was inferred from the median frame gap
  (6, 6, 3, 3), same caveat G38 carries.
- Whether the far-service-line mislabel (section 4) occurs on tennis_02-05 was not
  measured; it was read off renders of one clip.
- `TrackNetV3Detector` exists in `ball.py` but is not wired into the adapter.
  Whether it would avoid this was not tested.
- `MotionDiffDetector` is called only on evaluated frames that produced a
  homography, so its frame difference spans a variable and sometimes large source
  gap. Suspected to worsen blob selection; NOT measured.
- No fix was designed and none is proposed here. No threshold, detection
  parameter or bar was changed. Nothing was deployed to the pod.

## NEW GAPS (ids to be allocated by the orchestrator)

- `NEW GAP:` `MotionDiffDetector`'s `y < 2/3 * height` window excludes the near
  half of the court and includes the crowd, backdrop and scoreboard; no court,
  plane or appearance gate exists -- 0 of 12 renders detect the ball.
- `NEW GAP:` `ball_rows` projects an off-plane object through a ground-plane
  homography with no plane-membership check and no bound.
- `NEW GAP:` the court solver labels the far SERVICE line as the far baseline in
  all 12 nyYk renders, putting a ~1.3x error into the court length scale.
- `NEW GAP:` `tracking_harness.py:169` `ball_valid_pct` measures ball-row
  presence, not validity; tennis_03 passes it at 0.7754 with 39% of its ball
  coordinates off the court.
- `NEW GAP:` G38 section 5's "players in the SAME frames stay within 82.93 ft" is
  not supported; blow-up frames carry no player rows at all on 3 of 4 clips.
