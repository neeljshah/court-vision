GAP S341 | sport all captured | worktree harness-h10 (copy of the untracked main-tree files) | log cx_s341_fix1b
# Local Kalshi capture: DATA-INTEGRITY requirements (written 2026-09-21 after an independent REJECT; this file is the authority)

CONTEXT: scripts/platformkit/ingame/local_capture_runner.py (+ _row.py, _trades.py, tests/platformkit/ingame/
test_local_capture_runner.py) is a credential-free public-REST capture already running on the owner's laptop. It is the ONLY
forward measurement the project has. An independent review (codex gpt-5.6-sol) REJECTED it. Every item below is binding.

R1 NO TRADE MAY BE SKIPPED. The trade fetch drains EVERY page (follow the response cursor until it is empty) before any
   watermark advances. The watermark is (max created_time fully drained, the set of trade_ids AT that boundary timestamp) and
   is persisted ATOMICALLY (write temp + os.replace) per ticker group; every poll re-requests with a time OVERLAP (min_ts =
   watermark - 120 s) and relies on trade_id de-duplication. A venue timestamp more than 300 s in the future of the local UTC
   clock is quarantined to a separate file and never advances the watermark.
R2 DE-DUPLICATION IS ORDERED AND BOUNDED: an insertion-ordered bounded structure (deque + set), never arbitrary set eviction;
   restart restores watermark AND boundary ids; a failure to seed from the archive is COUNTED in the heartbeat and aborts trade
   capture for that ticker group until resolved -- it is never silently ignored.
R3 TIMESTAMPS ARE TRUE: request_start_ts is read from the UTC clock IMMEDIATELY before session.get (AFTER any rate-limit wait),
   response_end_ts immediately after the body is consumed. capture_ts is kept for schema continuity but is set equal to
   response_end_ts; the tick-start time, if wanted, goes in a NEW field tick_start_ts. No row may carry a time taken before its
   request was sent.
R4 TIMESTAMP PARSING IS VERSION-INDEPENDENT: MEASURED on this archive, 962 of 9,737 created_time values (9.9 pct) carry 4 or 5
   fractional digits (the venue trims trailing zeros); datetime.fromisoformat on Python 3.10 rejects them. ONE shared parser
   pads or truncates the fraction to 6 digits and handles a trailing Z; it is used everywhere a venue time is parsed (cursor
   seeding included) and tested with 0, 1, 3, 4, 5, 6 and 9 fractional digits.
R5 RAW VENUE FIELDS ARE STORED UNMODIFIED: for snapshot and snapshot_bulk rows the raw market object and the raw orderbook are
   stored under `raw_market` / `book` exactly as returned (fixed-point strings such as *_dollars and *_fp stay strings). Numeric
   conveniences may be ADDED under new names with a unit suffix; existing derived field names stay (contract B2) but must be
   computed with decimal.Decimal, never float round-trips of the raw strings.
R6 WRITES ARE CRASH-SAFE AND SINGLE-WRITER: an exclusive process lock file (second instance exits with a clear message); each
   record is ONE encoded line written with a single os.write on an O_APPEND descriptor, then flush + fsync at most once per tick;
   on startup an incomplete final line is moved to a .quarantine file, never parsed; a write failure is COUNTED and surfaces in
   the heartbeat (never swallowed); the daily shard is chosen from response_end_ts (UTC), not from the tick start.
R7 RATE CONTROL CANNOT BURST: the limiter reserves a monotonically increasing next-send deadline UNDER the lock before sleeping,
   so concurrent workers never wake together; Retry-After is honoured in BOTH forms (delta-seconds and HTTP-date); after a long
   sleep no accumulated credit exists. Live winner markets are scheduled FIRST each tick.
R8 NOTHING FAILS SILENTLY: every except clause increments a named heartbeat counter; the heartbeat reports, per source, attempts,
   successes, rows written, drops by reason, last actual WRITE time (not merely last HTTP success), current req/s and the
   10-minute 429 rate. In-memory maps keyed by ticker / trade id are pruned when a market closes and at the UTC day boundary.
R9 SCOPE: NEW or row-owned files only. Never edit kalshi_series_scope.py, kalshi_book_row.py or any pre-existing module -- if a
   shared helper is unsafe (kalshi_book_row.py:71-87 buffered append), write the safe writer in a row-owned file and use that.
   No credentials, no auth files, no custom User-Agent. Each file <= 300 LOC (add row-owned modules as needed), stdlib + requests.

TESTS (offline only): multi-page drain with > 100 prints between polls; overlap + dedup; boundary-id restart; future-timestamp
quarantine; seed failure counted; fractional-digit parser; raw-field byte preservation; torn final line quarantine; second-instance
lock refusal; shard by response_end across UTC midnight; limiter never releases two sends closer than 1/rate under 4 threads;
Retry-After both forms; every swallowed exception increments a counter.
ACCEPTANCE: per-file tests pass; the memo docs/evidence/harness/S341_local_capture_2026-09-21.md maps each R item to code lines and
tests and ends with a NOT VERIFIED list. Vocabulary follows contract Q6; automated scan required.

