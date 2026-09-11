VERDICT: PARTIAL. The merged current reference is 1,114/1,620 settled and 506 unsettled; held-out is 157 VISIBLE / 161 ABSENT / 26 UNKNOWN. A1 remains development 29/60 = 0.483333, Wilson 95% [0.361750, 0.606922], projection 457 [414, 502]. No arm trained or scored.

Premise: 596 reconciled queue keys remain 361 development + 235 held-out; all 1,620 sheets are primary-paired and the original 283 boxes/27 games reproduce. A1 is exactly ordinals 1,11,...,591: 30 prior decisions reused by frame key and 30 new development decisions from native 1920x1080 sheets. It is used only for the sealed supply inference.

Fix 1c (2026-09-10): ACCEPTANCE metric/n/eye-check finding fixed by merging all 60 prior decisions with all 30 new decisions by frame_key for the current reference and accounting; the former A1-only merge dropped 30 settled held-out keys, including eye-check index rows 8 and 13. B2 fixed by restoring parent allocation and verdict fields while retaining allocation_g384 and verdict_g384 aliases, and by making load(root) retain its one-argument default. A1 inference remains unchanged.

NOT VERIFIED: candidate arm, training, scorer, or held-out execution; complete reference; held-out A1 estimate; 500-box quota; pinned A9 receipt; deployment, route, weight, flag, or data/ write.

Q6: character-code patterns scanned the changed G384 artifacts and the appended ledger line; 0 non-opaque hits.

SHA-256 4c308dcbcbe8cdcc43391b1363979f2bb5bee82a276cb9e3beda60863a1da076 docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/queue_reconciliation.csv
SHA-256 ee3fe128863f283411637151831bd08019187e923a4c93df6727f88300fffcf7 docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/adjudications_g384.csv
SHA-256 dd9ecd1f7fd43208c01012a12124f4d0751e0e4c5d382a1017985020996cde6b docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/arm_readiness.json
SHA-256 1d64edae0c8779b1fc195d3207dc8f230166a4225f652dc35da1306487ef3b62 docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/arm_accounting.csv
SHA-256 3b9ac4a7c4d135d420ce0d45091bb0f6319e208765c18d66a2322e85ec002f50 docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/queue_summary.json
SHA-256 e6f2e7cd4ac820809c6109b48626de3f4e86e56b4294f8730d3bf460302f6eba docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/transform_checks.csv
SHA-256 ce9811e22aa84e14a799ae9b8534cca68f81f6d7081f1d423414f43f7f569df3 scripts/platformkit/tracking/g384_build.py
SHA-256 e2c52b7555ea0d35afb86d5577393793c883412fcc6f62e0aab76c3ad947020b scripts/platformkit/tracking/g384_adjudicate.py
SHA-256 dc016e7dc75c6184e2667462fba828105a946551e9b31e5642b3263536bd359c tests/platformkit/test_g384_ball_phase2_receipt.py
SHA-256 01bf4466f6041c146ee29a1120fd0f3d5389c4da18be8d2dfe4c28e4f51f2a33 docs/evidence/tracking/RESULTS_LEDGER.md

Fix 1d (2026-09-11, orchestrator, after codex-sol fix-1c REJECT B4): load(root) now defaults its completed set to docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/adjudications_g384.csv (DEFAULT_COMPLETED), so the one-argument loader returns the 506 unsettled keys disjoint from the 90 completed ones (asserted in the per-file test, 10 pass). Spec-listed phase-2 artifacts reference_v2.csv, dev_boxes.csv, weights/, predictions.csv, paired_frame_scores.csv and summary.json were NOT PRODUCED because no arm ran (A8 at LIMIT for execution accounting; supply inference 457 [414, 502]); they are named here as absent, never inferred. No measurement changed.
