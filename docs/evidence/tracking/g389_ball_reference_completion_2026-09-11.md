# G389 Ball Reference Completion -- MEASURED

VERDICT: DONE -- the fixed 506-key native queue is complete (506/506 reviewed, 1,620/1,620 states represented, 0 unsettled); audited development supply 530/500 boxes over 27/5 games -> READY FOR G390 CHECK (a premise check, not an authorisation to score any arm).

## Step 0 premise (BINDING before-condition, reproduced before any judgment)
manifest 1620 | settled 1114 | pending 506 = development 301 + held-out 205 | dev boxes 312 | held-out settled VISIBLE 157 / ABSENT 161 / UNKNOWN 26 | candidate executions 0. Every count matched, so the row proceeded; the queue was NOT already complete, so the FALSIFIED branch did not apply. All 506 pending native sheets were re-hashed and decoded: 506/506 present, 506/506 digests equal to `sheet_manifest_all.csv`, 506/506 decoded 1920x1080, 96,460,210 bytes total, 0 missing pixels. No sheet was ever re-rendered.
## What was done
Sealed sweep: pending keys sorted by split/game/section/frame_index/frame_key, cut into 30 contiguous equal-quantile bins, consumed one key per bin round-robin (all 506 ordinals archived BEFORE dispatch), disjoint allocation terra 253 / sol 253 plus a sealed even 30-key audit repeat rated by BOTH. 14 codex batches (7 per rater, 536 judgments) from blind full native sheets -- no candidate box, no legacy label, no other rater's output, no detector output. Only afterwards were the two G373 primary annotations revealed, for descriptive reconciliation. Claude then resolved all 29 conflicts from the pixels at native zoom (`renders/conflict_zoom_*.jpg`, `renders/conflict_wide_pairs.jpg`): 10 VISIBLE where the ball was identifiable at a named rater centre, 19 UNKNOWN retained after actual review. No arm was trained, scored or executed; 0 GPU minutes; the pod was not used.
## Bars (spec ACCEPTANCE RULE) with measured values
| row | bar | measured | verdict |
|---|---|---|---|
| Reference task completeness | all 506 reviewed; 1,620 states represented; zero duplicates or dropped completed decisions | 506/506 reviewed; 1,620/1,620 settled, 0 unsettled; 1,114/1,114 prior G373+G384 decisions reproduced (the merge refuses on any loss or relabel); 0 duplicate keys; 14/14 batches OK, 0 faults, 536 rows parsed, 0 keys re-judged | DONE |
| Audited development supply | >= 500 unique valid boxes / >= 5 development games; causal-neighbour dedup; no held-out context | 530 boxes / 27 games; 530 unique frame keys and 530 unique (section, frame_index) pairs; 1 causal neighbour skipped; 0 rows from a held-out game and 0 from a held-out section; full 1,071-key development census | READY FOR G390 CHECK |
| Reference usability / identity | inherited median rule; exact source bytes; native transforms; both held-out quotas >= 150 | median primary centre disagreement 17.33 px against the unchanged 18.50 px threshold, n = 715 both-VISIBLE pairs, p90 287.09, max 1521.26, 0 boxless pairs (byte-identical to G373 -- the bar did not move); sheet_scale 1.0 on all 1,620 rows; planted-at-reference controls 30/30 TP 0 FP development and 30/30 TP 0 FP held-out; held-out VISIBLE 302 and ABSENT 188 (both >= 150); all 549 held-out keys retained | MET |

