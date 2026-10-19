# S515 FIX 3 candidate: local MLB shadow quote recorder

Construct and copied-fixture verification only, in C:/Users/neelj/nba-harness-h180.
Authority: docs/evidence/tracking/specs/S515_spec.md, including A1, A2, A3 and A4.
This repair follows _verdict_s515_3.md and every binding Amendment 4 correction.
No deployment, flag change, external service or real archive was used by this lane.

## Pinned before seal
```json
{
 "scripts/platformkit/execution/capture_book_adapter.py": "d1a3ce8325d0142cf71d87ef0c6cfdc59a66f6e6dada055d968c2a1dcfa35b5a",
 "scripts/platformkit/execution/quote_engine.py": "878a345d68c4551a0c383983857ed487a5ce79a651b7e69b0d32571581abda30",
 "scripts/platformkit/execution/thresholds.py": "084749fd4c51b130c7a27a9dfad9f8cb5d674ed9fdd278523dd6d97be4c9a946",
 "scripts/platformkit/execution/venue_time.py": "fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3",
 "scripts/platformkit/ingame/blend_apply.py": "9f9ec929236c5a8f92f1fa8b01e6f1b5ed58b6708fdae6477f07703c7c3cdbdb",
 "scripts/platformkit/ingame/capture_watchdog.py": "9c82101dafc961c621cc8f264dbc988ee8c46133ceb045fd9b42239b12f08bbd",
 "scripts/platformkit/ingame/local_capture_writer.py": "ef36aff93500d7c9c71d5de8bd21deea811eb2131a0e242e09af32f65c4a5c2e",
 "scripts/platformkit/ingame/mlb_live_model.py": "921d2f547c46b861989429f01d698695f76e024c313a94497fbb566033c678a6",
 "scripts/platformkit/ingame/quote_freshness.py": "106529b5a1e6cd3e93dc593e9a145ef21bc6c4e792e9e271d4f1724630f0c008"
}
```

Seal source: committed base 50957aecf06a783d7a73a37ac12fee198416285e; SHA256 of LF-normalized module bytes. Only the nine A2h immutable modules are tested. No mutable schedule or byte-length pin is tested.

## Implementation and required disclosures
The core is pure and emits independent intents. The CLI is opt-in. No capture module, caller, feature flag or schedule was edited.
Venue clocks use parse_venue_time; the original fraction is retained as Decimal for strict visibility and cutoff comparisons. Equal capture clocks retain the specification's later-list-position tie rule. Initial p0 is derived only after its cutoff becomes observable. A p0 candidate needs a pre state at or before its book timestamp, with no non-pre state visible then. A1e caps initial p0_age_s at 3600 seconds, superseding the original unrestricted age; once accepted the prior stays frozen.
The adapter receives a copy with raw_market removed because that separately timed touch can disagree with the book. Raw close_time is still an explicit fallback. Quote yield is limited by capture cadence and has no acceptance bar. The mid arm ignores missing or stale state; unknown status and finality still stop both arms. State-change pull is disabled. Middle and End map to half index 2.
The venue_prior_state_blend arm is a venue pregame midpoint plus state residual, not an independent prior. Calibration with this substituted prior remains unvalidated. Orientation uses ticker code versus state abbreviations; yes_sub_title is not consulted.
Inventory stays zero and rooms stay one per side. These are independent intents with unknown fills; they must never be read as a position history. Each side has a unique id. Cancellation is derived from the next arm row or expiry after two tick intervals, whichever comes first. Capture and decision clocks are assumed to be on the same box; fixtures cannot verify that assumption.
Owned quantity and fee inputs remain Decimal/string. The unchanged quote_engine has an internal float fee-search path; its decimal_fees output is checked by the wrapper. Defensive limits reject rather than clamp malformed books, oversized counts and implausible decimal exponents.
The bounded reader uses capture_watchdog.decode because tail_rows accepts an unterminated final JSON record. Capture shards are never repaired or written. ssl and http.client arrive transitively through game_market_link; owned modules make no network call.

