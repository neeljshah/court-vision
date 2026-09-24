# S397 -- credential-free Polymarket live capture, 2026-09-22

Row: S397 | spec: docs/evidence/tracking/specs/S397_spec.md | worktree harness-h58.
Builder and fix lanes use local construct tests with stub clients; no network. The orchestrator
ran five bounded live smokes and recorded their facts in AMENDMENTS 2-8. The facts below are
quoted from that spec, not a fresh read of a live capture. No credential or wallet is used.

## First admissible decimal-text archive -- fifth smoke (AMENDMENT 8, verbatim)

AMENDMENT 8 (2026-09-22 18:5xZ; binding; VERBATIM FACTS from the orchestrator's FIFTH live smoke, the first on fix 1e: three ticks,
mlb, --state-root data/cache/ingame_state_local_v2, the committed 2026-09-22 full-selection schedule, exit 0). rows 1368 =
market_meta 26 + snapshot 120 + trade 1162 + trade_backfill_closed 60; FLOAT PATHS IN THE ARCHIVE: none (json.loads of every
written line contains no float); snapshot sample: best_bid '0.41', best_bid_size '94154.74', yes_bid_cents '41.00', yes_bid_size
'94154.74', yes_ask_size '70504.27', api_ts '1790102639945', api_ts_iso '2026-09-22T18:43:59.945000Z', game_key '824222',
link_path team_set; trade links by team_set for six game_keys (823328: 216, 823412: 195, 824709: 177, 824061: 172, 824867: 167,
824222: 142); heartbeat unlinked_markets 921 of n_markets_tracked 1274 with reasons linked_at_discovery 353, linked_by_meta 0,
no_start 667, no_codes 0, no_state_rows_for_day 2, no_code_match 208 (the former plain 'unlinked', now named), ambiguous 44;
trade gaps none; fetch_error rows none (no failed page in this run -- the receipt path is exercised by tests only). This is the
first archive admissible to the S398 scan; the memo records it verbatim as the first decimal-text archive facts.

Smokes 1-4 are SUPERSEDED HISTORY and are not admissible inputs to any S398 count. The fifth
smoke is the first archive whose decimal-text encoding is admissible. Its 1162 trades include
1069 linked trades across the six named keys; the quoted linked counts do not claim all trades
were linked. This smoke predates FIX 1f and does not validate its new drain or scheduling rules.

## Superseded smoke history -- AMENDMENTS 2-6

Smoke 1: three ticks, MLB, scratch root, 16:33-16:35Z, 211 requests, zero 429 responses.
It wrote 120 snapshots and 26 market_meta rows; best_bid 0.43, best_ask 0.44, sizes
70625.85 / 15316.29, 36 / 42 levels; api_ts '1790094822966'. Terms: game_start_time
'2026-09-22T22:40:00Z', minimum_tick_size 0.01, minimum_order_size 5, both base fees
1000, seconds_delay 0. Zero trades: 60 successful requests; trade_time_refusals 60,
trade_refusals 60, timestamp_parse_errors 600 and timestamp_invalid_format 600. The latter
600 were discovery start parsing, not evidence that the trade epoch conversion failed.
All 1226 markets were unlinked; 33 events tracked; unknown_sport_events 305 and
discovery_page_budget_exhausted 1. The initial gap path silently omitted refused pages.

Smoke 2: the live tape used integer timestamp 1790095561, size 1.754386 or 20 and price
0.5699999886 or 0.44. The string-only validator recorded trade_time_not_unsigned_epoch_text
60, page_refused 60 and refused_time_sample None. The scratch root lacked state rows;
every market was unlinked with link_no_start_date 0. FIX 1c accepted int/string epochs,
recorded source JSON types and added --state-root plus refused_time_type.

Smoke 3: three ticks wrote 3274 trades (1502 + 1772 across the two encodings),
55 trade_backfill_closed and 5 page_budget gaps; duplicate_trade_key 3871.
The 145 snapshot/meta rows remained unlinked; every other row was also unlinked.
Standalone state_index had 15 keys, including PIT/STL -> 823328; link_market returned
823412 for MIL/PHI. The run-path reproduction read a copied 651-row, 16-key state shard.
The true start was '2026-09-22 17:05:00+00'; eventStartTime, where present, was
'2026-09-22T17:00:00Z'. event.startDate '2026-05-17T14:16:13.49588Z' was market creation.
FIX 1d normalized the space/bare-offset syntax, excluded creation dates and retried the
unlinked unit after metadata. The same run-path construct then wrote game_key 823412
with link_path team_set, gamma_start_normalized 1, unlinked_markets 0.

