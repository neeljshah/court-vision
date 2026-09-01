# Football IMAGE_PX_DECLARED snap detection -- build and first real measurement

**Date:** 2026-09-01. **Lane:** T4-FOOTBALL.
**Funded by:** `docs/research/organization-sprint/FOOTBALL_POST_OCR_DECISION_2026-09-01.md`
Step 1 ("BUILD NOW: motion-energy / snap detection on the preserved corpus").
Numeral OCR stays terminally rejected; nothing here reads, scales or registers.

## Verdict

The module is built, tested and measured. On real broadcast football it does
not work.

**Hand-verified precision: 3/20 = 15.0%** on a seeded uniform sample of
detections drawn from two independent games. Thirteen of the twenty sampled
detections did not land on live football at all -- they landed on sideline
close-ups, studio shots and the broadcast's own graphic bumpers. Conditional on
landing on live play, snap precision was 3/7.

The mechanism the memo named is not the mechanism this footage rewards.
Whole-frame motion energy on a broadcast feed measures **the camera**, not the
play, and at `IMAGE_PX_DECLARED` football has no working field-view test to
tell a wide formation shot from a sideline close-up -- that test is exactly
what the dead registration path would have provided.

This is a partial application of the memo's KILL rule. The memo's *primary*
gate is recall (>= 70% of hand-marked snaps within +/- 0.5 s) plus a shuffled
null control. **Recall was NOT measured on real footage** -- see
"What is not verified". No threshold was moved after seeing a result.

## What was built

| Artifact | Path |
|---|---|
| Module | `scripts/platformkit/tracking/football_snap.py` (206 LOC) |
| Test | `scripts/platformkit/tracking/test_football_snap.py` (5 tests) |
| Snap events, game A | `docs/evidence/tracking/football_imagepx_snap/gameA_alabama_georgia_snaps.json` |
| Snap events, game B | `docs/evidence/tracking/football_imagepx_snap/gameB_20pezoC5jRQ_snaps.json` |
| Row-schema sample | `docs/evidence/tracking/football_imagepx_snap/schema_sample_head30.csv` |
| Hand-verified frames | `docs/evidence/tracking/football_imagepx_snap/pair_{A,B}_{1..5}.jpg` |

Every emitted row declares `coordinate_space=image_px`, `observation=observed`,
`calibration=none` via the shared `scripts/platformkit/coordinate_provenance`
stamper. Two channels share the table: `cls=motion_energy` (one row per frame
pair, carrying the energy and the motion centroid in **source pixels**) and
`cls=snap` (one row per detected event, carrying `ts_s` and `confidence`).
`test_rows_declare_image_px_and_carry_both_channels` asserts these rows still
raise `CoordinateTransformUnavailable` from `normalize_tracking_frame`, i.e.
they remain unscorable as court geometry. No distance, scale or metric claim is
derived from them anywhere.

The full per-frame CSVs (2.9 MB each) were kept out of the repo; regenerate
with the commands below.

### Pre-registered constants (fixed before any measurement, never moved)

`PROC_WIDTH=320`, `BASELINE_FRAMES=90`, `QUIET_FRAMES=12`, `STEP_FRAMES=8`,
`STEP_RATIO=2.5`, `ENERGY_FLOOR=1.0`, `REFRACTORY_S=4.0`, `CUT_ENERGY=40.0`.
They are echoed into each `*_snaps.json` so any run is self-describing.

A snap fires when a sustained quiet run (12 frames, at or below the trailing
90-frame median) is followed by a sustained motion step (8 frames at >= 2.5x
the quiet level), with single-frame camera cuts rejected by `CUT_ENERGY` and a
4 s refractory period.

## Synthetic-clip proof

```
python -m pytest scripts/platformkit/tracking/test_football_snap.py -q -s
synthetic: 8 truth, 8 detected, recall 1.000, precision 1.000
null control: real 1.000 vs shuffled mean 0.217
5 passed in 1.56s
```

The synthetic clip is moving rectangles on a textured background where the
camera holds still pre-snap and pans with the play -- the pan is what moves the
whole-frame median, so a generator without it would test nothing. Ground truth
is the 8 constructed transition frames; tolerance is the memo's +/- 0.5 s.
The shuffled-timestamp null (200 trials, same detection count at uniformly
random times) scores 0.217 against the real 1.000, comfortably below the
memo's "below half" bar.

**Truncation invariance** is a property of the design, not a tuning result:
detection is causal with a fixed 8-frame lookahead, so the decision at frame i
reads only `energy[i-90 .. i+8]`. `test_truncation_invariance` cuts the energy
series in half and asserts every event with `frame + STEP_FRAMES < cut` comes
back with an identical frame index and confidence. A whole-clip percentile
threshold would have been simpler and would not have this property.

`test_energy_matches_the_adapter_statistic` pins the reported energy to
`domains.football.tracking.adapter.FootballAdapter.motion_magnitude`, so this
module reports the same statistic the adapter already computed rather than a
second, silently different one.

