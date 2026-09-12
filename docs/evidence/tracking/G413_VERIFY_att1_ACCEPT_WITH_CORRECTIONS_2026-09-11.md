VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 1571091f07a8adb5a508678adee6616559cde701; acceptance source: docs/evidence/tracking/specs/G413_spec.md:17-23.
PASS ACCEPT complete re-audit: 60 unique keys, 206/592 boxes, 5 silent ticks, 59 exact receipts plus 1080p30_20 UNKNOWN; PARTIAL is correct (summary.json:2-29,61).
PASS ACCEPT residual: reproduced 117 matches/48 frames, equal-frame dx -0.75 px and dy -0.375 px, p90 24.0 px, max 100.5 px; fixed 30-frame/5-px bars pass (summary.json:45-60).
PASS ACCEPT reproduction/schema: 2 fresh runs, 70 tables/cards byte-identical, return codes 0/0; repeat shape retained (repeats.json:1-436).
PASS PREMISE: independently remeasured G406 as 60 unique keys, 206 producer rows, 592 comparator boxes, 51 old pairs/28 frames, 5 silent ticks (g406_masked_target_pixel_audit_2026-09-11/summary.json:1-153).
FAIL HEADLINE p50: claimed 5.719 px; ordinary median over 234 absolute coordinate residuals is 5.6095 px because the two middle values must be averaged (summary.json:47; g413_measure.py:169).
PASS B1: 2*117 matches + 564 unmatched = 206+592; all 60 ticks and the UNKNOWN receipt remain (denominator_table.csv:6-16).
PASS B2: fields/repeat shape remain; new receipt field is additive, G412 state meaning is unchanged, and reader census found no external reader (summary.json:31-35; g413_finalize.py:145-146).
PASS B3: changed code hashes inputs and summarizes evidence; it adds no absent-evidence gate (g413_hash_inputs.py:58-72).
PASS B4: changed code has no claim/retry path (g413_finalize.py:136-151).
PASS B5: EMPTY model set and CPU-only local measurement; no deployment action exists (g413_native_box_reaudit_2026-09-12.md:15-18).
PASS B6: no module moved/retired; candidate changes two existing modules (g413_finalize.py:1; g413_hash_inputs.py:1).
PASS B7: 60/60 exact-even cards, 60 unique review rows, and 60 renders exist (eye_index.csv:2-61; g413_native_box_reaudit_2026-09-12.md:19).
PASS B8: residuals use sealed transformed/comparator boxes and are scoped consistency, not independent validation (g413_native_box_reaudit_2026-09-12.md:18,25-27,45).
PASS B9: denominators are 60 unique frames, 206 rows, 592 boxes, and 48 matched frames (summary.json:12-23).
PASS B10: candidate does not change IoU 0.50, n>=30, or 5-px bars (prereg.md:21-23,42-46; g413_measure.py:171).
PASS Q1: seal recomputed exactly as 387cacc1e0b0084007b559318915d0aef109a1b76d1024ba92b5f819133381c4; e9efe2a84 predates scoring bbe119246 (prereg.md:57).
PASS Q2: no charged-trial/K claim exists (g413_native_box_reaudit_2026-09-12.md:15-18).
PASS Q3: sealed IoU, sample, and residual bars are unchanged (prereg.md:21-23,42-46).
PASS Q4: no OOS or meta-learning claim exists (summary.json:37; g413_native_box_reaudit_2026-09-12.md:16).
PASS Q5: no AHEAD claim exists; result is diagnostic PARTIAL/PASS/DONE (g413_native_box_reaudit_2026-09-12.md:1).
PASS Q6: field-aware manifest covers 27 paths; semantic candidate additions independently scan clean (q6_scan.json:134-164).
PASS Q7: sampled residual has 48 distinct matched frames and the draw has 60 unique frames (summary.json:15,18,54-55).
PASS Q8: prerequisite now exists; receipt hash and master 5a0b84cba independently reproduced (input_hashes.csv:45-47; g413_native_box_reaudit_2026-09-12.md:10-13).
PASS LOC: g413_finalize.py 156 lines; g413_hash_inputs.py 78 lines (g413_finalize.py:156; g413_hash_inputs.py:78).
PASS EVIDENCE: all 19 named G413 artifact paths exist; 80/80 SHA entries rehash (SHA256SUMS:1-81).
PASS NOT VERIFIED: memo lists independent teacher, geometry, production equality, training suitability, and unresolved PTS (g413_native_box_reaudit_2026-09-12.md:44-47).
TEST PASS: `python -m pytest tests/platformkit/test_g413_native_box_reaudit.py -q` -- 9 passed in 1.62s.
TEST IMPORT CENSUS: no existing test imports g413_finalize.py or g413_hash_inputs.py; no additional test command required.
CORRECTION minimal diff: g413_measure.py:169,173 use residuals(...)["absolute_p50"] instead of upper-middle percentile; regenerate residuals.csv, summary.json, repeats.json, SHA256SUMS, and memo line 27 as p50 5.6095 px.
2026-09-11 | tracking | G413 | 60/60 frames; 206 producer rows; 592 comparator boxes; 117 matches on 48 frames; equal-frame dx -0.75 px, dy -0.375 px; 1 PTS receipt UNKNOWN | PARTIAL native re-audit; residual PASS; reproduction DONE; ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: summary.json:32 names a worktree-relative G412 receipt absent from the candidate checkout; the durable copy is in master commit 5a0b84cba and the external hash receipt is input_hashes.csv:45.
NEW GAP: RESULTS_LEDGER.md:1-785 was rewritten from LF to CRLF; its semantic delta is only the G413 line at 785.
NEW GAP: g413_measure.py:199 populates wrong_object_matches with all 117 associations without a distinct visual adjudication state; add an explicit UNKNOWN/correct/wrong state.
NEW GAP: linked-worktree Git metadata denies index.lock writes, and no path-specific commit helper is installed; an external committer must commit this sole verification memo.
