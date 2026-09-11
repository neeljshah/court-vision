VERDICT: NOT VALIDATED -- all three quality bars missed. A10 (the A8 recipe plus 49 audited person-contained DEV hard negatives) scored C0 0.153, Wilson95 precision lower 0.292 and ALL FP/188 0.830 on the fixed 549-frame benchmark. The negative-supply clause was MET (49 jointly confirmed crops, 15 DEV games). The one training launch and the one candidate inference are spent; no rerun is permitted.

# G394 -- ball arm A10, the A8 recipe with audited person-contained DEV hard negatives

Preregistration: `docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/preregistration.md`, sealed ALONE at commit `1e2b57d2f195934e57e4dadf2269f8f3420c3bf1` with SEAL sha256 `6fdfa08ab1ce9f95db51f3bbdc9e6eb789b7f4027d03ad15b8dde61dabde90d5`, verified from the committed LF bytes before any measurement. It is unedited.

## Step 0 premise (BINDING before-condition, re-measured here)
The full joins over the landed G389 tables reproduced 530 DEV boxes in 27 games, 425 DEV ABSENT frames, 386 of those in the same 27 games, and held-out VISIBLE/ABSENT/UNKNOWN of 302/188/59. The premise HOLDS. The spec's stated input digests match the LF (git blob) bytes; this Windows worktree checks out CRLF, so every digest in this memo is over LF-normalized bytes. G391 landed DONE at `fcb7916eb` and G390 is NOT VALIDATED (adjudicated); both were read before any work here. Current readiness `d11a1c8cdd52098ee6de16aec6df103ca22990c00cd45cd4bb4f8712bd7c8ef6` was used, not G390's superseded digest.

## Negative audit (person rectangles SELECT records; no pixel was masked and no runtime veto exists)
386 eligible ABSENT DEV keys frozen, all native 1920x1080, every sheet digest matched the G373 sealed manifest (386/386). Split isolation: 27 DEV games / 27 sections vs 32 held-out games / 35 sections, game overlap 0, section overlap 0. A8 (weights `0f05a616...`, its original settings, conf 0.05) produced a rank-0 call on 88 of the 386; 55 of those centres fell inside at least one person rectangle (yolov8n class 0, imgsz 640, conf 0.25, IoU 0.70) across 16 games. N = 55 >= 30, so the row did not close before training. The even selection took all 55 (min(120, 55)). Two independent blind raters (terra, sol) rated 55/55 each, 0 faults; raw state agreement 0.927. ACCEPTED 49 (both raters NO_BALL_VISIBLE, no HIGH uncertainty), 49 unique parent frames, 15 DEV games. EXCLUDED 6 with no replacement: terra_BALL_AT_MARKER 2, terra_BALL_AT_MARKER|sol_BALL_AT_MARKER 2, terra_BALL_AT_MARKER|sol_BALL_ELSEWHERE 1, terra_BALL_ELSEWHERE 1. Every excluded state is retained in `audit_agreement.csv`.