## Corpus premise check -- most of the football corpus is not football

Before measuring, every locally reachable `football_*` clip was rendered and
inspected. **Four of six are volleyball**, mislabelled by ingest:

| File | Actual content |
|---|---|
| `data/footage_quarantine/football_fsrQPwTpaSQ.mp4` | volleyball (UC San Diego / California, ACCN) |
| `data/footage_quarantine/football_WHjFQ5Nca20.mp4` | volleyball (Butler / Clemson, ACCN) |
| `data/videos/bridge/football_BN5zn5hu1zU.mp4` | volleyball (Kent State / Virginia Tech, ESPN) |
| `data/videos/bridge/football_mqQsnKyLXlY.mp4` | not verified; same ingest batch |
| `data/videos/reference/football.mp4` | **real** -- Alabama / Georgia, 2012 SEC Championship, CBS |
| `nba-track-a3/data/footage_corpus/football__football_20pezoC5jRQ_360p_source.mp4` | **real** -- Florida / Alabama, 1990s SEC Championship |

Both quarantine files carry `reason: static_non_sport_no_playing_surface` in
their sidecar JSON, which was correct about "not this sport" for the wrong
reason. This is the `adapter_corpus_mismatch_2026-09-01` landmine again. An
early run against `fsrQPwTpaSQ` was discarded when the frames were inspected;
its outputs were deleted rather than reported.

The `football__giants_jets_format96_1080p.mp4` control used by the Wave 6H OCR
gate is **not present locally** -- it was staged on the pod. The measurement
below therefore uses the two verified 640x360 / 29.97 fps broadcasts above,
which satisfy the memo's ">= 2 independent games" requirement but not at 1080p.

## Real-footage measurement

```
python -m scripts.platformkit.tracking.football_snap data/videos/reference/football.mp4 \
  --out-dir docs/evidence/tracking/football_imagepx_snap --tag gameA_alabama_georgia
python -m scripts.platformkit.tracking.football_snap \
  /c/Users/neelj/nba-track-a3/data/footage_corpus/football__football_20pezoC5jRQ_360p_source.mp4 \
  --out-dir docs/evidence/tracking/football_imagepx_snap --tag gameB_20pezoC5jRQ

gameA_alabama_georgia: 28770 frames, 83 snaps
gameB_20pezoC5jRQ: 28771 frames, 83 snaps
```

Sampling was **ungated**: every consecutive frame of each full 16-minute clip
was processed, with no motion, field-view or quality precondition. Commercials,
replays, studio segments and huddles are all in the denominator.

Detection density is the first warning sign. The median inter-snap gap is 7.9 s
(game A) and 8.0 s (game B). A real football play cycle is roughly 30-40 s, so
the detector is firing about four times too often before anything is inspected.
Median detection confidence is 0.00 in both games -- most detections barely
clear the 2.5x ratio.

### Hand verification

Ten detections per game were drawn by a **seeded uniform sample over the whole
detection list** (`numpy.default_rng(17)`), never by confidence rank; picking
the most confident detections would be the gated-sampling error this program
has already found repeatedly. Each was rendered as a three-panel montage at
t-0.6 s / t / t+0.7 s and read frame by frame.

| # | Game | frame | t (s) | conf | What the frames actually show | Snap within +/-0.5 s |
|---|---|---:|---:|---:|---|---|
| A1 | A | 897 | 29.93 | 1.00 | sideline players walking, cut to helmet close-up | no |
| A2 | A | 2313 | 77.18 | 1.00 | sideline milling, cut to close-up | no |
| A3 | A | 4073 | 135.90 | 0.00 | QB close-up adjusting helmet | no |
| A4 | A | 4974 | 165.97 | 0.00 | bench close-up | no |
| A5 | A | 9266 | 309.18 | 0.00 | live run play, already under way at t-0.6 s | no (mid-play) |
| A6 | A | 11074 | 369.50 | 0.60 | QB talking with officials | no |
| A7 | A | 14493 | 483.58 | 0.40 | sideline, cut to QB close-up | no |
| A8 | A | 17515 | 584.42 | 0.20 | SEC Championship graphic bumper | no |
| A9 | A | 19264 | 642.78 | 0.20 | same graphic bumper, cut to field | no |
| **A10** | A | 21074 | 703.17 | 0.00 | offence set (2nd & 7) -> line engaged -> play under way | **yes** |
| B1 | B | 884 | 29.50 | 0.05 | sideline close-up | no |
| B2 | B | 4038 | 134.73 | 0.80 | wide shot cut to standing-player close-up | no |
| B3 | B | 5323 | 177.61 | 0.00 | live pass play, already under way at t-0.6 s | no (mid-play) |
| B4 | B | 7119 | 237.54 | 0.00 | sideline reporter to camera | no |
| B5 | B | 9793 | 326.76 | 0.20 | player close-up with a stats graphic | no |
| B6 | B | 11428 | 381.31 | 0.13 | live pass play, QB already dropped back | no (mid-play) |
| B7 | B | 15426 | 514.71 | 0.00 | tackle already in progress | no (mid-play) |
| **B8** | B | 20775 | 693.19 | 0.00 | offence set at the 40 -> line engaged -> play under way | **yes** (borderline) |
| B9 | B | 22570 | 753.09 | 0.00 | player close-up | no |
| **B10** | B | 23487 | 783.68 | 0.00 | offence set -> line fires off, QB drops, receivers release | **yes** |

