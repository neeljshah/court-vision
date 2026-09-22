GAP S397 | sport all captured (venue) | worktree harness-h58 (master-based) | log cx_s397_polymarket_capture
# Credential-free Polymarket LIVE capture: public CLOB books + public trade tape, S341 / S374 row discipline (workstream D; ASTRA_ROUND15 row 9)

SINGLE PROBLEM: Kalshi is captured live (rows S341 / S374 / S388) and Polymarket is not: the only Polymarket book capture in the tree
(scripts/platformkit/ingame/polymarket_book_capture.py, pod-gated by CV_CAPTURE_POD / CV_POLYMARKET_BOOK_ARCHIVE_LIVE) writes ts_ms /
enqueue_ts_ms instead of the request_start_ts / response_end_ts / tick_start_ts receipt envelope that the coherence scanner (S368),
the clock report (S364) and the forward replay (S362 / S389) require, captures no trade tape, declares no gaps, has no supervisor and
links to no game_key. A second venue that the landed tools cannot read is not a second venue.

BINDING BEFORE-CONDITION: quote from master (a) scripts/platformkit/ingame/local_capture_runner_row.py: the envelope (record_type,
venue, sport, series, ticker, event_ticker, venue_status, capture_ts, request_start_ts, response_end_ts, http_status,
capture_version) plus tick_start_ts, book_row fields (all Decimal, never float), local_capture_runner_trades.trade_row,
local_capture_backfill.gap_row (gap_kind before_first_contact | page_budget), the trade_backfill_closed record (row S374); (b)
local_capture_writer.py: the _capture.lock, recover(), append() (one os.write of ASCII JSON to an O_APPEND fd, sharded by
response_end_ts day), sync(), commit_groups (fsync BEFORE the cursor); (c) local_capture_limiter.py AIMD constants and
MAX_RETRY_AFTER_SEC; (d) the local_capture_state heartbeat fields; (e) polymarket_scope.py GAMMA_BASE / CLOB_BASE, the events query
and parse_token_ids (clobTokenIds is a JSON-encoded string); (f) local_state_capture.py game_key construction per sport and the state
row fields; (g) scripts/platformkit/execution/forward_schedule_sources.py team-code linkage (the S386 team_set link path); (h)
capture_supervisor.py and capture_watchdog.py CLIs.
VERBATIM PAYLOAD FACTS (orchestrator probe 2026-09-22 15:4xZ; default requests headers; four requests; bodies hashed, not stored):
- GET https://gamma-api.polymarket.com/events?limit=3&active=true&closed=false&tag_slug=sports&order=volume24hr&ascending=false ->
  200, a JSON list; event keys include id, slug, title, startDate, endDate, live, gameId, series, seriesSlug, negRisk, enableOrderBook,
  markets; market keys include conditionId, clobTokenIds (JSON string of a two-element list), outcomes (JSON string), question, slug,
  gameStartTime, eventStartTime, startDateIso, endDateIso, acceptingOrders, acceptingOrdersTimestamp, orderPriceMinTickSize (0.001
  seen), orderMinSize (5 seen), negRisk, feeSchedule, feeType, feesEnabled, makerBaseFee, takerBaseFee, secondsDelay,
  sportsMarketType, umaResolutionStatuses, resolutionSource, lastTradePrice, bestAsk, spread.
- GET https://clob.polymarket.com/book?token_id=<id> -> 404 {"error": ...} for a market whose acceptingOrders is false (a finished
  game); the landed polymarket_book_row expects bids / asks / timestamp / hash on 200. A 404 is a counted refusal, never an empty book.
- GET https://data-api.polymarket.com/trades?market=<conditionId>&limit=5 -> 200, a JSON list of trades with keys asset, conditionId,
  eventSlug, outcome, outcomeIndex, price (string), proxyWallet, side (BUY | SELL), size (string), slug, timestamp (epoch SECONDS as a
  string), title, transactionHash, plus profile fields (name, pseudonym, bio, profileImage, profileImageOptimized, icon) which are
  NEVER stored. There is NO trade id: identity = sha256 over (transactionHash, asset, proxyWallet, side, price, size, timestamp);
  duplicates are counted. Pagination parameters (limit, offset) and their ceilings are UNPROBED: the first live smoke records them.
