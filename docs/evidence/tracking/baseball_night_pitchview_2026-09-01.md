# Baseball night pitch-view probe (G11)

Date: 2026-09-01.

## What changed

`domains/baseball/tracking/pitch_view_gate.py` adds an opt-in `hue_geometry`
mode. The default `dominant_green` mode retains the existing central crop and
HSV green threshold. Nothing imports the new module, so the adapter,
segmenter, geometry gate, and existing thresholds retain their behavior.

The candidate ignores HSV value for grass/dirt colour tests and requires an
upper wide dirt band plus lower dirt evidence. Sampled day/night grass
hue/saturation medians were 40/114 and 43/74, while existing green fraction
fell from 0.461 to 0.005.

## Pod measurement

Read-only `nohup setsid nice -n 15` jobs sampled 400 evenly spaced targets per
clip. Two targets per clip were not decodable, leaving 398 samples. The daemon
and source videos were not changed.

| clip | old accepted | old fraction | new accepted | new fraction |
|---|---:|---:|---:|---:|
| mlb_2iosUkpL0Bc (day) | 302/398 | 75.9 pct | 313/398 | 78.6 pct |
| mlb_3Oc4S_1np98 (night) | 16/398 | 4.0 pct | 156/398 | 39.2 pct |

Annotated baseline and selected both-mode frames are under
`baseball_night_pitchview_2026-09-01/`; JSON files retain per-frame values.

## Visual review and honest verdict

Representative new night accepts show the center-field pitcher/batter view;
one also shows a wide third-base-side field view. Representative rejects are
player close-ups. The full requested 12-accept and 12-reject per-clip manual
tally was not completed, so no precision claim is made. This is an opt-in
candidate, not a validated replacement for the production gate.

## Verification

`python -m pytest domains/baseball/tracking/test_pitch_view_gate.py -q`

Result: `2 passed in 0.53s`.

Not verified: labelled-corpus precision/recall, integration with mound/infield
geometry, other night parks, or downstream tracking effects.
