VERDICT: PARTIAL (complete native re-audit: 1080p30_20 source/frame identity receipt UNKNOWN) + residual PASS within budget + reproduction DONE

# G413 native box re-audit

Prereg: docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/prereg.md
SEAL sha256 387cacc1e0b0084007b559318915d0aef109a1b76d1024ba92b5f819133381c4 (sealed alone at e9efe2a84; unchanged).

## Premise and handoff
- G406 reproduction: 60 sealed keys, 206 producer rows, 592 comparator boxes, 51 old pairs on 28 frames, and five producer-silent ticks.
- G412 receipt: master 5a0b84cba: docs/evidence/tracking/g412_box_frame_contract_2026-09-12/transforms.json (raw sha256 859b09571b73010c215b65d409cfb2a809d152384fb2580d26261b6eb2b26ed1; LF sha256 957ab0da4d1b14ae055a0e94157ef5cb60d470207e54b1809c65f4d805e86864).
- Complete native re-audit remains PARTIAL: 1080p30_20 has the one UNKNOWN PTS receipt (delta 0.033366 s).

## Method actually run
- CPU-only native decode and overlays; EMPTY model set; no inference, tuning, rematching, association, or draw changes.
- All 206 stored padded crop boxes were clipped before restoring native origin; historical residuals retain all 51 old pairs on 28 frames.
- visual_adjudication derives only from saved review.csv judgments; absent pair verdicts are UNKNOWN. The legacy wrong_object_matches field lists every sealed association, not an adjudication.

Fix 1b, 2026-09-12: absolute p50 is regenerated as the ordinary median; G412 uses the durable master receipt.
The per-association visual_adjudication state and counts are regenerated from the saved review only; associations, draw, and signed medians are unchanged.

## Results
- New association: 117/206 producer rows and 117/592 comparator boxes matched on 48/60 frames; 55/60 frames had producer boxes and five were silent.
- Pooled equal-frame weighted medians: dx -0.75 px, dy -0.375 px; fixed budget PASS.
- Absolute residuals: p50 5.6095 px, p90 24.0 px, max 100.5 px.
- visual_adjudication: correct_object 0/117, wrong_object 0/117, UNKNOWN 117/117.

## Table digests
5da978f7e0bfa6849d7caa070561f02f7c5de7b34cd0982e2706bd227e9c8f15 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/input_hashes.csv
485f9f8810c665a8bbab493688143f23e69b25315665af90f741e247b2275f24 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/source_receipts.csv
217020519d792a574cfd074bd44aa0a2cd947f4b2bb2d6e6905de0c9caef788e docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/draw.csv
6775884b8357fa3c78d7e8879deedfb25160909b4b82e703154d43f82e38c287 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/transformed_rows.csv
496d2839524cc626a0240a8802e13c462cb9eb32b54e3055452cf85cc67ae891 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/old_pair_residuals.csv
d99a491eb2bc394f489d8f144b3798d99f73e5e28a3e2b495abab0b28621f09b docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/associations.csv
624d2c7f08dd258bc2199e2fd61c7a30d76c318c2841ae9f49508fdea3f5dc8f docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/unmatched_boxes.csv
046b1680fc4722bce5f5e0af71c345f5c5a80e3de061543439e8755b0123344f docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/per_tick.csv
79b01a70a3a126751f84cd9b617188edee3de354e92323666786c9c054a16d69 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/residuals.csv
fb2ca1a6d8b56799dda6c078931af3bf2f3ea2e7a53ef3296e2e0d9320501568 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/review.csv
6a63004c9704d5e6494650719a49768a657005aaf135a3568422f9decfd35d27 docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/denominator_table.csv
2866d063fe83f2aa092b709608ade3c2e2525551734f1d9d2e4a9ce3d5a0ed0f docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/eye_index.csv

## NOT VERIFIED
- comparator = same detector family/weights, not an independent teacher.
- Physical court geometry, production equality, and training suitability.
- The one unresolved PTS receipt remains UNKNOWN.

Test: python -m pytest tests/platformkit/test_g413_native_box_reaudit.py -q -p no:cacheprovider --basetemp=C:/Users/neelj/nba-track-a7/.pytest_tmp_g413c
