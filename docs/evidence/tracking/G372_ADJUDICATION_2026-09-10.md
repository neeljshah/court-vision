# G372 adjudication -- 2026-09-10

## Verifier verdicts
`ACCEPTANCE RULE FAIL - scratch coverage is not over all unique attempts and is not an even sample (G372_spec.md:13-16; g372_phase_a.py:74-76,101-108,196-230).`
`ACCEPTANCE RULE PASS - phase A is correctly PARTIAL: coverage 5/50 = 0.100000 fails 1.000, agreement is 5/50 with only 5 joinable, and DONE/throughput/live claims are not made (memo:26-27,42-45).`
`ACCEPTANCE RULE FAIL - coverage is 43/81 = 0.530864 against 1.000; selected-pin agreement must retain 81 attempts, not the 43-row join; replay has 27 completed pairs below 30 (G372_spec.md:13-17; memo:21-26,35).`

## Orchestrator adjudication
Phase A = ACCEPT for code plus attribution: the source deleter was `vol_guard.py`, and attribution was 122/122.
Phase B deployed 2026-09-10T19:34Z and was measured for 61 minutes. Pin agreement was 43/43 over 13 videos; controls PASS and schema was additive.
Coverage per attempt was structurally capped by the `xb` write at 43/81, and the paired replay was short at 27 pairs.
After the window, ledger repeat-or-duplicate row share was 1.000 in the 30-60 and 60-120 minute windows post-restart, versus 0.181 in the hour before; only 9 files were in the bridge.
The daemon was re-tracking the same sections in a loop. The overlay was REVERTED at 2026-09-10T22:15Z.
Deploy `track_daemon.py` was restored to sha256 `9747d9a085405c492f04c4e3b162ed8b1d897309da6f0f9c014cb7092056f5ac`; the overlay remains beside it as `track_daemon.py.g372_overlay_reverted_2026-09-10`; the daemon restarted.
Whether the re-claim wave was caused by the overlay is NOT ATTRIBUTED. The memo falsified the quota-guard hypothesis.
Landing status = PARTIAL (adjudicated): the claim-time identity hook works for unique sections and the daemon overlay is withdrawn.
The allocated successor must add an idempotent bind, weight-digest fix, full exception scope, `_PENDING` fix, `test_g328` repair, and attribution of the re-claim wave before any re-deploy.
No threshold moved.

## Post-revert measurement (orchestrator, 2026-09-10T22:40Z)
26 ledger rows in the 25 min after the revert, repeat-or-duplicate 0 (share 0.000 vs 1.000 in the post-restart windows). The re-claim loop is attributed to the deployed overlay by revert-and-observe -- one uncontrolled comparison, so the successor row still owes a controlled attribution before any re-deploy.
