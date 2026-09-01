# Soccer S1 EXTENSION labeling protocol (verbatim from the sealed S1 packet)

Source: docs/evidence/tracking/soccer_s1_blind_verdict_2026-09-01.md, blinding
protocol step 2. Copied verbatim; nothing about the counting rule changed for
the n=100 extension.

Counting rule: distinct human players (outfield + goalkeepers, partial bodies
at the frame edge included when identifiable); referees, assistants, fourth
official, coaches, ball kids, photographers excluded.

Label from the frame JPEGs in `frames/`; use the matching image in `crops_2x/`
(a 2x cubic upscale of the same frame, no new information) only to resolve a
dense cluster. Do not open `detector_counts_separate_ext.csv` until every row
below is filled in and committed.

Columns (same as the original `blind_label_template.csv`):
frame_id,clip,manual_player_count
