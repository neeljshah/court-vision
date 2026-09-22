GAP S401 | sport all captured | worktree harness-h62 (master-based) | log opus_s401_state_recovery
# State capture: per-item full-shard recovery makes the first tick take hours (found 2026-09-22 on the supervised relaunch)

SINGLE PROBLEM: scripts/platformkit/ingame/local_state_capture.py line 172 calls writer.recover_states(now, [sport]) for EVERY
polled item whose key is not in state['last_state']; recover_states (local_state_capture_io.py:153) re-reads the sport's
yesterday + today shards in full on each call. The init recovery (line 103) keeps only non-final states, so every final game and
every newly seen game triggers a full re-read. MEASURED on the 2026-09-22 15:39Z relaunch from master under the supervisor: after 25
minutes the child (pid 30528) had 914 CPU-seconds, a 1.0 GB working set, zero rows written and no heartbeat for any sport; the
tennis shards it re-reads are 162 MB (2026-09-21) + 52 MB (2026-09-22) for 391 tracked games. A UTC day rollover resets last_state
(lines 97-101) and would repeat the storm during tonight's games; the frozen bar 'maximum state receipt gap <= 30 s' (S362 AMENDMENT
2, Q-2) cannot survive it.

BINDING BEFORE-CONDITION: quote lines 95-110 and 160-180 of local_state_capture.py and recover_states / recover_rows of
local_state_capture_io.py from master; run the per-file tests tests/platformkit/ingame/test_local_state_capture.py and
tests/platformkit/ingame/test_state_capture_io.py and quote the pass counts; write a shard-open-count test that builds a synthetic
shard of 2000 rows for 50 keys and counts how many times recover_rows opens the shard during ONE tick that polls 50 unseen keys
(expected today: 50; required after the fix: 1) and quote today's count in the memo.

CHANGE (owned files: scripts/platformkit/ingame/local_state_capture.py and tests/platformkit/ingame/test_local_state_capture.py
ONLY; local_state_capture_io.py is NOT edited; row S393 (worktree h52) also edits local_state_capture.py -- rebase this worktree on
master after S393 lands, before the verifier round):
1. Recover ONCE per (tick, sport): the init recovery keeps the FULL recovered map (final states included) in state['recovered']
   (never pruned within the day) while last_state keeps its present non-final semantics unchanged; the per-item path at line 172
   consults state['recovered'] first and calls writer.recover_states at most ONCE per sport per tick (memoized in a per-tick dict)
   and only for keys absent from both maps; the day rollover rebuilds state['recovered'] once. Every row the capture writes must be
   byte-identical to today's for the same inputs (the same previous-state semantics: a recovered previous state is still carried per
   field; state_changed is computed against it).
2. Tests: the shard-open-count test (exactly 1 open after the fix); a final game seen again after init still gets its previous state
   from the recovered map; a key absent from both maps triggers one recovery for its sport and a second such key in the same tick
   triggers none; the rollover rebuilds once; every existing test in both files passes unchanged.
3. Memo docs/evidence/harness/S401_state_recovery_cost_2026-09-22.md with the measured facts above.

CONTROLS: construct tests only; no network; never touch the running capture, its archive or its lock; relaunching the state capture
on the fixed code is recorded in NOW.md as the orchestrator's next step (a STOP sentinel is never written by an agent).
ACCEPTANCE: per-file tests pass one at a time; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 16:2xZ; binding; landing order). S401 lands BEFORE S393 because tonight's games depend on it: the S401
worktree (h62) is verified and landed from master as it stands, and row S393 (h52) rebases its candidate onto master AFTER S401 lands,
before its next verifier round. The sentence in CHANGE about rebasing h62 after S393 is superseded. Measured on the candidate (Opus
build, 2026-09-22 16:1xZ): one tick polling 50 unseen keys opened the shard 51 times on master and once after the fix; two unseen keys
in one tick open it once (plus one at init and one at the day rollover); 19 + 13 + 73 + 25 + 11 tests pass one file at a time.

AMENDMENT 2 (2026-09-22 17:0xZ; binding; after the Opus verifier round 1 REJECT). (a) The per-tick RESCAN IS REMOVED: after the
init recovery (and after the day-rollover rebuild) the recovered map is authoritative -- under the single-writer lock every row this
process writes updates the map, so a key absent from both maps has no archived state and no recover_states call is made inside a
tick at all (the verifier proved the rescan was a guaranteed-useless full re-read AND that its recovered.update(...) clobbered
entries mirrored from rows not yet committed, making the written row depend on scoreboard item order: a game finalized in tick T and
re-polled in tick T+1 wrote state_changed True where master writes False). (b) The fix ships a DIFFERENTIAL test: master's per-item
lookup (reimplemented in the test from the quoted master lines) against the candidate over a randomized scoreboard sequence (at least
60 seeds, several games, several ticks, both item orders) with ZERO divergences on every non-timestamp field; plus the explicit case
of a final game pruned in the same tick that a new key first appears, then re-polled. (c) The open-count test counts recover_rows
CALLS; state that fact in the test name and assert exactly one call at init, one at rollover, none inside a tick.
