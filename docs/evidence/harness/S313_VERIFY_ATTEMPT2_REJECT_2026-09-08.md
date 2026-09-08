[provenance: recovered by the lander from C:/Users/neelj/AppData/Local/Temp/cx_verify_s313.log, the first S313 attempt-2 verify run (TURN_END and EXIT:0 gap=verify_S313 at 2026-09-08T01:29:29-05:00, log lines 2921-2923). That run wrote its memo to docs/evidence/harness/S313_VERIFY_2026-09-08.md and could not commit it -- both `git add` and `lane_commit.py` failed on the shared-worktree index.lock -- so the three later verify runs overwrote the same path and only what the log captured survives. The log keeps the tail of each captured output, and the single surviving copy (the `type docs\evidence\harness\S313_VERIFY_2026-09-08.md` capture at log line 2848) begins mid-line inside a POD TEST line, so every line above it is unrecoverable. The log does record, from the same run, that the file was 39 lines long and that its SHA-256 was 71aab45560730e6fe8e69ab87bb4447378a698a2869ee04b82480c67047b01f3; 9 of those 39 lines survive here (8 whole, 1 truncated at its head). No git blob id exists, the file never having been committed.]

VERDICT: REJECT

The verdict line is taken from the harness log's own markers (`cx_verify_s313.log:2920` "VERDICT: REJECT" inside the run's closing report and `cx_verify_s313.log:2922` the run-level "VERDICT: REJECT" immediately before the EXIT marker); the memo's own first line did not survive. The same log records the run's stated ground for rejection at line 2847: "The candidate is rejected on the binding acceptance rule and B9: reproduced coverage is 3/6, and both stale and missing-prerequisite cases still expose numerical output." The candidate under verification was attempt 2, `808c2ce72`, and its recorded HEAD at the close of the run was 808c2ce72eda0c2cd1727262fca8fb205423d0ae.

RECOVERED TAIL, verbatim; the first line below is truncated at its head:

256 before pod contact.
POD TEST: `/c/Users/neelj/bin/pod_run a22 -- python -m pytest scripts/platformkit/answers/test_resolver_registry_routing.py -q -p no:cacheprovider` -> 0 collected; launcher rc 256 before pod contact.
CORRECTION: change memo:1,26, ledger line and route_status.md:19 from 4/6 to 3/6; do not count CONNECTION 2 as a stage.
CORRECTION: before `status=ok`, validate receipt hash/fields and freshness; refuse stale or mismatched rows, and make NOT_TESTABLE compose without `n=0`; reverse tests at lines 132-149 and 155.
2026-09-08 | harness-to-answers calibration | S313 | 3/6 stage receipts and 1/2 connection receipts; stale and missing-prerequisite routes still expose numeric output | REJECT (verified: codex-sol, contract A/B/Q)
NOT VERIFIED: the three pod-routed reader files (Git Bash cannot start: CreateFileMapping Win32 error 5); live resident connectivity; DATA, SIGNALS, PREDICTIONS and CONNECTION 1 receipts.
NEW GAP: S313-MANIFEST-SCAN-MISSING - prereg schema requires `scan`, but completion_manifest.json has none (`S313_answers_roundtrip_attempt2_prereg_2026-09-08.md:55-63`).
NEW GAP: S313-TEST-SUMMARY-NOT-ROWS - the new test recomputes from the summary, not archived rows (`test_s313_answers_label_survival.py:87-94`); verifier row-level recomputation supplied the binding check.
NEW GAP: S313-STALE-LEDGER-DOCSTRING - aggregate-reader docstrings still state 287 rows; current checked total is 291 (`mechanism_survival.py:1-2`; `mechanism_ledger_export.py:1-3`).

NOT RECOVERED: the 30 lines above the truncated one -- the memo's own VERDICT line, the candidate/diff line, the PREMISE and ACCEPTANCE dispositions, the A/B/Q per-item findings, the LOC and REPORT lines, every local TEST line, and the first 13 of the 14 POD TEST lines. The candidate answered this REJECT with fix 2b (`8fa8b7d65`), which was itself rejected (S313_VERIFY_FIX2B_REJECT_2026-09-08.md); attempt 3 and its fixes 3b and 3c follow, and the fix-3c memo landed as S313_VERIFY_2026-09-08.md supersedes this one at CLOSED AT LIMIT.

Vocabulary follows contract Q6; automated scan required.
