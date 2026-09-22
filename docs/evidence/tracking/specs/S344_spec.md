GAP S344 | sport all (maker channel) | worktree harness-h4 | log cx_s344_tape_fills
# Tape-supported paper fills: a book crossing is not an execution (astra round 10 rank 4)

SINGLE PROBLEM: scripts/platformkit/execution/paper_maker.py:114-142 fills a resting quote when the observed BOOK trades through
it, and executor/mock_exchange.py:84-88 treats unknown size as unlimited. No archive held a per-trade tape until the S341 local
capture (Kalshi GET /markets/trades rows: trade_id, ticker, created_time, yes_price, no_price, count, taker_side).

BINDING BEFORE-CONDITION (re-run, quote): `grep -n "def trades_through" scripts/platformkit/execution/paper_maker.py` hits;
`ls scripts/platformkit/execution/tape_fill_sim.py` fails.

CHANGE (NEW files only; paper_maker.py and mock_exchange.py are NOT edited):
1. scripts/platformkit/execution/tape_fill_sim.py (<= 300 LOC, stdlib, ASCII, pure, no I/O):
   `simulate_fills(quote_events, trades, book_snapshots, params) -> {"fills": [...], "unfilled": [...], "diagnostics": {...}}`
   - a resting quote is LIVE only from submit_ts + params.submit_latency_s until cancel_ts + params.cancel_latency_s
     (a cancel is not effective instantly: prints inside the cancel-latency window CAN still fill -- pessimistic).
   - an eligible print is an AGGRESSOR trade on the opposite side (taker_side hits our resting side) with trade ts inside the live
     window and a price AT or THROUGH our limit. Prints strictly THROUGH the limit fill up to print size. Prints AT the limit fill
     only after the queue ahead is depleted: queue_ahead starts at the displayed size at our price in the last book snapshot at or
     before submit (unknown size -> params.unknown_queue_contracts, default a LARGE pessimistic constant, never zero), is reduced
     ONLY by prints at that price (cancellations by others are never credited), and resets fully on a replace.
   - volume conservation: across all our resting quotes, total filled from one print never exceeds that print count; one
     trade_id is consumed at most once; duplicate trade_ids in the input are de-duplicated and counted in diagnostics.
   - no fill before arrival, none from an assumed spread, none from a print with missing size or side (counted unscored).
   - every fill record carries: quote_id, ticker, game_id, side, price, qty, fill_ts, trade_id, queue_ahead_at_submit,
     fee_units via venue_fees.fee_kalshi_maker per whole order, fee_schedule_version, and fill_basis in {"through","touch_queue"}.
2. tests/platformkit/execution/test_tape_fill_sim.py: duplicate prints, missing size, missing side, print before arrival, print
   inside cancel latency, touch without depletion (no fill), touch after depletion (fill), replace resets priority, two resting
   quotes competing for one print (conservation), unknown displayed size uses the pessimistic constant.
3. `_demo()` assert self-check; memo docs/evidence/harness/S344_tape_fills_2026-09-21.md.

CONTROLS: construct tests only; no measured fill rate (no tape long enough exists yet). Defaults cite their source line or are
declared ASSUMPTION in the memo. ACCEPTANCE: per-file test passes; diff = NEW files only. Vocabulary follows contract Q6;
automated scan required. Memo ends with a NOT VERIFIED list (polling cannot reconstruct cancellations or true queue position).

