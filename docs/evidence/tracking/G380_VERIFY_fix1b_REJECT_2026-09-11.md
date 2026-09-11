VERDICT: REJECT
PREMISE PASS: remeasured G368 66,723/114,064 = 0.584961; G370 0/89,655 labelled rows; G376 28,276/45,842 and 53,250/89,655, matching the claim (g380_producer_provenance_2026-09-10.md:8).
ACCEPTANCE LABELS PASS: reproduced 2,453/2,453 = 1.000000 over 998 unique frames (g380_producer_provenance_2026-09-10/trace_summary.json:2).
ACCEPTANCE RECEIPTS FAIL: reproduced equality 0/4, containment 4/4, with 2/15/10/56 receipt-only ticks; n=4 also misses the sampled n>=30 rail (g380_producer_provenance_2026-09-10/receipts_trace.csv:2).
ACCEPTANCE IDENTITY FAIL: reproduced 0/30 identical legacy-field pairs, claimed 0/30 (g380_producer_provenance_2026-09-10/summary.json:57).
ACCEPTANCE THROUGHPUT PASS: reproduced median 1.017054 on 30 pairs/20 videos, <=1.10 (g380_producer_provenance_2026-09-10/summary.json:34).
ACCEPTANCE LIVE FAIL: 60-min coverage phase not run (g380_producer_provenance_2026-09-10.md:20).
ACCEPTANCE CONTROLS PASS: 10/10 CONSTRUCT, including the five sealed branches; missing event is UNKNOWN (g380_producer_provenance_2026-09-10/controls.csv:2).
ACCEPTANCE EYE FAIL: 30 unique even frames span 0..2898 and include CLAMP, but no HELD; two separate CONSTRUCT images do not satisfy the sealed live set (g380_producer_provenance_2026-09-10.md:18).
ADDITIVITY/LOC/NOT VERIFIED PASS: proposal appends fields and ledger keys; 246 field readers report no closed-key assertion; candidate touches 0 .py; related new .py max 287 LOC; NOT VERIFIED exists (g380_producer_provenance_2026-09-10.md:10,16,19).
B1 PASS: all failed pairs and receipt-only ticks are named, not excluded (g380_producer_provenance_2026-09-10.md:14).
B2 PASS: structural schema is 70 legacy columns plus 3 appended; no rename/removal/status change or affected reader behavior found (g380_producer_provenance_2026-09-10.md:10,16).
B3 PASS: absent provenance emits UNKNOWN, never quarantine/drop (scripts/platformkit/tracking/g380_provenance.py:62).
B4 PASS: bind is stateless and failure returns an empty bind without retaining a claim (scripts/platformkit/tracking/g380_provenance.py:111).
B5 PASS: no deploy-tree write or restart is claimed (g380_producer_provenance_2026-09-10.md:3).
B6 PASS: no module moved/retired; proposed imports resolve in the spec test (tests/platformkit/test_g380_producer_provenance.py:15).
B7 PASS: 30 even, unique render frames span the set; this does not cure the separate eye-bar failure (g380_producer_provenance_2026-09-10/renders/overlays_index.csv:2).
B8 PASS: import-time trace records branch entries independently of the producer (g380_producer_provenance_2026-09-10.md:12).
B9 PASS: denominators are emitted rows, unique frames, and 30 distinct section pairs/20 videos (g380_producer_provenance_2026-09-10.md:12,14).
B10 PASS: A2 restores the original sealed bars verbatim and no candidate threshold changed (g380_producer_provenance_2026-09-10/g380_prereg_amendment_A2_2026-09-11.md:24).
Q1 PASS: all three seals independently hash-match; prereg commit 4093b2ecc predates scoring (g380_producer_provenance_2026-09-10/prereg.md:53).
Q2 PASS (not applicable): no charged trial is used (g380_producer_provenance_2026-09-10/prereg.md:3).
Q3 PASS: failed bars remain 1.000000/0/1.10 and are reported unmet (g380_producer_provenance_2026-09-10/prereg.md:47).
Q4 PASS (not applicable): no OOS comparison was run (g380_producer_provenance_2026-09-10/prereg.md:41).
Q5 PASS (not applicable): no AHEAD result is claimed (g380_producer_provenance_2026-09-10.md:1).
Q6 PASS: independent scan of 38 G380 text artifacts plus the ledger row found 0 hits (g380_producer_provenance_2026-09-10/q6_scan.txt:33).
Q7 PASS: five sealed construct branches are exhaustively enumerated and all pass (g380_producer_provenance_2026-09-10/prereg.md:33).
Q8 PASS: premise was recorded first and independently remeasurement holds (g380_producer_provenance_2026-09-10.md:7).
TEST: `python -m pytest tests/platformkit/test_g380_producer_provenance.py -q -p no:cacheprovider` -> 21 passed.
TEST: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed.
TEST: `python -m pytest tests/platformkit/test_g328_daemon_worker_accounting.py -q -p no:cacheprovider` -> 2 passed.
IMPORTER SET: candidate c48847415 touches no Python module, so no additional importing test file exists; the two memo-named regression files were run separately.
CORRECTION DIFF 1: - trace set = frames with emitted rows; + trace every producer-evaluated attempt before row filtering and require equality on >=30 sections.
CORRECTION DIFF 2: - nondeterministic A/B identity; + pin environment/seeds without production behavior changes and retain 30/30 zero-difference legacy-field pairs.
CORRECTION DIFF 3: - construct-only HELD outside the even live set; + satisfy the sealed live eye bar, or close G380 at limit without deployment.
CORRECTION DIFF 4: - live phase unrun; + run it only after steps 1-4 receive a fresh ACCEPT.
2026-09-11 | tracking | G380 | premise holds; labels 2453/2453 and median ratio 1.017054 on 30 pairs/20 videos, but receipt equality 0/4, unchanged-column identity 0/30, live coverage not run | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: Spec-named per_tick.csv, paired_runtime.csv, live_receipts.csv and overlays/ are absent; alternate trace/replay/renders paths exist (specs/G380_spec.md:58).
NEW GAP: Memo says fix 1b ended 09:25Z, but the candidate was committed 07:40Z and its three recorded runs total about 19 minutes (g380_producer_provenance_2026-09-10.md:22).
