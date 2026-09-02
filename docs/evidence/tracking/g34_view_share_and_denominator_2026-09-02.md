# G34: the rally denominator, and a contradiction between the stated rail and the harness

Date: 2026-09-02. Gap: G34. Two measurements, one hand-labelled and one from
code. No threshold moved, no gate touched, no module changed.

**Two findings.**
1. Rally view is **41.7 pct** of a tennis broadcast (300 hand labels, Wilson 95
   pct CI 0.362-0.473). That is the true ceiling on decoded-frame coverage,
   because the camera lock cannot solve a crowd shot.
2. **The harness does not use a decoded-frame denominator.** `coverage`, `oob`,
   `ball_valid` and `det_per_frame` are all divided by
   `n_frames = df["frame"].nunique()` -- frames that produced at least one row.
   Frames where the tracker emitted nothing are excluded from the denominator by
   construction. On four tennis clips this inflates coverage by **2.5x to 4.9x**.

## 1. Rally share (hand-labelled census)

Clip `tennis__tennis_09.mp4`, 7,501 frames at 25 fps. Seeded, evenly spaced
census of 300 frames at 1 frame per second across the entire clip, rendered as
12 labelled contact sheets and classified by eye. RALLY is defined as the
standard elevated wide camera with both baselines visible -- the only view the
camera lock can solve. Everything else (close-up, crowd, graphic, replay angle,
low net-level camera, changeover) is NON-RALLY.

| sheet | frames | rally |
|---|---|---:|
| 00 | 1-25 | 4 |
| 01 | 26-50 | 9 |
| 02 | 51-75 | 14 |
| 03 | 76-100 | 7 |
| 04 | 101-125 | 1 |
| 05 | 126-150 | 21 |
| 06 | 151-175 | 0 |
| 07 | 176-200 | 13 |
| 08 | 201-225 | 13 |
| 09 | 226-250 | 14 |
| 10 | 251-275 | 4 |
| 11 | 276-300 | 25 |
| **total** | **300** | **125** |

**Rally share = 125/300 = 0.4167, Wilson 95 pct CI [0.362, 0.473].**

Rally is heavily clustered, not uniform: sheet 06 has zero rally frames and
sheet 11 has all 25. Any future sampling that is not evenly spaced across the
whole clip will therefore be badly biased, which is precisely what contract A3
and B7 warn about.

**What this bounds.** No whole-clip decoded-frame coverage above ~0.42 is
reachable on this broadcast, so the frozen 0.90 coverage bar is unreachable on
decoded frames by a factor of more than two. That is a property of broadcast
tennis, not a defect in the solver, and it must be stated whenever a coverage
number is quoted.

## 2. The denominator contradiction

`scripts/platformkit/tracking_harness.py:146` sets

```
n_frames = int(df["frame"].nunique())
```

and lines 163-169 divide coverage, `det_per_frame` and `ball_valid` by it. The
string "decoded" does not appear anywhere in the file. So the denominator is
"frames that produced at least one row", not frames decoded and not frames
processed.

The program's stated rail, repeated in the register header, the research plan,
`docs/TRACKING.md` and every session prompt, is **"denominators = decoded
frames"**. The implementation does not do that.

Measured over the four tennis tables whose row counts match the daemon census
exactly. Stride is 3 on every clip, so "processable" is the frame span divided
by 3 -- the frames the adapter actually had the opportunity to emit for:

| clip | frames in table | processable at stride 3 | table share | coverage as harness reports | coverage on processable frames | inflation |
|---|---:|---:|---:|---:|---:|---:|
| tennis_02 | 1,951 | 9,560 | 0.204 | **0.1512** | 0.0309 | **4.90x** |
| tennis_03 | 3,392 | 9,398 | 0.361 | **0.4393** | 0.1585 | **2.77x** |
| tennis_04 | 3,789 | 9,582 | 0.395 | **0.5999** | 0.2372 | **2.53x** |
| tennis_05 | 2,905 | 7,953 | 0.365 | **0.3284** | 0.1200 | **2.74x** |

The left-hand coverage column reproduces the daemon census verdicts exactly
(0.15, 0.44, 0.60, 0.33), which confirms the probe is computing the same
quantity the harness does.

**Why this matters even though it changes no verdict.** Every one of these
clips already fails, and correcting the denominator makes the numbers worse, not
better, so no PASS has ever been manufactured by it. The problem is that it is
the B1 pattern: a metric computed after excluding the cases that would fail it.
The frames with no detections are exactly the hardest frames -- crowd shots,
close-ups, graphics -- and they are dropped from the denominator rather than
counted as uncovered.

## 3. The check this forces on the flagship tennis result

The G05/G18 result -- sequential 300-frame ranges at **0.897 coverage, harness
PASS** -- was computed by this same frozen harness, therefore on this same
denominator. If those ranges also emitted rows for only a third of their frames,
their decoded-frame coverage would be materially lower than 0.897 and the
headline would need restating.

**This is NOT a finding. It is a required check and it has not been run.** The
experiment is exact and cheap: for each of the 15 sequential ranges, report
`frames_in_table` against the 300 frames in the range. If the ratio is near 1.0
the 0.897 stands as measured and only the whole-clip numbers were inflated. If
it is near 0.36, as it is on whole clips, the flagship number needs a correction
notice. Nothing should be claimed either way until that is measured.

## 4. What I did not do, deliberately

I did not change the harness. `tracking_harness.py` is a shared module under the
token, denominators are a stated rail, and changing a denominator silently
rewrites the meaning of every historical number in `RESULTS_LEDGER.md`. This is
filed as **G40** for adjudication, with the recommendation that the fix is
ADDITIVE -- emit `coverage_processable` alongside the existing `coverage`, keep
both in the manifest, and never overwrite the old field.

## NOT VERIFIED

- The rally share is one clip, one tournament, one broadcaster. It is not a
  per-sport constant and must not be reused for basketball or soccer, which is
  what the remaining two thirds of G34 were meant to measure.
- Labelling was done by one observer with no second pass and no blind re-label,
  so there is no inter-rater agreement figure. Borderline cases (low net-level
  camera during a live point) were called NON-RALLY on the ground that the lock
  cannot solve them, which is a judgement, not a measurement.
- `tennis_09`'s tracking table was overwritten by a re-track after the pod
  restart, so the 0.417 rally share is NOT paired with a coverage number from
  the same run. The denominator table uses tennis_02 to tennis_05, whose source
  videos are no longer in the corpus.
- "Processable" assumes the stride-3 sampling seen in the tables was uniform
  across the whole clip. It was inferred as the minimum inter-frame step, not
  read from the adapter config.
- The sequential-range check in section 3 has not been run.