## Training (ONE launch, charged before it started)
Data only: 530 original positives + 425 original ABSENT negatives + the 49 accepted crops appended once each with an empty label file = 1004 images. Initialization `bc979654...` (A8's own), seed 373, ten epochs, no augmentation, final epoch only, imgsz 960, batch 2, otherwise reproducing G390's `args.yaml` (`463157bf...`). Final weights `3b0fe860ab4ee5c63747decb61ae3b2dfe73817e0d3ba418ddc6b8868533cf54`, sealed at commit `962d411d` BEFORE the held-out token was charged. Weights stay off-repo; nothing was written to `models/` or any deploy tree.

## Measurement (ONE charged candidate inference over all 549 planned keys; no sweep, no re-selection)
| arm | TP | FP | FN | C0 (/549) | Wilson95 precision lower | ALL FP / 188 | FP on ABSENT / 188 |
|---|---|---|---|---|---|---|---|
| A10 candidate | 84 | 156 | 218 | 0.15300546448087432 | 0.29244980923302405 | 0.8297872340425532 | 0.18617021276595744 |
| A8 archived | 90 | 169 | 212 | 0.16393442622950818 | 0.29211016505655896 | 0.898936170212766 | 0.26595744680851063 |
| A0 deployed route archived | 0 | 8 | 302 | 0.0 | 0.0 | 0.0425531914893617 | 0.010638297872340425 |

Bars, byte-identical to the spec and none moved: C0 >= 0.25 -> 0.153 MISSED; Wilson95 precision lower >= 0.90 -> 0.292 MISSED; ALL FP / 188 <= 0.01 -> 0.830 MISSED. Denominators 549 / 302 / 188 / 59 asserted in the scorer. A10 returned no detection on 309 of the 549 keys; every one stays in the denominator (`heldout_states.csv`). Centre tolerance max(3 px, diameter_720p/2), conf 0.05, rank-0 OBSERVED only, through the landed `g363_score.score_arm`. A8 and A0 are archived-prediction rescores, not fresh inference; A8 reproduced G390's published 90/169/0.163934/0.292110/0.898936 exactly. Two fresh processes reproduced every count identically (`repro_run1.json`, `repro_run2.json`).

## A10 versus A8 -- a SINGLE-RUN OBSERVATION, not a causal claim
On this one run A10 made 13 fewer false calls (169 -> 156) and 6 fewer true calls (90 -> 84); C0 fell 0.164 -> 0.153 and the Wilson lower bound was flat (0.29211 -> 0.29245). FP on ABSENT frames fell 0.266 -> 0.186. One training run of one arm on one reused benchmark cannot separate the added negatives from training stochasticity; no seed replicate exists and none is permitted. Nothing here is adopted, deployed or flagged on.

## Eye check
30 evenly spaced paired native renders over all 549 scored keys (not over detections), so no-detection frames are drawn in their own right: A10 cases TP 8, FP 2, FP/FN 8, NO_DETECTION 8, NO_DETECTION/FN 4. Inspected renders confirm the targeted failure persists -- e.g. `render_02_10b7527d0321.jpg`, an ABSENT huddle frame where A8 and A10 both place a near-identical box on a face in the crowd. 30 evenly spaced context/crop cards including the exclusions are in `cards/` with `cards_index.csv`.

## Accounting
GPU minutes this row: DEV candidate pass 0.4278, training 9.7941, candidate inference 0.2848, total 10.5067 -- under the 90-minute stage cap. Cumulative training 19.0269 of the 120-minute allowance after charging G390's 9.2328. All pod compute ran under the lane path `/workspace/wt/a7/.g394_scratch` (declared in `a10_config_receipt.json` before training). Wall time 2026-09-11 11:10Z to 11:55Z, about 45 minutes. Per-file test only. Q6 scan over 47 then-existing text artifacts; verifier test covers 48 including q6_scan.json incl. rater logs: one geometric token in a raw rater log replaced with `calibration-only`, before/after digests in `q6_redaction_manifest.csv`; 0 remaining non-opaque hits.

## NOT VERIFIED
- A10 repeatability, any seed replicate, any second inference, any threshold or epoch selection: not run and not permitted.
- Whether the 49 audited negatives, rather than training stochasticity, caused the 169 -> 156 false-call change.
- Any generalisation beyond this one reused 549-frame benchmark and these 27 DEV / 32 held-out games.
- A0 and A8 were not re-inferred; only their archived G390 predictions were rescored.
- The person detector's own accuracy was never measured; it only selected candidate records.
- No deploy, flag, registry or `data/` path changed; no operational adoption is proposed.

## SHA-256 (LF-normalized bytes)
544B1DE528C392970A4F9A58E217B639755E86D4AFF1FEEAA73929D93AB51EE5 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/preregistration.md
9C3641F9F4508AC7785994BE715787204C124C79668DDE5FC51F666F6752BC62 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/summary.json
624FE1B6FEFF5A3600EB0E8882CD5F02F4C41DE8859454A039A7FB9A04BAF292 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/predictions.csv
7AE4AE1A56BDE7B8E62277100BAC715FA259C162F6EAAB224D36C17C807E603C docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/paired_frame_scores.csv
8E681A4652C6684F94452CE95882E838541310406F9206BE9155F6CACDDE21A4 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/negative_manifest.csv
7D45C53E80CFA7AC7065075F508D845CC445C583E3518FEFF6C1418A52E93731 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/accepted_negatives.csv
BC06FADAC677B660899332A7D22246FC00EF646968CC8318B92A4A2F20871AFC docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/audit_agreement.csv
6BB6FB8A102C6702485AF08DB567A4814BBEF23BD753B2ECD423C8601EEA5DF6 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/split_assertions.json
E1C962CBA9A75C3A141C95F2CFFB9934B3DE65E4679BA107B5A3A0A7FCF8264B docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/a10_config_receipt.json
6EF15163119246138BB82AEB52B93744207066E13BE5D83E7E66CCB45012D1D3 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/weights_manifest.json
3D960E53E4B97C5F2C0EA0D3D3C2D1A39EEE3040AC77CA883E85A6537476C2AB docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/q6_redaction_manifest.csv
(every remaining artifact digest, incl. eligibility, masks, ratings, receipts and each render, is in this manifest)
D24DCA55B1B4A33D35CE0EFC0A00F038956159F6019391B8ACFF82C8F2679931 docs/evidence/tracking/g394_ball_person_negatives_2026-09-11/sha256_manifest.txt
BC979654E281C5DE6E0E992E1F9587B3A9FAA2EEC996EA41B1B03954BA0B6E52 input weights off-repo /workspace/deploy/nba-ai-system/models/weights/yolov8n_ball.pt
0F05A61618687BDA2005CE4AC8343C5987F60BA0076245597DE59F7380398762 input weights off-repo A8 final epoch, the candidate-selection detector
F59B3D833E2FF32E194B5BB8E08D211DC7C5BDF144B90D2C8412C47CCFC83B36 input weights off-repo /workspace/deploy/nba-ai-system/yolov8n.pt person checkpoint
3B0FE860AB4EE5C63747DECB61AE3B2DFE73817E0D3BA418DDC6B8868533CF54 output weights off-repo A10 final epoch /workspace/wt/a7/.g394_scratch/runs/a10/weights/last.pt
CBC7CD9DFB7E18691F310B7594BE046AC0D3184A279C43D8EB427210355BC9EA deployed route /workspace/nba-ai-system/src/tracking/ball_detect_track.py