- GET https://clob.polymarket.com/markets/<conditionId> -> 200 with minimum_tick_size, minimum_order_size, neg_risk, end_date_iso,
  game_start_time, seconds_delay, maker_base_fee, taker_base_fee (both 1000 on the probed sports market), accepting_orders, tokens.
  These are recorded VERBATIM per market once per discovery refresh (record_type market_meta); units are NOT interpreted here (S399).

CHANGE (owned files: NEW scripts/platformkit/ingame/polymarket_live_capture.py, NEW polymarket_live_sources.py, NEW
polymarket_live_rows.py, NEW tests/platformkit/ingame/test_polymarket_live_capture.py, NEW test_polymarket_live_rows.py, NEW
tests/platformkit/ingame/fixtures/s397_*.json (built from the payload facts above; no profile fields), memo; capture_watchdog.py gains
an ADDITIVE polymarket source (contract B2: existing sources unchanged; its landed test file passes unchanged); no other landed module
is edited):
1. polymarket_live_rows.py (<= 300 LOC): the SAME envelope as the Kalshi runner with venue 'polymarket', series = event slug, ticker =
   token_id, event_ticker = conditionId, venue_status = acceptingOrders as a string; snapshot rows carry book (verbatim), best bid /
   ask and their sizes as Decimal from the strings (never float), price_unit 'probability' and yes_bid_cents / yes_ask_cents as Decimal
   cents for the landed adapters (a price that scales outside (0, 100) is refused and counted), api_ts = the book's timestamp field
   verbatim, and a sequence field (the book hash verbatim) so that continuity, not liveness, is what a reader checks; trade rows carry
   every non-profile field verbatim plus trade_key (the sha256 identity) and created_time = the epoch-seconds string converted ONLY
   through scripts.platformkit.execution.venue_time.parse_venue_time (a finite numeric epoch is accepted there), with
   time_resolution_s 1 recorded; market_meta rows; fetch_error rows with http_status and reason.
2. polymarket_live_sources.py (<= 300 LOC): discovery from gamma (tag_slug sports, paged by offset until a short page, budgeted),
   sport classification from the event's series / seriesSlug / slug prefix with unknown -> counted and skipped; GAME LINKAGE to the
   state archive's game_key through the S386 team_set path (team codes from the slug / outcomes plus the UTC date of gameStartTime;
   ambiguous -> counted, not linked; unlinked markets are still captured); trades by (market = conditionId, limit, offset) with a
   per-tick page budget and an HONEST trade_gap when the budget is exhausted before the tape closes (the S374 rule: the newest trade
   time is never completeness; a reconnect or a quiet interval is never inferred from liveness), a trade_backfill_closed record when a
   page returns fewer rows than limit; every acknowledged page is appended and synced BEFORE its cursor is persisted.
3. polymarket_live_capture.py (<= 300 LOC): --output-root <root> --max-ticks N --sports mlb,nfl,tennis,nba,soccer --schedule <S386
   file>; archive at <root>/polymarket/<sport>/<date>.jsonl through the landed writer primitives (lock, recover, append, sync,
   commit_groups); scheduled games FIRST (both outcomes of a linked game together) then live events by volume within the budget; the
   AIMD limiter reused with its OWN budget (the Kalshi capture's anonymous budget is untouched: separate process, separate limiter
   state, separate lock); STOP sentinel <root>/STOP_POLYMARKET; heartbeat <root>/polymarket/<sport>/_heartbeat.json with the landed
   field names plus trades_written_total, market_meta_written_total, unlinked_markets, link_ambiguous, book_404_total; runs under the
   landed capture_supervisor unchanged (--name polymarket).
4. Tests: fixture rows end to end (event -> market_meta + snapshot + trade rows with Decimal fields and the envelope; profile fields
   absent); a 404 book -> fetch_error counted, no snapshot; a page budget exhausted -> trade_gap with gap_start_ts / gap_end_ts; a short
   page -> trade_backfill_closed; crash-boundary fixtures (kill after append before sync; after sync before cursor; after cursor before
   the next fetch) lose no acknowledged print and create no duplicate after a restart; a duplicate trade identity counted once;
   epoch-second timestamps through parse_venue_time; order independence; the watchdog reports SILENT for a flat polymarket heartbeat
   while live; network forbidden in tests (autouse); a test greps the new modules for the forbidden import
   scripts/execute_loop/L10_polymarket_client.
