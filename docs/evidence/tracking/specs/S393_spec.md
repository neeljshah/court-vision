GAP S393 | sport all captured | worktree harness-h52 (master-based) | log cx_s393_state_rows_scheduled_start
# Every state row carries scheduled_start_utc (so prospective schedules can be built from the archive alone)

SINGLE PROBLEM: the state capture links games by date and team through local_state_capture_dates.py but writes rows without the
scheduled start; the prospective schedule writer (row S386) therefore had nothing to read and refused all 484 games of 2026-09-22.

BINDING BEFORE-CONDITION: `head -1 data/cache/ingame_books_local/state/mlb/2026-09-22.jsonl` shows keys without scheduled_start_utc
(the builder reproduces this from the S380 spec's real row; never opens the archive). Read on master and quote:
scripts/platformkit/ingame/local_state_capture.py (the row writer), local_state_capture_sources.py (each sport's poller and what it
has of the venue start time), local_state_capture_dates.py (scheduled_start_utc resolution).

CHANGE (owned files: local_state_capture.py, local_state_capture_sources.py, the landed state-capture test files that assert the
exact row keys, memo; nothing else):
1. Every row gains `scheduled_start_utc` (timezone-aware ISO or null) and `scheduled_start_source` (the venue field it came
   from, or "unavailable"); resolved once per game per refresh through the landed dates module; never inferred from the first
   live row; a poller that lacks a start writes null + "unavailable" and counts it.
2. Additive schema: every existing key and its type is unchanged (a test compares the key set of a synthetic row against a golden
   list from the landed code plus the two new keys).
3. Tests: each sport's poller with an injected payload; null path counted; DST / named-zone start resolved through the dates
   module; all landed state-capture test files pass.
4. Memo docs/evidence/harness/S393_state_rows_scheduled_start_2026-09-22.md.

CONTROLS: construct tests only, no network, never touch a running capture or its output root. ACCEPTANCE: per-file tests pass one
at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list.


AMENDMENT 1 (2026-09-22 18:3xZ; binding; consolidates the rules that rounds 1-7 applied from task text so the spec artifact
carries them; the Opus round-7 verifier found the spec had no AMENDMENT lines). (a) REMEMBERED SCHEDULE: the capture remembers
(scheduled_start_utc, scheduled_start_source) per game across refreshes; a feed start (gameData.datetime.dateTime) supersedes a
discovery start (gameDate / date) and is remembered; two different non-missing starts from sources of the SAME rank within one
refresh emit (None, 'conflict') and count scheduled_start_conflicts once; a later refresh that carries one start resolves the
conflict. A feed start that supersedes a remembered discovery start is NOT a conflict: it is counted scheduled_start_superseded
(a distinct counter), never scheduled_start_conflicts (the round-7 correction: one counter had two meanings). (b) ONCE PER GAME
PER REFRESH: the dates resolver runs exactly once per output game per refresh, grouped by the sport's game identity (gamePk;
ESPN event id; tennis league plus competition id) -- and across ALL polls of one refresh: the MLB discovery polls yesterday and
today, so a gamePk present in both days' payloads (a suspended or carried-over game, the reason two days are polled) is
resolved ONCE at the union of both days, with date_field gameDate preserved as its source, and the null counter
scheduled_start_unavailable emitted once (the round-7 blocker: line 151-153 resolved per call, so one game counted twice). The
closing test drives the two-day discovery (or _prepare_tick) with the same gamePk in both payloads and asserts one resolver call
and one counter. (c) PRIVATE EVIDENCE: rows may carry raw start evidence under a private _start key during resolution; it is
stripped before emission; the emitted schema is master's keys plus scheduled_start_utc and scheduled_start_source only
(additive). (d) S401 INTACT: exactly one recover_states call; tests/platformkit/ingame/test_local_state_capture.py stays
byte-identical to master. (e) A never-seen FINAL is pruned from the task list (no row), its conflict (if any) still counted at
discovery. (f) The dedupe key in unique_games excludes raw and receipt (the round-7 note: json.dumps of the whole payload is
O(n x payload) per poll).


