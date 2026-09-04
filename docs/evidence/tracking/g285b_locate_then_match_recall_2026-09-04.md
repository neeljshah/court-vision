# G285b - locate-then-match detector-footpoint recall

## Verdict

**ACCEPT (measurement only).** The primary radius was fixed at 50 source pixels before matching. At that radius, 7 of 143 located visible on-court player-foot observations matched at least one G270-on-court G267 footpoint: **7 / 143 = 0.0490**, Wilson 95 percent interval **[0.0239, 0.0976]**. The 143 denominator is located visible-player observations, not authenticated players. The separate 88-footpoint denominator is G270-on-court detector-box observations from one non-deterministic G267 draw. This is one clip, one shot, 15 frames, and one labeller.

Pass A locating is the eye measurement: raw, marker-free tiles were used to find every visibly on-court player and record a source-pixel foot estimate. Pass B is arithmetic only: after Pass A was committed, the local script calculated Euclidean distances to frozen detector footpoints. No human judged whether a particular footpoint was on a person.

## Precommitted Pass A

Pass A is sealed in commit `6b4b3e410e50368193cd08e1c86fcfa6cf1fce8b`, before this memo's matching artifacts and before G267 was opened in this lane. The complete marker-blind protocol and coordinate ledger are `docs/evidence/tracking/g285b_locate_then_match_recall_artifact/pass_a_protocol.md` and `docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv`.

The selection is 15 evenly spaced frames from G284's 54 `COUNTED` rows, not a head slice: sort numeric `source_frame` and use inclusive indices `round_half_away_from_zero(i * 53 / 14)` for `i = 0..14`. The source-frame sequence is 19630, 19879, 20190, 20440, 20689, 20938, 21187, 21499, 21686, 21935, 22247, 22496, 22683, 22994, and 23368.

Each 1920x1080 raw JPEG was located in a 3 columns by 2 rows native-resolution tile grid. The 640x540 core cells extend 80 pixels across each internal edge, giving x ranges [0,720), [560,1360), [1200,1920), y ranges [0,620) and [460,1080), and 160-pixel overlaps. A seam player is visible in both tiles but logged once using the unique half-open 640x540 core cell containing the foot. That protects against both loss and double count.

The sealed Pass A protocol declares 50 pixels as the primary radius before any detector record was loaded. It also fixes the 25, 50, and 100 pixel sensitivity radii and the rule: a located player is matched if any same-frame G270-on-court footpoint is within radius; a footpoint is unmatched if it is farther than radius from every located foot. There is no one-to-one assignment and no post-result radius choice.

## Arithmetic result

| Radius (source px) | Matched located players / located visible-player observations | Recall, Wilson 95 percent | Footpoints matching no located player / G270-on-court footpoint observations |
| ---: | ---: | --- | ---: |
| 25 | 3 / 143 | 0.0210 [0.0072, 0.0599] | 85 / 88 = 0.9659 |
| 50 (primary) | 7 / 143 | 0.0490 [0.0239, 0.0976] | 81 / 88 = 0.9205 |
| 100 | 17 / 143 | 0.1189 [0.0756, 0.1821] | 71 / 88 = 0.8068 |

The player denominator is the 143 source-pixel locations, one per visibly located on-court player in the 15 frames. The separate footpoint denominator is the 88 retained G270-on-court G267 detector-box observations. The committed `player_matches.csv` and `footpoint_matches.csv` retain every nearest-neighbour distance and fixed-radius Boolean, so all cells are reproducible. No distance is visually judged.

## G284 sealed-count cross-check

G284's sealed counts total 150 visible on-court player slots in these 15 frames; the marker-blind Pass A locating ledger totals 143. The difference is 7 / 150 = 0.0467. It occurs in six frames: 20440 (8 versus 10), 21187 (9 versus 10), 21499 (8 versus 10), 22496 (9 versus 10), and 23368 (9 versus 10); the other ten frames agree at 10. This is a count-reproducibility finding, including difficult wide and graphic-obscured views, not permission to change either denominator. Recall above deliberately uses the 143 located-foot observations specified for this reissue; 150 sealed G284 slots remain a separate cross-check denominator.

