VERDICT: ACCEPT WITH CORRECTIONS
Candidate eef71caf8 PASS: full 7-path diff read; only one Python file is added (g380_q6_scan.py:1).
PREMISE PASS: remeasured G368 66723/114064 = 0.584961; G370 0/89655 labelled rows; G376 28276/45842 and 53250/89655, matching the memo (attribution.csv:1; decisions.csv:1; classification.csv:1).
REPRODUCED RECEIPTS: claimed/measured equality 30/30, containment 30/30, 0 receipt-only, 0 trace-only, 21177 ticks, 30 unique sections/21 videos; 14 sections contain 277 non-emitting attempts (receipts_trace_a3.csv:2).
REPRODUCED HEADLINES: trace 2453/2453 over 998 frames; controls 10/10; labels 109060/109060 with HELD=0 and UNKNOWN=0; receipts 30/30; identity 0/30; runtime median 1.017054 on 30 pairs/20 videos (trace_summary.json:2; controls.csv:2; summary.json:34).
ACCEPTANCE LABELS PASS: agreement is 1.000000 and missing provenance is UNKNOWN, never dropped (trace_summary.json:2; controls.csv:7).
ACCEPTANCE RECEIPTS PASS: attempt-level agreement is 1.000000 on the sealed 30-section/10-video minimum (summary.json:45; receipts_trace_a3.csv:2).
ACCEPTANCE THROUGHPUT PASS: median 1.017054 <= 1.10 on 30 completed pairs/20 videos (summary.json:34).
ACCEPTANCE CONTROLS PASS: all five sealed branches are CONSTRUCT-covered; all 10 rows pass (prereg.md:33; controls.csv:2).
ACCEPTANCE PARTIAL PASS: identity and live HELD are explicitly CLOSED AT LIMIT; live coverage is explicitly deferred and unclaimed, preserving the pre-deploy sequence (G380_ADJUDICATION_2026-09-11.md:53; G380_ADJUDICATION_2026-09-11.md:82; G380_ADJUDICATION_2026-09-11.md:97).
ADDITIVITY PASS: 70 legacy columns stay ordered before 3 additions; no field/status removal or changed reader behavior found across 260 current reader paths (g380_producer_provenance_2026-09-10.md:12; reader_survey.csv:1).
NOT VERIFIED LIST PASS: deploy, live coverage, identity, live HELD/UNKNOWN, one live branch and one-section label scope are named (g380_producer_provenance_2026-09-10.md:21).
EVIDENCE PASS: all local memo paths exist; four seals and five memo digests reproduce after LF normalization (g380_producer_provenance_2026-09-10.md:25).
B1 PASS: all 30 A3 sections remain in the denominator and all ran; no failing row was filtered (receipts_trace_a3.csv:2).
B2 PASS: fields and ledger keys are additive; the 14 current paths absent from the 246-row survey are path/count readers or fixtures and remain additive-safe (reader_survey.csv:1).
B3 PASS: absent provenance returns UNKNOWN and bind failure returns an empty bind without suppressing work (g380_provenance.py:75; g380_provenance.py:124).
B4 PASS: bind_attempt is stateless/idempotent and retains no pending claim (g380_provenance.py:124; test_g380_producer_provenance.py:122).
B5 PASS: scratch compute only; no deployed-tree write or restart is claimed (g380_producer_provenance_2026-09-10.md:3).
B6 PASS: no module/test/import is moved or retired; proposed imports resolve in the spec test (test_g380_producer_provenance.py:13).
B7 PASS: 30 unique even frames span 0..2898 with gaps 99..105, not a head slice (renders/overlays_index.csv:2).
B8 PASS: no fit/residual is used; the import-time hook records inputs before the receipt mutation (g380_trace_hook_sitecustomize.py:49).
B9 PASS: denominators are unique attempts, emitted rows, sections, videos and elapsed seconds, all nonconstant (receipts_trace_a3.csv:2; replay_pairs.csv:2).
B10 PASS: receipt, identity, runtime, live and eye bars remain byte-identical to the sealed preregistration (prereg.md:47; g380_prereg_amendment_A3_2026-09-11.md:54).
Q1 PASS: all four embedded seals reproduce; commits 4093b2ecc, 72c96704, 60b2d653 and b608fbe5b precede their measurements (prereg.md:53; g380_prereg_amendment_A3_2026-09-11.md:68).
Q2 PASS (not applicable): no charged trial is used (prereg.md:3).
Q3 PASS: no bar or threshold moved; unmet clauses are named, closed at limit, or deferred (g380_prereg_amendment_A3_2026-09-11.md:54).
Q4 PASS (not applicable): no OOS or meta-learner comparison is claimed (prereg.md:41).
Q5 PASS (not applicable): no AHEAD result is claimed; the row reports PARTIAL (g380_producer_provenance_2026-09-10.md:1).
Q6 PASS: independent restricted-language scan of the candidate memo, adjudication, summary, A3 receipt, ledger tail and scan utility returns 6 files/0 hits (q6_scan.txt:1).
Q7 PASS: 30 unique sections/21 videos match all 30 G386 receiver receipts and the five branch cases are exhaustively constructed (a3_sources.csv:2; controls.csv:2).
Q8 PASS: the premise was sealed before preparation and independently remeasured here (prereg.md:6).
TEST PASS: `python -m pytest tests/platformkit/test_g380_producer_provenance.py -q -p no:cacheprovider --basetemp=.pytest_tmp_g380` -> 25 passed in 0.90s.
IMPORTER PASS: `git grep -l g380_q6_scan -- tests` -> no importing test file; no additional per-file test exists.
LOC PASS: touched g380_q6_scan.py is 21 lines <= 300 (g380_q6_scan.py:21).
CORRECTION DIFF: receipts_trace_a3.csv:1 `attempted_frames_capped` -> `attempted_frames_capped,trace_bytes,trace_sha256`; rows 6-31 already carry both trailing values.
2026-09-11 | tracking | G380 | premise holds; labels 2453/2453; attempt receipts 30/30 over 21 videos and 21177 ticks; runtime median 1.017054 on 30 pairs/20 videos; identity and live HELD closed at limit; live coverage deferred | ACCEPT WITH CORRECTIONS (verified: codex-sol, contract A/B/Q)
NEW GAP: the A3 trace wraps note_attempt itself, so it verifies receipt transport but cannot detect an omitted call at the producer boundary; add an independently observed boundary event before deployment (g380_trace_hook_sitecustomize.py:49; PROPOSED_g380_producer_provenance.diff:156).
NEW GAP: master fcb7916e has no test_g380_producer_provenance.py, so contract A1 cannot run there; the exact candidate-worktree test is recorded above.
NEW GAP: reader_survey.csv has 246 paths while current independent grep finds 260; the 14 omitted paths were checked as additive-safe but the survey should be regenerated (reader_survey.csv:1).
