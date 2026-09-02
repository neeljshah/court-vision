# G44: how often is the tennis ball even visible and reachable on this footage

Date: 2026-09-02. Gap: G44 (limit measurement, not a fix). Read-only hand census
of one tennis clip on the pod. No code changed, no threshold moved, nothing
re-tracked. Builds on the MEASURED premise in
`docs/evidence/tracking/g39_ball_projection_diagnosis_2026-09-02.md`: on this
footage `MotionDiffDetector`'s only spatial rule (`y < 2/3*height`) admits the
backdrop/crowd/scoreboard and excludes the entire near half of the court, and
12/12 sampled renders of its actual output were not the ball.

**VERDICT: the ceiling is low and it is structural, not an algorithm problem.**
On the sampled rally footage the ball is visible to the eye in **64% (32/50)**
of true rally frames. Of those visible sightings, only about **half (16/31
classified)** fall inside the region `y < 2/3*height` even looks at -- the
other half sit in the near-court band the detector never scans, and that band
is exactly where sustained baseline rallies keep the ball. Combined ceiling on
ball recall for any detector confined to the current spatial window: **roughly
33% of rally frames**, before subtracting the false-positive confusion with
players/crowd/scoreboard established in G39. The ball itself is not
sub-pixel -- measured at 6-8px diameter near the net -- so this is a coverage
limit, not a resolution limit.

---

## 1. Clip and sample definition (contract A2, B7)

Clip: `data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4` (1280x720,
50 fps, **48,001** frames per `ffprobe -count_frames`). Chosen because it is
the same clip G39's renders and row-480 window measurements were made on, so
this measurement composes directly with that evidence.

**Step 1 -- find rally windows.** A coarse evenly-spaced census (N=60,
step=800, whole 48,001-frame clip, `/tmp/g34_census.py`) located the general
region of play. A finer evenly-spaced scan (step=40, `/tmp/g44_zoom.py`) over
frames 5200-8160 identified two rally windows by eye (wide-court view, both
players rallying, excluding crowd/graphics/close-up-reaction shots):

- Window A: frames **[5560, 5960)** -- one point, serve through point end.
- Window B: frames **[6480, 8000)** -- next point: serve + net exchange
  (broadcast cuts to a low net-level camera for this part) into a long
  baseline rally, ending with ball-kids clearing balls and a player-reaction
  cutaway.

Pool length = 400 + 1520 = **1,920 frames**.

**Step 2 -- seeded evenly-spaced sample, n=64.** `seed = 44`. `stride =
pool_len / n = 1920/64 = 30`. `offset = seed % stride = 44 % 30 = 14`.
Indices = `offset + i*stride` for `i in 0..63`, mapped back into the two
windows. Frame indices sampled (all 64, ascending):

```
5574 5604 5634 5664 5694 5724 5754 5784 5814 5844 5874 5904 5934
6484 6514 6544 6574 6604 6634 6664 6694 6724 6754 6784 6814 6844
6874 6904 6934 6964 6994 7024 7054 7084 7114 7144 7174 7204 7234
7264 7294 7324 7354 7384 7414 7444 7474 7504 7534 7564 7594 7624
7654 7684 7714 7744 7774 7804 7834 7864 7894 7924 7954 7984
```

All 64 were decoded at full 1280x720 resolution in one `ffmpeg select`
pass (`/tmp/g44_extract.py`) -- not a re-encode, not a head/tail slice.

## 2. Hand labeling method (contract B7 -- renders, not detector output)

An automated yellow-blob color scan was tried first as a spotting aid
(`/tmp/g44_ballcand.py`) but it systematically over-triggered on tan/khaki
court texture, wooden umpire-chair trim, and a fixed yellow sponsor graphic
that recurred at the same pixel coordinates across dozens of unrelated
frames -- none of which are the ball. It was **not trusted as ground truth**.
Every one of the 64 frames was instead hand-reviewed by eye with the Read
tool at a reliable zoom (full 1280x720 court band, upscaled 1.3x,
`/tmp/g44_fullverify.py`), cross-checked against the automated candidate crops
where they agreed, and a subset re-checked against the full frame a second
time (`/tmp/g44_verify.py`) after the first pass under-counted -- three of six
spot-rechecked "not visible" calls turned out to have a visible ball that the
first pass missed at that zoom level, so the fuller re-check is the version
reported below.

## 3. Rally-frame denominator (contract B1/B7 -- n >= 30)

Of the 64 sampled frames, **14 were not actually live rally** despite falling
inside the nominal window (ball kids retrieving balls between points, or a
player-reaction close-up after the point ended): frame indices 5904, 5934,
6934, 6964, 6994, 7024, 7744, 7804, 7834, 7864, 7894, 7924, 7954, 7984. These
are excluded from the denominator, honestly reflecting that "ball is only
meaningfully present during play." **n = 50 confirmed live-rally frames.**

## 4. Visible-ball fraction

| | count | of 50 rally frames |
|---|---:|---:|
| Ball visible somewhere in frame | 32 | **64%** |
| Ball not visible / not identifiable | 18 | 36% |

The 18 "not visible" frames are not uniformly distributed -- they cluster in
two patterns: (a) recovery/positioning moments between the serve and the next
shot, where the ball has already left the frame toward the other end, and (b)
frames right after a call ("OUT" graphic on screen) where the point is
effectively over but the camera hasn't cut away yet.