**Precision, game A: 1/10 = 10%. Game B: 2/10 = 20%. Combined: 3/20 = 15.0%.**

B8 is marked borderline: at t-0.6 s the line is set and at t the pile has
already formed, so the true snap is somewhere inside that 0.6 s window and may
sit just outside the +/- 0.5 s tolerance. It is counted as a hit, which makes
15.0% the *optimistic* reading.

### Decomposition of the failures

- **13/20 did not land on live football.** Sideline close-ups (6), graphic
  bumpers (2), studio/reporter (1), player close-ups with graphics (2), officials
  (1), bench (1). Every one of these is a **camera cut**: the shot before is
  quiet, the shot after is different, and whole-frame motion energy cannot tell
  a cut-into-a-close-up from a snap. `CUT_ENERGY=40.0` catches the single-frame
  spike of a hard cut but not a dissolve, a graphic wipe, or a cut whose two
  shots happen to have similar brightness.
- **4/20 landed on live play but late**, mid-play rather than at the snap.
  Once the camera is panning with a ball carrier the energy stays high, and the
  quiet-then-step rule can re-arm on a lull inside the play.
- **3/20 were genuine snaps.** All three are wide, static, pre-snap formation
  shots -- exactly the frames the detector was designed for.

Conditional on the detection landing on live football at all, precision is
3/7 = 43%. The mechanism has some signal; it has no way to get itself pointed
at the right shots.

## What is NOT verified

- **Recall on real footage was not measured.** The memo's primary gate ("`>= 70%`
  of hand-marked snaps detected within +/- 0.5 s", n >= 30 hand-marked snaps
  across >= 2 games) requires hand-marking snap ground truth by scanning the
  clips independently of the detector's output. That pass was not done, so the
  memo's KILL rule is only partially exercised. **The 15.0% figure is precision
  and must never be reported as the memo's gate.**
- **The shuffled null control was not run on real footage** -- it needs the same
  ground truth. It was run on the synthetic clip only (0.217 vs 1.000).
- **No confusion between "snap" and "any abrupt play-start"** was checked;
  kickoffs, punts and extra points were not distinguished from scrimmage snaps.
- The two measured games are 640x360. The 1080p Wave 6H control is not locally
  reachable, so no resolution-sensitivity claim is made either way.
- `data/videos/bridge/football_mqQsnKyLXlY.mp4` was not visually verified; it is
  excluded, not cleared.
- Per-frame player count (memo Step 2, the free byproduct) was **not** emitted.
  It needs the detector shim, and with the snap channel failing there was no
  reason to spend a detector pass on a QA-only diagnostic.

## Recommendation

Do not tune `STEP_RATIO`, `CUT_ENERGY` or the window lengths and re-run. The
memo pre-registered that response as the banned move, and the failure mode is
not a threshold miss -- it is that 13 of 20 detections were never looking at
football. The honest reading is that **whole-frame motion energy alone is not
a snap detector on a broadcast feed**, and the missing ingredient is a field-view
test that football does not have at `IMAGE_PX_DECLARED`.

Two things would be legal follow-ups, both out of this lane's scope and neither
started here:

1. A shot-boundary / shot-type classifier (wide field view vs. close-up) is
   `image_region`-legal and needs no scale. It is the piece the calibrated
   basketball and soccer adapters get for free from a solved homography. Note
   that this is a **precondition on the input**, not a gate on the metric's own
   bound, so it is not the banned tautology -- but it is new code with its own
   gate, not a tweak to this one.
2. Recall + null control on hand-marked ground truth, to close the memo's
   primary gate properly rather than leaving it half-measured.

Until one of those lands, football stays a preserved `image_px` corpus with no
validated signal, which is where the decision memo already put it.

## Sources

- `docs/research/organization-sprint/FOOTBALL_POST_OCR_DECISION_2026-09-01.md`
- `scripts/platformkit/teacher_feature_gate.py` (`IMAGE_PX_DECLARED`,
  `unlocked_families` -> `("image_region",)`)
- `scripts/platformkit/coordinate_provenance.py` (the declaration stamper)
- `scripts/platformkit/test_tracking_schema_coordinate_space.py` (the contract
  that makes `image_px` rows unscorable)
- `domains/football/tracking/adapter.py:54` (`motion_magnitude`, reused here)
- Memories: `adapter_corpus_mismatch_2026_09_01`,
  `tautological_gates_2026_09_01`, `impossibility_claims_selection_bias_2026_09_01`
