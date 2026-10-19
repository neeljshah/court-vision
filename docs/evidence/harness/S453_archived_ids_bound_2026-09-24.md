# S453 -- bound TradeGroup.archived_ids (Kalshi books runner)

GAP S453 | sport all captured | worktree harness-h107 (master-based) | log cx_s453_archived_ids_bound
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- A9, B1-B11, Q1-Q9, S1, S2, S4.
WHERE (S1): local, this worktree only. Construct tests only -- no network, no live capture,
no pod. The running capture (books runner pid 31768) was never touched.

**AMENDMENT 1 applied** (adjudicated by the orchestrator from the case-6 finding below):
`ARCHIVED_LIMIT` is now `100000`, not the `10000` the sections immediately below built and
tested first. The sections below this point are the historical record of that first build and
its finding; see `## FIX 1b (AMENDMENT 1)` for the current, landable state.

## BINDING BEFORE-CONDITION (S2) -- verified at worktree HEAD 2307ed3e5

- `scripts/platformkit/ingame/local_capture_runner_trades.py`: `SEEN_LIMIT = 10000` (line 15);
  `class TradeGroup` (line 43) held `self.order: deque[str]` (line 49) and
  `self.archived_ids: set[str] = set()` (line 56); `remember()` (lines 59-65) bounded the seen
  set by popping `self.order` when `len(self.order) > SEEN_LIMIT`; the duplicate test (line 77)
  read `trade_id in self.archived_ids or trade_id in self.seen`. Nothing removed from
  `archived_ids` -- confirmed by reading the file before any edit.
- `scripts/platformkit/ingame/local_capture_backfill.py`: `restore()` (line 78) added every
  restored id via `group.archived_ids.add(tid)` (line 153); `append_rows()` (line 160) added
  every appended id via `candidate.archived_ids.add(tid)` (line 179); `capture_pages()`
  (line 191) stripped `archived_ids` from the persisted pending payload (line 220) -- the set
  lived only in memory.
- LOC before edit: trades 118, backfill 280 (both read and counted with
  `len(text.splitlines())` before touching either file).

### Before-edit pass counts (recorded before any edit)

| file | result |
|---|---|
| `tests/platformkit/ingame/test_local_capture_runner.py` | 8 passed |
| `tests/platformkit/ingame/test_local_capture_backfill.py` | 12 passed |
| `tests/platformkit/ingame/test_inplay_capture_runner.py` | 5 passed |

## CHANGE built (exactly the spec's CHANGE section, nothing else)

- `ARCHIVED_LIMIT = 10000` added beside `SEEN_LIMIT` (trades.py:16).
- `TradeGroup.__init__` gained `self.archived_order: deque[str] = deque()` (trades.py:58).
- `TradeGroup.remember_archived(trade_id)` added (trades.py:69-75): appends to
  `archived_order` and adds to `archived_ids` only when not already archived; while
  `len(archived_order) > ARCHIVED_LIMIT`, pops the oldest id from both. A re-remembered id is
  never re-appended and never moves the eviction order.
- The two mutation sites now call `remember_archived` instead of `.add`:
  - `backfill.py:153` (`restore()`): `group.archived_ids.add(tid)` -> `group.remember_archived(tid)`
  - `backfill.py:179` (`append_rows()`): `candidate.archived_ids.add(tid)` -> `candidate.remember_archived(tid)`
- The membership test at trades.py:77 is unchanged. `payload()` is unchanged -- it never
  serialized `archived_ids`, so it does not serialize `archived_order` either; the persisted
  checkpoint and pending payload shapes are untouched.
- Nothing else in either file changed.

### wc -l after edit

- `local_capture_runner_trades.py`: 128 lines (was 118, budget 300).
- `local_capture_backfill.py`: 280 lines (unchanged -- both call-site edits are 1:1 line swaps).

## ACCEPTANCE RULE -- 6 CONSTRUCT cases (new file `tests/platformkit/ingame/test_local_capture_archived_bound.py`)

