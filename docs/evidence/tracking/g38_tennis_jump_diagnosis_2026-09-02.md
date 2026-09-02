# G38: what tennis `jump_p95` is actually measuring

Date: 2026-09-02. Gap: G38 (allocated by the end-to-end census earlier today).
Read-only analysis of four pod tracking tables. No code changed, no threshold
moved, nothing re-tracked.

**Verdict: `jump_p95` is a real defect in player SELECTION, not a metric
artifact and not a smoothing problem.** The dominant signature is the per-half
player slot switching between candidates 10 to 29 ft apart, three frames apart,
which is physically impossible motion.

## 1. Reproduction of the harness number (contract A2)

The probe recomputes `jump_p95` the way `tracking_harness.py:172-173` does
(players only, consecutive rows per `track_id` sorted by frame):

| clip | harness jump_p95 | probe jump_p95 | bar |
|---|---:|---:|---:|
| tennis_03 | 34.36 | **34.36** | 8.00 |
| tennis_05 | 36.79 | 36.75 | 8.00 |
| tennis_02 | 22.13 | 21.67 | 8.00 |
| tennis_04 | 10.03 | **10.03** | 8.00 |

Two reproduce exactly; two differ in the third significant figure, consistent
with quantile interpolation. The metric is being measured correctly.

## 2. Two hypotheses raised and FALSIFIED

**(a) Ball contamination -- FALSIFIED.** Track `99` is the ball
(`cls == "ball"`, 2,630 rows in tennis_03) and its projected coordinates are
catastrophically wrong: **max x = 106,853 ft** against a court length of 78 ft,
with individual transitions of 126,001 ft and 760,419 ft. That is a
projection blow-up, almost certainly a near-singular homography mapping a point
close to the horizon toward infinity. But it does **not** contaminate the gates:
`tracking_harness.py:161` computes coverage, oob and jump on
`df[df["cls"] == "player"]` only. Every player x stays inside 82.93 ft. The
harness is correct here. (The broken ball projection is a separate real finding
and is filed below.)

**(b) A re-appearance artifact -- FALSIFIED as the dominant cause.** The
harness diffs consecutive ROWS, not consecutive frames, and no track ever has
adjacent-frame rows: the sampling stride is 3, and the maximum frame gap runs to
1,122-7,806 frames. A track that vanishes for minutes and returns elsewhere
therefore registers a large "jump" that is not motion. That is real, but it is
secondary:

| clip | big jumps (>8 ft) | stride-adjacent (gap = 3) | after a gap |
|---|---:|---:|---:|
| tennis_03 | 508 | **332 (65.4 pct)** | 176 |
| tennis_05 | 370 | **238 (64.3 pct)** | 132 |
| tennis_04 | 254 | **144 (56.7 pct)** | 110 |
| tennis_02 | 46 | 14 (30.4 pct) | 32 |

On three of four clips the majority of oversized jumps happen between
**consecutive sampled frames three apart**, where no gap explanation exists.

## 3. What it actually is

Distance bands of the >8 ft jumps, tennis_03 (tennis_05 and tennis_04 have the
same shape):

| band (ft) | 0-9 | 10-19 | 20-29 | 30-39 | 40-49 | 50-59 | 60-69 | 70-79 | 80-89 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| count | 43 | **188** | **102** | 80 | 35 | 30 | 22 | 7 | 1 |

The mass sits at **10-29 ft**, not at the court length. Full end-swaps (the
60-95 ft band) are only **5.9 / 7.6 / 7.1 pct** on tennis_03 / 05 / 04, though
they reach 21.7 pct on tennis_02, and `jump_max` is 77-86 ft on every clip,
which is the length of a tennis court -- so end-swaps happen, they are just not
the story.

The story is the 10-29 ft band. At stride 3 and 30 fps that is 0.1 s, so a 10 to
29 ft displacement implies 100-290 ft/s. A world-class sprinter reaches about
39 ft/s, so roughly 4 ft in 0.1 s. **These displacements are one to two orders
of magnitude beyond human motion**, which rules out real movement, motion blur
and smoothing, and leaves association: the slot is being filled by a different
person or a different detection between one sampled frame and the next.

The structural fact that makes this possible: every clip has **exactly two
player tracks with exactly equal row counts** (tennis_03 1,490/1,490,
tennis_05 954/954, tennis_02 295/295, tennis_04 2,273/2,273). The adapter emits
precisely one player per half per sampled frame. There is no multi-track
association to get wrong -- there is a per-half *choice*, and it is unstable.

## 4. Relationship to G26 -- consistent, NOT proven

G26 measured that `detect_players` picks courtside non-players (staff, ball
kids, chair umpire) as the per-half player, which is the same class of defect.
This analysis is consistent with that and does not establish it. Testing whether
either endpoint of a big jump falls outside the generous G26 rectangle
(x in [-6, 84], y in [-4, 40] ft) accounts for only **4.9 / 7.6 / 13.0 / 8.7
pct** of the big jumps. That is weak evidence against a shared cause, but it is
not decisive, because ball kids at the baseline and line judges stand *inside*
that rectangle and would be counted as on-court by this test.

**The G26 attempt-2 limit measurement is the experiment that settles it.** It
dumps every candidate foot point with a render-attributed real/not-real label,
which is exactly the labelling needed to ask whether the 10-29 ft partners are
non-players. G38 should not be fixed before G26 attempt 2 reports.

## 5. New finding filed separately: the ball projection is broken

The ball's projected court coordinates reach 106,853 ft (transitions of 126,001
and 760,419 ft) in all four clips, while players in the same frames stay within
82.93 ft. The harness does not score it, so nothing downstream is currently
wrong because of it, but any future ball-derived teacher feature (rally tempo,
serve speed, contact-frame detection) would be built on numbers that are
physically impossible. Filed as **G39**.

## NOT VERIFIED

- No renders were viewed for this row. It is a numerical diagnosis over four
  tables and it names a cause by elimination, not by eye. The render-and-look
  belongs to the fix pass, and the acceptance rule for any G38 fix must require
  it.
- The four clips are the ones whose row counts match the census lines exactly;
  tennis_01, 07, 08 and 09 were re-tracked after the pod restart and their
  tables no longer correspond to the census verdicts, so they are excluded.
- Frame rate is assumed to be 30 fps in the ft/s arithmetic. It was not read per
  clip, and G27/G28 record that nyYk 360p and 720p differ 2x in frame index for
  the same duration, so a per-clip fps check belongs in the fix pass.
- Whether the unstable per-half choice is a non-player, a duplicate detection of
  the same player, or a partially-occluded second detection is NOT established
  here.
- The ball projection blow-up is reported, not diagnosed. No homography
  condition number was computed.