## 5. Ball pixel size (contract B7 -- several frames, not one)

Measured directly with a pixel-grid overlay (`/tmp/g44_measure.py`, 6x
nearest-neighbor upscale, 10px reference grid) on confirmed true-positive
sightings:

- **Near the net, standard wide broadcast camera** (frame 5604): ball spans
  roughly **6-8 px** in diameter. This is the relevant floor for the ordinary
  camera angle the detector runs on for most of the rally.
- **Low net-level camera cutaway** (frames 6604-6784, used by the broadcast
  for serve-and-net exchanges): ball spans roughly **15-30 px**, because the
  camera itself is physically closer to the court at those moments, not
  because the ball is closer in the rally sense. Broadcast camera choice, not
  court position, dominates apparent ball size in this footage.
- Far-baseline sightings (the smallest expected case) were not successfully
  isolated for a clean pixel measurement in this pass -- see NOT VERIFIED.

6-8 px is small but is not below a defensible detectability floor -- it is
larger than typical color-noise/JPEG-block artifacts at this bitrate, so the
limit established below is a coverage limit (the detector isn't looking in
the right place), not a resolution limit (the ball can't be seen at all).

## 6. Fraction inside the current detector window

`MotionDiffDetector`'s rule (`domains/tennis/tracking/ball.py`) is
`if y >= height*2/3: continue`, i.e. on this 720-row clip only pixels with
`y < 480` are ever considered. Each of the 32 visible-ball sightings was
checked against a `y=480` reference line drawn on the actual frame
(`/tmp/g44_line.py`) -- not inferred from geometry, read directly off the
pixel row the ball occupies.

| | count | of 31 classified |
|---|---:|---:|
| Inside window (`y < 480`, detector can see it) | 16 | **52%** |
| Outside window (`y >= 480`, structurally excluded) | 15 | 48% |
| Not classified (1 sighting, line-check not done) | 1 | -- |

This ~50/50 split is not random: the **excluded** sightings are concentrated
in one specific, important game phase. Nine consecutive sampled frames from a
single sustained baseline rally (indices 7054-7294) were **all** ball-visible
and **all** excluded (ball row 500-620, near-player's end of the court) --
exactly the kind of extended rally exchange that a "rally tempo" feature would
need. The **included** sightings cluster around serves, volleys, and
overheads near the net, a smaller share of total rally time in a baseline-
heavy point.

## 7. LIMIT statement

Combined ceiling on ball recall for any detector confined to the current
`y < 2/3*height` window, on this footage, at this resolution:

**0.64 (visible) x ~0.52 (inside window, given visible) ~= 0.33** -- at most
about a third of true rally frames could ever contribute a correct ball
detection, even with a hypothetically perfect classifier that never confused
the ball with a player, the crowd, or the scoreboard inside that window. The
G39 finding (0/12 real renders were the ball) shows the actual detector is far
below even that ceiling today, because within the visible window it is also
losing the discrimination problem against far-player heads/rackets and
backdrop clutter.

The near-court exclusion is a hard, position-independent wall: rows 480-619
(per G39's measured near baseline at row ~619) are **never** evaluated
regardless of ball size, contrast, or algorithm quality, and that band is
where the ball spends much of a baseline rally on this camera angle. Ball
pixel size itself (6-8px near the net on the standard camera) is not the
binding constraint -- the spatial gate is.

**This bounds every ball-derived feature** (rally tempo, serve speed,
contact-frame anchoring) on this footage to well under 33% frame coverage
before any detection-quality improvement, and to 0% during the disproportionate
fraction of rally time the ball spends behind that gate on the near side of
the court.

## NOT VERIFIED

- Only one clip (`tennis_nyYk2nPZAwY_720p`) and ~33 seconds of one match were
  sampled. tennis_06-10, `tennis_459iho5_AFs`, and `3x3eEWCZmWQ` (all
  confirmed present on the pod) were not examined -- camera distance and
  broadcast style differ per source and could shift both fractions measured
  here.
- The non-`_720p` source (`tennis__tennis_nyYk2nPZAwY.mp4`), possibly a
  higher native resolution, was not examined; ball pixel size at native
  resolution was not measured.
- Frame index 6904's window classification (inside/outside `y<480`) is
  counted as a visible sighting but was **not** confirmed against the
  `y=480` reference-line render; left out of the 31-frame window tally.
- Roughly a third of the visible/window calls were within a few pixels of
  ambiguous (faint single-digit-pixel dots, or right on the `y=480` line) --
  a stricter or looser call on those specific frames could move the 64% and
  52% figures by several points each without changing the overall
  conclusion.
- Rally-window boundaries (frames 5560-5960, 6480-8000) were set by eye from
  an evenly-spaced scan, not from frame-exact serve/point-end markers; the
  14-frame "not actually rally" correction in section 3 is the honesty check
  on that approximation, not a guarantee the remaining 50 are all equally
  "mid-point."
- Only the detector's static spatial gate (`y < 2/3*height`) and raw ball
  visibility were checked here. The motion-diff scoring step itself (which
  also has to beat other moving blobs for the same frame) was not
  independently evaluated and could lower real recall further even inside
  the 33% ceiling.
- A clean pixel-size measurement of the ball at the far baseline (the
  smallest expected case) was not obtained in this pass; the 6-8px figure is
  for a near-net sighting only.
