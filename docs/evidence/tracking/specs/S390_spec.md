GAP S390 | sport all captured | worktree harness-h56 (master-based) | log cx_s390_daily_qualification
# Daily score-blind qualification + week report over the production capture (design: ASTRA_ROUND14 row 6, ASTRA_ROUND15 row 3)

SINGLE PROBLEM: the landed forward replay (row S362, rebuilt 04ca2ecee; native bridge row S389) can qualify a day's games from the
production archives, but nothing runs it after each day's games, nothing hashes what it read, and its week arithmetic
(forward_replay_qualification.Qualification.weeks) writes a TEMPORARY FamilyWeekLedger under a TemporaryDirectory, so no completed
week is ever appended to a durable family / week ledger and no streak can ever reach the frozen eight-week requirement. Component
completion is not a qualified week.

BINDING BEFORE-CONDITION: quote from master (a) scripts/platformkit/execution/forward_replay.py parse_args (--qualify, --books,
--state, --native, --trades, --supervisor-journal, --as-of, --run-nonce, --schedule, --global-cap, --max-order-qty,
--reservation-ttl-s) and run(); (b) forward_replay_qualification.py: REASONS (the closed set BOOK_STALE, STATE_STALE, ADAPTER_REFUSED,
LINKAGE_INVALID, NOT_LIVE, RESERVATION_INVALID, COVERAGE_LOW, DECISIONS_LOW, BOOK_CADENCE, STATE_GAP, TRADE_GAP, HOST_GAP,
TAPE_INCOMPLETE), game_summary (verdict, reason_counts, covered_ms, total_ms = WINDOW_S * 1000, qualified_decisions,
book_gap_median_ms, book_gap_p95_ms, book_gap_max_ms, state_gap_max_ms) and weeks(); (c) family_week_ledger.py:
FamilyWeekLedger.__init__(self, path, families_path, *, as_of=None), records(), append(row) (raises 'only completed ISO weeks may be
appended'), streak(family), forecast(family, games_per_week), the exact row field set (iso_year, iso_week, family, sport, game_ids,
qualified_game_ids, fill_bearing_game_ids, qualified_games, fill_bearing_games, exclusions, capture_gap_seconds,
source_artifact_path, source_sha256) and the families JSON entry fields (family, sport, market_type, weekly_floor,
independence_rules); (d) forward_capture_bridge.load_native(books_paths, state_paths, trade_paths, supervisor_journals, schedule, *,
as_of=None); (e) capture_scheduler.heartbeat_fields (profile_sha256, scheduled_games_total, scheduled_admitted) and
capture_scheduler.schedule_rows (the two-games-per-hour refusal at its line 113).
REAL ROW KEYS (production, main tree; the builder copies at most 30 rows of each kind VERBATIM into tracked fixtures -- public game
state and venue quotes only): books data/cache/ingame_books_local/kalshi/<sport>/<date>.jsonl (record_type snapshot | snapshot_bulk
| trade | trade_gap | trade_backfill_closed | fetch_error; fields as the S389 fixtures), state data/cache/ingame_books_local/state/
<sport>/<date>.jsonl (sport, game_key, request_start_utc, response_end_utc, http_status, state, status, home_abbr, away_abbr,
scheduled_start_utc, capture_ts, tick_start_ts), supervisor journals data/cache/capture_supervisor/supervisor_<name>.jsonl (host_gap
records), the committed schedules under docs/evidence/forward/schedules/ (entries: game_id, ticker, sport, family, scheduled_start,
selected_at). NOTE 2026-09-22: the six-game selection for tonight lives in 2026-09-22_maker_forward_full_selection.json (the
denominator of record) while 2026-09-22_maker_forward.json holds the three-game capacity subset the runner serves; both are
prospective (committed before any start).

