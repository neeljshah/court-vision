GAP S421 | sport mlb (rule sport-blind) | worktree harness-h74 (master-based) | log cx_s421_qualification_causes

# The two things between the capture and a PASS day: name what ADAPTER_REFUSED actually is, and state status truth

SINGLE PROBLEM: the FIRST REAL S390 run (docs/evidence/tracking/specs/S390_spec.md AMENDMENT 7; artifact
docs/evidence/forward/qualification/2026-09-22.json; six of six MLB games FAIL) produced reason counts that CANNOT be acted on,
because the two dominant codes each conflate several distinct causes. The raw receipt cadence is healthy -- the S410 landed-code
re-audit (S410_spec.md AMENDMENT 5) measured in-window medians 5.179321 / 5.181505 / 5.163793 s with every frozen comparison met
on the three served games -- so the failure is NOT capture cadence. It is (a) an unnamed condition reported as ADAPTER_REFUSED and
(b) a state feed that never reported live for one served game. Neither can be fixed until it is named and counted.

BINDING BEFORE-CONDITION (every item MEASURED by the orchestrator on 2026-09-23 00:41-00:55Z against master and the real
2026-09-22 shards; quote from master):

(a) scripts/platformkit/execution/forward_replay.py:232 VERBATIM --
    `qualification.decision(row, converted and touch and not row.get("_refusal"),` -- ONE boolean feeds the gate, and
    forward_replay_qualification.py:58 turns its negation into the single reason `"ADAPTER_REFUSED": not accepted`.
(b) forward_replay.py:138-148 -- `converted = True` after the adapter returns; `touch = True` only when
    `all(any(price == best for price, _ in queue[side]) for side, best in (("yes", book["best_bid_cents"]),
    ("no", 100 - book["best_ask_cents"])))`; :150 gates the book-cadence bucket on `touch`, and :175 skips a linked row when
    `not touch`.
(c) MEASURED, the decisive fact: the landed adapter accepts EVERY snapshot of the three served tickers on the 2026-09-22 shard.
    Running scripts/platformkit/execution/capture_book_adapter.to_quote_book over
    data/cache/ingame_capture_view_v2/kalshi/mlb/2026-09-22.jsonl (record_type snapshot or snapshot_bulk), decoded with
    parse_float=Decimal and parse_int=Decimal: TORBAL 777 accepted / 0 refused, MILPHI 745 / 0, MIACHC 325 / 0. Every one of those
    snapshots also carries both yes_bid and yes_ask (777 / 745 / 325 both-sided, zero one-sided). YET the S390 run counted
    ADAPTER_REFUSED 146 (TORBAL), 529 (MILPHI), 575 (MIACHC). Therefore the refusals attributed to the adapter are NOT adapter
    refusals: they are the `touch` term of (a), or a `_refusal` set later in the same try block, and the reason code cannot say
    which. The day-level diagnostics one_sided_book 4857 and inconsistent_touch 5121 are whole-shard counts across every ticker
    and do NOT describe these three games.
(d) MEASURED, the second fact: the state feed never reported live for the served game TORBAL. In
    data/cache/ingame_capture_view_v2/state/mlb/2026-09-22.jsonl the rows keyed game_key "824785" number 417 and EVERY one has
    status "pre"; the two served peers carry both phases (game_key "823412" 316 pre + 592 live; "824624" 371 pre + 262 live).
    That is exactly the S390 result for that game: NOT_LIVE 660 and STATE_STALE 660 at every decision, state_gap_max_ms 3600000
    (the whole window), qualified_decisions 0. forward_replay_qualification.py:165 VERBATIM --
    `g["state_at"], g["live"] = (at if good else None), good and row["status"] == "live"` -- so a feed that never says live makes
    a game unqualifiable no matter how good the book is, and nothing in the artifact distinguishes "the game was postponed or
    delayed" from "the state source stalled".
(e) forward_replay_qualification.py:18-24 -- the frozen bars COVERAGE_PERCENT 90, MIN_DECISIONS 480, BOOK_MEDIAN_S 45,
    BOOK_P95_S 90, BOOK_MAX_S 120, STATE_GAP_S 30 and the REASONS frozenset. These are IMPORTED, never re-declared, and S421
    moves none of them.