Smoke 4: three MLB ticks, real v2 state root and full-selection schedule, exit 0 in 115 s.
Rows 1324 = market_meta 26 + snapshot 120 + trade 1118 + trade_backfill_closed 60.
Trade/team_set keys and counts: 823412:183, 823328:173, 824867:161, 824061:156,
824709:156, 824222:113, 824785:103, 824624:73. Snapshot/team_set: 823412:20,
824061:18, 823328:18, 824867:18. Gaps {}.
Heartbeat: unlinked_markets 875 / n_markets_tracked 1228; linked_at_discovery 353,
linked_by_meta 0, no_start 626, no_codes 0, no_state_rows_for_day 2, ambiguous 43,
plain unlinked 204. Counters: gamma_start_normalized 602, unknown_sport_events 303,
out_of_scope_sport_events 163, discovery_page_budget_exhausted 1, duplicate_trade_key
2022, non_object_events 0. The spec interpreted no_start as non-game markets and ambiguous
as doubleheaders/alias collisions; no per-market census independently established that.
The S398 probe refused all 120 snapshots as 'expected a decimal string'; a later probe
also reported missing yes_bid_size. These float archives remain superseded.

## Existing construction and reader boundaries

Six opt-in modules provide the receipt envelope, snapshots, public trades, metadata, fetch
errors, discovery, state linkage, CLI and heartbeat. The only watchdog change adds
"polymarket" to its existing venue tuple. The S397 fixtures omit profile fields.
PolymarketWriter reuses ArchiveWriter via a venue-directory layout adapter: the lock is
<root>/polymarket/_capture.lock. The landed writer and backfill modules are unchanged.
The S386 schedule orders games; it does not establish identity. Team-set identity comes
from the STATE archive. Public tape pages are bare lists, so GovernedClient.get receipts
are retained while the venue-specific drain uses offset pagination and trade_key restore.

FIX 1e decoded JSON numbers with JsonNumberText, preserving exact decimal digits and
source type ("float" versus "str"), and wrote prices/sizes as text or int. Derived cents
use Decimal and book epoch conversion uses integer divmod. Snapshot rows add yes_bid_size
and yes_ask_size while preserving best_* fields. Non-200/status-0/malformed/seed failures
write fetch_error receipts; mixed good/bad pages preserve valid trades and declare
partial_page, while wholly refused nonempty pages declare page_refused with refusal counts.
Failed metadata requests retry. no_code_match names the former plain unlinked reason.

Reader fact: capture_coverage_daily._size_present refuses floats by type and pairs
yes_bid_size with no_bid_size. These rows provide yes_bid_size / yes_ask_size, so that
reader's touch_size_rows still will not count them. A NO-side size is not inferred from a
YES-token book. The unlanded S398 scan consumes the YES bid/ask size fields.
The metadata row that supplies a previously absent link retains its pre-link state;
join that metadata by event_ticker rather than expecting its game_key to be populated.

## FIX 1f -- AMENDMENT 9

Drain continuations advance after durable pages and refused-page gaps; per-tick page counts
reset without resetting the saved offset. The cached group updates after each durable page,
so a later failure retries from its failed offset without rewriting earlier trades.
Closure requires an earlier page to cross below the frozen timestamp watermark followed
by a short page; a straddling page is reread once and watermark_rereads is counted.
Trade_backfill_closed identities participate in restore/dedupe, with duplicate closures
counted. Decimal identity uses canonical normalized, exponent-free price/size text while
the row retains venue text. Equal '0.44'/'0.440' values therefore identify one trade.
Correction to the old memo: string '1e-07' and JSON numeric 1e-07 already rendered the same
exact text and hashed identically. Canonical Decimal identity additionally equates
trailing-zero, exponent and plain encodings. Restore retains older archive hashes while
recomputing canonical keys from the bounded archive tail.