AMENDMENT 1 (orchestrator, 2026-09-21, from the PRODUCTION heartbeat after the swap; binding).
OBSERVED at 20:51Z on data/cache/ingame_books_local/kalshi/nfl/_heartbeat.json: error_counters max_pages_exceeded = 10 and the nfl
trade count frozen at its pre-swap value, while mlb and tennis grow normally. CAUSE: on FIRST CONTACT with a ticker there is no
watermark, so the drain walks the market's WHOLE trade history; an NFL winner market holds more than 200 pages x 100 prints, the
max_pages guard fires, the drain fails closed, the watermark never advances, and the next tick repeats the same 200 requests --
the ticker is never captured and the request budget is burned. Failing closed is right; an unbounded first backfill is not.
R1b BOUNDED FIRST CONTACT + EXPLICIT GAPS (replaces "first poll has no lower bound"):
  (a) On first contact with a ticker (no persisted watermark AND no trade for it in the archive) the drain is bounded BELOW by
      min_ts = now - FIRST_CONTACT_LOOKBACK_S (default 6 h). History older than that is OUT OF SCOPE by design and is recorded once
      per ticker as a gap record: record_type "trade_gap", ticker, gap_kind "before_first_contact", gap_end_ts = that min_ts.
  (b) If a bounded drain still exceeds max_pages, the capture KEEPS the pages it drained (they are the NEWEST prints, the most
      valuable), writes them, advances the watermark to the newest drained print, and writes a gap record gap_kind "page_budget"
      with gap_start_ts = the previous watermark (or the first-contact bound) and gap_end_ts = the OLDEST drained print time. The
      trades inside a recorded gap are never silently assumed absent: any consumer can see exactly which interval is missing.
      metrics count trade_gap records and max_pages_exceeded separately.
  (c) A ticker that produced a page_budget gap is NOT retried for the gap interval on later ticks (no budget burn); normal
      incremental polling continues from the new watermark with the usual overlap.
  (d) Per-tick request budget fairness: one ticker may consume at most MAX_PAGES_PER_TICKER_PER_TICK pages (default 20) in a
      single tick; a longer drain continues on the following ticks from a persisted backfill cursor, and the watermark advances
      only when that ticker's drain completes or is closed by a gap record. Live winner markets are served before any backfill.
  (e) The heartbeat reports per sport: tickers_in_backfill, gap_records_total, pages_this_tick.
Required tests (offline, fake client): first contact bounded by the lookback and one before_first_contact gap record written once;
a 500-page history ends with newest prints written + one page_budget gap + watermark advanced + NO repeat drain next tick; the
per-tick page cap spreads a long drain over ticks with a persisted cursor and survives a restart mid-backfill; live markets are
served first; gap records carry request / response receipts like every other record.

AMENDMENT 2 (orchestrator, 2026-09-21, after the independent verifier REJECT of fix 1d; binding).
OPERATIONAL NOTE, stated plainly: the fix-1d candidate is RUNNING in production from worktree nba-harness-h10 (not landed on master)
because the landed code had frozen NFL trade capture and the candidate's real-data smoke wrote 32,150 distinct NFL trades with
explicit gap records; three of the four findings below also exist in the landed code. It is an operational candidate, not an
accepted row.
R10 THE FOUR VERIFIER FINDINGS (codex gpt-5.6-sol), each reproduced on synthetic input:
  (a) local_capture_runner.py ~79: R1b (a) and (d) are not enforced PER TICKER -- duplicate discovery rows schedule one ticker twice
      (tickers ['T','T'], cap 20 -> 40 trade pages, 2 before_first_contact gaps). FIX: de-duplicate the due list by ticker,
      preserving the live-first order; one gap record and one page budget per ticker per tick.
  (b) local_capture_state.py ~27 + local_capture_runner.py ~41: a PARTIAL series-discovery failure replaces the cache with the
      partial result and the missing ticker is then pruned (cached ['A','B'], series status [200, 500] -> selected ['A']): B gets no
      requests and no gap record, violating R1. FIX: a sport refresh is ATOMIC -- if any configured series drain fails, keep the
      previous cache for that sport (or keep independent per-series caches); a ticker is pruned only on positive evidence that its
      market closed or settled, never because a discovery call failed; count discovery failures in the heartbeat.
  (c) local_capture_time.py ~30: the row-owned parser assumes UTC for a timestamp WITHOUT a zone ('2026-09-21T12:00:00' -> 12:00Z),
      while the shared parser scripts.platformkit.execution.venue_time.parse_venue_time refuses it (timezone_missing). FIX: delegate
      every non-empty venue time to the shared parser, convert its finite epoch to an aware UTC datetime, and COUNT refusals by
      reason; an unzoned venue timestamp is refused, never assumed.
  (d) local_capture_limiter.py ~21: a non-finite Retry-After is accepted (a 400-digit numeric header parses to inf -> wait inf ->
      next_send inf: the capture stalls forever). FIX: require math.isfinite, clamp a valid delay to a declared maximum (default
      300 s), count and ignore invalid values.
Required tests: each reproduction above fails before and passes after; the backfill test gains the duplicate-ticker construct; a
discovery failure never prunes; an unzoned time is refused and counted; inf, NaN, negative and absurdly large Retry-After values.