## Required comparisons

Against G284: primary 0.0490 locate-then-match recall is below G284's 0.416 assumption-dependent upper bound, so this direct measurement does not break G284's bound and remains consistent with detection being the dominant defect on this span.

Against G285: primary 0.0490 is materially above G285's rejected 0.0076 (its 95 percent lower endpoint is 0.0239), so this 15-frame result is not near 0.0076 and does not say G285 was right; it is nevertheless low at every preregistered radius.

## Inputs, route, and reproduction

Everything ran locally. No source video was decoded, no detector was rerun, and no pod, `src/`, or `domains/` path was changed.

- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g278_census_stratified_followup_artifact\part_a\frames\`: 61 JPEGs, 12,012,411 bytes total, each 1920x1080. Pass A opened only the 15 selected raw JPEGs named above.
- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g284_detector_recall_bound_artifact\per_frame_join.csv`: 4,228 bytes, SHA-256 `d615f87636adb6941c7fdd2b65be7d28c2479a8a50bdf95e4cbe5db2a8d3ef6c`. Fields used are `COUNTED`, `source_frame`, `frame_file`, and sealed `players_visible_on_court`.
- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g267_court_space_physical_plausibility_artifact\g267_measurement.json`: 12,446,681 bytes, SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`. It was opened after the Pass A commit. The unchanged G270 inclusive rectangle is `0 <= court_x_ft <= 50` and `0 <= court_y_ft <= 94`.
- Pass A protocol: 2,980 bytes, SHA-256 `e2d3133388bb0f14954977b00b7e52c800a65967f0c53c069e129068e4a7c934`. Pass A coordinates: 5,550 bytes, SHA-256 `25d94a8478313e44861d3556d4bb71e7725e15ff82809da24798af352556e76b`.
- Local route: `C:\Users\neelj\nba-track-a5\scripts\platformkit\tracking\g285b_locate_then_match.py`, 188 lines, SHA-256 `7a6d19a943800639a99e305d2e089592c9c0de07c309b56e6cce563d5cc9dddf`.

```text
python scripts/platformkit/tracking/g285b_locate_then_match.py --located-feet docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --per-frame-join docs/evidence/tracking/g284_detector_recall_bound_artifact/per_frame_join.csv --g267 docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json --player-output docs/evidence/tracking/g285b_locate_then_match_recall_artifact/player_matches.csv --footpoint-output docs/evidence/tracking/g285b_locate_then_match_recall_artifact/footpoint_matches.csv --per-frame-output docs/evidence/tracking/g285b_locate_then_match_recall_artifact/per_frame_results.csv --summary-output docs/evidence/tracking/g285b_locate_then_match_recall_artifact/summary.json
python -m pytest scripts/platformkit/tracking/test_g285b_locate_then_match.py -q -p no:cacheprovider
3 passed
```

## Verifier-contract self-check

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. A7: all cited inputs and all four result artifacts exist in this commit. A9: each opened input has a full path, byte size, and image resolution above. B1/B9: no located player or G270-on-court footpoint is filtered after matching; denominators are separately named. B2-B6: additive evidence, local script, and focused test only; no production schema, lifecycle, deploy, or module move. B7: the 15 selection points span all 54 G284 judgeable frames. B8: no fit or residual is presented as independent. B10: radii were committed before detector records were opened. Q does not apply to this tracking measurement.

## Limits and NOT VERIFIED

- This is 15 frames of one shot of one clip and one labeller, not a clip-wide, arena-wide, sport-wide, or stable-draw claim. G278 measured the span as friendlier than the parent clip (0.836 against 0.656, p = 0.0078).
- Occluded players remain invisible to labeller and detector alike, so the visible-player denominator remains inflated relative to true recall.
- A footpoint is not a box. The source-pixel foot is a human estimate, so each fixed radius absorbs locating and detector-footpoint error; sensitivity is not a tuning opportunity.
- The population is detector-box observations, not authenticated players. Identity, true precision, inter-labeller agreement, a second detector draw, causal explanation, and any filter, threshold, gate, retrain, or production intervention are not verified or proposed.