| # | case | result |
|---|---|---|
| 1 | `test_case1_25000_distinct_ids_bounds_both_collections` -- 25000 distinct ids through `remember_archived` -> `len(archived_ids) == ARCHIVED_LIMIT == len(archived_order)`, newest id a member, first-inserted not | PASS |
| 2 | `test_case2_re_remembering_does_not_grow_or_reorder` -- re-remembering an already-archived id does not grow either collection or change eviction order | PASS |
| 3 | `test_case3_evicted_archived_id_still_refused_via_independent_seen_set` -- an evicted archived id still in `.seen` is still refused as duplicate; the two sets stay independent (trades.py:77 unchanged) | PASS |
| 4 | `test_case4_restore_marks_every_restored_id_duplicate_immediately` -- `restore()` on a 3-row archive fixture marks every restored id refused-as-duplicate immediately after, through `remember_archived` | PASS |
| 5 | `test_case5_resend_refused_and_payload_byte_identical_to_master` -- `append_rows()` refuses a re-sent id on the next call; the persisted pending payload is byte-identical to a live run of the MASTER module (`git show master:...local_capture_backfill.py` exec'd as an independent module) on the same 2-record fixture, never compared to the candidate's own earlier run | PASS |
| 6 | the three existing test files pass with counts unchanged from the before-edit counts | **FAIL for one file -- see below** |

### Case 6 result -- a genuine regression, not a test bug

After the edit:

| file | result |
|---|---|
| `test_local_capture_runner.py` | 8 passed (unchanged) |
| `test_local_capture_backfill.py` | **11 passed, 1 failed** (was 12 passed) |
| `test_inplay_capture_runner.py` | 5 passed (unchanged) |

Failing test: `test_500_pages_keep_newest_close_gap_and_never_repeat_history`. It drives one
ticker through a single continuous backfill that legitimately touches 20,000 distinct trade
ids (500 synthetic pages x up to 100 ids), i.e. it crosses `ARCHIVED_LIMIT = 10000` inside one
ticker's life. After the edit the assertion `len(written) == 20000` observes 21,200 -- 1,200
extra rows. Root cause confirmed directly: monkeypatching `ARCHIVED_LIMIT` to a very large
number (no change to any other code) makes this same test pass again, isolating the eviction
itself as the cause, not a defect in `remember_archived`'s logic (cases 1-3 above show the
eviction discipline is correct in isolation).

Mechanism: the resumed-backfill paginator re-queries a small overlap window
(`watermark - 120s`) on every restart as a safety margin against pagination races. On master,
`archived_ids` never evicted, so any id re-observed in that overlap -- no matter how long ago
it was first archived -- was always caught as a duplicate. With `archived_ids` now bounded to
`ARCHIVED_LIMIT`, an id archived more than `ARCHIVED_LIMIT` ids ago (and also outside the
`SEEN_LIMIT`-bounded `.seen` window) is no longer recognized as a duplicate if it is
re-observed, and is written a second time.

This is exactly the tradeoff the spec's own CONTROLS section names plainly: "beyond
ARCHIVED_LIMIT archived ids per ticker a very old trade id could be re-appended, and the
downstream `duplicate_trade_id` counter and consumers already dedupe by trade id." That
statement is true and the built change matches the spec's CHANGE section exactly (verified
by the diff hunks below and by contract_preflight, all PASS). What was not anticipated is
that one of the three existing regression tests this row's own ACCEPTANCE RULE binds itself
to (case 6) exercises precisely that boundary (20,000 ids in one ticker) and therefore
detects the re-append as a real duplicate row rather than treating it as tolerable. The
CHANGE as specified and case 6 as specified are not simultaneously satisfiable for
`ARCHIVED_LIMIT = 10000` against this repository's existing test suite. No file was edited to
paper over this: `ARCHIVED_LIMIT` stays 10000 per the spec, and
`test_local_capture_backfill.py` was not touched (not owned by this row). Flagged for the
human/orchestrator to adjudicate (raise the bound, amend the existing test's scale, or accept
the regression) -- not decided unilaterally here.

**Resolved by AMENDMENT 1** -- see `## FIX 1b (AMENDMENT 1)` below.

## Hunks (file:line)

