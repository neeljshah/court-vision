VERDICT: ACCEPT WITH CORRECTIONS (no BLOCKING; all 7 AMENDMENT 2 items MET; memo inventory must be regenerated at landing)

S551 contract-tier verifier, round 2 (Opus; codex down). Candidate = uncommitted files in nba-harness-h222, HEAD fb59f6fff (fast-forwarded). Not edited.

## Reproduction
The tests were run one file at a time through run_files.py:
- test_s551_cancel_policy: 20 passed
- test_s551_replay: 14 passed
- test_s551_prereg_report: 10 passed

My own mutants (scratchpad/s551_r2_mut.py, monkeypatch only):
- M2a feeds trade created_time into the state triggers. case 21 KILLS it.
- M2b feeds trade receipts into the state triggers. case 21 KILLS it.
- M8 calls BEHIND on the unadjusted p. case 31 KILLS it.
- Both baselines pass.

## AMENDMENT 2 items
1. MET. Older-snapshot queue.
   - exec_policy_replay.py:99-112 counts a refused fill snapshot as `fill_snapshot_refused` and a refused mark tick as `mark_tick_refused`; the quote still decides.
   - phase2 at :206-209 passes each decision instant's own snapshot, or a level-less {ticker, ts, yes: [], no: []}.
   - tape_fill_sim._queue at :53-73 then reads `matching` as empty, so the queue is the UNKNOWN sentinel.
   - Both keys are in REFUSALS (report.py:37-40) and receipted at 0 in s551_expected.json.
   - Test: test_s551_replay.py:199-211. The 60 s quote with a duplicated, conflicting 49 level does not fill; the 0 s quote still fills with queue "5".
2. MET. Non-tautology.
   - The oracle is oracle_static_touch (test_s551_prereg_report.py:72-118). It calls make_quotes, simulate_fills, resolve_marks, markout_strict and fee_kalshi_maker directly, and imports no S551 module.
   - It recomputes the fill set, the fill rate, the +60 s fee-inclusive mean and the missing share, and asserts each against EXPECTED (:134-137). The receipt is asserted equal to EXPECTED at :126.
   - Construct pins (test_s551_cancel_policy.py:128-172) cover game_cell, primary, summarize and wquantile:
     - the 49c two-slice example gives +2 / -2 with per-fill values 1/3 and -3/-1, fee 0.02 per contract;
     - they also cover missing marks with MARKS_INCOMPLETE, and primary returning None.
3. MET. Exclusions are split.
   - The counters are separated at exec_policy_stats.py:147-165 and receipted at report.py:240.
   - Test: test_s551_cancel_policy.py:160-167 expects (1, 1, [0, 0]).
4. MET. Tape-trigger power.
   - Case 21 (test_s551_replay.py:152-178) shifts receipts by 17-77 s and created times by +-9 s.
   - It asserts that the exact cancel (decision_us, reason) set and the quote ids equal a tape-free reference, and that the fills differ.
   - M2a and M2b die (my run).
5. MET. Holm BEHIND.
   - test_s551_prereg_report.py:201-204: p_behind < 0.05 <= holm_p_behind gives NULL.
   - The code is at stats.py:237 (hb[k]). M8 dies (my run).
6. MET. Uptime.
   - quoted_us = covered_us over credit_spans (stats.py:104, replay.py:135-144), with the same 10 s cap as eligible_us.
   - Test: test_s551_replay.py:214-223 uses a 30 s gap and asserts uptime <= 1.
7. MET, with a correction. The memo is updated:
   - peak 335.8 MiB, about 78 MiB per game, >= 5 games exits 5 (memo:112-114);
   - the shared window end (:115-118);
   - the changed cells of expected.json (:119-124). I diffed these against scratchpad/s551_expected_r1.json: exactly the 8 quote_uptime values, the 4 quoted_us values, 4 x pair_no_mark60 = 0 and the 2 refusal zeros. Fill, markout, fee and verdict are unchanged.
   - The inventory rows for the 11 owned files match the current bytes and sha256 (LF).

## Round-1 MET items
No regression: A2, A5, A7, B1-B10, Q1-Q9 and items 1-11 still hold.
- Every module is 300 LOC or fewer and ASCII-only.
- The candidate edits no must-not-move file.

## Imports and reads
Every non-owned import is tracked on master:
- capture_book_adapter, exec_quality_audit(_io, _pool), markout_causal, quote_engine, seal_provenance, tape_fill_adapters, tape_fill_sim, venue_fees, venue_time;
- execution/ is a namespace package, as on master;
- the s550_real fixtures x3.

Every other file a test reads is in the owned list.

.gitattributes: master's 45 lines are unchanged, plus exactly the 3 s551 lines (s551_real/**, s551_*.json, exec_policy/*).

## CORRECTIONS (lander)
C1. Memo inventory (memo:192, :204) is stale after the fast-forward.
- It still says "verification base 4b9661123".
- Its .gitattributes row says 43 lines / sha 0dc09e4c. The file now has 48 lines / sha c47b9a7c... (LF).
- Regenerate both at lane_commit, per the memo SHA rule.

C2. Master moved one pinned must-not-move file between base 4b966 and HEAD: forward_replay_io.py (S496 landed 27ae6b756).
- S551 does not import it (checked via sys.modules), and test_seal_record_pins_base_blobs pins base blobs, so the test still passes.
- Disclose this in the memo, or re-baseline seal base_sha at landing.

## NOTE
- The round-1 notes 4, 5 and 7 stand as disclosed.
- The base-blob pin fails in a shallow clone.
- The CONFIRMATORY / `seen` path still has no test.

## NOT VERIFIED
- The tests have not been run on a master commit, because the candidate is uncommitted.
- The real PREREG commit and --check.
- Scored mode on real days.
- Py3.12.
- The incidence of malformed ladders in the live archive (data/ was not read).