## Ownership and line endings
Owned modules: scripts/platformkit/execution/live_shadow_quoter.py, live_shadow_io.py and the A2j extraction live_shadow_cli.py. Owned tests: tests/platformkit/execution/test_live_shadow_quoter.py, test_live_shadow_io.py and the new row-specific test_live_shadow_cli.py regression file. The memo, the three existing s515 fixtures and .gitattributes complete the lane scope.
The schedule fixture was re-derived per A2a, dropping only unused selected_at. Its authoritative SHA256 is bd48c732d9be7d4db9eb7e7706b6c5e4f3c7f1e1c63e9f526aa49dd3e97a6744. Books and state fixtures are unchanged. No additional JSON fixture or seal path was introduced.
.gitattributes is rebuilt from committed base 50957aecf06a783d7a73a37ac12fee198416285e plus `tests/platformkit/execution/fixtures/s515_* text eol=lf`. Existing `docs/operations/paper_desk_config.json text eol=lf` and `docs/evidence/forward/desk_audits/*.json text eol=lf` rules are preserved. The seal uses the same full committed base, LF-normalized hashes and no live git state in tests. Mutable schedules are covered only by the landing diff check.

## FIX 1
Historical results below precede FIX 3; A4 replaces the pid/guard protocol.
1. F1 / tier 2 item 1 / A2b: before, `t=1790378700`, `start=1790379600.000000`, three visible books produced `p0_books=["2026-09-25T22:52:59.735967Z"]`. New pre-start regressions failed twice with `assert 1 == 0`. The core now waits for the cutoff; regressions cover start-900, start-1, equality and an earlier visible live state.
2. F2 / tier 2 item 3 / A2c: before, synthetic bounded windows produced `shards 4 bytes 8388608`. D-1 fallback is now allowed only for a missing or complete current source window. The replacement regression requires exactly two reads when both window starts exceed zero, retains source metadata and refuses unmet needs.
3. F3 / tier 2 items 4 and 12 / A2d: identical schedule entries produced `duplicate [] {'schedule_bad_entry': 2}`. Repeated wrong-sport loads produced `tick 0 {'schedule_bad_entry': 1}` then `tick 1 {'schedule_bad_entry': 2}`. A2d formally supersedes the original NOTE: identical content coalesces, conflicting game keys refuse with schedule_conflict, and malformed/other-sport/conflict counts are per-tick gauges.
4. F4 / tier 2 item 9 / A2e: `available=1499, minimum=1500` produced `appended []`. The run identity now precedes the RAM gate; low RAM skips intent rows only. Freshness bars come from the same core defaults used by decisions.
5. F5 / tier 2 item 2 / A2a: A1l expected 95988c1669f2796937b10874d901a6470c54b7d7c9d6a32fa525695a1a183a52; actual was bd48c732d9be7d4db9eb7e7706b6c5e4f3c7f1e1c63e9f526aa49dd3e97a6744. This fix session found the formal A2a ruling already present. The authoritative A2a fixture hash regression passes; the fixture was not changed again.
6. F6 / A2j: fresh reproduction found `missing lines=[]` relative to the pinned base, so the missing-line symptom had already cleared. Rebuilding from that full SHA plus the S515 rule returned `F6 PASS: pinned base plus S515 rule=True`. Final inventory is regenerated below.
7. F8 / tier 2 items 2 and 11 / A2j: memo claimed test SHA d064939794ef5e3c8790d5e6412a64cd5f99bc05f05298857fca30f8253898d1; actual was 0dc6d92d1d930246cefda15f844804ff94088b83b89fd9235f76a3ea70ed5a83. Final file hashes/counts are generated after fixes; stale fixture wording and the dangling conflict sentence are removed.
8. Tier 2 items 5 and 8 / A2f: duplicate earlier .6 priors plus later .7 recovered `{'g': {'kind': 'p0', 'game_key': 'g', 'p0_home': '0.7', 't': 20}}`; the lock module was absent. The new core conflict regression failed with `assert 3 == 2`. Recovery now reads only the p0 side file, chooses the earliest valid prior, and retains a conflict sentinel when probabilities disagree. The core never re-derives a conflicted prior. A process lock protects the output root.
9. Tier 2 item 6 / A2g: inspection returned `independent_oracle=False frozen_p0_path=False`. The oracle now independently parses ISO strings with datetime and exact Decimal epoch arithmetic. It checks all 50 instants on both absent and frozen prior paths, including reversed row order.
10. Tier 2 item 7 / A2h: inspection found `mutable schedules in seal=36`; the old seal also failed on paper_night.py. The amended seal now checks only the nine listed immutable modules against committed hashes. It returned `A2h PASS: immutable seals=9`.
11. Tier 2 item 10 / A2i: injected heartbeat failure produced `raised injected heartbeat`. Exhausted heartbeat writes are now counted and the tick loop continues.
12. A2j authorizes the CLI extraction so each Python file remains within 300 lines. A2's header records an orchestrator PHI@ATL probe: 20 ticks, peak RSS 69.8 MiB, tick latency 0.12 s, mid quoted 19/20 and blend p0_missing 19/20. Those are attributed authority observations, not a run or remeasurement by this lane.

