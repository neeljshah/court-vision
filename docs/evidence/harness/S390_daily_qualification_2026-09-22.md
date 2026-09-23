# S390 -- daily score-blind qualification + completed-week report (build lane)
Row: S390 | sport all captured | worktree harness-h56 | 2026-09-22 | Spec
`docs/evidence/tracking/specs/S390_spec.md` (AMENDMENTS 1-6) | Contract
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q
This lane BUILT the two runners, their shared input module, the family declaration file
and their per-file tests. It ran NO production archive and produced NO measured number:
every test is a construct or a verbatim production-row fixture, and the first real run
belongs to the orchestrator.
## 0. Spec conflicts found (all adjudicated by AMENDMENT 1)
**C1 -- one family name cannot cover five sports.** `family_week_ledger.py:71-72`
refuses a repeated family name, `:76-77` requires an independence rule keyed by every
OTHER family, `:100-101` pins one sport per family. BUILT: five entries
`maker_forward_<sport>`, `market_type` `maker`, `weekly_floor` =
`forward_replay_qualification.WEEK_GAMES`, four independence sentences each. **C2 -- the
import-graph exclusion is only true of DIRECT imports.** `forward_replay.py:16` imports
`tape_fill_adapters` and `forward_replay_policy.py:14` imports `fill_to_markout_fill`,
so a transitive-closure assertion is unsatisfiable while spec item 2(b) requires running
that replay. BUILT (AMENDMENT 1(b)): the tests assert the new modules' OWN imports
(`ast`), that no artifact key CONTAINS a scoring token, and that every leaf is text, a
strict int, a boolean or null. **C3 -- an absent scheduled game fails `LINKAGE_INVALID`,
not `NOT_LIVE`**: FAIL, `covered_ms` 0, `total_ms` 3600000, `reason_counts`
`{BOOK_CADENCE:1, COVERAGE_LOW:1, DECISIONS_LOW:1, LINKAGE_INVALID:1, STATE_GAP:1,
TAPE_INCOMPLETE:1}`; `NOT_LIVE` comes only from an observed book decision. **C4 -- the
schedules carried no `game_key`**, which `bridge:80-85` requires; this lane does NOT
edit the human-gated writer and the orchestrator resolved it on master before any start
(AMENDMENT 1(d); S403 makes the writer emit it).
## 1. BINDING BEFORE-CONDITION (quoted from master)
**(a) `forward_replay.py`** -- `run()` at :266-268 returns `_prepare(...)[1]`, docstring
"Count qualification evidence only; no executions or marks are evaluated." `parse_args`
at :274-287 declares exactly `--qualify` (store_true, required), `--books` (nargs +,
Path, required), `--state` (nargs *, []), `--native` (store_true), `--trades` (nargs *,
[]), `--supervisor-journal` (nargs *, []), `--as-of`, `--run-nonce`, `--schedule` (Path)
and `--global-cap` (all required), `--max-order-qty` (Decimal, default `Decimal("1")`)
and `--reservation-ttl-s` (default `"2"`); :294 calls `run(events, params,
{"reservation_ttl_s": args.reservation_ttl_s}, {"global": args.global_cap}, ())`.
**(b) `forward_replay_qualification.py`** -- `REASONS` at :23-25 is the frozenset
`BOOK_STALE, STATE_STALE, ADAPTER_REFUSED, LINKAGE_INVALID, NOT_LIVE,
RESERVATION_INVALID, COVERAGE_LOW, DECISIONS_LOW, BOOK_CADENCE, STATE_GAP, TRADE_GAP,
HOST_GAP, TAPE_INCOMPLETE`. `game_summary` at :88-93 returns `verdict, reason_counts,
covered_ms, total_ms (= WINDOW_S * 1000), qualified_decisions, book_gap_median_ms,
book_gap_p95_ms, book_gap_max_ms, state_gap_max_ms`. `weeks()` at :210-262 builds its
`FamilyWeekLedger` inside `TemporaryDirectory(prefix=".s362-weeks-", ...)` at :225, so
its week rows are discarded when the call returns -- the premise of this row holds.
**(c) `family_week_ledger.py`** -- `__init__(self, path, families_path, *, as_of=None)`
:58; `records()` :127; `append(row)` :149, refusing at :152-153 with `ValueError("only
completed ISO weeks may be appended")` and at :155-157 on a duplicate `(iso_year,
iso_week, family)`; `streak(family)` :164; `forecast(family, games_per_week)` :190. The
record field set at :91-94 is exactly `iso_year, iso_week, family, sport, game_ids,
qualified_game_ids, fill_bearing_game_ids, qualified_games, fill_bearing_games,
exclusions, capture_gap_seconds, source_artifact_path, source_sha256`, a declaration
entry at :65-66 exactly `{family, sport, market_type, weekly_floor,
independence_rules}`.
**(d) `forward_capture_bridge.py`** -- `load_native(books_paths, state_paths,
trade_paths, supervisor_journals, schedule, *, as_of=None) -> NativeEvidence` at
:189-191. **(e) `capture_scheduler.py`** -- `heartbeat_fields` at :285-300 emits
`profile_sha256` (:287-288, 64 lowercase hex or refuse) with `scheduled_games_total` and
`scheduled_admitted` (:289); line 113 is the two-games-per-hour refusal `if any(b - a <
3600 for a, b in zip(starts, starts[2:])): raise ValueError("schedule exceeds two games
per hour")`.
## 2. What was built (amendments supersede earlier rounds)
The three modules are scripts/platformkit/ops/forward_qualification_daily.py,
forward_qualification_inputs.py and forward_week_report.py.
The daily CLI projects the prospective selection through ALLOWED_SCHEDULE_FIELDS,
resolves families by sport, and counts dropped fields. It hashes schedule, subset,
declarations, profile, supervisor journals and both UTC archive shards per sport
before qualification. Snapshots seal the complete-line prefix; retained digests
detect rewrites, and post-verification sizes count appends. The bridge reads the
snapshots; artifacts record real paths and state receipts. Missing date state
refuses; absent games remain in the full-selection denominator.
Native qualify-only replay uses the profile's reservation lifetime and focus tick.
Every bridge diagnostic is counted; game summaries retain the closed REASONS set,
strict integer counts, game_id and game_key, the schedule label and served flag.
Artifacts contain no scoring values; refusals exit 3 and still write an artifact.
Exclusive reservation and atomic writes preserve earlier date revisions.
Snapshot cleanup follows artifact creation and never masks an earlier refusal.
The shared inputs module owns digests, snapshot copy, prefix checks, profile,
archive layout, schedule projection and declarations used by both runners.
The week CLI reads daily bytes once for both rows and hashes, selecting the newest
non-refused revision. All seven UTC dates are required, including quiet days.
Complete weeks append every declared family, including zero-game FAIL rows,
through FamilyWeekLedger. Incomplete weeks append nothing; reruns deduplicate.
Ledger refusals propagate; artifact status records REFUSED, ABORTED or COMPLETE
truthfully. Streak and forecast use the landed ledger, with its exact row schema.
families_maker_forward.json declares five separate sport families; see C1.
## 3-4. Earlier validation
FIX 1f below records previous checks; FIX 1g records this local construct-only run.
## 5-6. FIX 1b and FIX 1c (previous rounds, kept as the record)
**FIX 1b -- AMENDMENT 2.** The production layout is
`<root>/kalshi|state/<sport>/<date>.jsonl` and both subtrees derive from ONE
`--capture-root` (a root missing either refuses `capture_root_missing_subtree`);
`reservation_ttl_s` / `focus_tick_s` come from the landed capture profile, never the
replay's 2 s default, which at a 5 s tick would have failed every game on `COVERAGE_LOW`
by construction rather than by capture quality; unconsumed supervisor records are
counted, never a failure.
**FIX 1c -- Opus r1 REJECT plus codex sol r1.** (1) AMENDMENT 1(a) binds the DAILY
artifact: `--families` is required and indexed by sport through the SAME `_declarations`
the week report calls; BEFORE `:31,156` copied the schedule's own `family` so all five
sports read `maker_forward`, AFTER each game carries `maker_forward_<sport>` with the
label kept as `schedule_family`, and `undeclared_sport`, `duplicate_sport_declaration`
and `family_differs_from_declaration` refuse. (2) Score blindness at the schedule
boundary: arbitrary fields were forwarded unchanged and the exact key match rejected
none of `yes_price` / `settlement_status` / `fill_count`; entries are now projected
through `ALLOWED_SCHEDULE_FIELDS`, every other key counted and dropped, and the test
matches any key CONTAINING a scoring token. ORCHESTRATOR RULING: the replay's own
parsing of book prices is the dependency's business -- the artifact carries no value.
(3) The week iterates the DECLARATIONS, so a declared family with no scheduled games
prints a zero-game FAIL row (its no-append rule is superseded by FIX 1f). (4) The post-run rehash is SUPERSEDED by
AMENDMENT 3 below. (5) Tie handling: base=A r1=A r2=B once dropped the date while base=B
r1=A r2=A kept it, so payloads are grouped per date first and only a tie AT the maximum
`as_of` matters. (6) The report creates the ledger's parent before the first append;
both caps are REQUIRED; every raise that could escape `main` is an enumerated exit-3
refusal, an unenumerated one `qualification_failed`.
## 7. FIX 1d -- AMENDMENT 3, the Opus r2 corrections, the codex sol r2 blockers
**AMENDMENT 3 (BLOCKING; MEASURED on the live archives).** The orchestrator's real
fix-1c run refused `input_changed_during_run` on the 186 MB mlb book shard and the mlb
state shard: the captures append every few seconds, so an exact post-run rehash can
never pass while a capture writes, and every daily run happens while one does. The
requirement stands; the mechanism changed. (a) Each archive input records its size AT
HASH TIME, that exact byte prefix is copied to
`<out>.snapshots/<kind>/<sport>/<date>.jsonl` (journals under `supervisor/journals/`),
the COPY is hashed, that digest is the artifact's input hash, and the BRIDGE is handed
the copies. A torn final line inside the prefix is copied unchanged and counted by the
landed reader as it counts it. The tree is deleted AFTER the artifact is written;
`inputs.snapshots` keeps `files`, `bytes`, `truncated` and `removed`, and every entry
keeps its `hashed_bytes`. (b) The post-run rehash became a PREFIX check: the live file's
first `hashed_bytes` bytes must still hash to the recorded digest. Bytes appended past
the prefix are counted `appended_bytes`, per input and in `input_counts`, and are never
a refusal; a rewrite INSIDE the prefix, or a truncation, still refuses
`input_changed_during_run`. (c) The as-of filter is unchanged. BEFORE (this candidate
reverted locally, one record appended mid-run): `refused` 1, `input_changed_during_run`,
`changed_inputs` the mlb book shard, no `appended_bytes`. AFTER: `refused` 0,
`changed_inputs` `[]`, `hashed_bytes` 5598 = `size_bytes` 5598 with `appended_bytes` 28,
the artifact hash equal to the snapshot digest, `snapshots.removed` true.
**r2 CORRECTION 1 -- a durable row could reference an unwritten artifact.** `_row`
(`:164`) and the per-family loop sat OUTSIDE the refusal envelope, so a raise after an
earlier append left a ledger row whose `source_artifact_path` named a week file never
written -- permanently, since a re-run refuses at the same point. Every row is now built
BEFORE any append, inside the envelope, and the append loop runs under `try/finally`
whose finally writes the artifact; the ledger's own refusal still propagates uncaught.
BEFORE: the mlb row is appended and `weeks/week.json` does NOT exist. AFTER: same
uncaught `ValueError`, mlb row appended, artifact EXISTS.
**r2 CORRECTION 2 -- `_fingerprint` crashed the run.** A daily artifact missing
`covered_ms` raised `KeyError: 'covered_ms'` out of `main` (exit 1, no artifact) because
`_artifacts` ran before the try. AFTER: `_artifacts` is inside the envelope and a game
missing any `SUMMARY_FIELDS` key raises the enumerated `unreadable_daily_artifact` --
exit 3, artifact written, nothing appended.
**r2 NOTES 3, 4, 5.** (3) `_resolve` counts the rows the schedule file held BEFORE
indexing the declarations. (4) A failed `_atomic` releases the reserved path: BEFORE a
zero-byte artifact occupied the date forever, AFTER it is gone. (5) `game_key` is typed
as a non-empty string; a non-string is `invalid_schedule_identity`.
**sol r2 BLOCKER 1 -- a TRUNCATED copy was accepted.** BEFORE: `{size_at_hash: 4,
available_at_copy: 2}` produced `{hashed_bytes: 2, raised: False}` and qualification ran
on the short copy. AFTER: the same input produces `{hashed_bytes: 2, raised:
input_changed_during_run}` and the run refuses with the path in BOTH `changed_inputs`
and `inputs.snapshots.truncated`.