Scheduled discovery no longer truncates at 40 slug permutations. Selection is per game
with aging priority, keeping its outcome units together; scheduled_slug_empty counts
HTTP 200 []. Heartbeats report scheduled_requested / discovered / selected / overdue.
Existing links are reconsidered against updated state; link_relinked counts changes and
link_ambiguous_after_link records newly ambiguous former links while clearing their keys.
Conflicting UTC dates between gameStartTime and CLOB game_start_time count
start_source_conflict and clear the key. Reproduction and validation outputs follow.

## Reproductions

Local machine: this Windows worktree; n = 15 (CONSTRUCT), every case in
test_polymarket_live_trades.py. Stub payloads derive from the S397 fixture trade tape.
One-liner executed unchanged before and after, using hexadecimal Python for cmd.exe quoting:
```
cd C:\Users\neelj\nba-harness-h58 && python -c exec(bytes.fromhex('66726f6d2074657374732e706c6174666f726d6b69742e696e67616d652e746573745f706f6c796d61726b65745f6c6976655f74726164657320696d706f727420726570726f647563650a726570726f647563652829'))
```
Decoded source: `from tests.platformkit.ingame.test_polymarket_live_trades import reproduce; reproduce()`.
Inputs: (a) pages {0:2,2:2,4:1}, limit=2, page_budget=2, two ticks; restart reloads
the saved group. refused replaces both offset-0 timestamps with "bad". (b) retry returns
HTTP 500 once at offset 2. (c) watermark is the timestamp of synth(2); reorder returns
[A,B] at offset 0 and [C,A,B] at offset 2; shift prepends C after the first [A,B] response.
(d) closure repeats the same drain identity after restart. (e) price/size pairs are
0.44/0.440 and 1e-07/0.0000001. Stub timestamps are 1790116199 minus the trade index.

BEFORE, verbatim:
```
progress {'offsets': [0, 2, 0, 2], 'trades': 4, 'unique': 4, 'closures': 0, 'rereads': 0, 'duplicate_closures': 0}
restart {'offsets': [0, 2, 0, 2], 'trades': 4, 'unique': 4, 'closures': 0, 'rereads': 0, 'duplicate_closures': 0}
refused {'offsets': [0, 0], 'trades': 0, 'unique': 0, 'closures': 0, 'rereads': 0, 'duplicate_closures': 0}
retry {'offsets': [0, 2, 0, 2, 4], 'trades': 7, 'unique': 5, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
watermark {'offsets': [0, 2, 4], 'trades': 5, 'unique': 5, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
reorder {'offsets': [0, 2, 4], 'trades': 3, 'unique': 3, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
shift {'offsets': [0, 2], 'trades': 2, 'unique': 2, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
closure {'offsets': [0, 2, 4, 0, 2, 4], 'trades': 5, 'unique': 5, 'closures': 2, 'rereads': 0, 'duplicate_closures': 0}
decimal 0.44/0.440,1e-07/0.0000001 False
```
AFTER, verbatim:
```
progress {'offsets': [0, 2, 4], 'trades': 5, 'unique': 5, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
restart {'offsets': [0, 2, 4], 'trades': 5, 'unique': 5, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
refused {'offsets': [0, 2, 4], 'trades': 3, 'unique': 3, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
retry {'offsets': [0, 2, 2, 4], 'trades': 5, 'unique': 5, 'closures': 1, 'rereads': 0, 'duplicate_closures': 0}
watermark {'offsets': [0, 2, 2, 4], 'trades': 5, 'unique': 5, 'closures': 1, 'rereads': 1, 'duplicate_closures': 0}
reorder {'offsets': [0, 2, 2, 4], 'trades': 3, 'unique': 3, 'closures': 1, 'rereads': 1, 'duplicate_closures': 0}
shift {'offsets': [0, 0, 2], 'trades': 3, 'unique': 3, 'closures': 1, 'rereads': 1, 'duplicate_closures': 0}
closure {'offsets': [0, 2, 4, 0, 0, 2, 4], 'trades': 5, 'unique': 5, 'closures': 1, 'rereads': 1, 'duplicate_closures': 1}
decimal 0.44/0.440,1e-07/0.0000001 True
```

Pinned tests also cover a refused-page restart, a closure synced before checkpoint failure,
a short page ABOVE the watermark (no closure), reread state across restart, capture_once
with 201 trades and a later-page failure, and exponent/long-precision canonical identity.
The older tuple-hash test now uses the fixture's explicit canonical price "0.52"; its old
"0.520" expectation failed once under the amended identity requirement. No assertion was
dropped. The sentinel test stubs existence and writes no STOP file.