AMENDMENT 1 (orchestrator, 2026-09-21; binding; MEASURED facts replace an assumption in this spec).
The SINGLE PROBLEM text says no archive held a per-trade tape before S341. That is FALSE: data/cache/book_depth/_archive/
kalshi_trades/<date>.jsonl is a real per-trade tape (census docs/evidence/ingame/kalshi_trade_tape_census_2026-09-21.json:
2,070,472 rows -> 69,577 DISTINCT trade_id; mlb 36,369 trades / 265 tickers / 97 events; wnba 33,208 / 185 / 59;
trade_ts 2026-07-08..2026-07-17; rows repeat across polls, so de-duplication on trade_id is mandatory; completeness of the
polling is NOT VERIFIED). Row schema: trade_ts (ISO, microseconds, venue time), ts (capture time), trade_id, ticker, sport,
taker_side in {yes, no}, price as a PROBABILITY float (0.51), count as a float.
BINDING CONSEQUENCES:
  (a) FRACTIONAL COUNTS ARE REAL: 35,841 of the 69,577 distinct trades carry a non-integer count. The simulator MUST accept
      fractional print sizes (use decimal.Decimal end to end for sizes; never float accumulation) and volume conservation,
      queue depletion and partial fills must hold exactly in Decimal. Our own quote qty stays an integer number of contracts;
      a fill may therefore be fractional only if the venue print is -- record filled size as a Decimal string.
      Rejecting a print because its count is not an integer is a DEFECT (it would drop about half of the real tape).
  (b) INPUT ADAPTERS, explicit and tested: `from_archive_trade(row)` for the schema above (price probability -> cents, with a
      refusal when price * 100 is not within 1e-9 of an integer cent) and `from_s341_trade(row)` for the raw venue fields the
      S341 runner stores (yes_price / no_price or *_dollars strings, count or count_fp). The core simulator takes ONE normalized
      print type; an unrecognized schema is refused with a reason, never coerced.
  (c) the trade time used for every window comparison is the VENUE time (trade_ts / created_time), never the capture time.

AMENDMENT 2 (orchestrator, 2026-09-21, after the second independent review; binding).
  (d) A NORMALIZED PRINT PRICE IS 1..99 CENTS INCLUSIVE. Both adapters refuse any print whose price (or whose 100 - price
      mirror) falls outside that range, with the reason "price out of range". MEASURED DEFECT this closes: a print at 0 cents
      was accepted, classified as THROUGH every resting quote, and filled a quote at 5 cents in full while an unknown queue of
      1e6 contracts stood ahead of it -- an optimistic fill that bypasses the queue.
  (e) EVERY RETURNED RECORD IS JSON-SERIALIZABLE: every size-like field (qty, queue_ahead_at_submit, unfilled qty, any Decimal)
      is emitted as a string; `json.dumps` over the whole result must succeed, and a test asserts it.
  (f) De-duplication consumes a trade_id ONLY for a successfully normalized print; a refused row never blocks a later valid row
      with the same trade_id, so the result does not depend on input order.
  (g) The memo states that the fee function receives the CUMULATIVE filled size of the order as a Decimal (possibly fractional)
      and how venue_fees coerces it.

AMENDMENT 3 (orchestrator, 2026-09-21; binding; found by feeding REAL captured rows to the adapter after 71 construct tests passed).
  (h) VENUE TIMESTAMPS ARE PARSED VERSION-INDEPENDENTLY. MEASURED on today's S341 archive: 962 of 9,737 created_time values
      (9.9 pct) carry 4 or 5 fractional digits because the venue trims trailing zeros (example 2026-09-21T19:20:51.1492Z);
      datetime.fromisoformat on Python 3.10 (this machine) raises on them, so the adapter REFUSED a real print, while Python 3.11+
      accepts it -- results would differ between machines. ONE parser in the adapters module normalizes the fraction to 6 digits
      (pad or truncate) and the trailing Z before parsing; it accepts 0 to 9 fractional digits; a refusal for an unparseable time
      stays, with the reason "unparseable venue time".
  (i) A REAL-ROW FIXTURE IS PART OF THE TEST SUITE: tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl (eight
      public trade records captured verbatim, two each with 3, 4, 5 and 6 fractional digits). A test feeds EVERY fixture row through
      from_s341_trade and asserts a NormalizedPrint for each, with the venue time equal to the row's created_time to the microsecond
      and the size equal to Decimal(count_fp). Construct-only tests are not sufficient for an adapter.