**sol r2 BLOCKER 2 -- the equal-`as_of` fingerprint ignored ledger inputs.** BEFORE:
`book_gap_max_ms [1000, 9000]` gave `fingerprints_equal True` while the week's
`capture_gap_seconds` were `['1', '9']`. AFTER: the COMPLETE games block, sorted by
`game_id` under `json.dumps(sort_keys=True)`, gives `fingerprints_equal False`, the date
is damaged and the week is INCOMPLETE.

**sol r2 BLOCKER 3 -- the snapshots were deleted before the artifact existed.**
`shutil.rmtree(..., ignore_errors=True)` ran ahead of `_atomic` and suppressed every
error. BEFORE: `{artifact_bytes_at_delete: 0}` -- only the empty reservation. AFTER:
`{artifact_bytes_at_delete: 4626}`, and a failing cleanup is counted
`snapshot_cleanup_failed` with `removed: false` and its `cleanup_error`, exit 3.

**FIX 1e (Opus r3 ACCEPT WITH CORRECTIONS).** (1) The `SUMMARY_FIELDS` check moved from
`_fingerprint` (reached only on an as_of tie) into `_artifacts` per payload, so a SINGLE
artifact whose game lacks `book_gap_max_ms` refuses `unreadable_daily_artifact` instead
of the raw `"'book_gap_max_ms'"` KeyError text. (2) `_refuse` sets `status REFUSED`,
`COMPLETE` is set only after the append loop succeeds, and an uncaught ledger refusal
leaves `status ABORTED`, so the `finally` writes the status the run actually reached
instead of `COMPLETE / refused 0`. (3) A failing `rmtree` sets `refusal_reason` only when
it is still None, so an `input_changed_during_run` run keeps its reason while
`snapshot_cleanup_failed` is still counted. NIT: the week fixture imports `MIN_DECISIONS`,
not the literal. `.gitignore` untouched.

