VERDICT: REJECT
Candidate 947f5ae1 receipt PASS: deployed hashes 4/4 match LF-normalized route bytes; treatment hashes 4/4 reproduce from the in-memory proposed patch; proposed diff hash matches (hash_receipt.json:4-19).
PREMISE PASS: measured G368 66723/114064=0.584961, G370 0/89655 source fields, G376 over-count 0.383186 and 0.406057; claims match (g380_producer_provenance_2026-09-10.md:7-8).
REPRODUCED: trace claim/measured 2453/2453; receipt exact claim/measured 0/1; identity claim/measured 0/30; paired median claim/measured 1.017054/1.017054, n=30 sections and 20 videos (summary.json:28-49).
ACCEPTANCE PASS: label agreement 1.000000, label coverage 109060/109060, receipt presence 30/30, throughput <=1.10, UNKNOWN construct retained, and 70 legacy columns remain ordered before 3 additions (memo:11-17).
ACCEPTANCE FAIL: receipt equality is 0/1 traced section, unchanged-column identity is 0/30, and live coverage is unmeasured; the memo correctly labels these unverified (receipts.csv:2; memo:25-26).
ACCEPTANCE FAIL: the sealed five-branch CONSTRUCT set is incomplete because coast is OBSERVED, not CONSTRUCT (prereg.md:33-37; controls.csv:10).
ACCEPTANCE FAIL: 30 even unique overlays span frames 0-2898, but none contains HELD; five evenly spaced renders were inspected (overlays_index.csv:2-31; memo:22-23).
NOT VERIFIED LIST PASS: deploy, live coverage, identity, receipt equality, one write site, HELD/UNKNOWN measurement, and one-section trace scope are listed (memo:25-26).
B1 PASS: all 30 completed pairs are retained and five failed pairs are named; no metric-failing completed pair is excluded (summary.json:8-13,28-36).
B2 PASS: 70->73 columns are additive; independent grep checked 258 references and found no closed-key reader behavior (memo:10-11,19-20).
B3 PASS: absent provenance returns UNKNOWN and bind failure degrades to an empty bind without dropping the attempt (g380_provenance.py:62-71,111-130).
B4 PASS: binding is stateless and idempotent; focused test covers repeat and absent source paths (g380_provenance.py:111-130; test_g380_producer_provenance.py:83-91).
B5 PASS: receipt records no deployed-tree copy or restart; scratch-only compute is reported (hash_receipt.json:11-12).
B6 PASS: candidate removes or moves no file, module, test, import, field, or status; its sole touched path is the receipt (hash_receipt.json:1-21).
B7 PASS: overlay frames are unique and evenly spaced with gaps 99-105, not a head slice (overlays_index.csv:2-31).
B8 PASS: no fit or residual is used; this is paired route instrumentation (prereg.md:39-45).
B9 PASS: denominators are emitted rows, traced attempts, paired sections, distinct videos, and elapsed seconds, all nonconstant (memo:13-17).
B10 FAIL: the sealed eye gate requires HELD and CLAMP, but amendment A1 adds "where they occur," weakening the gate (prereg.md:47-51; amendment_A1:46-53).
Q1 PASS: both embedded seals independently reproduce, and commits 4093b2ecc/72c96704 precede their scored outputs (prereg.md:53; amendment_A1:55).
Q2 PASS (not applicable): this is not a charged trial and prereg forbids a ledger change before measurement (prereg.md:3-4).
Q3 FAIL: amendment A1 says no bar moved but conditionally relaxes the unconditional HELD overlay bar; an unmet bar must not be lowered (amendment_A1:46-53; G380_spec.md:50-55).
Q4 PASS (not applicable): no OOS or meta-learner score is claimed (prereg.md:41-45).
Q5 PASS (not applicable): no AHEAD finding is claimed; the row reports PARTIAL (memo:3,16-17).
Q6 PASS: recorded automated scan covers 27 artifacts with 0 hits; verifier memo rescan also has 0 hits (q6_scan.txt:27-54).
Q7 FAIL: the prereg enumerates five exhaustive CONSTRUCT branches, while controls.csv marks coast only OBSERVED (prereg.md:33-35; controls.csv:10).
Q8 PASS: verifier independently remeasured the full premise artifacts before adjudication (memo:7-8).
TEST INFRA: `C:\Users\neelj\anaconda3\Scripts\conda.exe run --no-capture-output -n basketball_ai python -m pytest tests/platformkit/test_g380_producer_provenance.py -q` -> 16 setup errors from blocked temp access.
TEST INFRA: `C:\Users\neelj\anaconda3\envs\basketball_ai\python.exe -m pytest tests/platformkit/test_g380_producer_provenance.py -q --basetemp C:\Users\neelj\nba-track-a19\.pytest_tmp_g380` -> 16 setup errors from blocked temp access.
TEST PASS: `python -m pytest tests/platformkit/test_g380_producer_provenance.py -q --basetemp=.pytest_cache/g380_verify_947` -> 16 passed in 0.71s; this is the only test importing a G380 module.
LOC PASS: candidate touches no .py; all G380 .py evidence/helpers/tests are <=300 lines (largest g380_replay.py:300).
CORRECTION: amendment_A1:52 delete ` where they occur` to restore the sealed bar; then supply a HELD overlay or report CLOSED AT LIMIT.
CORRECTION: g380_controls.py:132-136 replace the coast OBSERVED placeholder with a producer-entering CONSTRUCT fixture and regenerate controls.csv/summary/memo.
CORRECTION: memo line 1 must be the VERDICT line; add the unmet coast-CONSTRUCT and HELD-overlay clauses to its NOT VERIFIED list.
2026-09-11 | tracking provenance | G380 | premise holds; trace 2453/2453; receipt exact 0/1; identity 0/30; paired median 1.017054 on 30 sections/20 videos; coast CONSTRUCT and HELD overlay absent | REJECT (verified: codex-sol, contract A/B/Q)
NEW GAP: A1 cannot run on master 3853991e because master does not contain tests/platformkit/test_g380_producer_provenance.py; candidate-worktree test is recorded above.
NEW GAP: reader_survey.py:23 scans only .py; current grep finds 10 operational shell readers absent from reader_survey.csv, although their existence/row-count behavior is additive-safe.
NEW GAP: spec evidence names per_tick.csv, paired_runtime.csv, and live_receipts.csv, while the package has receipts.csv, replay_pairs.csv, and no live artifact; memo line 26 discloses the unrun live phase.