Follow-up review of A2f reproduced two restart hazards: `A2f lock race replaced_live_owner= True` and `A2f recovery failure returned= {} errors= {'lock_exists': 1, 'stale_lock_takeover': 1, 'shard_read_errors': 1, 'p0_conflict': 0}`. Acquisition and stale takeover are serialized by an exclusive guard; side-file read errors count and abort decisions instead of becoming missing priors. Corresponding regressions cover a contender interleaving and injected side-file open failure. FIX 2 supersedes the orphan-guard limitation: a recorded dead owner is reclaimed under exclusive serialization; normal exits release the guard.

Passing minimal reproductions after fixes:
```text
F1 p0_rows at start-900/start-1/start=[0, 0, 1]
A2d served 1 {'schedule_bad_entry': 0, 'schedule_other_sport': 0, 'schedule_conflict': 0}
A2d both ticks {'schedule_bad_entry': 0, 'schedule_other_sport': 1, 'schedule_conflict': 0}
A2c synthetic mock shards 2 bytes 4194304 (the pre-FIX-2 reader itself exceeded this cap)
A2e appended ['run']
A2f recovery {'g': {'kind': 'p0_conflict', 'game_key': 'g'}}
A2i continued {'heartbeat_write_errors': 3, 'heartbeat_errors': 1}
```
The full regression files pass below, including lock contender exit 3 without replacement, recovery read-error abort before arms, independent truncation, immutable seals and the A2a fixture hash. Follow-up read-only review approved the observable-cutoff, conflict, oracle, seal, lock-interleaving and read-error fixes.