## 8. FIX 1f -- AMENDMENT 4, codex sol round-3 findings 1-4
Constructs only; the following BEFORE and AFTER lines are verbatim stdout from
Python one-liners using temporary shards, a read-time append, an empty selection,
and seven fixture days. No live archives or existing .s362-weeks-* were touched.
1. `_snapshot` retains the hash-time digest and refuses a short OR rewritten copy;
   the daily refusal names the path. Pinned by the input test
   `test_a_shard_changed_before_the_copy_refuses[rewrite]` (shrink remains tested).
2. `_prefix` checks the digest before `os.fstat(stream.fileno())` samples the size.
   Pinned by `test_growth_during_prefix_read_is_counted_from_open_handle`.
3. `_rows` accepts []; the daily runner emits zero games without replaying unrelated
   journals. `games_total` is additive; scheduled and served totals are zero.
   Pinned by `test_quiet_day_is_valid_but_unreadable_selection_refuses`, including
   malformed JSON, a non-list and non-ASCII input; the missing-file test remains.
4. Every prepared family row appends on COMPLETE, including a zero-game FAIL row.
   Pinned by `test_every_declared_family_including_quiet_ones_is_appended` and
   the week dedupe test. INCOMPLETE/REFUSED append-nothing tests remain unchanged.
```
1 input=abcd->WXYZ before=accepted,hash_retained=False
1 input=abcd->WXYZ after=input_changed_during_run,path=shard,hash_retained=True
2 input=size4->6_during_read before=changed[],appended_bytes=0
2 input=size4->6_during_read after=changed[],appended_bytes=2
3 input=[] before=exit3,refused1,schedule_not_a_nonempty_list
3 input=[] after=exit0,refused0,None,games_total0,all_counts_zeroTrue
4 input=COMPLETE,4_quiet_families before=rows1,quiet_appended0
4 input=COMPLETE,4_quiet_families after=rows5,quiet_appended4
```
FIX 1e's per-usable-artifact SUMMARY_FIELDS validation was confirmed, not rewritten.
Blank-line removals fund test additions; no existing test property was removed.
Test fixtures redirect the landed replay's TemporaryDirectory to pytest scratch.
Per-file results (daily, inputs, week): 26 passed in 1.68s; 45 passed in 1.41s;
19 passed in 1.08s. Both --help commands exit 0. B10 protected-file diff is empty.

