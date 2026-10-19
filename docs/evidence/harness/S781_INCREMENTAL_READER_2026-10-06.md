# S781 -- live shadow recorder: incremental per-ticker book reader (PAPER ONLY)

Branch cxp/S781-2026-10-06 (worktree /c/Users/neelj/wt-S781). NOT LANDED. Two verifier tiers requested.

## Seal check (before build)
- PREREG_S519 code_identity hashes live_shadow_quoter.py, blend_apply.py, mlb_live_model.py (the quoting
  policy: `decide`, the p0 rule, the blend). The reader (`live_shadow_io.read_tail` / `load_inputs`) and the
  CLI are NOT hashed (code_identity_rule: other files are not pinned). PREREG_S551 names only
  forward_replay.py. So the reader is replaceable without a re-seal; the three pinned files are untouched.
- The `tail_window_miss` reason string lives in the pinned quoter; it is not edited. The new reader reports
  window_start 0, so the quoter's `book_window_miss` is never set and the reason disappears from new rows;
  a ticker with no row becomes `book_missing` and the reader's own counted reasons explain why.

## Change
- NEW scripts/platformkit/execution/live_shadow_incr.py (IncrementalShards): per-shard byte offset at the last
  complete line; each tick reads only the appended bytes; bounded per-key deques of served keys only
  (keep 4500 s >= the p0 rule's 3600 s pre-cutoff book age + 900 s schedule lead, maxlen 2000, books snapshot/snapshot_bulk only); a cheap byte filter before decoding.
  First open = offset at the last newline at EOF, then a backwards bootstrap per never-seen key until it has a
  row or the 16 MiB budget is spent. Counted: bootstrap_scan_bytes, bootstrap_budget_exhausted,
  bootstrap_key_absent, shard_opened, shard_evicted (max 4 shards; UTC rollover = a new path),
  shard_truncated_reset (size < offset), forward_gap_reset (more than the 16 MiB budget appended since the last read, e.g. after an idle or low-RAM gap: re-position at EOF and re-bootstrap, so a tick never reads more than about the budget), unterminated_tail (partial line re-read next tick),
  capture_identity_refused, missing_shards, read_bytes_tick. book_src gains read_from.
- live_shadow_io.load_inputs: uses args.reader when set (else the old tail read, unchanged).
- live_shadow_cli: `--reader {incremental,tail}` default incremental; replay (--replay-start) keeps the tail
  reader (its deques would prune on future rows); live_shadow_incr.py added to the run-row sha256 map.
- tests: NEW tests/platformkit/execution/test_live_shadow_incr.py (11); test_live_shadow_io.py case22 expects
  7 hashed files (was 6).

## Evidence (2026-10-06 01:4xZ, Windows, per file)
- test_live_shadow_incr 11 passed; test_live_shadow_io 31 passed; test_live_shadow_cli 27 passed;
  test_live_shadow_prereg 13 passed; test_live_shadow_quoter 82 passed + 1 failed
  (test_pinned_must_not_move_seal on capture_watchdog.py: fails identically on master, pre-existing).
- 50 MB synthetic shard: second-tick bytes read = appended bytes only (< 1 pct of the file).
- r1 live smoke on the real 10-06 shards (scratch out-root, 3 ticks; NOT archived, UNVERIFIED): peak RSS 61.3 MiB, read_bytes_tick
  40,219, bootstrap_scan_bytes 10,485,760, rows 9, write_errors 0. Reasons: NYY at TB stale_book x6 (book age
  584-614 s), CWS at CLE game_final x2. Master's running recorder at the same time: tail_window_miss and
  book_refused:one_sided_book (the tail missed CWS at CLE's final state).
- FINDING: after S781 the remaining no-quote cause for NYY at TB is capture cadence, not the reader: its
  books snapshots arrive every 5 s until ~01:06Z (the focus hour) and then about every 10 min, against the
  5 s book freshness bar. Live paper quotes past a game's first hour need a capture-side change (focus).

## Round 2 (branch cxp/S781-2026-10-06-r2): Opus tier ACCEPT WITH CORRECTIONS + codex astra r1 REJECT, all folded
- keep_s 4500 (Opus MAJOR): 900 dropped the pre-cutoff book row the p0 rule accepts up to 3600 s old; test
  asserts p0_book_ts 2026-09-25T22:52:59.735967Z via load_inputs + decide on the case22 fixture (900 fails it).
- Age window against the TICK clock t (D4): load_inputs passes t; rows older than t - keep_s leave the left
  of each deque; a future-dated row never evicts the current one (it only meets maxlen). Tests: age window with
  a non-binding maxlen (TP2), future-dated row.
- Opened-file identity (D2): (st_dev, st_ino) and size from os.fstat of the opened descriptor; a replaced
  shard (same or larger size) resets (shard_replaced_reset) and re-bootstraps. Test (os.replace, both sizes).
- Not-positioned shard (D1): an open/boundary failure leaves offset None and never reaches a size comparison.
  Test: failed first read then successful retry.
- Bounded reads (Opus MEDIUM + D5): forward_gap_reset when more than the budget was appended (re-position at
  EOF, re-bootstrap); the boundary search and the bootstrap each read in min(CHUNK, budget - spent) steps and
  are counted (boundary_scan_bytes, bootstrap_scan_bytes, forward_read_bytes, all in read_bytes_tick), so a
  shard call reads at most 3 x budget, hence 12 x budget across four capture shards per tick (max_shards 4);
  steady-state file reads follow appended/partial bytes; cached-row processing also depends on retained rows; a tail with no newline inside the budget is an overlong record
  (overlong_record_skipped) discarded through its terminating newline before resuming; a partial line
  longer than a chunk is skipped the same way; an unchanged size is never re-read. Tests: newline-free 3 MiB
  shard (first read <= 2 x budget, then 0 bytes while unchanged, then recovers), budget 1 reads <= 2 bytes,
  long gap, unchanged partial tail reads 0.
- Re-served keys (D3, subsumes the Opus MINOR): scanned.intersection_update(served) before computing the
  missing keys, so {A,B} -> {B} -> {A,B} returns A at once and scanned stays bounded. Test.
- capture_identity_refused (C6): meaning narrowed in the module docstring to rows that mention a served key
  but carry no usable key field (validating every row would decode the whole shard).
- TP1: the bootstrap carry branch for a newline-free interior block was dead (a block always ends at a newline
  because the offset sits after one and the carry ends with one); removed, bootstrap skipped while the shard is
  inside an overlong record; the long-line test pads to 2 x CHUNK + 5000 and the carry mutant now fails it.
  RETRACTED (round 2 tiers): the overlong bootstrap guard is NOT an equivalent mutant; regression test
  test_newly_served_key_withheld_while_overlong (CHUNK unterminated bytes at the default 16 x CHUNK budget, then
  B newly served: withheld while overlong, recovered after termination; the guard-deleted mutant recovers early).
- Mutants run on r2: carry, no age pruning, no tick floor, re-read on unchanged size: each killed;
  overlong-bootstrap guard: killed by the new regression test.
- Per file r2 (Windows, RAM gate >= 2500 MB each): incr 21 (22 after the round-2-tier regression test), io 31, cli 27 passed.
- r2 live smoke, ARCHIVED verbatim in docs/evidence/harness/S781_SMOKE_2026-10-06.md (heartbeat + all rows;
  02:18Z, RAM gate >= 3000 MB passed at 3,146): 3 ticks, peak RSS 37.8 MiB, rows_written 7, write_errors 0,
  boundary 4,194,304 + bootstrap 8,388,608 bytes on the first tick, forward 373,390 bytes total;
  NYY at TB stale_book x6 at book age 1,132-1,162 s; tail_window_miss 0.
- Cadence (QUALIFIED): the Opus tier measured NYY at TB book snapshots every 5-30 s until 00:59:55Z, then gaps of
  379 s and 1,638 s, last row 01:33:32Z as of its read (about 01:4xZ); those gap measurements are NOT archived
  (UNVERIFIED). The archived 02:18Z smoke shows a later book row, book_ts 2026-10-06T01:59:03.825265Z (age
  1,132-1,162 s), so snapshots continued after 01:33:32Z at a sparse cadence. Quotes beyond a game's focus hour are a capture-policy decision (dispatcher).
- Limit kept: after a re-bootstrap past a game's cutoff the p0 book row is found only if the backwards scan
  reaches it within the budget (as with the tail reader). Recovery also depends on the 4500 s tick window and
  maxlen: a legal pre-cutoff prior can age out after a late restart; start before the cutoff as the runbook
  requires.

## Verifier contract
- Tier 1 CONTRACT (read-only): pinned files byte-identical; replay path unchanged; every counted reason
  reachable by a test; memory bounded by served keys x maxlen; per-shard-call reads <= 3 x budget (12 x budget per tick over 4 shards), steady state O(appended bytes).
- Tier 2 ADVERSARIAL mutants: drop the partial-line cut; reset offset to 0 instead of EOF on first open;
  skip the truncation check; rescan a scanned key each tick; keep unserved keys; carry bug on a line longer
  than a chunk; incremental reader in replay mode.

## Restart plan
Land in 08:45Z-11:45Z 10-06; create STOP_live_shadow, wait for the supervisor to exit, remove STOP, relaunch
via docs/operations/relaunch_live_shadow_2026-09-29.ps1 (-DryRun first) before 21:55Z 10-06 (LAD at ATL 22:00Z
is the first p0-at-cutoff game).