## FIX 2
Historical results below precede FIX 3; A4 replaces the pid/guard protocol.
1. Verdict finding 1 / A3a: before, `tail_bytes=100 read_bytes_tick=101`; after, `tail_bytes=100 read_bytes_tick=100`. The reader now seeks directly to window_start and always drops the first segment when truncated, including newline-aligned starts. Both cap regressions pass. The existing two-shard test asserts `read_bytes_tick <= len(shards_read) * tail_bytes`, without the extra byte allowance.
2. Verdict finding 2 / A3b: before, `attempts=['run', 'arm'] durably_accepted=['arm']`; after, `exit=4 attempts=['run', 'run', 'run'] durably_accepted=[]`, with stderr `run_row_failed`. The loop requires exactly one returned run row after complete write and fsync. Tests cover empty, wrong-kind and multiple-row returns, write/fsync/short-write/repair failures, and successful third-attempt recovery before any arm.
3. Verdict finding 3 / A3j: the dead-guard reproduction raised `SystemExit: 3`; a live guard emitted empty stderr. Guards now record pid and nonce; dead-owner takeover counts stale_guard_takeover, while a live or unidentified owner refuses with guard_busy. A reclaim interleaving initially failed `DID NOT RAISE`; generation-specific exclusive reclamation plus ownership rechecks now passes. Replacement-owner bytes are preserved. No live process was started or stopped by these constructs.
4. Verdict finding 4 / A3k: the FIX 1 base cited 50957aecf06a783d7a73a37ac12fee198416285e. FIX 2 inventory/landing base is pinned to 6ec825b08da604b6df20c9eb2dfbb2a36ce2b2ce, resolved once before edits; subsequent base checks use that literal. Immutable seal provenance remains the older committed source, and its nine hashes pass. File hashes and counts below are regenerated from final bytes. No test or memo check reads a moving ref.
5. A3c: repeated recovery failed `assert 2 == 1`. Recovery replaces its conflict gauge; each heartbeat derives the number from the in-memory sentinel map. Repeated recovery and two write-error ticks now both report one conflicted key.
6. A3d: empty, malformed and invalid-owner locks raised `SystemExit: 3`. While holding the acquisition guard these are now replaced and counted corrupt_lock_takeover. All five corrupt-lock constructs pass.
7. A3e: refusal tests failed on empty stderr instead of lock_busy/guard_busy, and an injected acquisition error escaped as `OSError: injected lock open`. Each lock refusal now prints exactly one requested ASCII token before exit 3; exhausted identity writes print run_row_failed before exit 4. All exit-token regressions pass.
8. A3f: before, `[('mid', 'quoted', 1), ('venue_prior_state_blend', 'p0_conflict', 1)]`; after, `[('mid', 'quoted', 0), ('venue_prior_state_blend', 'p0_conflict', 0)]`. Only the matching sentinel is excluded from p0_record_refused; malformed-prior counters remain one. The original conflict refusal and frozen-prior behavior stay intact.
9. A3g: synthetic new-game plus write-error recovery failed `assert 4 == 2`. Recovery now occurs once at startup and again after write errors; new keys use the in-memory map. The regression observes exactly two recoveries.
10. A3h: startup recovery during a low-RAM tick failed `assert 0 == 1`; inspection showed the old schedule gauges initialized to zero. Startup recovery now precedes the RAM gate and low-RAM schedule gauges are null. The regression asserts one startup recovery and all three null gauges.
11. A3i: injected first main write failure failed `assert not True` because the p0 side file already existed. Main-shard writes now precede side-file appends; the regression confirms no side file on main failure and matching persisted priors after success. Existing torn-side-file injections now target the second p0 write, retaining the verified recovery cases.
12. Verdict finding 5: all original core and I/O tests still pass. No imported module, freshness bar, immutable seal, fixture byte, mutable schedule or existing caller was changed in FIX 2.

Before implementation, the new regression file reported `21 failed`; after required corrections and additional short-write/guard-interleaving checks it reports `26 passed`. Original core and I/O files report `83 passed` and `28 passed`. The first I/O rerun exposed four injection failures after the required ordering/owner changes; injections now target the side file and distinguish the live guard PID, and all 28 pass.

A4 supersedes the former operator cleanup protocol. The recorder now holds an OS lock for its lifetime; legacy guard/reclaim files are ignored and lock-file contents never decide ownership. No manual crash-residue cleanup is required.

Attributed orchestrator observations, not rerun here: Amendment 2 records 20 PHI@ATL ticks, peak RSS 69.8 MiB, tick latency 0.12 s, mid quoted 19/20 and blend p0_missing 19/20. Amendment 3 records 12 ticks, peak RSS 65.3 MiB and 4,194,306 bytes across two shards before FIX 2. That byte count exceeded the exact 4,194,304-byte two-shard cap. This lane supplies construct/fixture checks only, with no new capacity measurement.

