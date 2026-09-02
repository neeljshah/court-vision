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

---

## 5. ADDENDUM, same day: the check in section 3 was run, and it is worse than expected

Section 3 called for reporting frames-in-table against the 300 frames per range
before the flagship number is quoted again. **No pod run was needed** -- the
committed plan JSONs in `tennis_sequential_plan_2026-09-01/` already carry both
denominators per range, as `solved_frame_coverage` (decoded) and
`harness_metrics.coverage_pct` (the harness denominator).

| match | range start | decoded | solved coverage | harness coverage_pct | verdict |
|---|---:|---:|---:|---:|---|
| tennis_09 | 615 | 300 | 0.7067 | **1.0** | FAIL (oob) |
| tennis_09 | 5070 | 300 | 1.0000 | **1.0** | FAIL (oob) |
| tennis_09 | 5775 | 300 | 0.5933 | **1.0** | FAIL (oob) |
| tennis_09 | 6960 | 300 | 1.0000 | **1.0** | PASS |
| tennis_09 | 7140 | 300 | 1.0000 | **1.0** | FAIL (oob) |
| tennis_10 | 150 | 300 | 0.3967 | **1.0** | FAIL (oob) |
| tennis_10 | 3585 | 300 | **0.4600** | **1.0** | **PASS** |
| tennis_10 | 3930 | 300 | 0.6767 | **1.0** | PASS |
| tennis_10 | 6345 | 300 | 0.8433 | **1.0** | PASS |
| tennis_10 | 6405 | 300 | 0.6533 | **1.0** | PASS |
| nyYk 720p | 5715 | 300 | 0.6100 | **1.0** | PASS |
| nyYk 720p | 33105 | 300 | 0.9900 | **1.0** | PASS |
| nyYk 720p | 33855 | 300 | 0.9967 | **1.0** | PASS |
| nyYk 720p | 41985 | 300 | 0.5733 | **1.0** | PASS |
| nyYk 720p | 43830 | 300 | 0.5600 | **1.0** | PASS |

`coverage_pct` is **exactly 1.0 on 15 of 15 ranges**. Honest decoded-frame solve
coverage over the same ranges runs 0.3967 to 1.0000, median 0.6767.

### Why it is 1.0, and why that is a tautology

`tracking_harness.py:37-38` sets tennis `min_players: 2` and
`coverage_min: 0.90`. Coverage is
`(frames where distinct player track ids >= 2) / (frames present in the table)`.

The tennis adapter emits **exactly one player per half on every frame it emits**
-- measured independently in the G38 work, where every clip has exactly two
player tracks with exactly equal row counts (1490/1490, 954/954, 295/295,
2273/2273). So every frame in the table has exactly 2 player ids, the numerator
equals the denominator, and **coverage is 1.0 by construction**.

**The tennis coverage gate cannot fail.** It is contract B1 (a metric computed
after excluding the rows that would fail it) and B9 (a degenerate denominator)
at the same time.

### What this corrects

Seven of the ten PASS ranges have decoded-frame solve coverage **below the 0.90
bar** -- 0.4600, 0.6767, 0.8433, 0.6533, 0.6100, 0.5733, 0.5600. `tennis_10`
range 3585 passes the harness at **46 pct** honest coverage. Had the 0.90 bar
been applied to the decoded-frame number, most of those passes would have
failed.

The G05 headline figure itself (`270/301 = 0.897` on range 15300-15600) is a
`solved_frame_coverage`, so **that number is honest** and is not restated here.
What is not honest is the PASS beside it: the coverage gate did not test it,
because for tennis that gate is 1.0 whatever the solver does. The claim "0.897
coverage, harness PASS" should be read as "0.897 solve coverage, and the harness
passed it on oob, jump and ball_valid, with the coverage gate inert".

**The rung is unchanged and nothing here is a fabricated pass in the other
direction** -- these ranges genuinely produce `court_feet`, the lines-on-lines
render check was 12/12, and no threshold was moved. But the program has been
quoting a coverage PASS that carried no information, and the honest per-range
coverage numbers are materially lower than 0.90 on most passing ranges.

This is escalated into **G40**, which now covers both the denominator
contradiction and this tautology.

---

## 6. Is the tautology systemic? Audited across all 8 sports -- NO

The obvious follow-up to section 5 is whether other coverage gates are inert the
same way. Audited over every tracking table on the pod (174 clips, 8 sports) by
computing the distribution of distinct player ids per emitted frame and the
resulting harness coverage:

| sport | min_players | clips | emitted frames | harness coverage | tautological |
|---|---:|---:|---:|---:|---|
| **tennis** | 2 | 9 | 8,394 | **1.0000** | **YES** |
| npb | 2 | 23 | 166,171 | 0.7975 | no |
| kbo | 2 | 35 | 226,695 | 0.7820 | no |
| mlb | 2 | 34 | 214,914 | 0.6430 | no |
| wnba | 6 | 7 | 16,231 | 0.5146 | no |
| soccer | 14 | 24 | 117,156 | 0.3905 | no |
| ncaa_basketball | 6 | 4 | 3,300 | 0.3018 | no |
| football | 14 | 38 | 252,950 | 0.1884 | no |

Tennis has the histogram `{2: 8394}` -- **every emitted frame across all nine
clips has exactly two players, with no other value present.** Every other sport
shows a real spread (football, for instance, runs 1 player on 76,378 frames up
through 8+, against a bar of 14).

**Conclusion: the harness is not the problem, and the defect is not systemic.**
The gate logic is sound and discriminates properly on seven of eight sports. It
is the tennis adapter's fixed two-slot design -- always emit exactly one player
per half, never zero, never three -- that makes `min_players: 2` unsatisfiable
to fail. This narrows G40's tennis half from "fix the harness" to "either the
tennis adapter must be able to emit fewer than two players when it cannot find
them, or tennis coverage must be measured on solved frames rather than emitted
frames". The first is the honest fix and it is an adapter change, not a harness
change.

Note the interaction with G26 and G38: a two-slot adapter that must always fill
both slots is exactly the mechanism that forces a courtside non-player into a
slot when a real player is not detected. **The same design choice plausibly
causes the tautological coverage, the oob failures and the jump instability.**
That is a hypothesis, not a measurement, and G26 attempt 2 is the experiment
that tests it.