(f) The S390 run's per-game qualified_decisions: TORBAL 0, MILPHI 117, MIACHC 103, STLPIT 2, CLEBOS 1, CINATL 4 -- against
    MIN_DECISIONS 480. The unserved three are the capacity subset (S410 AMENDMENT 2 and 5) and are out of scope here.

CHANGE (owned files: NEW scripts/platformkit/ops/qualification_cause_report.py, NEW
tests/platformkit/ops/test_qualification_cause_report.py, NEW tests/platformkit/ops/fixtures/s421_books.jsonl and
s421_state.jsonl, NEW docs/evidence/harness/S421_qualification_causes_2026-09-22.md. forward_replay.py,
forward_replay_qualification.py and capture_book_adapter.py are LANDED and are NOT edited by this row -- S421 MEASURES and
REPORTS; any change to them is a separate row written from this row's findings):

1. qualification_cause_report.py (<= 300 LOC) takes `--books-root`, `--state-root`, `--schedule`, `--date`, `--as-of` (a required
   zoned instant, parsed only through scripts.platformkit.execution.venue_time.parse_venue_time) and `--out`, and for each game of
   the schedule reports, as counts only:
   (i) THE DECOMPOSITION OF ADAPTER_REFUSED into three mutually exclusive named causes per book row, each computed by calling the
       LANDED code paths, never a reimplementation: `adapter_refused` (to_quote_book raised -- the ValueError text recorded
       verbatim as the sub-reason), `touch_unavailable` (the adapter returned but the (b) touch predicate is false -- and the
       report records WHICH side failed, yes or no or both, and the observed best price against the queue's nearest level), and
       `downstream_refusal` (the adapter returned and touch held, but `_refusal` was set later -- the text recorded verbatim).
       The three counts must sum EXACTLY to the rows the gate would call not-accepted; a test asserts the sum against a construct.
   (ii) THE STATE STATUS PROFILE per game: the count of state rows by `status` value, the first and last capture instant of each
       status, the longest run without a live row inside the scheduled window, and a `never_live` flag. No inference about WHY --
       "postponed" is never written by this report; the counts are the finding.
   (iii) A per-game LINE that puts the two together: qualified decisions the gate would reach, the decomposed not-accepted
       counts, and the state profile -- so a reader can say in one glance whether a game failed on books, on state, or on both.
2. Decimal discipline: every price, size and second is read with parse_float=Decimal and parse_int=Decimal and serialized as JSON
   number text (never a float); counts are strict ints; the artifact is written atomically (temp file in the destination
   directory, flush, fsync, os.replace) and a serialization failure leaves any previous artifact byte-identical.
3. Refusals, never silence: a book or state row the report cannot interpret is counted under a named reason with its raw text
   recorded (repr), never dropped; a missing shard is a named refusal with the path, never an empty result; a game absent from a
   shard is reported with zero counts and a named reason, never omitted from the artifact.
4. The memo records the REAL 2026-09-22 run of this report over all six games of
   docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json, cites S390 AMENDMENT 7 and S410 AMENDMENT 5 for
   the numbers it builds on, and states in Q6 vocabulary what the decomposition shows. It ends with the NEXT-ROW question its
   counts answer: whether the touch predicate of (b) is too strict for Kalshi's ladder shape (a reporting defect) or the ladder
   genuinely lacks the touch (a capture defect) -- and it does NOT answer that question by assertion.

TESTS (per-file only; run each file separately): construct fixtures cover an adapter refusal, a touch failure on each side and on
both, a downstream refusal, a clean accept, a game whose state rows are all pre, a game with both phases, a game absent from the
state shard, a missing shard, a non-finite and a null price, and the atomic-write failure path. The three decomposed counts sum to
the not-accepted total in every construct.

DO NOT: edit forward_replay.py, forward_replay_qualification.py, capture_book_adapter.py or any landed test; move a frozen value;
write data/registry/; flip a flag; run the trial runner or any real corpus scoring; state a market advantage or a currency amount;
re-print a retracted number. This row reports counts about the capture's own plumbing, nothing about a market.

AMENDMENT 1 (2026-09-23 16:0xZ; binding; MEASURED by an Opus 5.5 real-shard probe with the LANDED functions over the full
2026-09-22 shard and the S390-hashed 27,402,739-byte prefix of 2026-09-23, as_of 2026-09-23T06:00:00Z; record:
docs/evidence/harness/S421_real_shard_probe_2026-09-23.md, scripts scripts/platformkit/ops/probes/s421_probe.py + s421_probe_touch.py). THE BEFORE-CONDITION'S
ITEM (c) IS CORRECTED. The landed to_quote_book does NOT raise on a bad row: it RETURNS {"refused": True, "reason": <text>,
"refusal_count": 1} (capture_book_adapter.py:186-187). The 00:41Z probe counted exceptions and therefore saw zero refusals.
Counting the RETURNED refusals reproduces the S390 AMENDMENT 7 in-window counts EXACTLY -- TORBAL 146, MILPHI 529, MIACHC 575 --
and EVERY ONE is the adapter's own reason `inconsistent_touch`. The touch predicate of (b) never fails on an accepted row
(touch_unavailable 0 on every ticker, both sides) and no `_refusal` is set later (downstream 0). Whole-shard counts: TORBAL 777
rows / 146 refused / 631 touch ok; MILPHI 745 / 540 / 205; MIACHC 325 / 197 / 128 (MILPHI's 11 extra refusals lie outside its
window; MIACHC's window crosses midnight so most of its 575 sit in the 09-23 prefix). The path that carries the refusal:
forward_replay_policy.py:42-45 books() runs the three adapters and raises ValueError(out["reason"]) on a refusal dict;
forward_capture_bridge.load_native :259-266 calls _book(row) and sets row["_refusal"] = str(exc) BEFORE the replay starts;
forward_replay.py:66-67 re-raises it, so converted stays False and the gate's single boolean is False. There is no cadence
sampling: decision() runs once per book row (:231-232), and TORBAL's 660 in-window rows equal its NOT_LIVE 660. S390
AMENDMENT 8's second reading ("the unnamed touch term") is therefore WRONG and this amendment supersedes it (S390 AMENDMENT 9
records the same); every COUNT stands. WHAT inconsistent_touch IS on these rows: in every refused in-window row the orderbook
ladder's top level AGREES with the row's own yes_bid / yes_ask / no_bid / no_ask fields; only the raw_market price fields (the adapter's raw.* touch candidates)
disagree with them -- by exactly 1 cent on every TORBAL instance (165 side-instances), by 1-20 cents on MILPHI (423 of 1,040
side-instances at 1 cent; 34 at 17-20 cents), by 1-4 cents on MIACHC (563 of 1,083 at 1 cent). Only record_type snapshot rows
are refused; no snapshot_bulk row is. RULINGS. (1) CHANGE item 1(i) is restated: `adapter_refused` means to_quote_book RETURNED
a refusal dict OR raised; the reason text is recorded verbatim and adapter refusals are SUB-DECOMPOSED BY REASON; for
`inconsistent_touch` the report records per row WHICH source pair disagrees (ladder top vs row fields vs raw_market raw.* fields, on
each side) and the disagreement in cents, reported per ticker as a count-by-cents distribution (never a mean); `touch_unavailable`
and `downstream_refusal` are KEPT -- they are the zeros that must be shown to be zero, each with a construct test that makes it
nonzero. (2) CHANGE item 2 is narrowed: the report decodes book and state rows THROUGH THE LANDED READER, the same decode the
qualification run uses (parse_float=Decimal; integers stay Python int -- the landed count() refuses a Decimal integer with
invalid_count, measured on http_status), so its counts reproduce the S390 artifact; Decimal discipline applies to every value the
report DERIVES; a row the landed reader refuses is a counted named refusal. (3) The memo's NEXT-ROW question is restated: it is
NOT about the touch predicate. It is whether raw_market's raw.* price fields and the orderbook in the SAME capture row were fetched at
different instants (a capture-side defect; if so, which one is fresher) or whether the adapter's all-sources-must-agree rule
refuses a book the ladder alone would price (an adapter rule, argued in a separate row). The report answers neither by
assertion; it counts. (4) The state profile of (d) stands as measured (824785 pre 417 rows 16:58:34Z-23:59:53Z never live;
823412 pre 316 + live 592 from 22:19:58Z; 824624 pre 371 + live 262 from 23:15:47Z; timestamp field response_end_utc); the report
profiles by that field and names it. (5) The header's worktree is superseded: the build runs in nba-harness-h75. (6) The real
run of the memo (CHANGE item 4) must reproduce the three in-window counts above or stop.

AMENDMENT 2 (2026-09-23 16:4xZ; binding; from the ORCHESTRATOR REAL RUN of build 2 over the 2026-09-22 selection:
--books-root data/cache/ingame_capture_view_v2/kalshi --state-root data/cache/ingame_capture_view_v2/state --schedule
docs/evidence/forward/schedules/2026-09-22_maker_forward_full_selection.json --date 2026-09-22 --as-of 2026-09-23T06:00:00Z;
wall 16:19:58Z-16:21:33Z; peak working set 2,294 MB measured by the orchestrator's watch). THE COUNTS REPRODUCE AMENDMENT 1
EXACTLY: TORBAL causes adapter_refused 146 / touch_unavailable 0 / downstream_refusal 0, adapter_reasons inconsistent_touch
146; MILPHI 529 / 0 / 0 (inconsistent_touch 529); MIACHC 575 / 0 / 0 (inconsistent_touch 575); STLPIT, CLEBOS, CINATL 0 / 0 / 0
with no book rows (the unserved capacity subset); TORBAL rows 660, qualified_decisions 0, state_profile never_live true,
longest_without_live_s 3600, statuses pre count 546 (first 2026-09-22T16:58:34.287948Z, last 2026-09-23T02:09:48.967841Z,
timestamp_field response_end_utc; the 546 exceeds AMENDMENT 1's 417 because the report also reads the 2026-09-23 shard's rows
before as_of, which is correct for the window); diagnostics future_books 4357, future_state 425, LINKAGE_INVALID 1,
conflicting_state_linkage 1, state_key_conflicted 1, missing_directional_team_evidence 30, state_rows_missing_start 0.
DEFECT, MEASURED: the artifact is 283,940,291 bytes because every game carries a "details" list with the VERBATIM RAW TEXT of
every book row, accepted rows included -- a counts-only report that re-publishes the whole shard, and the reason the peak
working set reached 2.3 GB. RULING: (1) the artifact is COUNTS ONLY: no per-row "details" list; for each named refusal reason
the report keeps the count and at most THREE bounded examples (the row's capture timestamp and ticker plus the refusal text;
never the raw row) -- an uninterpretable row keeps repr(raw) truncated to 512 characters, per CHANGE item 3; the artifact for
a six-game day must be under 1 MB and a test pins the bound on a construct with 10,000 rows; (2) memory is bounded by
streaming: one pass per shard, per-game accumulators only, no list of rows retained; the real run records the measured peak
working set beside the wall time and the row count; (3) the memo records THIS real run verbatim (the counts above) as the
BEFORE record and the fix's real re-run by the orchestrator must reproduce the same counts with the bounded artifact;
(4) the inconsistent_touch sub-decomposition of AMENDMENT 1 ruling (1) (which source pair disagrees, count-by-cents per ticker)
is REQUIRED in the artifact -- confirm it is present or add it; the memo quotes the per-ticker cents distribution.

AMENDMENT 3 (2026-09-23 17:1xZ; binding; from round 1 on fix 1b -- Opus tier 1 REJECT, Opus tier 2 ACCEPT WITH CORRECTIONS;
every item MEASURED on constructs). (a) THE SUM MUST MATCH THE LANDED GATE, NOT THE REPORT'S OWN ADMISSION: the landed
load_native (forward_capture_bridge.py:259-267) carries a book row that fails _common (http_status not 200, a bad count), a
policy.books failure (to_fill_snapshot / to_mark_tick / size), a tied duplicate (forward_replay_io.py:129-131) or an
unrepresentable time INTO the replay with _refusal set, and decision() counts it ADAPTER_REFUSED; the candidate refuses such
rows upstream, so they never reach decision() and "rows", "not_accepted" and the three-cause sum undercount the gate
(http_status 500 -> report not_accepted 0 vs landed ADAPTER_REFUSED 1; orderbook size "NaN" -> 0 vs 1; two tied non-identical
rows -> 0 vs 2). The 2026-09-22 counts are unaffected (146 / 529 / 575 reproduced) but the invariant is wrong on inputs real
days carry. RULING: the report mirrors load_native -- every such row enters the observed replay with row["_refusal"] set
and is stored (add_valid); the cause set becomes FOUR mutually exclusive names that sum EXACTLY to the landed gate's
not-accepted: pre_adapter_refused (the bridge's _common / duplicate / unrepresentable-time refusals, reason verbatim),
adapter_refused (to_quote_book's returned refusal OR a policy.books refusal, reason verbatim -- AMENDMENT 1 names policy.books
as the carrying path), touch_unavailable, downstream_refusal; a test compares each construct game's not_accepted against the
landed _prepare's ADAPTER_REFUSED on the four constructs above; the precedence is STATED in the artifact (pre_adapter ->
adapter -> touch -> downstream) and an example is filed under the winning cause. (b) CENTS KEYS ARE PLAIN INTEGER TEXT:
str(Decimal.normalize()) wrote "2E+1" for 20 and "1E+1" for 10; keys are format(d, "f") or an int once the value is whole.
(c) THE CENTS UNIT IS NAMED AND THE SIDE COUNT IS REPORTED TOO: one unit is one disagreeing source pair on one side; on a
refused side the two raw fields agree with each other and disagree with the other three sources, so each side yields six
pairs (165 sides x 6 = 990 for TORBAL; 423 x 6 = 2538; 22 x 6 = 132; 563 x 6 = 3378). The artifact reports BOTH the pair count
and the SIDE-INSTANCE count by cents per ticker (a side counted once), and the memo states the factor and quotes the
artifact's per-ticker distributions verbatim. (d) EXAMPLES CARRY RAW TEXT ONLY FOR UNDECODABLE ROWS: refuse() wrote
raw[:512] for every refusal including interpretable rows (http_status_refused, nonfinite_size, duplicate_record); an
interpretable refusal's example is at / ticker / reason only. (e) A disagreements() failure counts under its own name
(disagreement_analysis_errors) and never re-counts the row as refused. (f) The SQLite spool goes to a tempfile scratch
directory, never out.parent (it landed beside the artifact under docs/); a killed run leaves nothing beside the artifact.
(g) The owned set gains the additive helpers the build wrote -- scripts/platformkit/ops/qualification_cause_stream.py and
qualification_cause_runtime.py (or the names the tree carries) and their tests -- provided each is <= 300 lines and no landed
module is edited; the memo lists every owned file with its byte size. (h) THE MEMO'S AFTER RECORD: the fix-1b real re-run
verbatim (command, wall 16:44:30Z-16:46:04Z, peak 617 MB, artifact 12,177 bytes, per-game counts, the unserved games at
rows 4 / qualified 2 / 1 / 4 reconciled against the BEFORE record's "no book rows", and the artifact's cents-by-pair
distribution); line 3 and NOT VERIFIED updated; and the fix-1c real re-run by the orchestrator must reproduce the same counts
with the four-cause artifact. The observer's sys._getframe read of the landed caller's locals, guarded by a code-object
identity check that fails closed (replay_observer_contract_changed), is ACCEPTED as designed and named in NOT VERIFIED.

AMENDMENT 4 (2026-09-23 18:1xZ; binding; from round 2 on fix 1c -- Opus tier 2 ACCEPT WITH CORRECTIONS and codex sol REJECT (four
blockers; both tiers found the state-row divergence independently)). Tier 2 MEASURED that not_accepted and gate_adapter_refused match the landed load_native +
_prepare ADAPTER_REFUSED on every book construct (quote refusal with a failing touch; to_fill_snapshot-only refusal; a
byte-identical duplicate collapsed by chronological on both sides; the window boundaries; pre_adapter winning over adapter on
one row; a fatal row beside two http-500 rows; six shard shuffles one output). CORRECTIONS RULED: (1) STATE ROWS MIRROR
load_native TOO: a refused state row (http 500, a tied duplicate, state "x", capture_sequence -1) at :03 between books at :01
and :05 gave qualified_decisions 2 in the report against 1 in the landed gate, because report.py:151-161 and the stream's
:157-159 / :173-175 refuse such rows before add_valid while load_native (bridge :276-285) replays any linkable state row with
_refusal set and observe (qualification :162-167) then sets live False and cuts coverage. RULING: linkable state rows that
fail a check enter the observed replay with _refusal set exactly as load_native does, and test_qualification_cause_landed.py
compares qualified_decisions as well as ADAPTER_REFUSED on these four constructs; the 2026-09-22 values (117 / 103 / 2 / 1 / 4)
equal S390 and are unaffected. (2) The memo's line 3 and NOT VERIFIED no longer call the fix-1c re-run outstanding (it is
recorded at :418-433), and the owned-files list carries the memo's ACTUAL byte size at landing (33,363 on disk at review).
NOTES recorded as the memo's wording: the fatal path (a 10-digit fraction) is real -- venue_time.py:49 accepts one to nine
digits, native_rows drops the row and load_native adds ADAPTER_REFUSED to every game, so max(not_accepted, fatal) is the right
per-game reading; a row can be both pre_adapter and adapter refused and pre_adapter wins by the read() order, stated at :27
and in cause_precedence; the cents unit -- disagreements() also counts the side _touch never reached, so one row can yield 12
pairs / 2 sides and TORBAL's 165 sides exceed its 146 rows: the memo says "a refused side" precisely as "a side whose raw pair
disagrees, whether or not _touch reached it"; per-game input_refusals draw on a global three-per-reason example cap (other
games can crowd a game out) and a books invalid_json example with ticker None appears under no game though its fatal flag
does -- both named in NOT VERIFIED; atomic_write's temp beside --out can survive a SIGKILL mid-write (the spool cannot).
(3) CAPTURED FIELDS ARE NEVER REFUSED: rows carrying _raw / _s421* keys were refused reserved_input_field (report :128-129) while
the landed _common accepts them -- report metadata lives in SQLite sidecar columns, never injected into or stripped from the
captured row, so landed parity is exact. (4) BOUNDED STREAMING HOLDS ON TIED GROUPS: qualification_cause_stream.py:168-170
materializes a whole tied group into memory (1,000 tied rows peaked at 361,133 bytes; 10,000 at 3,149,401) -- deduplication
and identity counting happen in SQL, streaming one grouped payload at a time; a 10,000-row tie construct pins the bound.
(5) THE MEMO IS <= 300 LINES (the file rail applies to memos as the harness has landed them): the 450-line memo is condensed
with the FIX sections summarized and the BEFORE / AFTER records kept verbatim in a compact form (command, wall clock, peak
working set, artifact bytes and per-game counts), stale 'outstanding' claims removed, and every byte / line entry regenerated
after the last edit; the real-run artifacts are COMMITTED at docs/evidence/forward/qualification_causes/2026-09-22_fix1c.json
(and the fix-1d re-run beside it) with SHA-256 in the memo, so a verifier can recompute counts and size. (6) The 10-digit
timestamp reading (a landed global fatal, represented apart from the four per-decision causes) is CONFIRMED by both tiers.

AMENDMENT 5 (2026-09-23 19:3xZ; binding; from the orchestrator's fix-1d real re-run, which reproduced every count of the fix-1c
run: TORBAL 146 / MILPHI 529 / MIACHC 575 all inconsistent_touch, pre_adapter_refused 0, qualified 0 / 117 / 103 / 2 / 1 / 4,
disagreement_sides_by_max_cents equal, cause_precedence stated). ONE RULING: every path an artifact under docs/ records
(inputs[].path and any other) is REPO-RELATIVE, resolved from the repo root, never an absolute local path -- docs/evidence/forward/
is exported publicly through the allowlist's `+ docs/` (the same ruling as S406 AMENDMENT 6(b)); the fix-1d artifact is
committed as the BEFORE state of this ruling at docs/evidence/forward/qualification_causes/2026-09-22_fix1d.json and the
next real re-run replaces it with repo-relative paths.

AMENDMENT 6 (2026-09-23 19:5xZ; binding; from round 3 on fix 1d -- Opus tier 1 ACCEPT WITH CORRECTIONS and Opus tier 2 REJECT on the
same two small items: the memo's self-pinned size test broken by the orchestrator's append, and the receipt field expression). Tier 1 confirmed every AMENDMENT 4 closure (refused state rows stay in the replay with
_refusal set; sidecar metadata; SQL GROUP BY streaming with the 10,000-row bound; the AMENDMENT 3 closures; the artifact hashes
and counts of both committed runs; a diff of fix1c vs fix1d changing only future_books / future_state and the 09-23 input bytes).
CORRECTIONS RULED: (1) THE RECEIPT FIELD IS THE LANDED EXPRESSION: the report reads response_end_ts for books and
response_end_utc for state (report :117) while the landed native_rows (forward_replay_io.py:168-169) reads
row.get("response_end_ts", row.get("response_end_utc")) for BOTH; a book row carrying only response_end_utc became a fatal in the
report (landed: accepted) and a state row whose two fields differ gave qualified 1 vs landed 0. RULING: the receipt is taken
with the landed expression for both sources; the state PROFILE keeps response_end_utc as AMENDMENT 1(4) names it, stamped
separately in the profile loop; both constructs join test_qualification_cause_landed.py; the memo records that real state rows
carry both fields and that they were equal on a 3,000-row head slice (not the whole set). (2) THE MEMO NEVER PINS ITS OWN SIZE:
test_qualification_cause_landed.py:180 asserted the memo's byte and line count and failed after the orchestrator appended the
fix-1d record (landing lesson 25 -- pin to a commit, never a working-tree size); the memo's self-entry leaves the inventory (or
is pinned to a commit after landing); the memo's 'passed' counts are regenerated after the last edit. (3) Stale lines removed
(line 4 'belongs to the orchestrator'; NOT VERIFIED 'remain pending'; line 3 lists fix 1d; line 6 cites AMENDMENTS 1-6).
(4) AMENDMENT 5 applied: str(p.resolve()) at :264 becomes a repo-relative path; a path outside the repo root is refused by
name; a construct test asserts no inputs[].path is absolute; the memo's own worktree / scratchpad paths become repo-relative
or placeholders. (5) The memo's 'every count identical' reads 'every per-game count identical' (the future_* diagnostics and
the 09-23 input bytes differ). The fix's real re-run by the orchestrator (AFTER-3) must reproduce every per-game count with
repo-relative paths.
(6) Tier 2's additional corrections: the SQLite sorter's native memory is NOT bounded by the main-database cache_size
(:347) -- tracemalloc peaks flat at about 5.9 MB from 1,000 to 30,000 tied rows while the process working set grew 60 / 99 /
185 MB from two USE TEMP B-TREE FOR ORDER BY steps in the events pass (about 2.5-4.5 KB per visible event, tied or not);
RULING: the events query avoids the temp B-tree sort (an index that serves the ORDER BY, or a streaming merge over the
grouped payloads) OR, if the sorter cannot be avoided, the memo states 'Python heap bounded; SQLite sorter about 2.5-4.5 KB
per visible event' with the measured numbers and the declared ceiling covers it; the 10,000-row construct measures the
process working set, not only tracemalloc. A naive state timestamp makes the landed path mark every game LINKAGE_INVALID
(unreadable_state, a global fatal); the report shows it only in top-level diagnostics -- NOT VERIFIED names it. The memo's
line about the fix1c / fix1d diff names the two fields that differ (future_books 12361 -> 19202, future_state 1380 -> 2086)
and the two input byte sizes, as input growth under a fixed as_of. Tier 2 confirmed on 20 state constructs and 7 book
constructs that not_accepted, qualified_decisions and the per-decision reason counters match the landed path, the sidecar
metadata parity on every reserved key, the four-cause sum, the six-pair unit (and 4 pairs / 1 side when one raw field
disagrees; 3 pairs with four sources), and the spool's removal on success and failure.