## FIX 3
1. Blocking finding 1 / A4b: before edits, injected main fsync failure produced `accepted=0 main_rows=1 side_rows=1 write_errors=1 p0_side_file_errors=0`. The writer now stages p0 payloads, fsyncs the main shard, then writes and fsyncs the side file. After: `accepted=0 main_rows=1 side_rows=0 write_errors=1 p0_side_file_errors=0`. The regression requires no returned row and zero side rows when main fsync fails.
2. Blocking finding 2 / tier 2 items 3, 4 and 7 / A4a: before edits, both `dead_guard_orphan_claim: exit=3 guard_busy=1` and `empty_guard: exit=3 guard_busy=1` reproduced. After replacement both print `acquired=True guard_busy=0`. A4 explicitly replaces the earlier exact guard-reclamation fix: guard, reclaim and pid-liveness code/counters/tests are removed. The descriptor holds msvcrt.locking on Windows or fcntl.flock elsewhere until close; pid/nonce bytes are informational. Subprocess regressions hold a real lock, verify a second CLI exits 3 with exactly `lock_busy` and zero rows, then verify restart after normal exit and forced termination. Empty, garbage, invalid-pid and current-live-pid contents cannot block an unlocked file.
3. Tier 2 item 1 / A4b: before edits, side write failure produced `accepted=0 main_rows=2 side_rows=0 write_errors=1 p0_side_file_errors=0`; side fsync failure produced `accepted=0 main_rows=2 side_rows=1 write_errors=1 p0_side_file_errors=0`. A main-durable p0 is now returned and frozen even if the side write/fsync fails; failures count p0_side_file_errors. After side write failure: `accepted=1 main_rows=1 side_rows=0 write_errors=0 p0_side_file_errors=1`; after side fsync failure: `accepted=1 main_rows=1 side_rows=1 write_errors=0 p0_side_file_errors=1`. Regression coverage includes repeated ticks without re-deriving the prior.
4. Tier 2 item 2 / A4c: before edits, `assert True is None` failed for the skipped tick's idle gauge. It is now null when RAM prevents schedule inspection; the existing schedule gauges remain null.
5. Tier 2 items 5 and 6 / A4d: before edits, startup and post-write recovery raised `ValueError: p0_recovery_failed`; an unrepaired output raised `ValueError: unrepaired_output`. Both now print exactly their ASCII token to stderr and exit 5, releasing the OS lock. Regressions exercise startup and tick paths and a subsequent successful restart. A real main-repair OSError regression then failed with `DID NOT RAISE <class SystemExit>`; both short and raised repair failures now print `unrepaired_output` and exit 5. The run row gets 3 attempts in total, as the unchanged A3b checks require.
6. Verdict notes 3 and 4: exact-tail reads, mandatory run identity and A3c-A3h behavior are retained. Inventory base remains pinned to 6ec825b08da604b6df20c9eb2dfbb2a36ce2b2ce; no moving-ref test or memo check was introduced. No fixture or seal path was added, so the existing `tests/platformkit/execution/fixtures/s515_* text eol=lf` rule covers all row fixtures.

Before module edits the updated CLI test file reported `6 failed, 18 passed`; the failures covered idle, acquisition token and four recovery/output exits. With the OS-lock implementation and the added live-pid-content case it reports `27 passed` after the final main-repair cases. Tests use TEMP/TMP under this worktree to resolve the verifier's unwritable temporary-directory limitation. FIX 3 uses construct/fixture inputs only. File inventories below are generated from final bytes.

## Landing rulings (orchestrator 4, r4: sol ACCEPT WITH CORRECTIONS, Opus tier 2 ACCEPT WITH CORRECTIONS, 0 blocking)
- Orchestrator re-probe after FIX 3 on the live PHI@ATL game at 19:23Z (not a lane measurement): 6 ticks, peak RSS 55.9 MiB, exactly 4,194,304 bytes read per tick over two shards, all six ticks `stale_book` on both arms because the capture's bulk cadence for that ticker was 11-30 s at the time. This does not satisfy the owed two-game bounded run (S517).
- Ruling (Opus r4 item 1): an unrepairable torn intent shard hit while writing the mandatory run row exits 4 `run_row_failed` (A3b precedence during the run-row phase); after the run row, the same condition exits 5 `unrepaired_output` (A4d). Both fail closed with zero arm rows.
- Disclosure (Opus r4 item 2): any OSError in the lock phase (mkdir, open, lock, identity write) reports `lock_busy`; the token means "lock not acquired", not only contention.
- The guard/reclaim narrative above is historical; AMENDMENT 4 replaced it with the OS lock.