5. Memo docs/evidence/harness/S397_polymarket_capture_2026-09-22.md.

CONTROLS: construct tests only; no network in the builder's run; the ORCHESTRATOR runs the bounded live smoke (--max-ticks 3 into a
scratch root) and amends this spec with verbatim findings before the first verifier round; no credential, key or wallet is read or
referenced. ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with
NOT VERIFIED.

AMENDMENT 1 (2026-09-22 17:2xZ; binding; the Opus build's four conflicts, accepted). (a) local_capture_writer.py:120 hardcodes the
kalshi venue directory: the Polymarket archive uses a PolymarketWriter subclass whose root layout remaps only the venue directory
(the device of local_state_capture_io.py:119 _StateLayout) so that append / sync / recover / atomic / commit_groups / checkpoint_path
/ page_path / persist / archive_tail are reused unchanged, with the lock at <root>/polymarket/_capture.lock; no landed writer line is
edited. (b) The S386 schedule entries carry no team codes: the team_set linkage runs against the STATE archive (game_key, home_abbr,
away_abbr, scheduled_start_utc) and the --schedule file orders prospective games only, never identifies them. (c)
local_capture_backfill.restore() requires a trade_id the venue does not publish: the Polymarket group state restores from trade_key
through the landed archive_tail / page_path / checkpoint_path helpers; no venue field is invented. (d) local_capture_client.drain()
expects a dict body with a list under a key plus a cursor; gamma and the data API return bare lists paged by offset, so the drain
calls GovernedClient.get(url, params, source) directly and keeps its receipt (rate limiting and receipts unchanged).

AMENDMENT 2 (2026-09-22 16:4xZ; binding; VERBATIM FACTS from the orchestrator's live smoke of the candidate: three ticks, mlb, a
scratch root, 16:33-16:35Z, 211 requests, 0 x 429). (a) WORKS: 120 snapshot rows and 26 market_meta rows with the full envelope
(request_start_ts / response_end_ts / tick_start_ts / http_status / capture_version polymarket_live_capture_v1), Decimal prices
(best_bid 0.43, best_ask 0.44, yes_bid_cents 43.0 / yes_ask_cents 44.0, sizes 70625.85 / 15316.29, 36 / 42 levels), api_ts
'1790094822966' (the venue's book timestamp is EPOCH MILLISECONDS as a string -- record it verbatim AND derive api_ts_iso through
parse_venue_time from the integer milliseconds), sequence = the book hash; market_meta carries game_start_time
'2026-09-22T22:40:00Z', minimum_tick_size 0.01, minimum_order_size 5, maker_base_fee / taker_base_fee 1000, seconds_delay 0.
(b) DEFECT: ZERO trades written -- 60 trade requests succeeded (http 200) but every row was refused: error_counters
timestamp_parse_errors 600, timestamp_invalid_format 600, trade_time_refusals 60, trade_refusals 60. The trade timestamp is an
epoch-SECONDS STRING ('1790089963'); the candidate handed the string to parse_venue_time, which does not accept a digit string as
an epoch. FIX: validate the string as an unsigned integer of at most 11 digits, convert to int, then parse_venue_time(int) (a finite
numeric epoch); anything else is a counted refusal. (c) DEFECT: a page whose every trade was refused produced NO trade_gap and NO
fetch_error record -- the archive shows a silent empty tape while the heartbeat counts refusals. FIX: when a fetched page yields
zero accepted trades from a non-empty payload, write ONE trade_gap record (gap_kind page_refused, with the refusal counts and the
request params) for that market and tick; the reader must be able to see the missing tape from the archive alone. (d) DEFECT: every
market unlinked (unlinked_markets 1226, link_path no_start_date): the candidate looked for an event start field that gamma's payload
names differently. FIX: the game start for linkage is, in order, the market's gameStartTime, the event's startDate, and the CLOB
market_meta game_start_time; the UTC date of that instant plus the team codes parsed from the slug (mlb-mil-phi-2026-09-22 ->
MIL, PHI) go through the S386 team_set path against the STATE archive; a market with none of the three is counted
link_no_start_date and still captured. (e) OBSERVED: unknown_sport_events 305 (non-MLB sports skipped, counted) and
discovery_page_budget_exhausted 1 (33 events / 1226 markets tracked from the first pages): the discovery budget must prioritise the
scheduled games' slugs BEFORE volume paging so a scheduled game is never beyond the budget; a test proves a scheduled slug on page
three is discovered within budget.

AMENDMENT 3 (2026-09-22 17:2xZ; binding; VERBATIM FACTS from the orchestrator's second live smoke of fix 1b and a three-row re-probe
of the tape). (a) The data API's trade fields are NOT uniformly strings: on the live MIL at PHI market the payload carried timestamp
as a JSON INTEGER (1790095561), size as a float (1.754386) or an int (20), price as a float (0.5699999886 / 0.44), outcomeIndex as an
int; the first probe's finished esports market had carried them as strings. The candidate's text-only epoch validation refused
every row (trade_time_not_unsigned_epoch_text 60, refused_time_sample None) and the honest page_refused gap records (60) now show it.
FIX: the trade timestamp is an unsigned epoch in SECONDS delivered as either a JSON integer or a digit string: an int is
range-checked; a string of at most 11 digits is converted; a bool, a float, a negative or anything else is a counted refusal;
size and price are converted to Decimal through the shortest round-trip repr of the JSON value (Decimal(repr(value)) for a float,
Decimal(str(value)) for an int or a digit string), NEVER through float arithmetic, and the row records the source JSON type per
field (size_type, price_type, timestamp_type) so the mixed encoding stays visible; a NaN / inf float is a counted refusal; the
fixtures carry both encodings verbatim. (b) LINKAGE needs the state archive: the capture reads state rows from --state-root
(defaulting to the capture root); the second smoke ran into an empty scratch root, so every market was unlinked (link_path
'unlinked', link_no_start_date 0): the third smoke copies today's real mlb state shard into the scratch root first. (c) The
page_refused gap record must carry the refused value's JSON type beside refused_time_sample (a None sample is a defect of the
sampler, not evidence about the venue).