- `scripts/platformkit/ingame/local_capture_runner_trades.py:16` -- `ARCHIVED_LIMIT = 10000` added.
- `scripts/platformkit/ingame/local_capture_runner_trades.py:58` -- `self.archived_order: deque[str] = deque()` added.
- `scripts/platformkit/ingame/local_capture_runner_trades.py:69-75` -- `remember_archived()` added.
- `scripts/platformkit/ingame/local_capture_backfill.py:153` -- `restore()` call-site swapped to `remember_archived`.
- `scripts/platformkit/ingame/local_capture_backfill.py:179` -- `append_rows()` call-site swapped to `remember_archived`.

## RSS observation (context for the single problem; not re-measured by this row)

Observed 2026-09-24: the books runner RSS grew 285 -> 512 MB over approximately 4 hours of
MLB focus (`Get-CimInstance WorkingSetSize`), then read 440-448 MB at approximately 22:3xZ the
same day. This row addresses the one identified unbounded per-ticker collection
(`archived_ids`); it does not re-measure RSS after landing.

## must-not-move check (B10, Q3)

`git diff --stat master -- <must-not-move files>` is empty for all seven paths below --
byte-identical to the current shared `master` ref, which does not differ from this
worktree's HEAD (2307ed3e5) on any file this row touches or must not touch (confirmed via
`git log --oneline HEAD..master` and a scoped `git diff --stat` showing no changes to either
candidate file between HEAD and master).

## A9 identity table (historical -- at worktree HEAD 2307ed3e5, before AMENDMENT 1; superseded by the regenerated table in FIX 1b below)

absolute path, byte size, sha256 of LF-normalised bytes (`read_bytes().replace(b"\r\n", b"\n")`)