(f)/(g) independently measured before/after:
```
f input: 21 games, two slug permutations each; output: 40
g input: linked first, then two state keys; output: first team_set {}
g input: gamma Sep22, CLOB Sep23; output: first team_set {}
f input: 21 games, two slug permutations each; output: 42
g input: linked first, then two state keys; output: None ambiguous {'link_relinked': 1, 'link_ambiguous_after_link': 1}
g input: gamma Sep22, CLOB Sep23; output: None start_source_conflict {'start_source_conflict': 1, 'link_relinked': 1}
```
Tests pin all 42 stub slug requests (all HTTP 200 [] counted), 21 games/two markets each:
20 games/40 markets first tick, the omitted game first next tick, all 21 covered.
Run-path tests reconsider cached, refreshed and failed-refresh indexes, and retain the
known CLOB date when a later metadata request fails.

## Verification (regenerated after the last FIX 1i edit)

Interpreter: C:\Users\neelj\AppData\Local\Programs\Python\Python310\python.exe, Python 3.10.0
(the conda basketball_ai env and RunPod Python 3.12 were NOT run). Each file ran alone with
`python -m pytest tests/platformkit/ingame/<file> -q -p no:cacheprovider`; pass counts:
```
capture 18, json 19, link 22, relink 16, rows 57, trades 32 passed (owned files)
test_capture_watchdog.py 105 passed (landed); 269 total
```
CLI: `python -m scripts.platformkit.ingame.polymarket_live_capture --help`, exit 0.
Preflight command (every owned file; the verdict file excluded):
```
cd C:\Users\neelj\nba-harness-h58 && python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/polymarket_live_capture.py scripts/platformkit/ingame/polymarket_live_json.py scripts/platformkit/ingame/polymarket_live_link.py scripts/platformkit/ingame/polymarket_live_rows.py scripts/platformkit/ingame/polymarket_live_sources.py scripts/platformkit/ingame/polymarket_live_trades.py scripts/platformkit/ingame/capture_watchdog.py tests/platformkit/ingame/test_polymarket_live_capture.py tests/platformkit/ingame/test_polymarket_live_json.py tests/platformkit/ingame/test_polymarket_live_link.py tests/platformkit/ingame/test_polymarket_live_relink.py tests/platformkit/ingame/test_polymarket_live_rows.py tests/platformkit/ingame/test_polymarket_live_trades.py tests/platformkit/ingame/fixtures/s397_clob_book.json tests/platformkit/ingame/fixtures/s397_clob_book_404.json tests/platformkit/ingame/fixtures/s397_clob_market_meta.json tests/platformkit/ingame/fixtures/s397_data_trades.json tests/platformkit/ingame/fixtures/s397_data_trades_mixed.json tests/platformkit/ingame/fixtures/s397_gamma_events.json tests/platformkit/ingame/fixtures/s397_schedule.json tests/platformkit/ingame/fixtures/s397_state_rows.jsonl docs/evidence/harness/S397_polymarket_capture_2026-09-22.md --base master --spec docs/evidence/tracking/specs/S397_spec.md
PASS vocab clean over 22 files
PASS crlf no index-side CRLF over 22 file(s); 21 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema tests/platformkit/ingame/fixtures/s397_clob_book.json new (no master baseline); tests/platformkit/ingame/fixtures/s397_clob_book_404.json new (no ma
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 5 dir(s)
PASS row_duplication no row duplication over checked artifacts
```
Physical lines (all ASCII): sources 194, trades 298, link 236, capture 269, rows 298, json 43, watchdog 289; tests json 300,
trades 291, relink 298, capture 300, link 300, rows 300; this memo 300; fixtures 16/1/17/32/32/90/3/2.
Fixture byte sizes (CRLF): 552, 31, 712, 1249, 1243, 3241, 210, 808.
Fixture byte sizes (LF): 536, 30, 695, 1217, 1211, 3151, 207, 806.
CRLF = this checkout (core.autocrlf true); LF = the blobs (Linux / autocrlf off). Each file is
compared against the set matching the bytes it holds; no .gitattributes change (outside the owned set).
capture_watchdog.py differs from master only by line 86's venue tuple adding polymarket.
Nothing committed. No network, live capture, data/cache or STOP file accessed.

## FIX 1g -- AMENDMENT 11

