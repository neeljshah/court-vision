# G286: What is at the footpoint?

## Verdict

ACCEPT, measurement only. The dominant point-level result is bare court or
floor: 40/79 = 0.506. This supports the box-geometry explanation for the
dominant outcome: the footpoint often lies below or beside the player on floor,
consistent with a box extending beyond the feet. A footpoint is not a box, so
this is an inference and not a box measurement.

A separate 29/79 = 0.367 are broadcast graphics or score tickers. Different
person is 7/79 = 0.089, so nearest-neighbour assignment is sometimes wrong,
but it is not dominant. Those seven are a finding about the matching method,
not the tracker; they were not re-paired or used to revise the 172 px value.
Located-body-not-feet is 3/79 = 0.038 and does not support a general
footpoint-convention reading.

Denominators: one non-deterministic detector draw produced 112 finite
detector-box footpoint observations in 15 frames of one shot from one clip.
The player-present classification population is 79/112. It has one nearest
sealed located-foot pairing per detector-box observation and one labeller.
It is not a population of authenticated players.

## Inputs and local execution

All work ran locally in C:\Users\neelj\nba-track-a5. No pod process, decode,
re-detection, re-location, source code, or domain code was touched.

The exact full path, byte size, and resolution of every input opened are in
docs/evidence/tracking/g286_what_is_at_the_footpoint_artifact/input_manifest.csv.
The 15 native 1920x1080 JPEG inputs are under
C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g278_census_stratified_followup_artifact\part_a\frames\
and are part_a_000.jpg (222374), part_a_004.jpg (211330), part_a_009.jpg
(238212), part_a_013.jpg (232732), part_a_017.jpg (235365), part_a_021.jpg
(189994), part_a_025.jpg (229527), part_a_030.jpg (193354), part_a_033.jpg
(180621), part_a_037.jpg (235294), part_a_042.jpg (232799), part_a_046.jpg
(204441), part_a_049.jpg (177028), part_a_054.jpg (218086), and
part_a_060.jpg (191776). Other inputs: located_feet.csv at
C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g285b_locate_then_match_recall_artifact\located_feet.csv
(5550 bytes, CSV), and g267_measurement.json at
C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g267_court_space_physical_plausibility_artifact\g267_measurement.json
(12446681 bytes, JSON).

## Set, crop, and blind protocol

All finite G267 footpoints in the 15 sealed frames total 112. G273's unchanged
512x640 native-pixel neighbourhood (+/-256 px horizontal, +/-320 px vertical)
contains a sealed located foot for 79/112 = 0.705, confirming the stipulated
79. The other 33/112 have no sealed located foot in that crop.

Every classified render is a G273-matching 512x640 full-source-resolution
crop centered on the footpoint, with G273 rounding and black padding. A red
cross plus red ring marks the detector footpoint at crop center; a yellow
diamond plus yellow ring marks the sealed located feet. Both are inside the
crop by construction. This is the fix for the scale fault that invalidated
G285: the blind judgement has both points visible in one crop. All 79 crops
are blind_renders/blind_001.jpg through blind_renders/blind_079.jpg under
docs/evidence/tracking/g286_what_is_at_the_footpoint_artifact/.

Random order used seed 28620260904. Before unblinding, the identity map was
committed only as SHA-256 d1fefa51cc3a5e37565c8ec29271362719f974cc1470b832926ccae0af8ef16e.
Blind order, verdicts, and directions were committed in
49b25efb11c7bc12d5b413a69f2f31d163f4ee31 before unblind_map.json,
classified_rows.csv, or counts existed.

## What lies under the detector marker

| Category | Count / 79 detector-box observations | Fraction |
| --- | ---: | ---: |
| Located player's feet | 0 | 0.000 |
| Located player's body, not feet | 3 | 0.038 |
| Bare court or floor | 40 | 0.506 |
| Different person than the located one | 7 | 0.089 |
| Something else | 29 | 0.367 |
| Cannot judge | 0 | 0.000 |

All 29 SOMETHING_ELSE labels are BROADCAST_GRAPHIC_OR_SCORE_TICKER. CANNOT_JUDGE
stays separate and was not merged. Classified rows, identity map, and summary
are classified_rows.csv, unblind_map.json, and measurement_summary.json in
the same artifact.

## Offset direction

Direction is from the sealed located feet to the detector footpoint, using the
larger absolute image-axis component; positive image y is below.

| Direction | Count / 79 | Fraction |
| --- | ---: | ---: |
| Above | 12 | 0.152 |
| Below | 37 | 0.468 |
| Left | 19 | 0.241 |
| Right | 11 | 0.139 |

Below is largest and vertical directions total 49/79. This corroborates the
earlier per-frame median +147 px downward signal; it does not replace that
arithmetic summary.

## Limits and not verified

- One shot, one clip, 15 frames, one labeller, one detector draw. Per G278
  the span is friendlier than the clip (0.836 versus 0.656, p = 0.0078), so
  this is not clip-wide.
- Located feet are human estimates. A located-feet label would test the
  estimate as much as the detector; its count here is zero.
- A high different-person count would be a finding about matching method, not
  tracker. The seven observations are reported that way.
- Not verified: replication beyond this clip or draw; a particular box extent;
  source of overlay observations; authenticated-player assignment; causal
  source of the 172 px error; any filter, threshold, gate, retrain, or change.

## Verifier-contract self-check

This follows docs/evidence/tracking/VERIFIER_CONTRACT.md. B1: the 112-to-79
exclusion is named and retained as 33 no-player observations. B2-B6: additive
evidence and a new local harness only; no schema reader, gate, deployment,
move, or retirement changed. B7: all 79 decision crops are retained. B8: no
fit or residual is claimed. B9: each unit is a distinct (source_frame,
marker_index) finite detector-box observation. B10: no threshold or bar moved;
G273 crop geometry is unchanged. This is not an S-row. Focused test:
python -m pytest scripts/platformkit/tracking/test_g286_what_is_at_footpoint.py -q
passed: 1 passed.