AMENDMENT 4 (2026-09-22 17:3xZ; binding; VERBATIM FACTS from the orchestrator's third live smoke of fix 1c and a two-event gamma
re-probe). (a) WORKS NOW: 3274 trades written in three ticks with both encodings (timestamp int / size int or float / price float:
1502 + 1772 rows), 55 trade_backfill_closed, 5 honest page_budget gaps, duplicate_trade_key 3871 counted, created_time derived
from the integer epoch. (b) STILL EVERY MARKET UNLINKED (145 rows link_path 'unlinked', game_key None) although link_market,
market_day and state_index WORK STANDALONE on the same real inputs: state_index over the v2 state root gave a 15-key index
(('mlb', frozenset({'PIT','STL'}), '2026-09-22') -> {'823328'} ...), market_day on the real market_meta gave ('2026-09-22',
'meta.game_start_time'), slug_codes gave ['mil','phi'] and link_market('mlb', ...) returned ('823412', 'team_set'). The run
path therefore drops the link between relink() and the written rows (the unit is not updated, or the rows are built from a
stale unit, or relink receives a different body / index than the standalone call): reproduce with the real market_meta row and
the real v2 state shard through the SAME code path the capture uses (capture_once with a stub client returning the fixture
payloads), then fix and pin it with a test that asserts every snapshot row written AFTER the market_meta row carries the key.
(c) GAMMA START FIELDS, verbatim: market.gameStartTime is '2026-09-22 17:05:00+00' (a SPACE separator and a bare '+00' offset,
which parse_venue_time refuses: timestamp_invalid_format 600 at discovery); market.eventStartTime is ISO ('2026-09-22T17:00:00Z')
when present; event.startDate is the MARKET CREATION instant ('2026-05-17T14:16:13.49588Z' for a game played on 2026-09-22) and
must NEVER be used as the game start. FIX: the start order is market.gameStartTime (normalized ONCE by a declared rule -- the
space becomes 'T' and a bare '+00' / '-05' offset gains ':00' -- then parse_venue_time), else market.eventStartTime, else the
CLOB market_meta game_start_time; event.startDate is removed from the order; the normalization is counted (gamma_start_normalized)
and tested with the verbatim value. (d) The heartbeat's unlinked_markets must carry a reason breakdown (no_start, no_codes,
no_state_rows_for_day, ambiguous, linked_by_meta, linked_at_discovery) so the next smoke can be read from the heartbeat alone.