Candidate files (this row's edits):

| path | bytes | sha256 (LF-normalised) |
|---|---|---|
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_runner_trades.py` | 5793 | `92cbf144e11552bd88373e8b43f457b8daa5c6806d6b06743b153ee78e467afa` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_backfill.py` | 14601 | `4d685892c000623281f737d26e9fee909e1a067275e43dd4ea251cb28408949e` |
| `C:\Users\neelj\nba-harness-h107\tests\platformkit\ingame\test_local_capture_archived_bound.py` | 6616 | `702ea1e570b0604eaab4cb1eec7a00686751e505311d7d67deced98189f4a6d0` |

Must-not-move files (byte-identical to master, confirmed above):

| path | bytes | sha256 (LF-normalised) |
|---|---|---|
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_runner.py` | 18288 | `b67b59ac799f259c61b5b9a4cab99340276717463a605b3b6b6ec11f5d8e834d` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_state.py` | 7403 | `0275cd04497c6f39e75b25a66efca940bc689cf78ab43d09c2890906560968e4` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_writer.py` (spec's glob `local_capture_runner_writer*.py` matches no file in this directory -- this is the only writer module, and it is what the glob evidently intends) | 7873 | `7ba00c2200ecf53cba81ab3f3ecbb3ad80ea7233f0607d5094c8bdda72f8cee0` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\capture_schedule_loader.py` | 3350 | `6e5bbdd3aa0a9fce855be37ed9d6311a010bf05b0878bd124dbdcb90854d5820` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\schedule_pointer.py` | 9549 | `8f9dbae90ff2597a96d17b83f6c5f8b7b98e731ddaf76b86aba02b8abb8aebf0` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_state_capture.py` | 17829 | `243dd7bdb7a1ccfa8e985830b278c1e649a603194e9b1f86aa28c70d712c1b5c` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\polymarket_live_capture.py` | 15122 | `28f5f5ecf54d2eee2b25e7388eb88087f6c213b9dd8c2e75463e2ffae3eb2073` |

## contract_preflight

`python -m scripts.platformkit.tracking.contract_preflight --paths
scripts/platformkit/ingame/local_capture_runner_trades.py
scripts/platformkit/ingame/local_capture_backfill.py
tests/platformkit/ingame/test_local_capture_archived_bound.py --base master --spec
docs/evidence/tracking/specs/S453_spec.md` -- all 9 checks PASS (vocab, crlf, loc, schema,
head_slice, spec_threshold, proposed, removed_artifact, row_duplication).

## FIX 1b (AMENDMENT 1)

The orchestrator adjudicated the case-6 finding above: never-repeat-history wins. Applied at
worktree HEAD/master `70eac9803` (fast-forwarded; this row's two modules were preserved
unchanged by the fast-forward).

**(a) Constant and case 1.** `ARCHIVED_LIMIT` raised `10000` -> `100000` (ten times
`SEEN_LIMIT`), `trades.py:16`. Nothing else in `remember_archived` or the two call sites
changed -- the eviction discipline itself (cases 2-3, unaffected by the constant's value) was
already correct. `test_case1_250000_distinct_ids_bounds_both_collections` now inserts 250,000
distinct ids and asserts `len(archived_ids) == len(archived_order) == ARCHIVED_LIMIT == 100000`,
with the newest id present and the first-inserted absent.

**Failing count before -> unchanged counts after:**

| file | before AMENDMENT 1 | after AMENDMENT 1 |
|---|---|---|
| `test_local_capture_runner.py` | 8 passed | 8 passed |
| `test_local_capture_backfill.py` | **11 passed, 1 failed (21,200 rows observed, wanted 20,000)** | **12 passed** |
| `test_inplay_capture_runner.py` | 5 passed | 5 passed |

`test_500_pages_keep_newest_close_gap_and_never_repeat_history` passes again unmodified: its
scenario tops out at 20,000 distinct ids in one ticker's continuous backfill, now well inside
the 100,000-id cap, so the paginator's overlap re-query never crosses an eviction boundary.
New-file suite (`test_local_capture_archived_bound.py`): 6 passed (all 6 cases).

**(b) Memory arithmetic, stated honestly.** Each archived id costs roughly 140 bytes (a
40-character `str` object plus its set and deque entries). At the new cap of 100,000 ids per
ticker that is at most roughly 100,000 x 140 bytes ~ 14 MB per ticker -- not zero, but bounded
and small next to the RSS growth actually observed. The process total is bounded only by how
many `TradeGroup` instances are alive at once (one per ticker ever seen for the life of the
process, per the BINDING BEFORE-CONDITION item (c) above), which this row does not change and
does not claim to fix: this row is a per-ticker safety net on one collection, not an
explanation of the 285 -> 512 MB growth observed on 2026-09-24. The process-level lever --
pruning closed tickers' `TradeGroup` entries and the scheduled cache -- is S454, not this row.

**(c) Limitation, stated plainly.** A single ticker that accumulates more than 100,000 trades
within one continuous backfill overlap window could still re-append an id evicted earlier in
that same overlap; this is the same class of event as before, just at a bound ten times
larger and (per the current shard evidence) outside the range this row has observed or can
construct a realistic fixture for. The downstream `duplicate_trade_id` counter and consumers
already dedupe by trade id independent of this collection, per the spec's CONTROLS section.

**Preflight and rails re-checked at `70eac9803`:**

- `contract_preflight --paths scripts/platformkit/ingame/local_capture_runner_trades.py
  scripts/platformkit/ingame/local_capture_backfill.py
  tests/platformkit/ingame/test_local_capture_archived_bound.py --base master --spec
  docs/evidence/tracking/specs/S453_spec.md` -- all 9 checks PASS.
- must-not-move: `git diff --stat master -- <7 paths>` is empty (unchanged from the historical
  check above).
- `git status --short`: same shape as before AMENDMENT 1 -- 2 modified modules, 2 untracked
  (this memo, the new test file).
- wc -l: `local_capture_runner_trades.py` 128, `local_capture_backfill.py` 280,
  `test_local_capture_archived_bound.py` 144 -- all under the 300 LOC rail.

### A9 identity table, regenerated at base sha `70eac9803`

absolute path, byte size, sha256 of LF-normalised bytes (`read_bytes().replace(b"\r\n", b"\n")`)

Candidate files:

| path | bytes | sha256 (LF-normalised) |
|---|---|---|
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_runner_trades.py` | 5794 | `077294e24cd4d813dfe05b6bfefe480636bd6abca8beb2dc47285c0a9b6ea72c` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_backfill.py` | 14601 | `4d685892c000623281f737d26e9fee909e1a067275e43dd4ea251cb28408949e` |
| `C:\Users\neelj\nba-harness-h107\tests\platformkit\ingame\test_local_capture_archived_bound.py` | 6629 | `5bb92a38bd8cc3d86dfdc3f050b9991546a925f775a1d5e1510bb814ac0aa6b9` |

Must-not-move files (unchanged from the historical table -- confirmed byte-identical again):

| path | bytes | sha256 (LF-normalised) |
|---|---|---|
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_runner.py` | 18288 | `b67b59ac799f259c61b5b9a4cab99340276717463a605b3b6b6ec11f5d8e834d` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_state.py` | 7403 | `0275cd04497c6f39e75b25a66efca940bc689cf78ab43d09c2890906560968e4` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_capture_writer.py` (spec's glob `local_capture_runner_writer*.py` matches no file in this directory) | 7873 | `7ba00c2200ecf53cba81ab3f3ecbb3ad80ea7233f0607d5094c8bdda72f8cee0` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\capture_schedule_loader.py` | 3350 | `6e5bbdd3aa0a9fce855be37ed9d6311a010bf05b0878bd124dbdcb90854d5820` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\schedule_pointer.py` | 9549 | `8f9dbae90ff2597a96d17b83f6c5f8b7b98e731ddaf76b86aba02b8abb8aebf0` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\local_state_capture.py` | 17829 | `243dd7bdb7a1ccfa8e985830b278c1e649a603194e9b1f86aa28c70d712c1b5c` |
| `C:\Users\neelj\nba-harness-h107\scripts\platformkit\ingame\polymarket_live_capture.py` | 15122 | `28f5f5ecf54d2eee2b25e7388eb88087f6c213b9dd8c2e75463e2ffae3eb2073` |

## HOST TEST RUN (orchestrator, AMENDMENT 2(a); 2026-09-24 23:2xZ, worktree nba-harness-h107 at master 70eac9803)

The codex sandbox has no writable temporary directory, so the four authorised files were run on the
host by the orchestrator, one file at a time (`python -m pytest <file> -q -p no:cacheprovider`):

- tests/platformkit/ingame/test_local_capture_archived_bound.py: 6 passed in 2.03s
- tests/platformkit/ingame/test_local_capture_runner.py: 8 passed in 1.42s
- tests/platformkit/ingame/test_local_capture_backfill.py: 12 passed in 62.67s
- tests/platformkit/ingame/test_inplay_capture_runner.py: 5 passed in 83.43s

Case 6 (unchanged counts 8 / 12 / 5 against the before-edit counts) is therefore established on the host.

## NEW GAP (AMENDMENT 2(c), out of this row's scope)

scripts/platformkit/ingame/polymarket_live_trades.py mutates `TradeGroup.archived_ids` directly at lines
60, 74, 78, 99 and 133, bypassing `archived_order`, so on the Polymarket route the bound does not apply and
the set stays unbounded. The Polymarket capture child was observed at 277 MB RSS at 22:3xZ. Allocated at the
next register touch; route-specific regressions belong to that row.

## NOT VERIFIED

- Overnight RSS after the owner-visible relaunch (planned 2026-09-25 schedule switch): not measured here; this
  row does not claim the `archived_ids` bound alone explains the 285 -> 512 MB growth observed on 2026-09-24
  (FIX 1b (b); the process-level lever is S454, itself DEFERRED pending an RSS attribution measurement).
- Downstream duplicate handling beyond the cap: that every consumer's own dedupe-by-trade-id absorbs a very old
  re-appended id is asserted by the spec CONTROLS section and not independently re-verified here.
- The greater-than-100,000-trades-within-one-backfill-overlap limitation (FIX 1b (c)): stated, not exercised.
- The Polymarket route (NEW GAP above): not covered by this row's tests.
- The running capture (pid 31768) was never touched; adoption happens only at the relaunch.
