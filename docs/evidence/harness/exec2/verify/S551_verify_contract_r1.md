VERDICT: REJECT (narrow fix pass: findings 1 and 2; everything else MET or NOTE)

S551 contract-tier verifier, round 1 (Opus standing in for sol). Candidate = uncommitted files in nba-harness-h222 (HEAD 4b9661123db7a664d6c8f3dc5fd9714e01bbca1e); master = e34ca335c0820f58991f74b4813d81754eaf4808.
Per-file tests reproduced: test_s551_cancel_policy 17 passed, test_s551_replay 12 passed, test_s551_prereg_report 10 passed.

## Findings (ranked)

1. BLOCKING (optimistic fill, silent on reachable input). Files: scripts/platformkit/execution/exec_policy_replay.py:227-228 and :322, with tape_fill_sim.py:53-58.
   - What happens: when to_fill_snapshot refuses a row that to_quote_book accepted, the refusal is dropped with no counter. phase2 then passes only the snapshots of other submit instants. tape_fill_sim._queue takes the latest snapshot at or before the submit, so the order is given an OLDER instant's queue. Item 6 forbids this ("the replay never passes an older row"; a missing level must be the UNKNOWN sentinel).
   - Repro: book at 0 s 49/51 with a yes ladder [[0.49,5],[0.48,0]]. Book at 30 s 48/50 with the yes ladder [[0.48,3],[0.48,900]], which is refused `conflicting_level_size` while the quote book is fine. Run cancel_on_book_move under displayed_depletion with a 1-lot yes-48 print at 45 s. Result: fill_snaps holds only the 0 s snapshot; the 30 s refresh at 48 gets queue_ahead_at_submit '0' and fills touch_queue. The correct result is an UNKNOWN queue and no fill.
   - Reachability: 0 of 74 snapshots on the fixture, but it is reachable on any malformed ladder.
   - Fix: count `fill_snapshot_refused`. In phase2, give every submit instant without its own snapshot a level-less snapshot at that instant ({"ticker", "ts": iso(t), "yes": [], "no": []}) so that _queue returns UNKNOWN. Add one construct test (the repro above).
   - Also count to_mark_tick refusals (:220), which are dropped silently too.

2. BLOCKING (a contract item is not met: ACCEPTANCE RULE, NON-TAUTOLOGY).
   - What happens: s551_expected.json was produced by the new modules themselves (test_s551_prereg_report.py:3-6; memo NOT VERIFIED). The only independent oracle (:76-103, :118) re-derives the static_touch x through_only FILL SET. No markout, fee, weighting, uptime or fill-rate number is checked independently, and no construct test exercises game_cell, primary, summarize or wquantile.
   - My probe of the arithmetic is correct. It used synthetic fills at 49c, two 0.5 slices, fee_units 0.01 and a 0 fee, with YES mid 0.52. The game mean came out +2.00 (YES) and -2.00 (NO), and the per-fill values 1/3 and -3/-1 match (sum(qty*gross) - sum(fee))/sum(qty) (N5). Nothing pins this, though.
   - Fix, two parts:
     - (a) Extend the oracle to compute the static_touch|through_only +60 s net mean, the missing share and the fill rate via resolve_marks + markout_strict directly, and compare them to EXPECTED["cells"].
     - (b) Add a construct test of game_cell and primary with the probe above (YES and NO, a fractional slice, a missing mark giving `mark_*` and MARKS_INCOMPLETE).

3. CORRECTION: exec_policy_stats.py:320-323.
   - pair_no_fill merges "no fill" with "fills but every +60 s mark missing".
   - Fix: count them separately (`pair_no_marked_fill`) so B1 names the excluded set exactly.

4. NOTE: exec_policy_report.py:147-148 and exec_policy_replay.py:287.
   - The submit window end (the final row or the cap) is derived from the whole day's state rows. That is hindsight, but it is arm-neutral and mandated by the spec's grid definition.
   - Case 20 passes the full-data window to the truncated runs. Disclose this in the memo.

5. NOTE: test_s551_prereg_report.py:283-289.
   - The test runs `git show <fixed base_sha>:path`. That is live git objects but not a moving ref, so it is acceptable. It fails in a shallow clone.
   - It checks the base blobs, not that the working files are unmoved. I verified that part by git diff: the candidate edits no MUST-NOT-MOVE file.