Local CONSTRUCT regressions reproduced every finding before its fix; the results here supersede the FIX 1f checks above.
- T1-1: `candidate=('idle', 600.0)` for the five-digit start became `('live', 10.0)`. Cadence now uses parse_ts; four/five-digit and strict submicrosecond boundaries are pinned.
- T1-2: failed metadata/book/trade counts were `{('mlb', 'market_meta'): 1}`, `{('mlb', 'books'): 1}`, `{('mlb', 'trades'): 1}`. All now use fetch_error; total rows count them, successful totals and last_success exclude them.
- T1-3: `AssertionError: 2026-09-22T22:35:00.400000Z` reproduced the wrong tick. trade_receipt now receives the original tick on HTTP, transport, malformed-body and seed-failure paths; the original .000000Z tick passes.
- T2-1: reversed pages failed byte comparison (`At index 400 diff: b'8' != b'6'`). The tick stages all pages, sorts trades by created_time/trade_key (venue identity), then appends and fsyncs before its cursor; identical-receipt page reversals now have identical archive bytes.
- T2-2: future recovery raised `ValueError: invalid archived trade` or retained a trade key / `{'closure:future'}`. Receipt filtering now precedes validation/state changes and counts as_of_excluded; all three cases, including cutoff plus one nanosecond, pass. Exact cutoff remains included.
- T2-3: decoded numeric text reported `float`; it now reports `float-text`. Exact Decimal preservation is unchanged; quoted and decoded-numeric source-type tests pass.
- T2-4: `AssertionError: 552, 31, 712, 1249, 1243, 3241, 210, 808` exposed stale memo sizes. The actual on-disk sizes above now pass a fixture-size regression.
Question-based moneyline selection and directional outcome mapping are outside this capture-all row and belong to S398 pairing.
Before fixes: trade-file regression run 11 failed/16 passed; JSON-file regression run 7 failed/9 passed. Strict cadence boundary additions initially gave 2 failed/16 passed, then passed.
HISTORY (fix 1g; current counts under Verification): capture 18, json 18, link 21, relink 16, rows 57, trades 27, watchdog 105 passed (262 total). Crash fixtures now restart as of the latest actual receipt; their no-loss/no-duplicate assertions remain intact.
CLI --help exited 0; no self-check option is exposed. Final contract_preflight: 9 PASS, zero FAIL across 22 owned paths; verdict file excluded.
Every staged tick is acknowledged only after append/fsync; a failed later fetch flushes prior valid pages before retry progress is saved. No fresh live archive or service was exercised.

## FIX 1h -- AMENDMENT 12 (round 4: tier 1 ACCEPT WITH CORRECTIONS, tier 2 REJECT)

Every item reproduced FIRST on a construct (stub clients, now 2026-09-22T22:35Z), then fixed.
- (a) BLOCKER. Input: startDate 2026-05-17T14:16:13.49588Z, endDate 2026-09-24T03:00Z. Before:
  'live' (startDate read as the start). Input: no startDate, gameStartTime '2026-09-22 22:05:00+00',
  endDate 2026-09-23T03:00Z. Before: 'idle'. FIX: classify_event_state(unit, now, errors) reads
  link.market_start -- gameStartTime, then eventStartTime, then the meta game_start_time, the
  link's own order and normalization; event.startDate is read nowhere in the row. Live = not
  ended AND (begun with a known end or the venue live flag, or NO start evidence plus the flag:
  see FIX 1i for the tick in which meta links it). After: pregame (start 23.5 h
  ahead), live, idle (ended, flag True); n_games_live 2 of six units = the two started, unended.
- (b) Pages [A,B],[C,A2] vs [C,A2],[A,B], A2 = A with title 'DIFFERENT' / price '0.5200'.
  Before: bytes identical False. FIX: every parsed row is staged; the tick sorts by
  (created_time, trade_key, canonical JSON body) and dedups AFTER the sort (first wins;
  duplicate_trade_key counts the loser). After: True, duplicate_trade_key 1 in both orders.
- (c) Receipt 22:29:00Z, trade 22:29:59Z. Before: created_after_receipt 0. After: 1 (archived;
  venue clock skew is provenance). Receipt 22:20:00Z (600 s ahead) over two ticks: before
  future_timestamp 2; after 1 -- the quarantined key is remembered once; its re-fetch counts
  duplicate_trade_key. Over-300 s quarantine unchanged.
