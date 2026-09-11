# G387 paint localization with coordinate controls

VERDICT: PARTIAL -- ACCEPTANCE RULE row "Known-position localization", clause "Below bar: PARTIAL, protocol not qualified" (13/30 admissible (19/30 post-redispatch diagnostic) controls against the 27/30 bar); the "Audited real-paint localization" row is therefore also PARTIAL with visibility/protocol ambiguity (1/30 against the 24/30 bar).

## Premise (step 0, reproduced before any measurement)

`frames.csv` (LF SHA-256 `80e4b930578cbf42eb8b0e30029c1dacb10e775a830e53b32079172173da15bb`): 60 planned states, 49 `RETAINED`, 11 `DECODE_FAILED`, `selection_status` `PLANNED` on all 60. `adjudication.csv` (`2c586bbc6b46f007a1da8a18feb0837106729b3a3ba54cfc06502b7d637791d8`): 175 PAINTED rows, 57 agreed same-id pairs, 34 of them with zero overlap. `identity_map.csv` (`a1923ded8cb1d9d1f6a091784e6d18c4779e497d9f5ea8fecdedd55f4a1d2142`): 49 `READY` native PNGs, all 49 SHA-256 matches, all decoded 1920x1080, 135,177,764 bytes total, 11 `ABSENT`. `marking_only.json` (`9bc53aa82046834770436c51d7f0823f34a747b21fac288b86a0f3072e9602a2`): 49 SCORED entries holding 0 strokes in total, so no independent correspondence supply exists and the G383 reference supply stays CLOSED AT LIMIT. PREMISE HOLDS; the row proceeded.

Prereg sealed alone at `fb1111522`; the seal recomputed over the LF bytes above the seal line matches. All five prepared route hashes match their sealed values.

## Measured bars

| bar | measured | met |
|---|---|---|
| All 60 original states retained in accounting | 60 rows in `census.csv` and `eligibility.csv` (49 eligible, 11 `DECODE_FAILED_NO_NATIVE_FILE`) | YES |
| 30 real contexts and 30 controls attempted, hashes exact | 30 contexts, 180 tiles, sender and receiver SHA-256 equal on all 30; 30 controls rendered | YES |
| Known-position localization >= 27/30 | 13/30 admissible (19/30 post-redispatch diagnostic) | NO |
| Audited real-paint localization >= 24/30 plus the control bar | 1/30 | NO |
| Two fresh processes byte-identical | probe digest `610eb3c2abc0aea384c0114b438e37522c1dc4a18da78ad924c8b069a44e935c` twice, score canonical `7b7ca56f6bb46927d89860a8dd2ce26d17224a0c8d22ff4cee858f31ff5409d1` twice | YES |

The selection is the sealed even draw: indices 0,2,3,...,46,48 of the 49 sorted retained rows -- not a head slice, and it includes the last ordered row -- giving 30 unique frame keys over 12 videos and 12 sections.

## The three-way outcome, stated explicitly

The controls do NOT pass at the sealed 3 px tolerance, so this row cannot separate "the G382 reference protocol failed" from "the paint is genuinely unlocalisable". The sealed reading is PROTOCOL NOT QUALIFIED. The measured detail qualifies that: the failure is a tolerance miss, not a protocol collapse. Over the 60 rater-observations on known bands, endpoint error is p50 2.3 px, p90 3.2 px, max 33.1 px; 49/60 endpoints and 59/60 midpoints are within 3 px, and exactly one observation (terra on `G387_028`) is a gross miss at 33.1 px. The bar needs BOTH raters within 3 px on the same image, which 13 of 30 admissible (19 of 30 post-redispatch diagnostic) images meet.

Real paint: the adjudicator, blind and before any rater output existed, recorded a straight painted marking VISIBLE on 22/30 contexts, ABSENT on 6/30 (close-ups of coaches, a bench, an official) and UNKNOWN on 2/30. Localization under the sealed rule is 1/30 on the all-frame denominator, 1/22 on the adjudicator-visible denominator, and 1/12 among the frames where both raters named the same physical marking. On the one passing frame, `G387_018`, all nine audited positions of both traces lie on the visible white lane-line paint. Of the other 11 shared-id frames, three (`G387_017`, `G387_023`, `G387_030`) are collinear within 6 px -- both raters are on the SAME painted band, verified at native resolution -- yet disagree by 47 to 244 px on which contiguous sub-segment is the longest visible one, so the sealed endpoint rule rejects them. The dominant real-paint failure mode is segment-extent disagreement, not wrong-line identification.

Against the G382 reference on these same 30 frames: 35 old agreed painted ids on 18 frames, 22 of them with zero overlap; the two new blind raters named 60 ids, 13 of which coincide with an old id on the same frame. No new-versus-old geometric agreement is claimed.

## Deviations and corrections

- Terra's control batch 02 wrote nothing: the sandbox refused its output directory (`rater_logs/cx_g387_rater_terra_control02.log`, "outside the permitted editable workspace") and the process still exited 0. That is ABSENT evidence rather than a rater judgement (contract B3), so that batch alone was re-dispatched once with the identical instruction, identical images and no feedback (`cx_g387_rater_terra_control02b.log`). The re-run supplied 6 of the 19 passes, so under the strict "missing clicks fail" reading the rate would be 13/30. Both readings are below the 27/30 bar, and no bar was moved.
- The prereg's canonical digests for the selection (`b67f676c...`) and for the known points (`68d720b5...`) could not be reproduced by any canonicalization tried here. This lane's own canonical forms are `0e32f7eac95c5a9817783702f1c863f112f11ffafd21f46ee7841354c7a724ed` and `d6ef292f78c6ab3d3292ddd2ae7733a5e97b3f60046e413d9b90d0cc8c423da4`. The sealed selection RULE and the sealed control-generation CODE are byte-identical to the prereg, and the resulting draw satisfies both stated properties, so the draw is verified; only the digest convention is unreproducible.
- `g387_receipts.vocabulary_hits` is defective: its patterns are built with doubled backslashes inside raw strings and cannot match. The Q6 scan was run instead by `g387_finish.py q6` with correctly built character-code patterns. No sealed file was edited.
- A rater midpoint convention drifted: several reported midpoints are the exact average of the two endpoints despite the instruction to click the interior independently.

## Q6 scan

164 text artifacts including all 17 rater logs: 0 non-opaque hits (`q6_scan.json`). No rater wrote a prohibited token, so no substitution was needed.

## NOT VERIFIED

Paint recall; the G383 oracle supply; any homography, registration or extractor result; deployment; any other corpus; whether a wider endpoint tolerance would qualify the real-paint route; whether the 3 px control bar is reachable by these raters at all.

## Test and receipts

`python -m pytest tests/platformkit/test_g387_paint_localization.py -q` -- 7 passed. Wall time of the measuring run: 92 minutes. The full `SHA256SUMS` covers 213 paths.

fbb6c9878fbc7a425dc7dfdd53044ad21777d6ffe6d6f9c3177caa7bdd76d093  docs/evidence/tracking/g387_paint_localization_controls_2026-09-11/prereg/g387_prereg_2026-09-11.md (SEAL line value)
4c3040d34902877c2f375dfcc044ed61e5dca11acd3828b278d1f1fac7f2766e  docs/evidence/tracking/g387_paint_localization_controls_2026-09-11/visibility.csv
7b7ca56f6bb46927d89860a8dd2ce26d17224a0c8d22ff4cee858f31ff5409d1  canonical scoring digest recorded in summary.json
610eb3c2abc0aea384c0114b438e37522c1dc4a18da78ad924c8b069a44e935c  two-process rendering probe digest recorded in repeats.json