6. NOTE (memo SHA rule): master moved 4b9661123..e34ca335c on HARNESS_GAPS, the S496/S503/S511/S561 specs and ops/per_file_test_sweep.py.
   - None of these is owned or imported by S551, so there is no overlap and the lander regenerates the SHAs.

7. NOTE: a crash between the ledger writes (report.py:257-263) and the receipt leaves the date at exit 4 until someone cleans up by hand. This is disclosed. Also, CONFIRMATORY labelling and the `seen` path (report.py:195, :252) are never exercised by a test.

## Contract walk
A1 NOT VERIFIED: the candidate is uncommitted, so its tests could not be re-run on master. They were run in the worktree.
A2 MET: the receipt was reproduced via the test's pin, and the arithmetic by my own probe.
A5 MET: new files only; the .gitattributes change adds exactly the 3 specified lines.
A7 MET: the memo's fixture paths are tracked on master.

B1 MET, except finding 3.
B2 MET: new files only.
B3 MET: report.py:145-146 excludes and counts non-OK census games; tape_provisional is counted (replay.py:355-356).
B4 MET. B5 n/a. B6 MET.
B7 MET: the whole fixture game is used.
B8: the pinned file is not claimed as independent, but finding 2 applies.
B9 n/a.
B10 and Q3 MET: 0.3 / 0.05 / 0.5 / 30 / 5000 / seed 7 / Holm 4 match AMENDMENT 1 (stats.py:198-199; prereg.py:61).

Q1 MET: prereg.py:103-133; the seal mismatch, body mismatch, not-committed and date boundaries are tested (test_prereg_report:205-221).
Q2 MET: K is read at launch, before the replay (report.py:218).
Q4 n/a: no OOS model.
Q5 MET: AHEAD_SINGLE_WINDOW (stats.py:396).
Q6 MET: a word-boundary grep over the modules, memo and expected file is clean.
Q7 MET: floor 30 PAIRED, all cells (stats.py:381); 29 vs 30 tested (:177-190).
Q9 MET: games.jsonl holds per-game cells for both arms with game_key, and comparisons hold the diffs.

Items:
- 1 clocks MET: to_us, tested (replay.py:157-169).
- 2 order MET: tests 9-14; causal ordering and the pending-cancel fill are shown at :186-198.
- 3 latency and N2 MET: replay.py:177-185; C > S exits 2 (case 16).
- 4 arms v1 MET: exec_cancel_policy.py:76-107.
- 5 signature MET.
- 6 scenarios: NOT MET, see finding 1. B3 (one call per arm, scenario and game) is MET (report.py:162-166).
- 7 metric MET: arithmetic probed; B5 symmetric rule at stats.py:393-396.
- 8 prereg / seal / exploratory MET: scored-date refusal tested (:224-245); EXPLORATORY and DESCRIPTIVE labels tested (:112, :119); exploratory --out under exec_policy exits 2 (:162-168).
- 9 and B6 tape completeness MET: tested (:248-260).
- 10 ledger / receipt / B1 pooling / B2 roots MET: tested, including prior_sidecar_mismatch, duplicate_game_across_dates and the exit codes 3, 4 and 5.
- 11 risk gate MET: tested (:263-280).
- Priority loss MET: case 15.
- raw_market stripped MET: mirrors the landed live_shadow_quoter.py:125; disclosed in memo item 2.

Other checks:
- Imports and reads: every file the tests import or read is committed on master, including the s550_real fixture and exec_quality_audit*. The orchestrator override for s550_real is disclosed.
- .gitattributes covers s551_*.json and exec_policy/*.
- Every file is 300 lines or fewer and ASCII-only; the memo ends with a NOT VERIFIED list.

## NOT VERIFIED
- The tests have not been run on master (the candidate is uncommitted).
- The real PREREG commit and `--check` in the real repo.
- Scored mode on real days.
- Py3.12.
- The frequency of ladder conflicts in the live archive (data/ was not read, per the RAM rail).
- The CLI byte-equality was checked only through case 28, not re-run by hand.
