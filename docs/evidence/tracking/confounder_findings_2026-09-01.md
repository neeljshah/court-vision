# Measurement confounders found 2026-09-01

Three defects were already known to corrupt this program's numbers (carried-over
calibration inflating coverage 150x, 640x360 ingest, and a corpus that is 50.9%
not-the-sport). A systematic hunt for MORE of that class found the following.
Each entry says plainly whether it was measured or inferred.

## CONFIRMED BY MY OWN CHECK -- the harness has no time base

`scripts/platformkit/tracking_harness.py` references `frame_rate` at lines 76,
89, 91, 96, 105, 131 and 193 -- every one of them RECORDS it into the report.
No gate ever uses it. `scripts/platformkit/liveness_metrics.py` contains zero
references to fps at all. Meanwhile `scripts/platformkit/adapter_run.py:65`
applies a fixed `{"max_frames": 30000, "stride": 3}` to every clip.

Corpus frame rates measured across retained clips: 25/1, 2997/100 (29.97),
30/1, 30000/1001, and 60000/1001 (59.94).

So the interval between two sampled frames is 0.120s at 25fps and 0.050s at
59.94fps -- a 2.4x difference -- while `jump_p95` is a per-step distance in feet
compared against a FIXED threshold (8.0 ft for tennis, 6.0 basketball, 10.0
baseball). A tracker of identical quality produces jump_p95 values that differ
by 2.4x purely from the source frame rate, and the gate does not adjust.
`median_step_distance`, `zero_step_share` and `stationary_track_share` share the
defect.

Consequence: per-step metrics are not comparable across clips, and are not
comparable across sports at all. Threshold tuning against them has been tuning
against a moving time base.

## MEASURED BY THE HUNT, NOT INDEPENDENTLY RE-RUN

- The permanently retained reference clips under `data/videos/reference/`, kept
  specifically so tracking can be re-measured, contain no baseball: `kbo.mp4` is
  a studio talk show in 8 of 8 sampled frames and `mlb.mp4` is a webcam podcast
  in 8 of 8. `npb.mp4` is real game footage but carries a StreamYard watermark.
  Any baseball before/after measured against those two measured a talk show.
- Up to 87% of decoded frames in some retained clips are byte-identical repeats
  (ffmpeg mpdecimate: kbo t=300 kept 117 of ~900). A perfect tracker on
  87%-duplicate frames produces 87% zero steps, which the liveness check reads
  as a frozen tracker. The recorded "held-position defect, zero-step 0.8658"
  should be re-examined against duplicate share before it is treated as a
  tracker property.
- American football broadcasts render on-field virtual graphics (first-down
  line, line of scrimmage, down-and-distance arrows). White text inside those
  graphics passes the football white-line mask (S<=100, V>=150 inside dilated
  grass), adding high-confidence false line segments on exactly the pre-snap
  frames the adapter keeps.

## REFUTED BY MEASUREMENT -- lowering the tennis bright threshold does not help

A comment in `domains/tennis/tracking/adapter.py` records that a far baseline
"is only ~172 grey and does not survive the 200 bright threshold", which implies
the mask threshold sits above its signal. Swept on 300 frames of controlled 720p
footage, counting frames that reach the five-cluster gate and frames whose cross
ratio is then valid:

    thresh    5clust      xratio_ok   1-2clust
    120     34 (0.113)    7 (0.023)   52 (0.173)
    140     23 (0.077)    4 (0.013)   14 (0.047)
    160     19 (0.063)    4 (0.013)   24 (0.080)
    172     29 (0.097)    3 (0.010)   33 (0.110)
    185     31 (0.103)    7 (0.023)   35 (0.117)
    200     44 (0.147)   10 (0.033)   32 (0.107)

The SHIPPED value of 200 is the best of the six. Lowering the threshold admits
noise faster than it admits court lines. Threshold tuning is not the tennis fix,
and the plausible-sounding inference from that comment is wrong.

Even at the best threshold only 3.3% of frames yield a valid cross ratio, which
points back at cluster SELECTION: the five clusters found are usually not the
five court lines.

## Soccer calibration: the learned path is blocked by WEIGHT LICENSING, not capability

Surveyed 2026-09-01 for a sellable product (ultralytics/AGPL is already being
removed from the serving path for the same reason):

| path | code licence | pretrained weights |
|---|---|---|
| TVCalib (MM4SPA/tvcalib) | MIT | `train_59.pt` has NO STATED WEIGHT LICENCE |
| SoccerNet baseline (SoccerNet/sn-calibration) | - | checkpoint has no stated terms |
| Sportlight (NikolasEnt/soccernet-calibration-sportlight) | - | no licensed inference checkpoint published |

Nothing was downloaded or vendored. An MIT SOURCE licence does not carry the
weights; those are a separate artifact and here they are unlicensed.

### S-STAGE CORRECTION

This is NOT an S4 impossibility proof and soccer must not be recorded as S4.
The distinction matters and the report itself states it correctly:

- BASEBALL's full-field homography is genuinely impossible on this corpus. It is
  a PHYSICAL measurement: broadcast centre-field FOV p50 is ~42 ft against a
  90 ft infield, and 0 of 24 sampled frames contained two bases. No algorithm
  can solve from a view that never holds two known points.
- SOCCER calibration is demonstrably POSSIBLE -- the SoccerNet camera
  calibration challenge exists and public models achieve it. What is blocked is
  our access to a LICENCE-CLEAN pretrained model, on the three paths surveyed.

A licensing blocker is a procurement problem, not a physics one, and it can be
removed by a licensed model or by labelling our own pilot set. Soccer therefore
stays at S0 with a fail-closed court path and a declared image_px corpus of
867,044 rows across 71,460 frame ids.

## The football QUEUE is contaminated at source, not just the staged corpus

Three independent samples now say the football lane is not football:

1. A corpus audit classified 12 football-labelled clips as college soccer or
   volleyball. I verified four by rendering frames: women's college soccer,
   Marymount vs California soccer, KANSAS vs PITT VOLLEYBALL on ESPN2, and
   Portland vs Wake Forest soccer.
2. The football agent independently found only 2 of 11 readable staged clips
   are genuine American football.
3. Fetching a fresh high-resolution clip straight from the FOOTBALL QUEUE
   (`football_lsYEcWf4Zbg`) produced "NFL PLAYERS: SECOND ACTS" -- three people
   in armchairs in a studio. It was discarded rather than uploaded.

Point 3 is the important one: the defect is in the QUEUE, not only in what was
downloaded earlier. `queue_expander` accepts an id on
`duration >= MIN_DURATION_SECONDS` alone and requests only id and duration, so a
long studio programme is indistinguishable from a game. The football queue needs
rebuilding from validated sources before any football measurement is meaningful.

Note also that the new `footage_content_gate` screens by playing-surface
fraction and therefore CANNOT separate soccer from American football -- both are
green fields. It would have caught the talk show but not the twelve mislane
clips. A sport-specific discriminator is still needed.