## Reproduction
Run each test file separately, from this worktree:
```text
python -m pytest tests/platformkit/execution/test_live_shadow_quoter.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_live_shadow_io.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_live_shadow_cli.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.live_shadow_quoter --help
python -m scripts.platformkit.execution.live_shadow_io --help
python -m scripts.platformkit.execution.live_shadow_cli --help
```
Case 22 stages the copied fixtures under temporary roots and runs the CLI twice with --replay-start 2026-09-25T23:58:00Z --max-ticks 12 --every-s 15. Comparisons exclude process ids, nonce, emission clock and derived quote ids. Run identity is checked separately because argv has different temporary paths.

## Generated final inventory

Enumerated acceptance cases: 22/22. Core tests: 83 passed; I/O tests: 31 passed; CLI tests: 27 passed; total: 141 passed. CLI help: 3/3 passed. No separate self-check flag is defined; construct/fixture tests exercise the checks.

| Case | Test functions |
| --- | --- |
| 1 | `test_live_shadow_quoter.py::test_case01_availability_equality_and_nextafter` |
| 2 | `test_live_shadow_quoter.py::test_case02_invalid_clocks`; `test_live_shadow_quoter.py::test_case02_conflicting_clock_count` |
| 3 | `test_live_shadow_quoter.py::test_case03_book_age`; `test_live_shadow_quoter.py::test_case03_state_age` |
| 4 | `test_live_shadow_quoter.py::test_case04_refusal_precedence` |
| 5 | `test_live_shadow_quoter.py::test_case05_status` |
| 6 | `test_live_shadow_quoter.py::test_case06_market_status` |
| 7 | `test_live_shadow_quoter.py::test_case07_missing_prior` |
| 8 | `test_live_shadow_quoter.py::test_case08_orientation_and_alias` |
| 9 | `test_live_shadow_quoter.py::test_case09_fraction`; `test_live_shadow_quoter.py::test_case09_strict_counts` |
| 10 | `test_live_shadow_quoter.py::test_case10_cutoff_join_and_stale`; `test_live_shadow_quoter.py::test_case10_observable_cutoff` |
| 11 | `test_live_shadow_quoter.py::test_case11_bad_prior`; `test_live_shadow_quoter.py::test_case11_frozen_prior`; `test_live_shadow_quoter.py::test_case11_conflict_never_rederived` |
| 12 | `test_live_shadow_quoter.py::test_case12_model_and_quote_goldens` |
| 13 | `test_live_shadow_io.py::test_case13_midnight_selective_previous_and_schedule`; `test_live_shadow_io.py::test_case13_window_miss_metadata_and_final_not_repeated`; `test_live_shadow_io.py::test_case13_future_malformed_identity_and_non_snapshot_fallback` |
| 14 | `test_live_shadow_io.py::test_case14_complete_lines_only_and_bounded_snapshot` |
| 15 | `test_live_shadow_io.py::test_case15_restart_recovers_and_nonce_unique`; `test_live_shadow_io.py::test_case15_recovery_time_order_future_duplicates`; `test_live_shadow_io.py::test_case15_submicrosecond_recovery_boundaries` |
| 16 | `test_live_shadow_quoter.py::test_case16_invariance_and_order` |
| 17 | `test_live_shadow_io.py::test_case17_low_ram_and_idle_until`; `test_live_shadow_io.py::test_case17_activity_window` |
| 18 | `test_live_shadow_io.py::test_case18_write_failure_repairs_and_atomic_heartbeat`; `test_live_shadow_io.py::test_case18_combined_torn_prior_recovery_freezes_before_next_decision` |
| 19 | `test_live_shadow_io.py::test_case19_strict_round_trip_fresh_process` |
| 20 | `test_live_shadow_io.py::test_case20_import_graph` |
| 21 | `test_live_shadow_io.py::test_case21_malformed_duplicate_schedules` |
| 22 | `test_live_shadow_io.py::test_case22_real_rows_cli_end_to_end`; `test_live_shadow_quoter.py::test_case22_real_fixture_end_to_end` |

Fixture replay: 2 runs; normalized outputs identical (per-file case 22). Each emitted `{"arm": 24, "p0": 1, "run": 1}`. Per-arm reasons (no yield bar):
```json
{
 "mid:quoted": 5,
 "mid:stale_book": 7,
 "venue_prior_state_blend:quoted": 5,
 "venue_prior_state_blend:stale_book": 7
}
```

