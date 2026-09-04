# G285 - sealed per-person detector-footpoint recall

## Verdict

**ACCEPT (measurement only).** On G284's 54 sealed judgeable frames, **4 / 524 = 0.0076** of sealed visible on-court player slots had a G270-on-court G267 footpoint at their feet under the predeclared 25-pixel eye-judgement radius (95 percent Wilson interval **[0.0030, 0.0195]**). The denominator is **524 sealed visible player slots**, the marker denominator is **365 G270-on-court detector-box observations**, and the study is one clip, one shot, 54 frames, and one labeller. The population is detector-box observations, not authenticated players.

G284's 0.416 was an assumption-dependent upper bound, not recall. The directly measured 0.0076 is below 0.416, so **the G284 bound held**; it does not rescue its unverified precision-transfer assumption.

## Fixed policy and sealed order

The fixed policy was written in `g285_per_person_recall_artifact/judgement_protocol.md` before any marker render was reviewed. Each retained G270-on-court footpoint is a magenta filled circle, seven-pixel radius, with a one-pixel black outline. No box, label, crop boundary, or inferred geometry is drawn. A sealed player slot is `MATCHED` only when a marker centre is visually at that player's feet or within **25 source-image pixels**. The near-boundary band was fixed at approximately 20--30 pixels; **3 / 524** player verdicts are in that band. The radius was not tuned after review.

The review order is G284's ascending `blind_id` order, excluding only its seven already sealed `CANNOT_COUNT` rows. Each `player_slot` is a stable audit handle, assigned left-to-right by visibly judged feet (top-to-bottom breaks a tie); it is not a new count. `person_verdicts.csv` commits one explicit verdict for every one of the 524 sealed slots. `marker_verdicts.csv` separately commits one verdict for every one of the 365 rendered markers. More than one marker may land on the same player; that produces one matched player and multiple markers on a visible player, not a fabricated unmatched marker.

The protocol, frame order, marker manifest, 524 per-person verdicts, 365 per-marker verdicts, and all 54 renders were committed as `b665616f6bf7d38bc647f1a10dd78994bdcdcbdd` before `summary.json` was produced. The summary therefore cannot decide which player rows exist or change their individual verdicts after seeing an aggregate.

## Result

| Quantity | Numerator | Denominator | Value |
| --- | ---: | ---: | ---: |
| Per-person footpoint recall | 4 matched visible player slots | 524 sealed visible player slots | 0.0076, Wilson 95 percent [0.0030, 0.0195] |
| Unmatched visible player slots | 520 | 524 sealed visible player slots | 0.9924 |
| Markers on no visible player | 360 unmatched markers | 365 G270-on-court marker observations | 0.9863, Wilson 95 percent [0.9683, 0.9941] |
| Near-boundary per-person verdicts | 3 | 524 sealed visible player slots | 0.0057 |

The unmatched-marker rate **does not roughly agree** with G273's 15 / 72 = 0.208 `NOT A PERSON` rate: this local per-footpoint result is 360 / 365 = 0.9863. That large disagreement is a finding, not an error to reconcile away. G273 classified whether a person was visible in a fixed crop around an all-finite detector location; this row asks the stricter and differently conditioned question of whether a G270-on-court marker lies at a sealed player's feet. The difference is therefore not a precision estimate and does not overwrite either study.

## Inputs, render evidence, and reproduction

Inputs opened locally were:

- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g278_census_stratified_followup_artifact\part_a\frames\` - 61 JPEGs, 12,012,411 bytes total, each 1920x1080; 54 G284-sealed judgeable frames were rendered.
- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g284_detector_recall_bound_artifact\per_frame_join.csv` - 4,228 bytes, SHA-256 `d615f87636adb6941c7fdd2b65be7d28c2479a8a50bdf95e4cbe5db2a8d3ef6c`.
- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g267_court_space_physical_plausibility_artifact\g267_measurement.json` - 12,446,681 bytes, SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`.
- `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g273_detector_precision_blind_sample_2026-09-04.md` - 8,257 bytes, SHA-256 `41f0378e15f4bce082bee83b6a1fc30b9ab851dd4da4e1c80f607561ea3333de`, read only for its published 15 / 72 comparison.

Every required marker-only render is under `g285_per_person_recall_artifact/renders/` (54 JPEGs, 23,222,728 bytes total). The local route was `C:\Users\neelj\nba-track-a5\scripts\platformkit\tracking\g285_per_person_recall.py`, SHA-256 `09d0e8bd9894fbe3358b55ee91e5531d83e06535bcad76f8b3912c259c178b14`. It only reads committed images and records; it performs no decode, redetection, source-video write, or production change.

Reproduce the post-verdict calculation with:

```text
python scripts/platformkit/tracking/g285_per_person_recall.py summarize --per-frame-join docs/evidence/tracking/g284_detector_recall_bound_artifact/per_frame_join.csv --marker-manifest docs/evidence/tracking/g285_per_person_recall_artifact/marker_manifest.csv --person-verdicts docs/evidence/tracking/g285_per_person_recall_artifact/person_verdicts.csv --marker-verdicts docs/evidence/tracking/g285_per_person_recall_artifact/marker_verdicts.csv --summary-output docs/evidence/tracking/g285_per_person_recall_artifact/summary.json
```

Focused validation:

```text
python -m pytest scripts/platformkit/tracking/test_g285_per_person_recall.py -q -p no:cacheprovider
2 passed
```

## Verifier-contract self-check

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. A7: every cited source, verdict table, render, and summary exists in this commit. A9: the opened input paths, byte sizes, and frame resolution are named above. A11: the local route SHA-256 is recorded above. B1/B9: all 524 pre-sealed visible-player slots and all 365 G270-on-court marker observations are retained with named denominators; the seven nonjudgeable G284 rows were excluded before any marker review. B2--B6: additive evidence and local harness only; no production schema, lifecycle, deploy, or module move. B7: all 54 judgeable frames are rendered and judged, not a head slice. B8: no fit or residual. B10: the 25-pixel radius and 20--30-pixel boundary band were fixed before review and never moved. Q does not apply.

## Limits and NOT VERIFIED

- One clip, one shot, 54 frames, one labeller, and one non-deterministic G267 detector draw. This is not a clip-wide, arena-wide, sport-wide, or stable-draw result.
- The denominator remains visible players. Fully occluded players are invisible to labeller and detector alike, so this recall remains inflated relative to true recall.
- G278 measured this span as friendlier than the parent clip (0.836 against 0.656, p = 0.0078); do not quote this clip-wide.
- A footpoint is not a box. A marker on a person says a detection claimed that location, not that it bounded the person correctly.
- True detector precision, authenticated player identity, inter-labeller agreement, causal explanation, and any filter, threshold, retrain, or production intervention are not verified or proposed.
