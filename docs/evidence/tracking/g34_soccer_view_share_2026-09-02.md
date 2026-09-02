# G34 (soccer half): wide-pitch view share, hand-labelled census

Date: 2026-09-02. Gap: G34, soccer half. Companion to
`g34_view_share_and_denominator_2026-09-02.md` (tennis half, rally share
41.7 pct, 125/300, Wilson 95 pct CI [0.362, 0.473]). Same method, applied to
one soccer broadcast. No CLIP, no model, no new dependency -- the hand labels
are the measurement. No threshold moved, no gate touched, no module changed.

## Why this matters

The research plan row S2 says the wide-pitch view share bounds every later
soccer calibration number, the same way the rally share bounds tennis. Soccer
is currently at rung S0 with no verdict. The broadcast camera holds only
10-16 of 22 players even during a wide shot, so knowing what fraction of the
broadcast is even a wide shot is a precondition for any honest soccer
calibration claim -- a homography solver cannot begin to work on a close-up,
replay, or dugout shot.

## Method

Clip `soccer__soccer_AgspyOj5BPk.mp4` (Belgium vs USA, 2014 World Cup
broadcast), 28,805 frames at 30 fps, on the pod at
`/workspace/nba-ai-system/data/footage_corpus/`. Built with the existing
`/tmp/g34_census.py` on the pod (unchanged from the tennis run): one ffmpeg
`select` pass samples every `total_frames // 300 = 96`th frame across the
*entire* clip, scales to width 320, and montages 25 tiles per sheet in a
5-wide grid with the frame index burned into each tile. Launched as

```
nohup setsid nice -n 10 python /tmp/g34_census.py soccer__soccer_AgspyOj5BPk.mp4 300 > /tmp/g34_soccer.log 2>&1 &
```

giving 300 sampled frames across 12 contact sheets (`sheet_00.jpg` ...
`sheet_11.jpg`) plus `census.json`. Sampling is a fixed arithmetic sequence
(step 96, starting at frame 0) with no RNG -- reproducible from `total_frames`
and `N` alone, so there is no seed to record beyond that formula. Full index
list is in `census.json` (`indices: [0, 96, 192, ..., 28704]`).

Sheets were scp'd to local scratch and every one of the 300 tiles was viewed
with the Read tool and classified as exactly one of:

- **WIDE** -- the main elevated broadcast camera showing a large span of
  pitch with visible line markings (touchlines, box lines, halfway line,
  center circle), i.e. the view a homography solver has something to work
  with. This includes the camera's normal zoom-in during open play, as long
  as a large span of pitch and multiple line features remain visible -- it
  does NOT require both penalty boxes in frame.
- **NON-WIDE** -- close-up on 1-3 players, a replay/graphic, crowd shot,
  dugout/coach shot, corner-kick or set-piece tight shot, or any shot where
  pitch line markings are mostly absent or reduced to a sliver.

## Per-sheet tally

| sheet | frame positions | sample indices | wide |
|---|---|---|---:|
| 00 | 1-25   | 0-2304     | 17 |
| 01 | 26-50  | 2400-4704  | 15 |
| 02 | 51-75  | 4800-7104  | 12 |
| 03 | 76-100 | 7200-9504  | 15 |
| 04 | 101-125| 9600-11904 | 13 |
| 05 | 126-150| 12000-14304| 19 |
| 06 | 151-175| 14400-16704| 16 |
| 07 | 176-200| 16800-19104| 17 |
| 08 | 201-225| 19200-21504| 22 |
| 09 | 226-250| 21600-23904| 16 |
| 10 | 251-275| 24000-26304| 14 |
| 11 | 276-300| 26400-28704| 19 |
| **total** | **300** | | **195** |

## Result

**Wide-pitch share = 195/300 = 0.6500, Wilson 95 pct CI [0.594, 0.702].**

Non-wide (105/300, 0.35) breaks down mostly as close-ups following individual
players (dribbles, tackles, throw-ins), set-piece tight shots near a goal
mouth, and dugout/coach reaction shots, with a smaller share of graphics and
crowd cutaways. Unlike the tennis clip, wide share here is not sharply
clustered by sheet -- it ranges 12-22 out of 25 across all 12 sheets (48 pct
to 88 pct locally), so there is no single multi-second stretch of the clip
that is entirely non-wide the way tennis sheet 06 was entirely non-rally.

## What this bounds

No whole-clip decoded-frame coverage above ~0.65-0.70 is reachable on this
broadcast under any tracker, because roughly a third of frames are views a
homography solver cannot begin to work on. This is the soccer analogue of the
tennis 0.417 ceiling, and it sits above the tennis number -- soccer's main
camera holds a usable wide shot noticeably more of the time than tennis's does.
It bounds:

- Any future soccer `coverage` or `oob` metric computed on this harness,
  by the same G34-tennis logic that a decoded-frame denominator cannot exceed
  the wide share regardless of tracker quality.
- The S2 research-plan row directly: the wide share is now a measured number
  (0.65, CI [0.594, 0.702]) rather than an assumed one, and S0 soccer work can
  cite it instead of guessing.
- It does **not** bound player-count coverage. A WIDE frame here is judged
  purely on camera framing and line visibility, not on whether all 22 players
  (or even both teams) are inside the frame -- the broadcast camera holding
  only 10-16 of 22 players (stated in the G34 soccer task brief) is a
  *separate* ceiling that still applies on top of this one, inside the wide
  35-70 pct.

## NOT VERIFIED

- One clip, one broadcaster, one tournament (2014 World Cup TV coverage).
  This is not a per-sport constant; other soccer broadcasts (different
  leagues, broadcasters, or eras) may frame the pitch differently and are not
  covered by this number.
- Labelling was done by one observer, one pass, no blind re-label, so there
  is no inter-rater agreement figure. Borderline cases (moderate zoom during
  open play that still shows most of the pitch width) were called WIDE on the
  judgement that a solver has enough line features to work with -- that
  judgement was not independently checked.
- A WIDE frame is not automatically a calibratable one. This label only means
  "the standard elevated broadcast camera, large span of pitch, lines
  visible" -- it does not verify that a homography solver actually converges
  on any of these 195 frames, does not check line occlusion by players, and
  does not check camera motion blur. That is a separate measurement.
- The WIDE/NON-WIDE line is fuzzier than tennis's RALLY/NON-RALLY line, which
  had a bright-line rule (both baselines visible). Soccer's main camera pans
  and zooms continuously during play, so several frames near the boundary
  (moderate zoom on 2-3 players with a large span of pitch still visible
  behind them) were judged case by case rather than against a fixed rule.