AMENDMENT 2 (2026-09-22 18:4xZ; binding; from the codex sol round-7 verdict, three blockers on the evidence key). (a) ZONE IN
THE EVIDENCE KEY: two unzoned '20:00' starts under different competition / venue zones (America/Chicago vs America/New_York)
are different instants; the _evidence key is built with the same event / competition / venue zone precedence and dict
normalization as schedule(), so they emit (None, 'conflict') with one conflict count in both input orders, never a silent
single instant. (b) NO TEAM-PAIR IDENTITY: a record without a game id (ESPN id null) never falls back to team pairing as its
dedupe identity (two id-null NY@CHI events on different starts collapsed to one row with a null start); it is counted
missing_game_id and keyed by a stable surrogate of league, teams and the raw scheduled start text so distinct events stay
distinct. (c) DETERMINISTIC REPRESENTATIVE: excluding raw and receipt from the dedupe key (AMENDMENT 1(f)) stands, but a
semantic-key collision selects its representative deterministically -- the earliest request timestamp, raw sha256 as the
tie-break -- never last-input-wins; both orders emit the same row. Tests: both orders for (a), (b) and (c).


AMENDMENT 3 (2026-09-22 18:5xZ; binding; the orchestrator's ruling on the round-8 disagreement between the two tiers, plus two
sol round-8 blockers). (a) ONE RESOLVER CALL, FEED FIRST: Opus round 8 read the feed poll's resolve as a legitimate higher-rank
source; sol round 8 read it as a second dates-resolver call for one game in one refresh. Both are right about what the code
does; the rule is sharpened: the capture GATHERS start evidence from every poll of a refresh per game (discovery gameDate for
both days, the feed's gameData.datetime.dateTime), SELECTS the highest-rank evidence (feed over discovery; two same-rank values
= conflict), and invokes the dates resolver ONCE per output game per refresh on the selected evidence. The whole-tick resolver
call list for one game is therefore exactly one entry; the closing test asserts one call for the discovery-only, feed-present
and feed-null shapes. The remembered-schedule and superseded / conflict counters of AMENDMENTS 1-2 are unchanged in meaning.
(b) REMEMBERED SCHEDULE FOR EVERY SPORT: known_games is MERGED per game identity on every refresh, never replaced wholesale; a
valid-then-missing start on any non-MLB poller (nba, soccer, nfl, ncaaf, tennis) keeps the remembered (start, source) pair and
emits it (measured defect on the 1h candidate: NBA game1 '2026-09-21T20:00:00-05:00' then null emitted [.., 'date'] then
[null, 'unavailable'] and the remembered map lost the pair); tests per poller. (c) SURROGATE IDENTITY FOR EVERY POLLER: the
counted stable-surrogate identity of AMENDMENT 2(b) applies to NFL, NCAAF and tennis as well as the generic ESPN path (measured:
two id-null NFL events with the same teams and different starts collapsed to one game_key null (null, 'conflict') with
missing_game_id 0; two id-null tennis competitions collapsed to atp:None / wta:None); both-order tests per poller.