## 9. FIX 1g -- AMENDMENT 5(a)-(e), astra round-4 critique
Local constructs only. AMENDMENT 5 supersedes earlier missing-state and torn-tail
behavior above. Full selection remains the denominator; served=false may PASS on
incidental receipts. The frozen window is scheduled_start through +WINDOW_S;
independent identity attestation belongs to S409.
(a) Week bytes are read once and retained with parsed rows for hashing.
Pinned: test_daily_swap_between_rows_and_hash_uses_one_read (seven opens total).
(b) Initial JSONL hashing seals the last newline; copy and verification use the same
prefix. size_bytes includes torn_tail_bytes; hashed_bytes excludes it. appended_bytes
measures growth past size_bytes after verification.
Pinned: test_torn_tail_is_excluded_from_snapshot_digest_and_prefix (two torn tails).
(c) Refused revisions are counted and skipped; latest non-refused as_of wins.
Pinned: test_refused_revisions_never_replace_latest_usable_revision.
(d) root_realpath and state_root_realpath call os.path.realpath; state entries retain
size_bytes, first_response_end_ts and last_response_end_ts from the snapshot,
normalizing response_end_utc. Missing date state refuses state_shard_missing.
Pinned: test_state_provenance_uses_realpaths_and_snapshot_receipts and
test_missing_book_is_not_a_refusal_but_missing_state_is.
(e) game_key is beside game_id, pinned by test_a_poisoned_schedule_entry_never_reaches_the_artifact.
Python one-liner stdout (e reverts just the projection line in memory); temporary
constructs only, BEFORE on fix 1f and AFTER on fix 1g:
~~~
a before rows=G1 hash_matches_rows=False
a after rows=G1 hash_matches_rows=True
b before refused=0 torn=0 unreadable=2 ADAPTER_REFUSED=True
b after refused=0 torn=2 unreadable=0 ADAPTER_REFUSED=False
c before selected=0 refused=2 missing=1
c after selected=1 refused=2 missing=0
d before missing=None realpaths=False
d after missing=state_shard_missing realpaths=True
e before game_id_present=True game_key=None
e after game_id_present=True game_key=401872945
~~~
Fix 1f's digest, append-count, quiet-day and zero-game family assertions remain.
Blank lines fund additions. Missing-state refusal supersedes the old missing-archive
assertion; absent-game behavior remains checked with present but empty state shards.
Per-file: daily 27 passed in 1.87s; inputs 47 passed in 1.54s; week 22 passed in 1.33s.
The first week run failed its read spy (keyword mode missed); the corrected spy
asserts one read per file and passes. Both helps exit 0; preflight 9 PASS / 0 FAIL; B10 diff empty.