Checkpoints over the sealed order (30/120/240/360/506) reached 30/120/240/360/506 with new development boxes 12/48/103/157/218; the sweep never stopped at a box quota. Final census labels: VISIBLE 833, ABSENT 613, UNKNOWN 174; development 1,071 and held-out 549 settled.
Audit repeats (descriptive, never accuracy against truth): 30 keys rated by both adjudicators, label agreement 0.767, centre disagreement p50 29.68 px over the 16 pairs where both gave a centre, max 1080.16 px. Reconciliation against the revealed primaries: AGREES-BOTH 229, AGREES-ONE 211, AGREES-NEITHER 53, UNRESOLVED before pixel review 13; conflicts open after resolution 0.
Eye check: `renders/eye_check_g389_60.jpg` -- 30 evenly spaced backlog keys plus the 30 independent audit keys, 0 overlap between the two sets, 34 development / 26 held-out. All 60 tiles render; the marked centre sits on the ball in every VISIBLE tile inspected, and the ABSENT tiles are crowd, coach, graphic and arena shots. A defect was found and fixed here: the first render sampled the backlog with the SAME even-index formula that had chosen the audit keys, so it showed one set of 30 twice; audit keys are now excluded from the backlog pool.
## Q6
0 non-opaque hits over 97 text artifacts including every rater log. The 11 flagged files are each classified with a reason: 6 OPAQUE-RETRACTION-QUOTATION (a codex event dump echoing this repository's own retraction sentence from CLAUDE.md), 4 OPAQUE-RULE-IDENTIFIER (a transcript citing the rule file's NAME, which the Q6 note forbids masking), 1 OPAQUE-SCANNER-REPORT. Four raw rater files used the reserved token geometrically; it was replaced with `calibration-only` and the before/after digests are in `q6_redaction_manifest.csv`. Two launcher logs were redacted in error and were RESTORED unmodified once the hit was identified as the rule identifier. Scanner patterns and the finding report are built from character codes, so no artifact spells a reserved token.
## Faults and incidents (disclosed, never silently re-run)
- The preregistration was sealed twice: the first commit `1d59ccb61` carried a seal that does not hash its own committed bytes; it was RE-SEALED alone at `4719604dd`. The re-seal is the binding one and this lane verified it before measuring. The prepare-only skeleton's seal string `4c241fe0...` is superseded.
- `g389_rater_sol_01` was OPERATOR-STOPPED before it wrote any output, while the finisher verified that the raters really were opening images. No judgment had been made, so its 40 ids were reassigned under the sealed failure policy (`raters/sol_faults.txt`).
- Image-open receipt: a control probe on a settled key reported 1920x1080, the correct jersey colours, and a ball centre at about (901, 578) against the G373 reference (908.25, 579.75) -- 7.4 px (`raters/probe_02.txt`).
- The pre-halt terra loop had already appended batches 01-02 when the operator replayed the same two raw files, duplicating 80 rows. The duplicate copies were byte-identical (0 conflicting rows -- no judgment was repeated or changed); they were removed and the driver now re-reads the completed key set before every append.
- The PC gate was never raised: at most 3 `codex exec` processes and free RAM >= 2.8 GB, checked before every batch and shared politely with the G388 lane.
## NOT VERIFIED
- No arm was trained, scored, tuned or executed. Detector quality is NOT measured by this row; 530 >= 500 permits G390's premise check only.
- The 29 conflict resolutions are one reviewer's judgment from the pixels, not ground truth. The 19 keys left UNKNOWN are NOT evidence that a ball is absent.
- Audit-repeat agreement and the primary-agreement counts are descriptive, not an accuracy measurement; no truth set exists. The adjudicator contradicted a unanimous primary pair on 20 keys and all 20 were pixel-reviewed, but the other 33 AGREES-NEITHER keys stood against a SPLIT primary pair and were not re-reviewed.
- The codex `.events` dumps were scanned but not landed; only the launcher transcripts are in `logs/`.
- Wall time 56 minutes (preregistration commit 2026-09-11T00:13:43-05:00 to 01:09 CDT); 0 GPU minutes, 0 pod minutes, 0 candidate executions.
## Artifacts (SHA-256)
6553969494563712b5c6db35068ca39ba51f8b8f2c18787db631c513929426fd docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/preregistration.md
0dc379cd6ee811769b39f97b98c8c6b1f524330535ac8f67b66964fcaaf6d3d5 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/premise.json
c5a3de3cddd9953bf5598d553c43a8cf2fc901b99f4cb3b6118487da5aa3b437 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/pending_sheet_receipts.csv
73fc8b06cafc4df4e606625c70a0517a49db52b87c35a29280bed65b2e9b0901 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/sweep_permutation.csv
cbf4d80f9195c94dc3fce0660f688f4cc5301f2acf98c2f60a80ad4c01595668 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/key_sheet_census.csv
53992f40b7971e87f3c66d78588bb34391d710797763d3cafdcb8b28a13461cc docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/ratings_g389.csv
e32b37a3aa2750b10e5dd2be1ed9c46190bcf29e4adf686abb3173a6170a3e6d docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/ratings_g389_sol.csv
55b1ae38da07a506c27d28b788fe0d9581489038cc74120768d2ebb79f4ff9f0 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/adjudications_g389.csv
dcbe5179eebcc3eb7cd987983f46ee4aa4a149f2dfce6ffc92a1bff6c3d4f25c docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/reconciliation.csv
c04418aabbea7c23ef71425ef06f9c400b4510fcdbe60d8e161ccd3664117f91 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/audit_agreement.csv
72951aa257bfd9d1280773293f4453c784cbed6f9aaed192473372ffcec71011 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/resolutions_claude.csv
8596c92932cebbe852b3728799a9668f26b44e7a0fd49184b25036b1de24a8dd docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/checkpoints.csv
ad00670c3601706d5d817de734fc85d82e8fdc379ea03b21bbe1a46e272ad09e docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/reference_v3.csv
11797e162dd303441a7bde18e66fae4b404341fa2bd611678226182258d58945 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/frames_v3.csv
e151f932c3b4bffe84c89aa8fde18f08c346a1e3a6e65d27ed4b36f095b7b4fa docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv
336a436a6312a10ddef1dd542644a4869c728d29411bc758e24a0a0970bee1e2 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/context_audit.csv
91f72ddcc041f974661381ca290adec4bacdfe0503ab030a0ec3ad658a8e92be docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/transform_controls.csv
d11a1c8cdd52098ee6de16aec6df103ca22990c00cd45cd4bb4f8712bd7c8ef6 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/readiness.json
fe8bcbeff936ed7162b706c14b7d1bdf61e32b90ab2aee186be105847f611b64 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/summary.json
67a468b50f240b1d64f62c50bf55d24d8baba1bae8c36af074ec8493fe5fbb84 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/batch_receipts.csv
bdd275461eb9baaa526dc376ad2fd12b410b89541b7ae8e2b52b4fc60c4c9d92 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/q6_scan.json
c1cf9ee3cb7f25fecf6030d81eddc1a0e65278e7a827c83afc48b2cfb00118d2 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/q6_redaction_manifest.csv
7df8dddad53ff77df284a8213322a4fe5d9b9da084d593939f305e140ee5c019 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/renders/eye_check_g389_60.jpg
0db590eebe4200a5eaa56c019db45d9727df45c50fda7e6fec12dd920afe0239 docs/evidence/tracking/g389_ball_reference_completion_2026-09-11/renders/eye_check_index.csv
15684f9c6439f3853074d90fbb9c515f54709965e6146db2551ee7de853d1091 PREREGISTRATION SEAL -- sha256 of every byte above the SEAL line at commit 4719604dd, verified by this lane before any measurement

TEST: `python -m pytest tests/platformkit/test_g389_ball_reference_completion.py -q` -> 3 passed (prior decision never dropped or relabelled; sealed sweep order identical under input permutation; uneven or prefix partial pass refused; causal-neighbour dedup; restart, overlapping allocation, reviewed-versus-unvisited UNKNOWN, full-schema merge, even checkpoints, no quota-based early stop). `tests/platformkit/test_loc_rail_scope.py` -> 1 passed; every new file is <= 300 lines.
