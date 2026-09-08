VERDICT: PARTIAL -- BAR NOT MET (2 gates clear both A0 bars; 3 are required)

G353 | worktree a10 | corrected finisher measurement | 2026-09-08 | Spec: docs/evidence/tracking/specs/G353_spec.md.
Prereg is sealed at docs/evidence/tracking/g353_prereg_2026-09-08.md (sha256 efcda1c31dec0e51463a4d93fa4f8df8453c56db1f5258f55d637de5aa212343, verified).

PREMISE: 18 reported rows, 16 IMAGE_SPACE_COMPUTABLE and 2 COURT_ONLY (coordinate_contract and oob). The sealed table at prereg lines 19-36 says 16/18 and 2; its summary at lines 38-39 disagrees and is not changed. Premise HOLDS.

2026-09-08 fix 1b: corrected premise and result-row counts; added the 16-gate census mapping (13 core, 2 ball, 1 containment); named A5 exclusions 000008, 000017, and 000024 (no_embedded_ball_rows); archived production translation and 2,160 fixture gate-arm statuses; and made g325 NOT_APPLICABLE when decoded frame dimensions are absent.

GATE x ARM: 30 windows, four arms; A3/A4 are UNIDENTIFIABLE by construction. gates.csv preserves the 72 aggregate cells and adds NOT_APPLICABLE reasons; fixtures_status.csv contains every fixture x gate x arm status. A0 dispositions are:

| gate | A0 rejected/evaluated | disposition |
| --- | --- | --- |
| coordinate_contract | 0/0 | NOT_APPLICABLE: court_space_required |
| insufficient_data | 30/30 | fails |
| duplicate_frame_identity | 0/30 | clears |
| coverage_attempted_frames | 0/0 | MEASURED_NO_BAR |
| median_track_len | 0/30 | clears |
| oob | 0/0 | NOT_APPLICABLE: court_space_required |
| jump_max | 0/0 | MEASURED_NO_BAR |
| attempted_frames | 0/0 | MEASURED_NO_BAR |
| ball_valid_attempted_frames | 6/30 | fails |
| liveness_frozen | 7/30 | fails |
| zero_step_share | 8/30 | fails |
| median_step_distance | 9/30 | fails |
| distinct_position_ratio | 5/30 | fails |
| stationary_track_share | 19/30 | fails |
| jump_p95 | 0/0 | MEASURED_NO_BAR |
| ball_detected_share | 6/30 | fails |
| g325_wholly_off_frame | 0/0 | NOT_APPLICABLE: frame_size_absent |
| any_gate | 30/30 | derived |

DETECTION: A1_FROZEN to liveness_frozen is 30/30; A2_ID_MERGE to duplicate_frame_identity is 30/30; A5_BALL_SHIFT to ball_detected_share is 27/27 after the three named exclusions. Each meets the 0.80 bar. The unmodified evaluate() rail REJECTs coordinate_contract on 30/30 A0 windows. Every image result is scorable=False and coordinate_space=image_px.

CENSUS: 653 tables; 644 declare image_px; 0 have both decoded frame dimensions. census.csv remains the three group totals; census_gates.csv maps its 13 core, 2 ball, and 1 containment groups to all 16 image gates. NBA is 639/648 image_px and WNBA is 5/5.

LIMITATIONS: image passing is necessary, not sufficient, for court geometry; this does not certify coordinates. The 30 windows from four games screen only. Decoded width and height are absent in 30/30 fixture windows and 653/653 census tables, so g325 is not evaluated.

EYE CHECK: NONE.

NOT VERIFIED: behavior on the 9 census tables not declaring image_px; decoded dimensions against an authentic video source.

TEST: C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g353_image_space_gates.py -q -p no:cacheprovider --confcutdir=tests/platformkit -> 4 passed in 1.32s.
TEST: C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g353_production_translation.py -q -p no:cacheprovider --confcutdir=tests/platformkit -> 1 passed in 1.03s.
2026-09-08 | tracking | G353 | premise 16/18 image-space-computable; 11/18 A0 gates evaluated 30/30, 2/11 meet false-rejection <=0.05; identifiable detections 30/30, 30/30, 27/27 (3 exclusions named); census 653 tables, 644 image_px, 0 with both frame dimensions | PARTIAL -- BAR NOT MET

2026-09-08 lander: ACCEPT WITH CORRECTIONS (codex-sol) after one REJECT; A0 evaluated-gate count restated 11/18 (2/11 clear both bars) per the verifier's recount; NEW GAP in the ledger (16 NBA fixture source files unavailable locally at verification; rail reproduction covered the 14 WNBA windows).

SCAN: touched deltas scanned with the specified expression; 0 non-measured hits; no measured collision.