## 10. FIX 1h -- AMENDMENT 6(a)-(b)
Source open/read OSError exceptions in _snapshot now become
ValueError("input_changed_during_run"), with filename carrying the source path
and the original exception as cause. _snapshots records the path in truncated,
which the daily runner copies into changed_inputs before refusing.
Destination open/write errors retain their original class and reason.
Pinned: test_a_shard_changed_before_the_copy_refuses[vanish] deletes the source
after hashing; the daily artifact refuses and names the path without replaying.
test_snapshot_source_errors_are_distinct_from_destination_errors enumerates
source open/read and destination open/write PermissionError cases.
Every previous assertion remains; comments and wrapping fund the LOC budget.
Same Python one-liner before/after: temporary source hashed, deleted, then
source-open FileNotFoundError("vanished") injected for a stable label:
~~~
input=present_at_hash_then_vanished_before_copy output=('FileNotFoundError','vanished') named_paths=[]
input=present_at_hash_then_vanished_before_copy output=('ValueError','input_changed_during_run') named_paths=['vanished']
~~~
AMENDMENT 6(b): Python 3.10.0; resolved temporary root:
C:\Users\neelj\AppData\Local\Temp
Sequential pytest -q -p no:cacheprovider:
daily: 31 passed in 1.56s; inputs: 48 passed in 1.48s; week: 22 passed in 1.11s.
Both helps exit 0; preflight 9 PASS / 0 FAIL; B10 diff empty.
No environment_unverifiable result: temporary constructs and all cases ran.
FIX 1e/1f/1g assertions remain, including status, cleanup, digest, append counts,
quiet days, family rows, tails, one-read provenance, revisions, paths and game_key.
No commit, network, live capture or real ledger operation was performed.
## 11. NOT VERIFIED