| Path | Bytes | Lines | SHA256 |
| --- | --- | --- | --- |
| `scripts/platformkit/execution/live_shadow_quoter.py` | 15324 | 290 | da2b3afaf427b9900104a7df92a7e7bdc29769e64f6ab6c9cfc859ee3c4c21a0 |
| `scripts/platformkit/execution/live_shadow_io.py` | 13187 | 253 | aed768e08753d7917aef46ed0eaf3249fe4b5a8a90642a8ef3f29f4f53b6d9e2 |
| `scripts/platformkit/execution/live_shadow_cli.py` | 8994 | 173 | 2ae87f86420c40ec1a6e906fa256fb598404e763cf21e96208e7d486591d7ae1 |
| `tests/platformkit/execution/test_live_shadow_quoter.py` | 14099 | 290 | a210b2701c7fc0de2bdc3ddfa0e3cc6eac0b25a22d2f80a0dbc5b53dccca9c0a |
| `tests/platformkit/execution/test_live_shadow_io.py` | 21402 | 300 | d646a3ae0db746636b769efc54fe7fdd0d950216d4e8d16ad66100858ce62420 |
| `tests/platformkit/execution/test_live_shadow_cli.py` | 10938 | 244 | 9925133f55a3387026d995e62b6de9b644b0eea655508fd27b12a18fe428b900 |
| `tests/platformkit/execution/fixtures/s515_real_books.jsonl` | 124926 | 26 | 3d8bcb29f85490542e7b4f23da78b6ebc9b22badfda07609ae7417995211e782 |
| `tests/platformkit/execution/fixtures/s515_real_schedule.json` | 223 | 10 | bd48c732d9be7d4db9eb7e7706b6c5e4f3c7f1e1c63e9f526aa49dd3e97a6744 |
| `tests/platformkit/execution/fixtures/s515_real_state.jsonl` | 13677 | 12 | 5558b08dcdfc76193dc80998c85050fea4395f6779c2eec3c0e719ac1d63e65f |
| `.gitattributes` | 1553 | 26 | e2da0f2226291b75189ce3e4937e326780b6fa76339b68067f3374e7b92d9091 |

Inventory regenerated by a local Python script from final file bytes, AST case names, fresh per-file pytest/CLI outputs and copied-fixture output shards. FIX 3 inventory base: 6ec825b08da604b6df20c9eb2dfbb2a36ce2b2ce. Owned bytes are ASCII. The nine immutable LF-normalized seals pass; schedule diff against the pinned full base is empty.

## Contract preflight
Required preflight: 9/9 checks PASS over the eleven owned paths, excluding the verdict. The command uses --base master only as explicitly required by dispatch; tests and the memo seal use the full pinned base.
```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/live_shadow_quoter.py scripts/platformkit/execution/live_shadow_io.py scripts/platformkit/execution/live_shadow_cli.py tests/platformkit/execution/test_live_shadow_quoter.py tests/platformkit/execution/test_live_shadow_io.py tests/platformkit/execution/test_live_shadow_cli.py tests/platformkit/execution/fixtures/s515_real_books.jsonl tests/platformkit/execution/fixtures/s515_real_state.jsonl tests/platformkit/execution/fixtures/s515_real_schedule.json .gitattributes docs/evidence/harness/S515_live_shadow_quoter_2026-09-29.md --base master --spec docs/evidence/tracking/specs/S515_spec.md
```
Checks: vocab, crlf, loc, schema, head_slice, spec_threshold (9 literals), proposed, removed_artifact and row_duplication. No files were committed or deployed.

## NOT VERIFIED
This lane ran no live or supervised session, fill, other sport, real archive, real p0 age distribution or capacity run. Calibration with the substituted venue prior remains unvalidated. The unchanged engine's internal float search remains outside this row.
After landing the orchestrator owes a bounded run covering at least two live MLB games, ideally 30 minutes, with peak_rss_mib compared to 120 MiB, per-reason counts and CPU observations. Fixture checks do not supply those measurements.
