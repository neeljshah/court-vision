GAP S374 | sport all captured | worktree harness-h40 (master-based) | log cx_s374_write_as_you_drain
# Trades are written as pages drain, not when a multi-tick backfill closes (design: ASTRA_ROUND13 section 1 row 2; verifier NOTE on S341 fix 1e)

SINGLE PROBLEM: the landed capture (row S341, fixes 1b-1g) holds every fetched trade page of a multi-tick backfill in memory and in
the tick checkpoint until the backfill closes. MEASURED in production on 2026-09-21: the NFL backfill ran about 16 minutes and wrote
ZERO nfl trade rows until it closed (then 38,088 at once). A kill, a reboot or a sleep in that window refetches everything, relies on
the venue replaying the same pages, and leaves the archive silent about prints the process already held.

BINDING BEFORE-CONDITION: read scripts/platformkit/ingame/local_capture_backfill.py, local_capture_runner_trades.py,
local_capture_state.py and local_capture_writer.py on master; quote in the memo (a) where fetched pages are staged, (b) where and when
they are appended, (c) where the watermark advances, (d) how trade ids are de-duplicated and how that set is seeded after a restart.
Run `python -m pytest tests/platformkit/ingame/test_local_capture_backfill.py -q -p no:cacheprovider` and quote the pass count.

CHANGE (owned files: local_capture_backfill.py, local_capture_runner_trades.py, NEW tests/platformkit/ingame/test_local_capture_drain.py,
the memo; edit NO other capture module -- if another module must change, stop and say so in the memo instead):
1. Each VALIDATED page is appended to the archive (append + flush + os.fsync through the existing writer) BEFORE the cursor that
   points past it is persisted in the checkpoint. Order per page: validate -> de-duplicate by trade id -> append + fsync -> persist
   cursor. A crash between append and cursor persistence must only ever cause a refetch whose rows are dropped as duplicates.
2. The completeness watermark advances ONLY at backfill closure or when an explicit trade_gap record is written -- exactly as today.
   Appending early must never advance it, and a reader must be able to tell drained-but-open rows from closed ones: every trade row
   written during an open backfill carries `backfill_open: true` and the backfill id; the closing record carries the same id.
3. After a restart the de-duplication set is seeded from the ARCHIVE (the existing seeding path) so pages appended before the crash
   are not written twice; seeding reads are bounded (tail of today's and yesterday's shard), order-independent, and count
   unparseable lines instead of raising.
4. The checkpoint no longer stores staged rows (only the cursor, the page count, the backfill id and the declared gap state), so its
   size is bounded; a checkpoint written by the landed version (with staged rows) must still load: its staged rows are appended
   first, then dropped from the checkpoint (migration test).
5. Heartbeat: trades_written_total rises DURING a backfill; add backfill_pages_appended_total (strict int).
6. tests (injected client, writer and clock; no network): rows appear after the FIRST page of a 5-page backfill; kill between append
   and cursor persistence -> restart -> no duplicate row, no lost row, distinct trade ids conserved; kill between cursor persistence
   and the next fetch -> same; the watermark is unchanged until closure; max-pages gap record still written; migration of an old
   checkpoint; seeding skips a torn final line; results independent of page arrival order within the same cursor chain.
   All six landed capture test files must still pass unchanged.
7. Memo docs/evidence/harness/S374_write_as_you_drain_2026-09-21.md.

CONTROLS: construct tests only, no network, no real archive, never touch a running capture or its output root. ACCEPTANCE: the new
test file and the six landed capture test files pass one at a time; --help works; <= 300 LOC per file; ASCII; contract Q6
vocabulary; the memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-21; binding; the first build lane stopped correctly on a contradiction the orchestrator wrote). The landed
tests/platformkit/ingame/test_local_capture_backfill.py asserts the OLD behaviour (staged rows held in the checkpoint, no archive
write before closure). That file is now an OWNED file of this row: rewrite the assertions that encode the old staging behaviour
to encode the new one (rows appended per page, checkpoint holds no staged rows). What may NOT be weakened or removed in that file:
the honest trade_gap record on max-pages, the watermark advancing only at closure or gap, trade-id de-duplication, the seeding of
the de-duplication set from the archive, the multi-tick cursor chain, and every refusal count. The memo lists each changed
assertion with the old and the new expectation side by side. The other five landed capture test files stay unchanged and passing.

AMENDMENT 2 (2026-09-21; binding; the second build lane stopped correctly on a further contradiction). tests/platformkit/ingame/
test_local_capture_runner.py::test_first_poll_drains_and_failed_later_page_never_advances asserts the OLD behaviour too (a valid
first page followed by a failed second page leaves ZERO archived trades). Under this row that first page IS archived (100 rows,
backfill_open true, no checkpoint cursor beyond it is required by the test) while the watermark stays None and the second tick
still yields exactly 101 distinct archived trades. test_local_capture_runner.py is therefore an OWNED file with the same rule as
AMENDMENT 1: rewrite ONLY the assertions that encode old staging (here: the `not any(... == "trade")` line and, if needed, the
checkpoint-existence line), keep the watermark-None, the 101-distinct-rows and every refusal assertion, and list each change
old-vs-new in the memo. General rule for this row, so a third stop is unnecessary: any landed capture test assertion that encodes
"nothing is archived until closure" may be rewritten to "archived per page, watermark unchanged"; every other assertion stays.