AMENDMENT 5 (2026-09-22 18:0xZ; binding; VERBATIM FACTS from the orchestrator's fourth live smoke of fix 1d: three ticks, mlb,
--state-root data/cache/ingame_state_local_v2, --schedule 2026-09-22_maker_forward_full_selection.json, exit 0 in 115 s).
(a) THE RUN PATH LINKS NOW: rows written 1324 = market_meta 26 + snapshot 120 + trade 1118 + trade_backfill_closed 60; links by
(kind, path, key): trade/team_set for eight game_keys (823412: 183, 823328: 173, 824867: 161, 824061: 156, 824709: 156, 824222: 113,
824785: 103, 824624: 73) and snapshot/team_set for four (823412: 20, 824061: 18, 823328: 18, 824867: 18); gaps {} (no page_budget
gap this run). (b) HEARTBEAT: unlinked_markets 875 of n_markets_tracked 1228 with the reason breakdown linked_at_discovery 353,
linked_by_meta 0, no_start 626, no_codes 0, no_state_rows_for_day 2, ambiguous 43, unlinked 204; counters gamma_start_normalized
602, unknown_sport_events 303, out_of_scope_sport_events 163, discovery_page_budget_exhausted 1, duplicate_trade_key 2022,
non_object_events 0. (c) READING: the 626 no_start markets are non-game markets on game events (futures, props, series) and the
out-of-scope sports; they are counted, never refused; the 43 ambiguous are events whose slug codes match more than one state key
for the day (doubleheaders or alias collisions) and stay unlinked by design; the verifier judges the 204 plain 'unlinked' (a
market that reached neither reason) as a finding if the code can reach that value on a market that has a start and codes.
(d) The memo records (a)-(b) verbatim as the first archive facts; the S398 re-probe runs on THIS smoke-4 archive.

