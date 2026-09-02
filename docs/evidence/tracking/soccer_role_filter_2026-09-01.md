# Soccer role filter -- 2026-09-01

## Scope

This is a producer-only experiment for future soccer packets. It does not
alter the detector, S1 preregistration, tracking harness, sealed labels, or
the n=100 S1 AMBIGUOUS verdict. That verdict was determined from the manual
count and remains in force.

`scripts/platformkit/soccer_s1_adjudication_packet.py` and
`soccer_s1_ext_packet.py` both call `SoccerAdapter().detector`; the adapter
loads the soccer box detector through `scripts.platformkit.detection.shim`.
The new filter is intentionally downstream and image-space only.

## Method

`scripts/platformkit/tracking/soccer_role_filter.py` takes the frame and raw
person boxes and labels each valid box `player` or `non_player`, recording its
decisive cue. The ordered cues are:

1. HSV green pitch mask (hue and saturation, no value threshold): a bottom
   contact point outside the pitch or in its boundary band is non-player.
2. Torso mean color clustering for the two most populated team clusters:
   a distant third-cluster color is a jersey outlier.
3. Local box-height median at a comparable image row: unusually small or
   large boxes are size outliers.

The measurement ran one detector process over all 100 stored JPEGs, then
applied the filter. The before statistic uses the sealed/published raw count;
the after statistic uses the fresh detector run plus the filter.

## Measurement

| subset | n | manual - old raw | manual - filtered player boxes | 14-line flips |
|---|---:|---:|---:|---:|
| Pooled | 100 | -1.230 | 2.260 | 28 |
| soccer_AgspyOj5BPk | 34 | -1.794 | 2.147 | 7 |
| soccer_DdnvC6-PGYY | 33 | -0.545 | 2.758 | 7 |
| soccer_kSgNjoaqCpI_1080p | 33 | -1.333 | 1.879 | 14 |

The after value overshoots in the opposite direction. This first fixed-rule
filter removes real players, particularly third-kit/goalkeeper colors,
edge/touchline players, and crowded distant players. It is not acceptable as
a validated count producer yet.

The fresh raw detector run differed from the sealed old raw count in 27/100
frames. Therefore this is not a clean isolated A/B on bit-identical detector
output; the published before statistic is retained exactly, but any apparent
filter effect is confounded by detector/runtime reproducibility and must not
be read as a performance claim.

## Render-and-look tally

Twelve deterministic renders (four per clip) are in
`soccer_role_filter_2026-09-01/`, with green player and red non-player boxes:
S1_0001, S1_0012, S1_0047, S1_0058, S1_0013, S1_0024, S1_0068, S1_0079,
S1_0025, S1_0036, S1_0089, S1_0100.

Hand tally: 21 disagreements among 163 displayed detector boxes (142/163,
87.1 percent role agreement). This is a visual sanity check, not an
independent blinded accuracy study. Most disagreements are real players
rejected by the jersey or pitch-foot cue; some cropped staff were retained.

## Result

The module and its synthetic cue tests exist for future iteration, but this
parameterization is a measured reject for packet-count use. No S1 labels were
changed or re-adjudicated, no harness value moved, and no stage decision is
licensed by this result. It also does not verify stable detector reproducibility,
role accuracy on a held-out corpus, identity tracking, or calibration.

## G17b -- minimal two-cue revision

### Pre-measure design

This revision was fixed before its measurement. It keeps only two independent
image-space cues, and a box is `non_player` only if either fires:

1. Its foot point is off the largest connected HSV green pitch component, or
   lies in the excluded touchline band.
2. Its torso mean color is farther from both of the two most-populated team
   clusters than twice the larger team-cluster radius.

The local size prior is removed. No detector or harness threshold changed.
The detector input is the pinned JPEG path documented in
`soccer_detector_determinism_2026-09-01.md`.

### Measurement

| subset | n | baseline manual - sealed raw | manual - G17b player boxes | 14-line flips |
|---|---:|---:|---:|---:|
| Pooled | 100 | -1.230 | 0.900 | 11 |
| soccer_AgspyOj5BPk | 34 | -1.794 | 0.765 | 5 |
| soccer_DdnvC6-PGYY | 33 | -0.545 | 2.000 | 4 |
| soccer_kSgNjoaqCpI_1080p | 33 | -1.333 | -0.061 | 2 |

The pooled delta moves toward zero and has absolute value below 1.0. The old
sealed raw column is retained only as the stated -1.23 baseline; it differs
from the deterministic packet-JPEG raw output in 27/100 rows and was not
rewritten.

### Twelve-frame render tally

Viewed renders: S1_0001, S1_0012, S1_0047, S1_0058, S1_0013, S1_0024,
S1_0068, S1_0079, S1_0025, S1_0036, S1_0089, S1_0100. There were 19 role
disagreements among 167 displayed detector boxes (11.4 percent). Cue-specific
disagreements: 11 foot/touchline false rejections, 2 strong-color false
rejections, and 6 all-cues-pass false retentions. This is a visible role tally,
not an independent blinded accuracy study.

### Verdict: NOT VALIDATED

Although the pooled count delta satisfies the numerical direction check, the
hand tally exceeds the required fewer-than-10-percent disagreement limit. The
failure mode is still boundary-foot false rejection of real players, with
additional retained referees/staff and duplicate/person boxes. G17b is not a
validated packet-count producer. The S1 AMBIGUOUS verdict is not re-adjudicated
by this experiment.