CHANGE (owned files: NEW scripts/platformkit/ops/forward_qualification_daily.py, NEW scripts/platformkit/ops/forward_week_report.py,
NEW docs/evidence/forward/families_maker_forward.json, NEW tests/platformkit/ops/test_forward_qualification_daily.py, NEW
tests/platformkit/ops/test_forward_week_report.py, memo; NO landed module is edited):
1. families_maker_forward.json: one entry per captured sport (mlb, nfl, tennis, nba, soccer) with family maker_forward, market_type
   maker, weekly_floor equal to forward_replay_qualification.WEEK_GAMES (a test asserts the file's value equals the constant), and
   an independence_rules sentence per family stating that sports are separate strata and are never pooled.
2. forward_qualification_daily.py (<= 300 LOC): python -m scripts.platformkit.ops.forward_qualification_daily --date <UTC date>
   --schedule <denominator-of-record file> --books-root <root> --state-root <root> --supervisor-log-dir <dir> --as-of <UTC instant>
   --run-nonce <str> --out docs/evidence/forward/daily/<date>_maker_forward.json. It (a) resolves every archive file the replay will
   read for that date (the date shard AND the next UTC day's shard: a window can cross midnight), computes the SHA-256 of each, of the
   schedule, of every supervisor journal and of scripts/platformkit/ingame/forward_capture_profile.json, and writes them into the
   artifact BEFORE qualification; (b) runs the landed replay in native, qualify-only mode through its Python entry points (the bridge
   plus forward_replay.run) with --global-cap and --max-order-qty recorded as declared constants in the artifact; (c) emits, for EVERY
   scheduled game (absent games included: they FAIL with their reason codes and stay in the denominators), the game_summary fields
   verbatim plus game_id, ticker, sport, family, scheduled_start, and a served flag (whether the game also appears in the capacity
   subset the runner served, when a subset file is given by --served-schedule); strict-int counts; (d) never reads, imports or
   forwards any outcome, settlement, fill, mark or price VALUE: the artifact carries statuses, counts, milliseconds and hashes only,
   and a test asserts that the module's import graph excludes every scoring module (baseline_four_arm*, markout*, tape_fill*,
   gate_a0*) and that no key named outcome, settlement, result, fill or mark appears in the artifact; (e) refuses (exit 3; the
   artifact is still written with refused = 1 and the reason) when the schedule is absent or when any entry's selected_at is not
   strictly before its scheduled_start; a MISSING archive file is NOT a refusal: the affected games FAIL NOT_LIVE / LINKAGE_INVALID
   and the run continues; (f) writes the artifact atomically (tmp + fsync + os.replace) and never overwrites an existing artifact for
   the same date (a re-run writes <date>_maker_forward.r<N>.json and says so on stdout).
3. forward_week_report.py (<= 300 LOC): --ledger data/cache/forward/family_week_ledger.jsonl --families
   docs/evidence/forward/families_maker_forward.json --daily-dir docs/evidence/forward/daily --as-of <UTC instant> --out
   docs/evidence/forward/weeks/<iso_year>-W<iso_week>_maker_forward.json. For each (sport, family) it assembles the COMPLETED ISO
   week strictly before as-of from the daily artifacts (games assigned by scheduled_start), builds the ledger row with the exact
   field set (fill_bearing_game_ids = [], exclusions = the failing games with their reason codes, capture_gap_seconds = the largest
   book_gap_max_ms of the week as a decimal string of seconds, source_artifact_path = the week report path, source_sha256 = the
   SHA-256 over the daily artifacts' bytes concatenated in date order), appends it through FamilyWeekLedger.append ONLY when that
   week is complete (the ledger's own refusal is the guard: the report never catches and hides it), and prints per family:
   qualified games this week, PASS / FAIL against weekly_floor, streak() and forecast(). A week with a missing daily artifact for a
   day that had scheduled games is reported INCOMPLETE and NOT appended. Idempotent: re-running for an appended week reports the
   existing row and appends nothing (dedupe on (iso_year, iso_week, family, sport)).
4. Tests: fixtures from the REAL row shapes; a day whose one scheduled game is absent from every archive -> FAIL NOT_LIVE with
   covered_ms 0 and total_ms equal to WINDOW_S * 1000, still counted; the artifact's hashes equal the fixture files' SHA-256; the
   import-graph assertion; re-run does not overwrite; the week report refuses the current week (the ledger raises), appends a
   completed week once, dedupes on the second run, reports INCOMPLETE when a daily artifact is missing; streak arithmetic through
   the landed ledger only (no parallel implementation; AMENDMENT 3(f) of S362 applies); the served flag is false for a game absent
   from the served subset and never changes its verdict.
5. Memo docs/evidence/harness/S390_daily_qualification_2026-09-22.md.

CONTROLS: construct / fixture tests only; no network; no real archive run by the builder beyond copying fixture rows; the FIRST real
run is the orchestrator's from the repo root after tonight's games. ACCEPTANCE: per-file tests pass one at a time; both --help work;
<= 300 LOC each; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED. No bar or threshold is restated as a literal: every bar
is imported from forward_replay_qualification (contract Q3).

AMENDMENT 1 (2026-09-22 17:0xZ; binding; the Opus build's four conflicts plus the orchestrator's schedule fix). (a) FamilyWeekLedger
refuses duplicate family names (family_week_ledger.py:71-72) and pins one sport per family (:100-101): the declarations file names
five families maker_forward_<sport>; the daily artifact and the week report resolve a scheduled game's family BY SPORT from the
declarations and refuse a sport carrying two families; schedule entries keep the prospective label maker_forward. (b) The import-graph
assertion binds the NEW modules' own direct imports (ast); the landed replay's own imports are the dependency's business; the
artifact-shape test (no outcome / settlement / result / fill / mark key; statuses, counts, milliseconds and hashes only) is the binding
score-blindness proof. (c) MEASURED on the real archives: a scheduled game absent from every archive FAILS with LINKAGE_INVALID plus
BOOK_CADENCE, COVERAGE_LOW, DECISIONS_LOW, STATE_GAP and TAPE_INCOMPLETE, covered_ms 0, total_ms 3600000; NOT_LIVE arises only from an
observed book decision; CHANGE item 4 asserts LINKAGE_INVALID. (d) The S389 bridge requires a nonempty game_key per schedule entry
(forward_capture_bridge.py:80-85) while the S386 writer emits six fields without it: the orchestrator added game_key (= the MLB gamePk
= game_id, the state capture's key for MLB) to both 2026-09-22 schedule files before any start (commit on master); row S403 makes the
writer emit it. (e) A week is INCOMPLETE unless a daily artifact exists for all seven UTC dates (a quiet day needs a zero-game
artifact): the lane's fail-closed choice, accepted.

AMENDMENT 2 (2026-09-22 17:2xZ; binding; from the orchestrator's real-archive runs of the candidate). (a) ARCHIVE ROOTS: the
production layout is <root>/kalshi/<sport>/<date>.jsonl for books and <root>/state/<sport>/<date>.jsonl for state; the candidate
joined <root>/<sport>/<date>.jsonl and therefore found no archive (absent_or_unreadable_input 4, every game LINKAGE_INVALID). The
CLI takes ONE --capture-root (the S391 --root, data/cache/ingame_books_local) and derives the kalshi and state subtrees itself; the
artifact records both resolved paths; --books-root / --state-root are removed (a root that does not contain the two subtrees is a
refusal, counted). (b) DECLARED PROFILE, NOT REPLAY DEFAULTS: the reservation TTL, the focus tick and the profile hash come from
scripts/platformkit/ingame/forward_capture_profile.json (the landed S388 declaration: focus_tick_s 5, reservation_ttl_s 5), never
from the replay's own 2-second default -- a 2 s reservation at a 5 s tick can cover at most 40 percent of a window and would fail
every game on COVERAGE_LOW by construction rather than by capture quality; the artifact's declared_constants names the profile path,
its sha256 and each value it took from it. global_cap and max_order_qty stay declared constants of the qualification (recorded).
(c) unconsumed_supervisor_records (child_start and the like) are counted, never a failure.

AMENDMENT 3 (2026-09-22 17:4xZ; binding; from the orchestrator's real run of fix 1c on the live archives). MEASURED: the run refused
with input_changed_during_run on the mlb book shard (186 MB) and the mlb state shard because the LIVE captures append to today's
shards every few seconds -- the rehash-after-qualification rule of AMENDMENT 2 / the sol ruling can never pass while a capture is
writing, and every daily run happens while some capture writes (tennis and next-day discovery run until midnight UTC). The
requirement stands (the hashes must identify the bytes qualification read); the mechanism changes: (a) for every archive input the
runner records the size at hash time, copies exactly that byte prefix into a run-scoped snapshot directory beside the artifact
(<out>.snapshots/<kind>/<sport>/<date>.jsonl; the copy is bounded to the recorded size, a torn final line inside the prefix is
handed to the landed reader unchanged and counted as it counts it), hashes the SNAPSHOT (that digest is the artifact's input
hash), and hands the SNAPSHOT paths to the bridge; the snapshot directory is deleted after the artifact is written (its size and
per-file byte counts stay in the artifact); (b) the post-run rehash is replaced by a prefix check: after the run the live file's
first <recorded size> bytes must still hash to the recorded digest (an in-place rewrite of the prefix refuses input_changed_during_run;
bytes appended beyond the prefix are counted appended_bytes and are never a refusal); (c) the as-of filter is unchanged. Tests:
a live-shard construct that grows during the run passes with appended_bytes > 0; a prefix rewrite refuses; the artifact's hashes
equal the snapshot digests; the snapshot directory is gone after the run.


AMENDMENT 4 (2026-09-22 18:4xZ; binding; from the codex sol round-3 verdict on fix 1d, read together with Opus round 3; fix 1e
already closed the per-artifact SUMMARY_FIELDS validation, the REFUSED / ABORTED status truth and the cleanup-never-masks rule).
(a) PREFIX RACE CLOSED: the digest computed at hash time is RETAINED; after the size-bounded copy the snapshot's digest must
equal it, else the input refuses input_changed_during_run naming the path (a rewrite between hashing and copying can no longer
become the artifact's hash). (b) appended_bytes is measured from the file size taken AFTER the prefix verification, through the
open handle, never from a size sampled before the read. (c) QUIET DAY: an EMPTY schedule (a committed file whose selection has
zero entries) is a valid day -- the daily artifact is written with games_total 0 and every count 0, NOT refused, so the week can
complete; a MISSING or unreadable schedule file still refuses. (d) For a COMPLETE week every prepared family row is appended,
including a zero-game family row (which the WEEK_GAMES bar makes a FAIL row -- an honest record), exactly as CHANGE 3 states.
(e) The ten-plus .s362-weeks-* directories in the worktree root are leftovers of the LANDED forward_replay_qualification.weeks()
TemporaryDirectory (cwd-relative; Windows cleanup fails); they are not candidate files (the landing commits by pathspec), their
removal was denied to the fix agent and is recorded for the owner; a PROPOSED fix to the landed module belongs to its own row.


AMENDMENT 5 (2026-09-22 19:1xZ; binding; from the astra round-4 critique on fix 1f; the full critique is archived as
docs/evidence/harness/S390_astra_r4_critique_2026-09-22.md and is binding where it names a line). (a) WEEK PROVENANCE FROM ONE
READ: the week report reads each daily artifact's bytes ONCE and derives BOTH its parsed rows and its recorded hash from those
same bytes (forward_week_report.py:90 parsed, :189 re-opened for hashing -- a daily republish between the two reads let a
COMPLETE week carry the hash of refused bytes); a test swaps the file between the two operations and shows the hash and the rows
agree. The daily runner may still write twice (the artifact, then the cleanup outcome) but every reader hashes what it parsed.
(b) TORN TAIL TRIMMED AT COPY: the size-bounded prefix copy ends at the LAST NEWLINE within the recorded size (the bytes after it,
a torn final line, are counted torn_tail_bytes and are NOT part of the snapshot or its digest), so a torn line never reaches the
landed reader where forward_replay_io.py:162 counts malformed JSON and forward_capture_bridge.py:253 makes unreadability fatal for
every game; the prefix check after the run compares the same trimmed prefix; tests: a shard whose recorded size ends mid-line
passes with torn_tail_bytes > 0 and no ADAPTER_REFUSED. (c) REVISIONS: a refused revision of a date does not poison the date --
the week selects the latest NON-refused revision by as_of (refused revisions counted refused_daily_artifacts, never selected);
a date with only refused revisions stays missing. (d) PROVENANCE OF THE STATE ROOT: the artifact records, for the capture root and
the state subtree, the resolved real path (os.path.realpath, so a junction's target is named), and for the date's state shard
its byte size and the first / last response_end_ts read from the snapshot; a MISSING state shard for the date refuses
state_shard_missing (never a silent zero coverage). (e) GAME KEY IN THE PROJECTION: the per-game projection carries game_key and
game_id together (a swapped key is at least visible beside its ticker); independent attestation of the six mappings is row S409
(schedule identity attestation, astra round 16 candidate 1), allocated now and NOT this row. (f) NOTED, unchanged: a game not
served by the capture can still qualify on incidental receipts (served false, verdict PASS) -- the artifact's served flag makes it
explicit and the memo says the denominator is the full selection; the qualification window is [scheduled_start, +3600 s) by the
frozen bar (late starts lose coverage, extra innings do not extend it); unknown per-game reasons fail closed. (g) The memo records
the copy wall clock and the snapshot bytes for the first real run when the orchestrator runs it.

AMENDMENT 6 (2026-09-22 21:3xZ; binding; from the codex sol round-4 verdict on fix 1f, read after fix 1g landed AMENDMENT 5). (a) A VANISHED SOURCE NAMES ITS PATH: MEASURED by the round-4 verifier -- a source present at hash
time and gone before the size-bounded copy escapes _snapshot as FileNotFoundError, and the outer handler reports a
generic qualification_failed with no affected path (forward_qualification_daily.py:88-91; reproduction
input=present_at_hash_then_vanished_before_copy output=('FileNotFoundError','vanished') named_paths=[]), which AMENDMENT 4(a) already forbids. RULING: every OSError raised while OPENING or READING a source inside _snapshot
converts to ValueError("input_changed_during_run") carrying that path, so _snapshots records it in changed_inputs;
an OSError raised while WRITING the snapshot DESTINATION keeps its own failure class and is never relabelled an
input change. Tests: a source deleted between the hash and the copy refuses input_changed_during_run with the path
present in changed_inputs; an unwritable destination still fails as a write error with its own reason.
(b) A ROUND THAT CANNOT RUN TESTS SAYS SO: MEASURED -- the round-4 verifier executed none of the required 27/47/22
cases because every case failed during tmp_path setup in a read-only environment, so the REJECT rests on static
reading alone and the memo's 26/45/19 counts were never independently reproduced (fix 1g reports 27/47/22 passing).
RULING: a verification round that cannot create a temporary directory records environment_unverifiable for the test
clause and may NOT convert that inability into a candidate defect; the round is re-run with a writable TMPDIR before
any test-based finding of that round is binding. Test: the verifier's transcript prints the resolved temporary root
and the three pass counts, or prints environment_unverifiable beside them.
(c) NOTED, unchanged: the round-3 closures (retained digest on prefix change, appended_bytes from the post-verification
size, empty-selection parse, five family rows, unreadable_daily_artifact) and AMENDMENT 5(a) and 5(c) were reproduced
by this round and need no fix; real archives, real qualification, a real ledger append, junction targets and
large-shard runtime stay NOT VERIFIED and belong to the orchestrator's real run, not to this row's fix agent.

AMENDMENT 7 (2026-09-23 04:4xZ; RECORD, not a rule; the FIRST REAL RUN of the landed code e25ed056d by the orchestrator over the
2026-09-22 shards after the 00:40Z boundary; --as-of 2026-09-23T06:00:00Z; run_nonce s390-first-run-2026-09-22; declared
constants global_cap 1 / max_order_qty 1 / focus_tick_s 5 / reservation_ttl_s 5 / window_s 3600 / capture profile sha256
5bb818074c5083049e804bffda59c2b5b701706048983d32bbb313120ea3607c; artifact docs/evidence/forward/qualification/2026-09-22.json;
wall clock 1 m 23 s; snapshots 7 files / 398,431,477 bytes then removed; mlb books archive 359,982,871 bytes sha256
4d51e331d9af5962d1d720409a1aa58095a64ad0790a0ef52b2ce825632ce06d with 252,238 bytes appended to the 2026-09-23 shard during
the run; torn tail 0; changed_inputs []; refused 0). VERDICT: six of six MLB games FAIL, qualified_games 0 -- the expected
honest result; the reason codes are the finding. Per game (book gap ms median / p95 / max; covered_ms; state_gap_max_ms;
qualified decisions; reason counts): TORBAL served 5178 / 7980 / 287751; 0; 3600000; 0; NOT_LIVE 660, STATE_STALE 660,
RESERVATION_INVALID 660, LINKAGE_INVALID 778, ADAPTER_REFUSED 146, BOOK_STALE 146, BOOK_CADENCE 1, COVERAGE_LOW 1,
DECISIONS_LOW 1, STATE_GAP 1, TAPE_INCOMPLETE 1. MILPHI served 5202 / 189616 / 716332; 510471; 11090; 117; ADAPTER_REFUSED
529, BOOK_STALE 526, LINKAGE_INVALID 746, RESERVATION_INVALID 541, BOOK_CADENCE 1, COVERAGE_LOW 1, DECISIONS_LOW 1,
TAPE_INCOMPLETE 1. STLPIT unserved 297953 / 2043914 / 2043914; 7235; 11088; 2; LINKAGE_INVALID 73, RESERVATION_INVALID 2, plus
the four single-count codes. CLEBOS unserved 396566 / 2044769 / 2044769; 5000; 11081; 1; LINKAGE_INVALID 73,
RESERVATION_INVALID 3, plus the four. CINATL unserved 646567 / 1377337 / 1377337; 19353; 26090; 4; LINKAGE_INVALID 75, plus the
four. MIACHC served 5219 / 218384 / 324319; 437941; 26104; 103; ADAPTER_REFUSED 575, BOOK_STALE 568, LINKAGE_INVALID 785,
RESERVATION_INVALID 587, STATE_STALE 2, plus the four. Day diagnostics: inconsistent_touch 5121, one_sided_book 4857,
price_out_of_range 3554, invalid_backfill_id 328, unlinked_state_row 8013, unconsumed_books_records 145921,
unconsumed_trades_records 66134, unselected_trade_records 135884, missing_directional_team_evidence 30,
missing_tape_lower_bound 3, open_backfill 4, conflicting_state_linkage 1, state_key_conflicted 1, LINKAGE_INVALID 1. READING
(counts, not conclusions): the served games' RAW receipt cadence is the S410 picture (median about 5.2 s) but the USABLE-book
cadence is not -- adapter refusals (one-sided / inconsistent books) and BOOK_STALE dominate the served games, and TORBAL had no
linked state row for its entire window (state_gap_max = the window; NOT_LIVE at every decision) while its two served peers
linked. NEXT SPEC (S421, to write): the state-to-market linkage for game_key 824785 and the unlinked_state_row 8013 count; the
usable-book cadence vs receipt cadence gap. No frozen value moves.
