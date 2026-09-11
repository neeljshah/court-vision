VERDICT: REJECT
Candidate: dc4b58f4f9b9ccbc95a10ae6fb8e85e4269b2251.
ACCEPTANCE metric PASS: independent union gives 1,084/1,620 settled and 295 audited development boxes; no rank-0 score was made (queue_summary.json:13-16; arm_readiness.json:2,12-14).
ACCEPTANCE before PASS: 283 boxes/27 games and agreement median 17.33 px, nearest-rank p90 287.09 px, n=715 were reproduced (memo:4,13; G384_spec.md:19).
ACCEPTANCE bar PASS: incomplete reference correctly prevented arm scoring; held-out counts reproduce as 157 VISIBLE and 161 ABSENT (memo:12,14-15,25).
ACCEPTANCE n PASS: 596 unique queue keys are accounted; 60 unique decisions contain 30 per split, with 536 explicitly unsettled (memo:5,23,26).
ACCEPTANCE eye check PASS: 30 held-out native frames span sorted positions 0..332 of 344 and include 15 VISIBLE, 12 ABSENT, 3 UNKNOWN; render inspected (memo:33; eye_check_index.csv:2-31).
ACCEPTANCE must-not-move PASS: no protected route, historical seal, split, matcher, daemon, or flag changed (memo:29; G384_spec.md:23).
ACCEPTANCE verdict FAIL: A8 CLOSED AT LIMIT relies on B7-invalid yield sampling, so its supply conclusion is not verified (memo:23; G384_spec.md:24).
MEMO NOT VERIFIED PASS: an explicit list is present and names unscored arms, 536 unsettled keys, extrapolation, and untouched deployment (memo:24-29).
B1 PASS: all 60 sampled outcomes enter the stated yield; no outcome-based exclusion is shown (memo:23).
B2 FAIL: queue fields ordinal/source and status PENDING were removed; transform field status was replaced by verdict without aliases (queue_reconciliation.csv:1; transform_checks.csv:1; g384_build.py:17-21).
B3 PASS: unresolved labels remain unsettled and are not converted to ABSENT (memo:26).
B4 FAIL: the finisher loader always passes an empty completed set, and append has no duplicate-key guard, so completed keys remain claimable (g384_adjudicate.py:22,79-86).
B5 PASS: no deployed-tree write or pod execution occurred (memo:29,31).
B6 PASS: the candidate moves or retires no module; all imports resolve in the focused test environment (g384_adjudicate.py:10-11; g384_build.py:8-12).
B7 FAIL: all 60 adjudications are ordinals 1,6,...,296 of a 596-row queue, a prefix-derived sample despite the memo's whole-queue claim (adjudication_decisions.json:3,652; memo:8).
B8 PASS: no residual or independent-performance claim was made (memo:25).
B9 PASS: yield denominator is 30 unique keys per split, not recycled identifiers (memo:23).
B10 PASS: no harness threshold or gate value changed (G384_spec.md:20,23; memo:12-20).
Q1 PASS: no scored comparison exists; the prereg seal is nevertheless named (memo:25,36-37).
Q2 PASS: no charged trial or metric launch exists (memo:25,31).
Q3 PASS: scoring bars remain unchanged and no bar was lowered (G384_spec.md:20; memo:12-20).
Q4 PASS: no OOS score or meta-learner result exists (memo:25).
Q5 PASS: no AHEAD result is claimed (memo:2,25).
Q6 FAIL: independent added-line scan found 8 non-opaque prohibited hits: two in disclosure rows and six historical figures embedded in scanner code (q6_redaction_manifest.csv:2-3; g384_q6_scan.py:10-17).
Q7 PASS: the reported sampled yields each use n=30 (memo:23).
Q8 PASS: premise remeasurement gives claimed 283/27 and queue 596=361 development+235 held-out; all 1,620 keys have both primary ratings (memo:4-7; queue_summary.json:2-12).
REMEASURE: claimed/reproduced reference 1,084/1,620; held-out VISIBLE 157/157; ABSENT 161/161; development boxes 295/295; transform PASS 33/33 (memo:12-20).
REMEASURE: claimed/reproduced development yield 12/30=0.400, Wilson [0.246,0.577], projection 427 [372,491]; inference rejected under B7 (memo:23).
LOC PASS: g384_adjudicate.py 86, g384_build.py 138, g384_q6_scan.py 39; each <=300 (memo:50-52).
TEST PASS: `python -m pytest tests/platformkit/test_g384_ball_phase2_receipt.py -q -p no:cacheprovider` -- 6 passed in 0.79s.
TEST PASS: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -- 1 passed in 0.66s.
IMPORTER SURVEY PASS: no existing test imports any of the three touched modules; focused test ran as required (test_g384_ball_phase2_receipt.py:5-8).
CORRECTION: - replaced queue/transform fields; + retain ordinal, source, PENDING, and status, adding new fields/statuses under new names (g384_build.py:17-21,28-32).
CORRECTION: - ordinals 1,6,...,296; + preregister 60 even positions spanning 1..596, adjudicate them, then recompute yield, interval, projection, and A8 state (adjudication_decisions.json:3,652).
CORRECTION: - empty completed set and literal scanner figures; + load prior decision keys, reject duplicate append keys, encode scan patterns, and retain only hashes/lengths in disclosure (g384_adjudicate.py:22,79-86; g384_q6_scan.py:10).
PROPOSED RESULTS_LEDGER_SYSTEM: 2026-09-10 | tracking | G384 | premise 283 boxes/27 games and queue 596 reproduced; 1,084/1,620 settled and held-out 157 VISIBLE/161 ABSENT reproduced; A8 closure not verified because 60 adjudications span queue ordinals 1-296 only; B2/B4/B7/Q6 fail | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: spec-listed G384 canonical outputs reference_v2.csv, dev_boxes.csv, and summary.json are absent; headline state is split across G373 plus delta artifacts (G384_spec.md:25).
NEW GAP: none of the three new modules is imported by an existing test; the focused test imports only pre-existing helpers (test_g384_ball_phase2_receipt.py:5-8).