AMENDMENT 4 (2026-09-22 19:0xZ; binding; from the codex sol round-9 verdict and the astra round-9 critique, plus two rail
clarifications after the first codex fix lane stopped). RAILS: (i) the landed test file tests/platformkit/ingame/
test_local_state_capture.py writes a STOP_STATE file under pytest's tmp_path -- that is a construct inside a temporary directory,
NOT a capture STOP file (the invariant covers data/cache/** STOP files only); running that test file is REQUIRED; (ii) the
working copy of that file carries CRLF line endings while the master blob is LF -- core.autocrlf normalization; `git diff master
--stat` empty is the byte-identity test, not a raw byte count. FINDINGS (all on the 1i candidate; AMENDMENT 3(a)-(c) remain
unimplemented and are restated by sol round 9 with the same reproductions): (a) REMEMBERED STARTS MUST NOT REGRESS: after
discovery A, a postponed feed start B on another day, a rediscovery of A and a feed without dateTime, the archive returned to A
and scheduled_start_superseded incremented again without an archived change; the remembered pair is replaced only by evidence
of equal or higher rank, never by a later lower-rank rediscovery. (b) COUNTERS DESCRIBE EMISSION: every schedule counter
(unavailable, partial, superseded, conflicts) increments exactly when an emitted row carries that verdict for the first time in a
refresh; a counter delta equals the count of emitted rows with that verdict; a discovery-time count with no emitted row is a
defect. (c) TIMESTAMP SPELLINGS: two spellings of one instant ('2026-09-22T03:00:00Z' vs '2026-09-22T03:00:00+00:00') are the
same evidence, never a conflict -- evidence is compared after parse_venue_time normalization. (d) REPRESENTATIVE TIE: equal
request timestamps and equal raw sha256 with different receipt ids select by the receipt id text as the last tie-break, so the
selected receipt (and its response_end time reaching the row) is order-independent. NEW GAPS OUT OF SCOPE (allocated as their own
rows by the orchestrator, recorded here so this row can land): UTC-midnight tracking reset not reseeding last_state on later
rollovers and a live game discovered FINAL being pruned without its final row (local_state_capture.py:119, :129, :161);
competition-shape changes (missing / duplicate competitions, walkover, retired) losing or misdescribing events across the ESPN
pollers and tennis. This row's memo names both gaps under NOT VERIFIED.

AMENDMENT 5 (2026-09-22 23:0xZ; binding; from the astra round-10 critique on fix 1j). (a) COUNTERS ADVANCE ONLY ON A SUCCESSFUL
APPEND: MEASURED -- with one NBA event lacking a start and a writer that raises before its first append, the refresh emitted 0
rows yet published unavailable 1 (local_state_capture.py:213); the retry then emitted the row without a second increment, so
the failed refresh published an unsupported count. RULING: every schedule counter (unavailable, partial, superseded, conflicts,
missing_game_id) is staged per refresh and committed only after the row it describes is durably appended; a refresh that
raises before its appends publishes no counter movement; test: writer raises before the first append -> counters unchanged;
the retry -> counters move exactly once. (b) THE REPRESENTATIVE COMPARES NORMALIZED INSTANTS: MEASURED -- request timestamps
'2026-09-22T01:00:00+02:00' and '2026-09-22T00:00:00Z' with equal hashes selected the second in both orders although the first
is an hour earlier (local_state_capture_sources.py:80, a lexical comparison). RULING: the earliest-request rule of AMENDMENT 2(c)
compares instants after parse_venue_time normalization, then raw sha256, then the receipt id text; test with mixed offsets in
both orders. (c) DIRECT HELPERS COUNT TOO: MEASURED -- mlb_poll called directly with dateTime None returns (None, 'unavailable')
with its unavailable counter at 0 (sources.py:177) while the deferred capture path counts; RULING: the direct helper reports
through the same staged-counter path (or is documented as capture-only and refuses direct use); test. (d) NEW GAPS, out of
scope, allocated by the orchestrator: cross-identity reconciliation when a gamePk is renumbered (1 -> 2 emits both (1,
remembered) and (2, null)); recovery after a restart restores STATE but not the remembered SCHEDULE (local_state_capture_io.py:161;
archived feed B becomes discovery A) -- the second joins S407's scope (the terminal row and the remembered schedule both survive
a rollover / restart); the memo's NOT VERIFIED names both. (e) S407 / S408 reproduce as excluded, unchanged.

AMENDMENT 6 (2026-09-22 23:2xZ; binding; from the codex sol round-10 verdict on fix 1j). (a) THE TIE-BREAK USES A FIELD THE
PRODUCTION RECEIPT CARRIES: MEASURED -- AMENDMENT 4(d)'s final tie-break expects receipt_id, but the landed ReceiptGetter
(local_state_capture_io.py:113) never emits that field, so two production receipts with equal request instant and equal raw
sha256 but different response_end select differently by input order (forward / reverse gave ['...01Z', '...02Z']); the
synthetic test passed only because it injected a non-production receipt_id. RULING: the final component is receipt_id when
present, otherwise the canonical sorted JSON serialization of the COMPLETE receipt (all fields, sort_keys, no whitespace), so the
selection is order-independent on the real field set; the both-orders test uses the ACTUAL ReceiptGetter field set. (b) Every
other AMENDMENT 3-4 closure reproduced in both orders by the round-10 verifier: resolver lists [A] / [B] / [None] one row each,
remembered starts retained on all five non-MLB sports, NFL / NCAAF / tennis surrogates two rows and two missing_game_id, no
lower-rank regression, spelling and zone stability, emitted verdict rows -> counter deltas [1,1,1,1], pruned rows -> [0,0,0,0].

AMENDMENT 7 (2026-09-23 00:2xZ; binding; from the astra round-11 critique of fix 1k). Two blockers, both MEASURED on
constructs: (a) RESTART MUST NOT ABORT UNRELATED DISCOVERY -- the MLB merge at local_state_capture.py:165 did
`.update(game)` on a known_games entry that S401 recovery never creates (recovery fills last_state independently), so
"append game 1 LIVE, fail game 2's append, restart, discover [1 FINAL, 2 LIVE]" raised KeyError '1', n_tasks 0, new rows 0,
tracked games [] -- game 2 lost with it. RULING: the merge is create-or-update (setdefault) for every sport; one game's
failure never aborts the loop for another (per-game isolation, the failure counted and named); the construct above must
track both games after restart with S401 preservation intact. (b) DIRECT HELPERS COUNT EMISSION, NOT DISCOVERY --
_identity (sources.py:127) incremented missing_game_id before dedupe, so 1/2/3 identical id-null events yielded one row and
counts 1/2/3 (NBA, soccer, NFL, NCAAF), and direct MLB discovery with gamePk None (sources.py:139) returned zero rows while
counting 1. RULING: AMENDMENT 5 applies to every counter on every path -- missing_game_id moves once per EMITTED row lacking
an id, after dedupe, and the direct helpers report through the same staged path as the capture loop; zero rows means zero
movement. Both with pinned tests and before/after reproductions; everything else from fixes 1j-1k byte-identical in behaviour.

AMENDMENT 8 (2026-09-23 02:0xZ; binding; from the sol round-12 REJECT of fix 1l). ISOLATION IS PER GAME ON EVERY PATH, AND
COUNTERS PUBLISH ONLY FOR ROWS RETURNED -- MEASURED: (a) the tennis parser (local_state_capture_sources.py:234) wrapped the whole
league in one handler, so two ATP competitions [bad, good] with bad.competitors[0].linescores = [{"period": "bad"}] captured []
in one order and ['atp:good'] in the other, each reporting one TypeError without the failed competition's identity; (b) the direct
helpers (sources.py:105) raised AttributeError on a malformed game (event a date None; event z venue "malformed") for NBA, soccer,
NFL and NCAAF, returned no result, yet published {'scheduled_start_unavailable': 1}, and the malformed game prevented the valid
game from being returned. RULING: AMENDMENT 7(a)'s per-game isolation applies to every parser and every direct helper for every
sport: one malformed competition or game is counted under a named reason that carries the league / competition identity, and
every other game is still returned -- byte-identical in either input order (both-order tests for the tennis parser and for every
helper); staged counters are published only for rows successfully returned (a helper that returns nothing publishes nothing).
BASE NOTE: the fix-1l candidate sat on an orphaned base commit (5a42c84ed, an amended-away S405 fix that carried a broken test
file); the orchestrator moves the candidate files byte-for-byte to a fresh worktree on master, so no unrelated commit is part of
the candidate. Everything from fixes 1j-1l byte-identical in behaviour otherwise.

AMENDMENT 9 (2026-09-23 03:1xZ; binding; from the astra round-13 REJECT of fix 1m -- five blockers, all MEASURED on constructs;
sol round 13 was ACCEPT WITH CORRECTIONS on the sandbox-only test execution). (a) KEYWORD COLLISION CRASHES THE RESTART PATH:
local_state_capture_io.py:223 put last_adapter_error into metrics while the landed local_state_capture_commit.py:68 supplies that
keyword explicitly and again through the snapshot -- restart after game 2's failed append, then discover [malformed 3, FINAL 1,
LIVE 2]: TypeError dict() got multiple values for keyword argument 'last_adapter_error' in both orders after two valid rows.
RULING: no S393 metric or snapshot key may collide with any keyword the landed commit module passes; the adapter diagnostics live
under ONE new key (adapter_failures: a list of {identity, reason, sport}) that the commit module never names; a test drives the
real commit path on that construct. (b) IDENTITY BEFORE ISOLATION: sources.py:238 evaluated comp.get('id') before entering the
isolation, so competitions [17, good] captured [] in one order and ['atp:match1'] in the other, one unnamed AttributeError.
RULING: every per-item operation -- identity construction included -- runs inside the isolation; a non-dict item is counted under
a named reason with a positional surrogate identity and the peers still emit, both orders identical. (c) DIAGNOSTICS ARE
BEST-EFFORT: an injected failure in diagnostic storage or callback (io.py:223) raised RuntimeError in both orders and discarded a
valid peer's result. RULING: a diagnostic write failure is itself counted (diagnostic_write_failed) and never affects the row,
the peers or the return value. (d) PUBLICATION IS ATOMIC: sources.py:105 applied staged counters one by one, so a failure in the
second publication left unavailable at 8 with no result returned, on all six discovery / poller paths. RULING: staged deltas are
computed fully, the result is constructed, and the deltas are applied in ONE step that cannot partially fail (a single dict
update from a completed staging object after the return value exists); a test injects a failing counter object and asserts no
movement. (e) DISTINCT FAILURES, DISTINCT IDENTITIES: two id-null malformed competitions both produced the diagnostic identity
tennis:atp:None. RULING: a failed item's diagnostic identity is the AMENDMENT 2 stable surrogate when derivable, else a content
hash of the raw item text (repeatable across runs, distinct across items); identified items keep their ids. Everything from fixes
1j-1m byte-identical in behaviour otherwise (the round-13 sol reproductions must still hold).

AMENDMENT 10 (2026-09-23 04:0xZ; binding; from the sol round-14 REJECT of fix 1n -- one blocker, MEASURED). BEST-EFFORT
DIAGNOSTICS APPLY TO EVERY PATH, INCLUDING THE RESOLVER'S: with [event a officialDate 'bad', event good] and a metrics adapter
whose drop() raises only for timestamp_parse_errors, the capture returned ['good'] instead of ['a', 'good'] with
schedule_adapter_errors 1 and diagnostic_write_failed 0 -- in both orders, across NBA, soccer, NFL, NCAAF, MLB discovery and
tennis (local_state_capture_sources.py:112): an optional-date diagnostic raised inside the dates resolver and took the whole row.
RULING: AMENDMENT 9(c) covers every diagnostic write reachable from S393 code, including those inside the resolver and the
landed helpers it calls -- owned code passes a GUARDED metrics adapter into the resolver (every write counts
diagnostic_write_failed on failure and returns), so resolution continues and the row, its peers and the return value are
unchanged; both-order tests cover every resolver diagnostic path. MEMO: every earlier round's reproduction keeps its exact source
block (or cites an immutable archived artifact that holds it) so each claim stays reproducible byte-for-byte. Everything from
fixes 1j-1n byte-identical in behaviour otherwise.

AMENDMENT 11 (2026-09-23 04:1xZ; binding; from the astra round-14 REJECT of fix 1n -- two blockers, MEASURED). (a) COUNTING THE
DIAGNOSTIC FAILURE MUST NOT RAISE: with [bad, good], a raising callback and a Counter whose get('diagnostic_write_failed') raises,
both orders ended in RuntimeError with no result reaching the caller; the global diagnostic tally advanced to 1 first
(local_state_capture_io.py:197). RULING: the diagnostic-failure counter is itself guarded -- a failure while counting a failure
is absorbed after a best-effort global tally, never raises, never recurses; the row, the peers and the return value are
unchanged; a both-order test plants the raising counter. (b) THE CONTENT HASH IS CANONICAL: an id-null tennis competition with
malformed linescores and date {'value': ts, 'zone': 'America/Chicago'} produced equal_content True but same_identity False when
only the date dict's key order was reversed -- the semantic branch serialized the malformed date object without sorted keys
(io.py:248). RULING: the AMENDMENT 9(e) fallback identity hashes the WHOLE raw item as canonical JSON (sort_keys=True, fixed
separators, default=repr for non-serializable values) so equal content gives equal identity regardless of key order or
nesting, and different content gives different identities; a test reverses nested key orders. The memo rule of AMENDMENT 10
stands (every earlier reproduction keeps its exact source). Everything from fixes 1j-1n byte-identical in behaviour otherwise.

AMENDMENT 12 (2026-09-23 05:0xZ; binding; from the sol round-15 REJECT of fix 1o -- two blockers, MEASURED). (a) THE CAPTURE
LOOP'S OWN DIAGNOSTIC IS STILL UNGUARDED: with [bad venue 'malformed', good] and a metrics adapter whose drop() raises
RuntimeError('diagnostic storage') only for adapter_errors, capture_state_once produced ['good'] with one append when
diagnostics were healthy, but RuntimeError with ZERO appends and diagnostic_write_failed 0 when they failed -- for NBA, soccer,
NFL, NCAAF, MLB and tennis, both orders (local_state_capture.py:141). RULING: the capture loop's diagnostic call goes through the
SAME guarded reporting path as every other diagnostic (AMENDMENTS 9(c) and 10) -- the named game error is retained, the failure
counts diagnostic_write_failed, nothing raises, and the valid peer still reaches the writer; both-order FULL-CAPTURE tests
(driving capture_state_once with fixture responses and an in-memory writer) assert the append and the count for every sport. No
diagnostic call anywhere in S393 code may remain direct: a test enumerates them. (b) THE ARCHIVE MUST BE SELF-CONTAINED: six
archived round-10 reproductions (events 37, 39, 41, 43, 48, 50) source their construct from a memo preamble that no longer exists
-- their exact source runs Path(memo).read_text().split('BEGIN_REPRO_SOURCE\n```python\n')[1] and raises IndexError because the
marker is absent (S393_reproductions_2026-09-22.md:215). RULING: every archived reproduction is executable against the CURRENT
tree with no dependency on deleted text -- the archive carries the exact bytes each one needs (restored preamble with its
delimiters, or the historical fragment inlined), the original reproduction sources stay unchanged, and a test executes three
archived sources at random and compares their output to the archived output byte-for-byte. Everything from fixes 1j-1o
byte-identical in behaviour otherwise.

AMENDMENT 13 (2026-09-23 05:1xZ; binding; from the astra round-15 REJECT of fix 1o -- two blockers beyond AMENDMENT 12's, both
MEASURED). (a) THE FALLBACK IDENTITY MUST NOT RAISE ON MIXED KEY TYPES: an id-null NBA event with a malformed period and
extra={1: 'x', 'a': 'y'} alongside a valid peer produced TypeError (comparing a string key with an integer key inside the
canonical serialization) in both orders, with no result returned and counters {} -- the identity builder raised WHILE handling
the original failure (local_state_capture_io.py:186 through :254). RULING: the canonical serialization never compares keys of
different types -- every key is rendered to text before ordering (sort by the rendered text, with the key's type tag included),
and the whole identity computation is itself inside the isolation: if it cannot be computed it falls back to a positional
surrogate under a named reason and NEVER raises. (b) DIFFERENT CONTENT, DIFFERENT IDENTITY -- MEASURED: {'x': Decimal('1.0')}
and {'x': "Decimal('1.0')"} produced the SAME identity because default=repr renders the Decimal to the text the string already
holds; any two classes whose repr matches collide (the datetime / ISO-string and Decimal / float pairs do differ correctly).
RULING: every non-JSON value is rendered with its TYPE included (for example the fully qualified class name and the repr
together) so a value and a string that merely spells it are distinct; a test asserts the Decimal / string pair, the datetime /
ISO pair and a custom class whose repr equals another's all give distinct identities, and that equal content still gives equal
identity under nested key reordering. AMENDMENT 12 (the guarded capture-loop diagnostic and the self-contained archive) stands;
the archive blocker is the same one both tiers found. Everything from fixes 1j-1o byte-identical in behaviour otherwise.

AMENDMENT 14 (2026-09-23 05:5xZ; binding; from the round-16 REJECT of fix 1p -- both tiers; three blockers, all MEASURED. Both
tiers confirmed AMENDMENT 12's capture-loop guard, the archive repair and the resolver guard as CLOSED for the paths they cover).
(a) THE DEDUPE SERIALIZATION PRECEDES THE ISOLATION: calling nba_poll with [dict(event(), id=None, extra={1: 'x', 'a': 'y'}),
dict(event(), id='good')] and its reverse raised TypeError ("'<' not supported between instances of 'str' and 'int'") with
counters {} and no returned peer, in both orders -- 12 of 12 direct-helper constructs (local_state_capture_sources.py:88-94).
The receipt and semantic keys are built and sorted BEFORE the per-item isolation, so AMENDMENT 8's isolation never sees the
failure. RULING: the receipt and semantic keys are computed INSIDE the per-item isolation with a mixed-key-safe encoding; a key
that cannot be built counts a named failure by identity and the item is dropped from the sort only, never taking its peers; the
sort runs over successfully prepared records alone; both orders pinned for every helper. (b) THE LANDED COMMIT HELPER'S
DIAGNOSTICS ARE REACHABLE AND UNGUARDED: with a writer append / sync / heartbeat failure plus a failing drop() for
state_write_errors, state_sync_errors or state_heartbeat_errors, 36 of 36 constructs (six sports, both orders) raised
RuntimeError with diagnostic_write_failed 0, and the append and sync cases also omitted the failure heartbeat
(local_state_capture_commit.py:20, calls at 38, 44, 46, 76); the AMENDMENT 12(a) enumeration test excludes that landed helper.
RULING: S393 code passes the SAME guarded metrics adapter into local_state_capture_commit (that landed file is NOT edited --
the guard is applied at the S393 call boundary), so every diagnostic it makes is best-effort: counted, never raising, and the
failure heartbeat is still written; the enumeration test covers every diagnostic reachable FROM S393 code, including through
landed helpers. (c) THE CANONICAL IDENTITY IS STILL NOT CANONICAL: a = {'nested': ({'b': 2, 'a': 1},)} and
b = {'nested': ({'a': 1, 'b': 2},)} compare equal yet produced different identities (tuple contents fall through to repr,
io.py:263), and two factory-created classes with identical qualified names -- the second subclassing the first without
overriding repr -- produced the SAME identity, as did tuple and frozenset keys holding different-class equal-repr objects
(io.py:255). RULING: canonicalization RECURSES through every container (dict, list, tuple, set, frozenset) and through KEYS as
well as values, retaining each container's type tag, so nested key order never changes the identity and nested types are never
lost; the type tag distinguishes two classes that share a qualified name and a repr (include the class's module and its
identity-bearing attributes, or refuse to fingerprint and fall back to the positional surrogate under a named reason rather than
return a colliding identity). A test pins the nested-tuple equality, the subclass pair and the container-key cases in both
directions. Everything from fixes 1j-1p byte-identical in behaviour otherwise.

AMENDMENT 15 (2026-09-23 16:2xZ; binding; orchestrator ruling after fix 1q). The owned set gains ONE companion test file,
tests/platformkit/ingame/test_state_capture_fix_1q.py (the 154 regressions fix 1q wrote for AMENDMENT 14(a)-(c): dedupe keys
inside the isolation, the guarded metrics adapter at the landed commit helper's call boundary, and the recursive canonical
identity), admitted so the 300-line rail never forces a confirmed assertion out of an existing file. It tests this row's own
modules only; local_state_capture_commit.py stays unedited (the guard is applied at the S393 call boundary, per 14(b)). Nothing
else in the owned set changes.

AMENDMENT 16 (2026-09-23 16:5xZ; binding; from round 17 on fix 1q -- sol ACCEPT WITH CORRECTIONS (the only correction is
sandbox-only test execution) and astra REJECT (two blockers), both tiers confirming AMENDMENT 14(a) and 14(b) CLOSED and the
archive seal 7b91941f42a7e228ad6f9740a4c3e4829534dd12cdc937a6c424c4ebd8ef5a65 matching). (a) CONTAINER SUBCLASSES RECURSE:
class L(list) holding {'b': 2, 'a': 1} vs {'a': 1, 'b': 2} compared equal but produced different identities (exact-type
checks sent the subclass through insertion-order-sensitive repr; io.py:262); a dict subclass reproduced it, including inside a
hashable tuple key. RULING: canonicalization dispatches by isinstance for dict, list, tuple, set and frozenset (subclasses
recurse like their base) and the container's type tag records the CONCRETE class's module and qualified name, so a subclass
still differs from its base while its contents are canonical. (b) UNRESOLVABLE CLASSES REFUSE TO FINGERPRINT: two factory
classes with the same qualified name, the second subclassing the first with an inherited repr, produced the SAME identity
sha256:e1c9a6b1... with no named refusal (io.py:271; the ambiguity check looked only at one immediate base's subclasses).
RULING: a class is fingerprinted by module + qualified name ONLY when importing that module and walking the qualified name
resolves to that very class object (the getattr chain `is cls`); any class that cannot be resolved that way (factory-made,
local, dynamically created) REFUSES to fingerprint under the named reason identity_unresolvable_class and falls back to the
positional surrogate -- the refusal branch AMENDMENT 14(c) already allows -- so two distinct unresolvable classes can never
share an identity; the counter is visible in the row's diagnostics. Tests: the factory pair (identical qualname + repr) ->
two named refusals, never one shared identity; a module-level class and its module-level subclass -> two distinct identities;
L(list) / D(dict) reorder -> same identity; a plain tuple containing a dict is not a dict key (Python raises first; not a
case). (c) Everything from fixes 1j-1q byte-identical in behaviour otherwise; the archive gains no new block for this round
unless a source changes.

AMENDMENT 17 (2026-09-23 17:3xZ; binding; from round 18 on fix 1r -- BOTH Opus 5.5 tiers ACCEPT WITH CORRECTIONS; both re-tested
AMENDMENT 16(a) and 16(b) as CLOSED, the AMENDMENT 12 guard and 14(b) adapter over 1,200 fault runs with 0 bad, the archive seal
bb53c6f2...27a5 matching with 24 of 24 blocks and 6 of 6 record seals, and 1,048 tests). CORRECTIONS RULED: (1) THE IDENTITY
REFUSAL COUNTERS REACH THE CAPTURE'S OWN METRICS: failure_identity calls report(None, league, reason)
(local_state_capture_io.py:287), which counts into the process-global SOURCE_METRICS, while the production StateClient owns its
own Metrics (local_capture_client.py:48), so identity_unresolvable_class and identity_serialization_errors never reach the
sport's drops_by_reason / errors (and land under 'atp' / 'wta' for tennis); the refusal tests hid this by monkeypatching
io.SOURCE_METRICS. RULING: failure_identity takes the getter (get=None) and reports through report(get, source, reason) at every
call site in local_state_capture_sources.py (:89, :147, :216, :239, :293); one refusal test asserts on get.metrics WITHOUT the
monkeypatch; the counter appears under the sport (tennis under 'tennis', the source under its own key as the landed convention
dictates -- quote the convention). (2) DICT ENTRIES SORT BY KEY AND VALUE CANONICAL TEXT: io.py:271 sorts entries by the key's
canonical JSON alone, so two distinct non-JSON keys with the same canonical form (a module-level class with repr 'k' and the
default hash, instances k1 and k2: {k1: 1, k2: 2} == {k2: 2, k1: 1} is True) leak insertion order into the identity. RULING:
the sort key is (canonical key text, canonical value text); one reorder test pins it. NOTES (recorded, not blockers): a module
that raises anything other than ImportError during the resolvability import is counted identity_serialization_errors (named,
not swallowed) -- the check may run a module's top-level code; a __main__ class resolves to '__main__.X' (two entry scripts could
share the tag); depth 10,000 refuses by name, never a RecursionError; two instances of one resolvable class sharing a repr but
holding different attributes share an identity under AMENDMENT 13(b)'s class-plus-repr rule (named in NOT VERIFIED). Everything
else in fixes 1j-1r byte-identical; the archive gains the FIX 1s block and is resealed.

AMENDMENT 18 (2026-09-23 17:5xZ; binding; after fix 1s applied AMENDMENT 17 -- both corrections closed, 1,080 tests, archive resealed 2e96a5115a33af641729cc06b21200881ddcc716441499f387dbcd4b5b0d9fd0). The owned set gains the companion test file tests/platformkit/ingame/test_state_capture_fix_1s.py (nine routing and sort-order regressions; test_state_capture_fix_1q.py sits at the 300-line rail). The memo was re-joined for length (layout only, stated in the memo). LANDING NOTE: the live state2 writer runs the pre-S393 landed code; adopting S393 is a supervised relaunch from the main tree (owner-visible, recorded BEFORE / AFTER) or a second writer into its own root, never a STOP file written by an agent; tonight the running writer is left as is.
