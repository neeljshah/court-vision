VERDICT: PARTIAL -- diagnostic complete on accounting and pixel review; PARTIAL because the exercised producer route never sets a suppression argument, so none could be sealed from it.

# G406 masked target pixel audit

Diagnostic only. This row measures whether the G402 target rows sit on real people at native pixels, and how a replay of the producer's own detector compares. It qualifies no target for training, promotes no accepted reference, and establishes no teacher.

## Premise (step 0, reproduced before any drawing)

From the landed G402 export: 19,087 sealed rows, class table CLAMP 9,354 / PREDICTION 5,259 / SUBPIXEL 1,399 / DETECTION 3,075, HELD 0, repeated coordinates CLAMP 7,760 and SUBPIXEL 1,303, candidate rows 3,075, forbidden admissions 0, windows 59 COMPLETE of 60 with `1080p30/RIrGQJ_jsGQ_s90` retained UNKNOWN. The 30-per-kind exact-even draw was recomputed from all bounded evaluated ticks ordered by draw_order then source-frame index (N = 2,500 and 2,810) and is identical to G402's 60 cards; 60 distinct ticks come from 53 source windows. All 60 retained sources rehashed equal off pod, and all 60 native frames decoded independently with matching dimensions.

- `c2c4f57a56330afbc9a7772b61743864aa04d746d9715e0374743e724a79dc71` docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11/target_mask.csv
- `d0019a5b0460cca99fe5afade3e414173c104eba5997fc1683f43d1de2bcd436` docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11/eye_index.csv
- `88449bac72ab8bbe972faf01944e3d53c60c5a95342205dc32fddf1099d7aba5` prereg seal, docs/evidence/tracking/g406_masked_target_pixel_audit_2026-09-11/prereg.md

## Comparator identity (sealed before the single launch)

- `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36` /workspace/deploy/nba-ai-system/yolov8n.pt, 6,549,796 bytes, hashed before the copy
- `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36` /workspace/g406_scratch/yolov8n.pt, hashed again before the load
- `712068471b1d69e8254b06de0f20bbfad45288a29be569cd5319048d44d1bf74` scripts/platformkit/tracking/g406_comparator.py, identical on PC and pod before launch
- `c3bc2f7d4c4fda366f83523dd0aac86e47a40fecaf26e36b490d5a8c73ca5cc7` /workspace/deploy/nba-ai-system/src/tracking/player_detection.py, the argument source

Exercised route: `FeetDetector.get_players_pos` calls `self.model(frame, classes=[0], conf=0.3, verbose=False, imgsz=640, half=True, device=0)` on the unresized native frame. No engine file exists and tensorrt does not import, so `yolov8n.pt` is the selected weight. One invocation, sequential, six cores, one thread, RTX 3090, ultralytics 8.4.146 / torch 2.8.0+cu128 / python 3.12.3. The suppression argument is absent at the call site; the library default was recorded but never substituted, which is what makes this row PARTIAL.

## Review sequence

Sixty blind judgments were written with UTC timestamps before any overlay existed, on grid-annotated native frames carrying no prediction; `blind_order_receipt.csv` shows blind completion preceding overlay exposure on 60 of 60 ticks. Association is the sealed one-to-one maximum-IoU rule at 0.50 with lexicographic ties, published with every unmatched box. Every one of the 206 producer rows, all 592 comparator boxes and all 5 producer-silence ticks were adjudicated at native pixels: 803 adjudication rows, none omitted. A box counts as supported when a real person occupies its centre or the majority of its area.

## Measured (n = 60 ticks, 30 per kind)

| metric | 1080p30 | 720p60 | pooled |
|---|---|---|---|
| candidate rows judged a real person / all candidate rows | 18/18 | 16/16 | 34/34 |
| candidate rows whose box extent is also correct | 0/18 | 0/16 | 0/34 |
| masked CLAMP rows on a person | 51/56 | 46/49 | 97/105 |
| masked PREDICTION rows on a person | 24/25 | 20/22 | 44/47 |
| masked SUBPIXEL rows on a person | 11/12 | 8/8 | 19/20 |
| producer rows matched to a comparator box | 32/111 | 19/95 | 51/206 |
| comparator boxes matched to a producer row | 32/305 | 19/287 | 51/592 |
| producer-silent ticks | 1/30 | 4/30 | 5/60 |
| comparator-silent ticks | 0/30 | 0/30 | 0/60 |

Geometry on the 51 sealed matched pairs: centre dx median 0.0 px (p10 -13.5, p90 27.25); centre dy median -58.2 px (p10 -67.75, p90 -45.75). The same sign appears on the descriptive nearest-comparator offset over all 206 rows (dy median -59.5 px). The producer's stored boxes are horizontally aligned with a same-detector replay on the same native frame and sit roughly 60 px too high; only 1 of 206 rows was judged extent-correct. All five producer-silence ticks were adjudicated PERSONS_PRESENT, with 9 to 13 comparator boxes each.

Blind marks: 586 instance marks (102 uncertain) plus 156 dense regions holding at least 6,062 further persons that were deliberately not instance-marked. Producer rows matched 19 of the 586 instances, so 567 marked instances carry no producer row; the producer emits about 3.4 rows per tick by construction, so this figure describes coverage, not an error rate.

Denominators. Full window: 60 windows, 27,000 decoded frames, 5,310 evaluated ticks, 19,087 bounded rows, 3,075 candidate rows, 355 receipt zero-output evaluated ticks (one window UNKNOWN), 3,277 evaluated ticks without a candidate (the coverage table's `zero_output_evaluated_ticks`, aliased in `window_accounting.csv` as `zero_candidate_evaluated_ticks`). Sampled: 60 decoded frames, 60 evaluated ticks, 206 producer rows, 592 comparator boxes.

## Verification performed

Masks are unchanged from G402 and no tick was replaced. Two fresh processes regenerated every delivered table and all 60 cards from the delivered comparator output, blind marks and adjudications; both rounds are digest-identical (`repeats.json`, parent shape retained). The field-aware vocabulary scan reports 0 non-opaque hits over 43 text artifacts, emitting pattern indices only; one four-letter spatial token in my own review prose was replaced by "border" before the scan, receipted in `runtime_receipts/vocabulary_substitution.json` with no verdict or coordinate changed. Test: `python -m pytest tests/platformkit/test_g406_target_pixel_audit.py -q`.

There is no delta in this row. If a later row reports one, its sign convention is baseline loss minus candidate loss; positive means the candidate has lower loss. This diagnostic has no candidate acceptance bar.

## NOT VERIFIED

- Teacher independence. The comparator is the producer's OWN detector family and the SAME weights file; no independently frozen teacher exists in this program. Agreement and disagreement here measure same-detector consistency, never corroboration, and a mismatch cannot prove the historical model changed.
- Target suitability for training. Nothing here qualifies a target; the export has zero training callers and no accepted-reference promotion.
- The suppression argument of the exercised route (absent at the call site, never substituted).
- Decoder byte identity with the producer's in-process capture: the comparator read independently decoded native PNGs.
- Instance-level counts inside the 156 dense crowd, bench and stands regions, which stay UNKNOWN at instance level by declared scope; and the cause of the roughly 60 px vertical offset, which is measured here and not explained.
