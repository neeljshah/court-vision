VERDICT: ACCEPT WITH CORRECTIONS
Candidate: 137a30001469c47912b2896b30c13c419f7550d0.
PREMISE PASS - active cap is 3000 source frames, independently yielding 50.0500 s at 60000/1001 fps (scripts/platformkit/track_daemon.py:96; src/pipeline/unified_pipeline.py:1534).
REPRODUCED - policy 16/34 = 47.0588%; attribution CAP 25, EOF 3, FAILED_ATTEMPT 1, UNKNOWN 5 (g401_fps_cap_duration_shadow_2026-09-11/summary.json:2).
REPRODUCED - paired mechanics A 0/30, B 29/30; 30 unique sources from the sealed 89-source draw (g401_fps_cap_duration_shadow_2026-09-11/summary.json:19).
TEST PASS - `python -m pytest tests/platformkit/test_g401_fps_cap_duration.py -q` -> 18 passed in 3.24s.
IMPORT CENSUS PASS - this is the only existing test file importing a touched G401 module (tests/platformkit/test_g401_fps_cap_duration.py:8).
EVIDENCE PASS - 53/53 listed digests match; all required paths and 30 renders exist; even visual sample j00,j06,j12,j17,j23,j29 plus failed j02 is legible (g401_fps_cap_duration_shadow_2026-09-11/eye_index.csv:2).
PASS ACCEPT-policy - whole sealed window is 34 unique sections and positive loss is reported PARTIAL, not as zero-loss sufficiency (g401_fps_cap_duration_shadow_2026-09-11.md:18).
PASS ACCEPT-mechanics - fixed 30/30 bar was not moved; measured 29/30 is correctly NOT VALIDATED (g401_fps_cap_duration_shadow_2026-09-11.md:29).
PASS ACCEPT-proposal - all 7 fixtures parse, default argv is exact, aliases remain, and proposal is unused (g401_fps_cap_duration_shadow_2026-09-11/proposal_receipt.json:2).
PASS B1 - all 34 unique rows remain in the denominator, including unscored states (g401_fps_cap_duration_shadow_2026-09-11/policy_per_section.csv:1).
PASS B2 - no field/status removal; independent reader census found all 716 rows and 3 proposed changes (g401_fps_cap_duration_shadow_2026-09-11/proposal_receipt.json:16).
PASS B3 - absent/invalid rate falls through to legacy cap with UNKNOWN basis (g401_fps_cap_duration_shadow_2026-09-11/PROPOSED_g401_fps_cap.diff:31).
PASS B4 - proposal changes cap construction/receipts only, not claiming behavior (g401_fps_cap_duration_shadow_2026-09-11/PROPOSED_g401_fps_cap.diff:70).
PASS B5 - proposal_applied_anywhere is false (g401_fps_cap_duration_shadow_2026-09-11/summary.json:30).
PASS B6 - proposal targets one existing module and moves/retires none (g401_fps_cap_duration_shadow_2026-09-11/proposal_receipt.json:30).
PASS B7 - draw indices are the sealed even 0..88 schedule, not a head slice (g401_fps_cap_duration_shadow_2026-09-11/draw.csv:2).
PASS B8 - paired mechanics reuse one PTS stream and fit no model (g401_fps_cap_duration_shadow_2026-09-11.md:33).
PASS B9 - denominators are 34 unique sections and 30 unique sources (g401_fps_cap_duration_shadow_2026-09-11/summary.json:37).
PASS B10 - 100 s, >5 s, 3000, and 30/30 bars equal the seal; failure is retained (g401_fps_cap_duration_shadow_2026-09-11/prereg.md:24).
PASS Q1 - seal independently hashes to 35133397... and its identical blob was committed first at a37fed51b (g401_fps_cap_duration_shadow_2026-09-11/prereg.md:55).
PASS Q2 - no charged trial or launch-K applies to this fixed mechanics row (g401_fps_cap_duration_shadow_2026-09-11.md:29).
PASS Q3 - no bar moved; 29/30 remains a failed 30/30 mechanics check (g401_fps_cap_duration_shadow_2026-09-11/summary.json:19).
PASS Q4 - no OOS predictive score or meta-learner is claimed (g401_fps_cap_duration_shadow_2026-09-11.md:58).
PASS Q5 - no AHEAD claim is made; result remains PARTIAL (g401_fps_cap_duration_shadow_2026-09-11.md:1).
PASS Q6 - independent scan of all added text found 0 restricted-vocabulary hits (g401_fps_cap_duration_shadow_2026-09-11.md:59).
PASS Q7 - scored sets satisfy n >= 30: whole window 34 and even draw 30 (g401_fps_cap_duration_shadow_2026-09-11/summary.json:37).
PASS Q8 - premise was remeasured and activation corrected to 13:08:37Z (g401_fps_cap_duration_shadow_2026-09-11/policy_receipt.json:55).
NOT VERIFIED list PASS - explicit runtime, output-quality, coverage, and tracking-quality limits are present (g401_fps_cap_duration_shadow_2026-09-11.md:55).
CORRECTION minimal diff - memo:1 `6 UNKNOWN` -> `5 UNKNOWN plus 1 FAILED_ATTEMPT`; summary.json:40 and policy_receipt.json:51 should distinguish unscored=6 from UNKNOWN=5.
CORRECTION minimal diff - memo:52 `704 call sites` -> `716 reader rows`; regenerate reader_survey.csv:694-701 so its seven test-file line numbers move by +7.
2026-09-11 | tracking | G401 | post-preference cap loss 16/34 (47.06%); paired 60 fps mechanics 29/30, below fixed 30/30; proposal remains unused | PARTIAL (verified: codex-sol, contract A/B/Q)
NEW GAP: g401_finish.py is 309 LOC, above the 300-line rail; all other touched .py files are <=300 (scripts/platformkit/tracking/g401_finish.py:309).
NEW GAP: the proposal labels any positive single cv2 rate probe VALIDATED_FPS without two-reader or PTS validation; keep it unused pending a validated basis (g401_fps_cap_duration_shadow_2026-09-11/PROPOSED_g401_fps_cap.diff:31).
NEW GAP: linked-worktree Git metadata is outside the writable sandbox; targeted git add and lane_commit.py both failed at index.lock, so an external path-specific committer is required.
