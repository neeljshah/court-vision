# Soccer S1 blind adjudication verdict -- 2026-09-01

**Verdict: INCONCLUSIVE (pre-registered branch (c) AMBIGUOUS).**
Manual pct>=14 = 0.5833 lands inside the 0.30-0.85 ambiguous band. Per the
prereg, the packet is NOT licensed either way: no impossibility packet (S6)
and no detector-repair route may be filed on this n. The prereg's own
remedy is to enlarge to n=100 frames before ANY filing.

## Pre-registration (verbatim source)

`docs/research/organization-sprint/TRACKING_RESEARCH_DIGEST_2026-09-01.md`
line 613 (agent 12, step S1 gate):

- n>=30 frames pooled across >=3 clips.
- (a) DETECTOR-BOUND if manual median >= 14 AND manual pct>=14 >= 0.85.
- (b) CAMERA-BOUND if manual median < 14 AND manual pct>=14 <= 0.30.
- (c) AMBIGUOUS if manual pct>=14 falls in 0.30-0.85, OR paired mean delta
  (manual minus detector) exceeds 3.0 in the camera-bound branch -> enlarge
  to n=100 before any filing; still ambiguous -> soccer stays S0.
- Nothing moves the 0.85 harness gate or the 14-player minimum.

## Blinding protocol (as executed)

1. Premise check: packet tracked on master at `e790ea219` (36 frames, 3 clips
   x 12, `scripts/platformkit/a1_artifacts/soccer_s1/`), sealed
   `detector_counts_separate.csv` present (37 lines, line count only),
   prereg present at the digest line above.
2. Labels written from the frame JPEGs only (plus 2x/3x crops of the same
   JPEGs for dense clusters), one row per frame, to
   `scripts/platformkit/a1_artifacts/soccer_s1/blind_labels_2026-09-01.csv`.
   Counting rule: distinct human players (outfield + goalkeepers, partial
   bodies at the frame edge included when identifiable); referees, assistants,
   fourth official, coaches, ball kids, photographers excluded.
3. Labels committed at `016b9aa58` BEFORE the sealed file was opened.
4. Sealed file first read in the join step after that commit (this memo's
   numbers are the first time its contents appeared in this session).

## Numbers (n = 36, 3 clips)

Source: join of `blind_labels_2026-09-01.csv` (manual) and
`detector_counts_separate.csv` (detector) on `frame_id`.

| scope | n | manual median | manual pct>=14 | detector median | detector pct>=14 | mean delta (manual - detector) |
|---|---|---|---|---|---|---|
| pooled | 36 | 14.0 | 0.5833 | 14.5 | 0.5833 | -0.72 (median -1.0) |
| soccer_AgspyOj5BPk (BEL-USA 720p) | 12 | 13.5 | 0.500 | 12.5 | 0.417 | -0.58 |
| soccer_DdnvC6-PGYY (KOR-GER 720p) | 12 | 12.5 | 0.417 | 13.5 | 0.500 | -0.17 |
| soccer_kSgNjoaqCpI_1080p (COL-JPN 1080p) | 12 | 15.0 | 0.833 | 17.5 | 0.833 | -1.42 |

Gate evaluation:
- (a) DETECTOR-BOUND requires manual median >= 14 (met: 14.0) AND manual
  pct>=14 >= 0.85 (NOT met: 0.5833). Fails.
- (b) CAMERA-BOUND requires manual median < 14 (NOT met: 14.0) AND manual
  pct>=14 <= 0.30 (NOT met: 0.5833). Fails.
- (c) AMBIGUOUS: manual pct>=14 = 0.5833 is inside 0.30-0.85. Holds.

Paired delta is -0.72 pooled (|delta| well under 3.0); the delta clause is
not triggered, and it only applies inside the camera-bound branch anyway.

## What the frames say (context, not a verdict)

The eye and the detector agree on the ceiling: both put exactly 21/36 frames
(0.5833) at >=14 players. The ambiguity is real framing variance, not a
producer defect: 6 of 36 in-play `is_pitch_view` frames are close-ups /
corner shots holding 1-4 players (S1_0002, S1_0004, S1_0014, S1_0023,
S1_0029, S1_0020), and the 720p clips sit near the 14-player line while the
1080p clip clears it 10/12.

Detector OVER-counts the human eye on 20/36 frames (negative delta) --
consistent with referees/staff/crowd-edge boxes being counted as players --
and UNDER-counts on 11/36. The one large miss is the very-high wide shot.

Frames where the detector exceeds the manual count (spurious boxes):
- S1_0014: manual 4, detector 9 (close-up with referee + physio; delta -5)
- S1_0024: manual 6, detector 11 (defensive third; referee + photographer; -5)
- S1_0034: manual 17, detector 22 (midfield; assistant + coach on touchline; -5)
- S1_0003: manual 15, detector 19 (midfield; referee; -4)
- S1_0025: manual 15, detector 19 (midfield; referee; -4)

Frames where the detector misses players (camera/small-object cases):
- S1_0018: manual 16, detector 5 (very wide high shot, players ~15 px; +11)
- S1_0011: manual 13, detector 10 (pan blur, stacked reds at right; +3)
- S1_0010: manual 14, detector 12 (midfield; +2)
- S1_0016: manual 20, detector 18 (free-kick wall occlusion; +2)
- S1_0032: manual 19, detector 17 (box cluster occlusion; +2)

## Caveat on the detector column

The packet builder (`scripts/platformkit/soccer_s1_adjudication_packet.py`,
`_valid_detection_count(detector(frame))`) records raw valid detector boxes
per frame, not the adapter's distinct `track_id` count named in the prereg
text. This comparison therefore isolates detector recall/precision from
tracker identity churn; the churn component is not measured here. It does
not change the verdict, which depends only on the manual column.

## Routing per prereg

- S6 impossibility packet: NOT licensed (branch (c)).
- Detector-repair route: NOT licensed (branch (c)).
- Required next step before any filing: enlarge the blind sample to n=100
  frames (same protocol, same sealed-first order). If still ambiguous, soccer
  stays at S0 this cycle.
- The 0.85 coverage gate and the 14-player minimum are unchanged.

No edge or dollar claim is made here; this is a coverage-ceiling
measurement only.