- No production archive was read for qualification and no week was appended to a real
  ledger: every number above is a construct or a fixture and no week exists.
- The `game_key` linkage (C4) is UNTESTED against the live archive; the subtree join
  is proven by fixtures, not the real root.
- AMENDMENT 5(g): orchestrator records first-real-run copy wall clock and snapshot
  bytes here. The copy has never run against a 186 MB shard: its cost
  is UNMEASURED and `<out>.snapshots` is assumed to have room for the day's shards. A
  prefix rewritten IN PLACE with identical bytes and size still passes the check.
- The transitive import closure of the daily runner DOES include `tape_fill_adapters`
  and `replay_units.fill_to_markout_fill` through the landed replay (C2). Only the direct
  import graph is asserted, plus the artifact's key and leaf-type shape.
- `forward_replay._prepare` locks `TARGET_LEDGER` under `vault/S362/`; the tests
  redirect it to a temporary directory, so the real run's locking under a concurrent
  writer is untested. `heartbeat_fields` was quoted, not exercised; two runs racing on
  one `--out` are handled by an exclusive create, never simulated.
- The seven-date completeness rule is a lane decision, not a measurement: no test
  distinguishes "a day with no scheduled games" from "a day whose artifact was never
  produced", because a missing artifact carries no evidence either way.
- Nothing here is a claim about qualification quality. A FAIL day is an honest
  result of this row, not a defect of the row.

## FIRST REAL RUN (orchestrator, 2026-09-23 00:41Z; AMENDMENT 7 record)

Landed code e25ed056d over the 2026-09-22 shards, --as-of 2026-09-23T06:00:00Z, run_nonce s390-first-run-2026-09-22, 1 m 23 s.
Six of six MLB games FAIL, qualified_games 0, refused 0 -- the expected honest result. Served games: TORBAL 0 qualified
decisions (no linked state row for the whole window: NOT_LIVE 660, STATE_STALE 660); MILPHI 117 and MIACHC 103 qualified
decisions of the 432 needed (ADAPTER_REFUSED 529 / 575, BOOK_STALE 526 / 568, LINKAGE_INVALID 746 / 785). Unserved games:
1-4 qualified decisions each (capacity subset). Every reason count and the day diagnostics are transcribed verbatim in
docs/evidence/tracking/specs/S390_spec.md AMENDMENT 7; the artifact is docs/evidence/forward/qualification/2026-09-22.json.
Counts only; no frozen value moves; the next spec (S421) is the state linkage for game_key 824785 and the usable-book
cadence versus the raw receipt cadence.