AMENDMENT 6 (2026-09-22 18:2xZ; binding; from the orchestrator's S398 scan over the smoke-4 archive). MEASURED: the landed decimal
reader (coherence_scanner_inputs.decimal_value, the same reader every downstream count uses) refused ALL 120 snapshot rows with
'expected a decimal string': the writer stores best_bid / best_ask / best_bid_size / best_ask_size / depth_* / yes_bid_cents /
yes_ask_cents (and the trade tape's price / size) as JSON floats (43.0, 0.44, 95025.05) although the CLOB book sends every price and
size as decimal TEXT ('0.43', '95025.05') and the trade tape sends a mix. A float is not the venue's number. CHANGE (additive):
(a) every venue payload is decoded with json.loads(text, parse_float=str) so a venue decimal reaches the row as its exact text;
integers stay integers; the row's price and size fields are written as decimal text (or int) and NEVER as a float; derived fields
(yes_bid_cents = the venue price times 100) are computed through Decimal and written as decimal text; the source type recording of
AMENDMENT 3 stays (int / float-text / str per field). (b) A test pins the verbatim CLOB values '0.43' / '95025.05' and the trade
tape's float-encoded size through the decoder and asserts the written row round-trips through decimal_value with no float anywhere
in the row (json.loads of the written line must contain no float). (c) The archive written before this change (smokes 1-4) is
superseded and is not an input to any S398 count; the memo says so.

AMENDMENT 6(d) (2026-09-22 18:2xZ; binding; from the S398 probe 3 refusal-reason counters): the landed cross-venue quote reader
refused all 120 snapshot rows with KeyError 'yes_bid_size' -- the S397 row carries best_bid_size / best_ask_size while the
Kalshi-shaped reader (capture_book_adapter) requires the touch sizes in the YES frame as yes_bid_size / yes_ask_size. The
snapshot row ADDS yes_bid_size and yes_ask_size (the touch size at the YES bid and at the YES ask, decimal text, derived from
the venue's size text with no float), keeping best_* as written; a test asserts the written row passes the landed reader's
field requirements (yes_bid_cents, yes_ask_cents, yes_bid_size, yes_ask_size, api_ts, response_end_ts, venue_status).

AMENDMENT 7 (2026-09-22 18:4xZ; binding; from fix 1e). (a) OWNED SET PINNED: scripts/platformkit/ingame/polymarket_live_capture.py,
polymarket_live_sources.py, polymarket_live_trades.py (the trade tape split out for the 300-LOC rail), polymarket_live_rows.py,
polymarket_live_link.py, polymarket_live_json.py (JsonNumberText decoding), the additive one-tuple change in capture_watchdog.py,
tests/platformkit/ingame/test_polymarket_live_capture.py, test_polymarket_live_json.py, test_polymarket_live_link.py,
test_polymarket_live_relink.py, test_polymarket_live_rows.py, tests/platformkit/ingame/fixtures/ (the S397 fixture files), and
the memo. (b) READER FACT, reported by the fix agent and not smoothed: in this worktree the landed reader of the yes_*_size names
is capture_coverage_daily._size_present (lines 123-136, 205-206), which refuses a float by type and pairs yes_bid_size with
no_bid_size (the Kalshi two-token frame); the S397 row emits yes_bid_size and yes_ask_size (a YES-token book has no NO side of its
own), so touch_size_rows in that landed reader will not count Polymarket rows; inferring a NO-side size from a YES book is
unmeasured (an S399 question) and is NOT guessed -- the memo names it; the S398 scan (unlanded) reads yes_bid_size / yes_ask_size
and is the consumer this row serves. (c) The fifth smoke (fix 1e) is the first archive whose rows carry decimal text; smokes 1-4
are superseded for every downstream count.

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

AMENDMENT 9 (2026-09-22 19:0xZ; binding; from the codex sol round-2 verdict and the astra round-2 critique on fix 1e). (a) DRAIN
PROGRESSION: a budget-limited drain must progress past the first page window -- pages {0: 2 rows, 2: 2, 4: 1} with page_budget 2
over two ticks requested offsets [0, 2, 0, 2] and never reached 4, and an all-refused first page followed by a valid page gave
[0, 0]: on budget exhaustion or a durably recorded refused-page gap the continuation is ADVANCED and persisted (only the per-tick
page count resets); backfill closes only after a short page; multi-tick and restart tests prove offsets 0, 2, 4. (b) RETRY
DUPLICATES: the drain deep-copies the group, so a later-page failure returns without updating the cached group and the retry
re-writes the earlier pages' trades -- the cached group is updated page by page as rows are durably appended, so a retry resumes,
never repeats. (c) CROSS-PAGE REORDERING: trades that move across an offset boundary between pages ([A, B] then [C, A, B] at
offset 2) are lost with a closure written -- closure requires a timestamp WATERMARK: the backfill is closed only when a page's
oldest timestamp precedes the watermark AND the next page is short; a page whose items straddle the watermark is re-read once;
counted (watermark_rereads). (d) CLOSURE RECORDS IN DEDUPE: trade_backfill_closed rows are subject to the same restore / dedupe as
trades (duplicate closures counted, never re-written). (e) TRADE KEY ON THE DECIMAL VALUE: '0.44' and '0.440' are one trade --
the trade_key hashes the canonical Decimal text (Decimal(text).normalize() rendered without exponent) while the row keeps the
venue text verbatim; identity fields keep their text. (f) SCHEDULED COVERAGE: slug permutations per game are not truncated at 40
and selection is per GAME with aging priority (a scheduled game not selected in the previous tick ranks first), so 21+ scheduled
games are all selected over consecutive ticks; a renamed or empty slug (HTTP 200 []) counts scheduled_slug_empty; the heartbeat
carries scheduled_requested / discovered / selected / overdue. (g) LINK RECONSIDERATION: an existing key is reconsidered when the
state index later shows ambiguity for its team set and day (a doubleheader's second game appearing after the first was linked):
the unit is re-linked, a change counted link_relinked, an unresolved ambiguity counted link_ambiguous_after_link and the key
cleared; stale gameStartTime never outranks a CLOB game_start_time on a different UTC date (counted start_source_conflict, key
cleared). (h) MEMO: AMENDMENT 8's fifth-smoke facts recorded verbatim (1368 rows, zero float paths, six linked keys,
no_code_match 208, no gaps, no fetch errors); smokes 1-4 kept as superseded history; the 'unsmoked' sentence removed; the
1e-07 identity claim at memo line 286 corrected (exact text hashes identically across encodings). NOT VERIFIED must carry the
bounded crash-recovery guarantees (unsynced bytes; delayed restart beyond the two-day tail can duplicate uncheckpointed trades).