- (d) Fixture sizes: see the two lines under Verification; the test is line-ending aware.
- (e) Bad endDate / start text: before 0 in the metrics counter, 2 in global PARSE_ERRORS;
  after 2 in the heartbeat's error_counters, 0 global (select_due / _due take the counter). A
  commit() failure inside the fetch except: before cause None; after `raise failure from error`.
- (f) Interpreter stated above. Byte identity holds under EQUAL receipts only: under an
  advancing clock each trade's response_end_ts follows fetch order (legitimate provenance).
  drain.json recent_ids order, and so its bounded eviction, depends on page order.
  NEXT-ROW (not fixed here): seed_failure dead end -- an invalid or future checkpoint or an
  invalid archived trade blocks that market's tape every tick until an operator acts.
Tests: json (cadence table, n_games_live, counter), trades (twin bodies, skew, quarantine-once,
chained commit, size sets; eight scenarios folded into one table, assertions unchanged), relink.

## FIX 1i -- AMENDMENT 13 (round 5: both tiers ACCEPT WITH CORRECTIONS; the live-flag rule ratified)

- (a) capture_once construct: event live True, no market start, meta start 23:55Z (same UTC day,
  links), now 22:35Z. Before: game_key 776112, state live, n_games_live 1. FIX: reclassify after
  relink, before _publish. After: 776112, pregame, n_games_live 0 (test_polymarket_live_link.py).
- (b) Before: live_by_flag_no_start absent. After: 1 -- counted per EVALUATION (per unit per
  classification; the link tick evaluates twice), in error_counters. The rule has no span cap;
  such a unit cannot link (link_market needs a day from the same start evidence), so after (a)
  it never counts toward n_games_live; it ranks below linked games under MAX_UNITS_PER_TICK.
- (c) End-evidence precedence: an endDate in the past wins over a live flag (idle); begun + flag
  + no end is live with no maximum span; begun + endDate days ahead is live until that endDate;
  begun + no endDate + no flag is idle (600 s, not polled): stricter than 12(a), kept (an unknown end is not evidence of live).
- Notes: gamma_start_normalized and timestamp_parse_errors count evaluations per unit per tick, not markets.
  A fixture with mixed line endings fails the size test as a list mismatch; the test first asserts eight fixtures.
  An identical trade_key implies an identical created_time (the timestamp is inside the key).
  A quarantined key re-fetched counts duplicate_trade_key (no separate name).

## NOT VERIFIED

- Crash recovery is bounded, not a general exactly-once guarantee. Unsynced bytes can be lost.
  Recovery consults a two-day archive tail capped at 64 MiB per shard; a delayed restart beyond
  that window or cap can duplicate uncheckpointed trades and closure rows. Construct crash
  boundaries do not establish power-loss or filesystem durability beyond fsync guarantees.
- Offline tests cannot prove behavior under arbitrary venue reordering. The frozen timestamp
  watermark plus one counted straddle reread is bounded; offset shifts outside that coverage
  can still hide trades. A timestamp is not proof that every older print has arrived.
- The venue pagination ceiling and ordering remain unprobed; a silent page-size cap can look
  like a short page. Closure rows expose page_len, requested_limit and pages. The query has
  no time floor, so before_first_contact gaps are not emitted and older history is unbounded.
- Only MLB was exercised live. Other sport prefix mappings, tennis tour:key linkage and real
  doubleheader resolution remain unconfirmed. UTC-midnight discrepancies are not resolved by
  guessing a date. Other non-ISO start shapes remain refused/counted.
- Fee/tick-size units are uninterpreted (S399); fees_trusted denotes a finite positive parse.
  S398 decimal-text admissibility does not resolve the landed touch_size_rows mismatch.
- Watchdog SILENT was tested; paired --watch-s growth, supervisor operation and S368/S364/
  S362/S389 readers on a Polymarket shard were not established by these offline constructs.
  AIMD/retry/429 transport behavior and two simultaneous live venue captures remain unverified.
- Gamma's scheduled-slug response behavior has no live confirmation in the quoted smoke
  facts; HTTP 200 [] handling is a construct. Slug grammar comes from one live example and
  multi-segment code fallback remains unconfirmed.
- Whether a live gamma event's endDate or live flag tracks the real game end is unprobed.
FIX 1i (and 1f-1h) needs its own bounded live smoke
