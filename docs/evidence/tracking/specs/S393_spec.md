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
