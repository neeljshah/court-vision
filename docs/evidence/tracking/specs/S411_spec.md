GAP S411 | sport all captured (venue) | worktree harness-h70 (master-based) | log cx_s411_fill_realism
# Fill realism on the captured Kalshi books and trade tape, counts only (workstream E; DIRECTION Session E)

SINGLE PROBLEM: a paper maker fill is a counterfactual -- our order was never in the book, so no print is evidence that WE would have been filled. tape_fill_sim is landed but has only ever run on
constructed rows; nothing has counted what it does on the real captured books and tape: how much displayed size sits ahead at the touch, how often a fill is credited by a print trading THROUGH the
quoted price versus out of the touch queue, how many instants carry no touch size at all, what partial fills look like, what quote life a run actually models, and whether a fill's markout differs
after a state change. Zero paper fills exist, so the assumption every maker measurement rests on has never been measured. The only defensible output is a bound across declared queue assumptions plus
a count of what was refused -- never a point fill rate.

BINDING BEFORE-CONDITION: quote from master (a) tape_fill_sim._queue(quote, books, unknown, diagnostics) (:53-75), which reads the displayed size at EXACTLY the quote price from the latest book at or
before submit_ts and returns `unknown` when any candidate lacks that level, with UNKNOWN_QUEUE_CONTRACTS = 1_000_000 (:14) and FEE_SCHEDULE_VERSION (:15); (b) the credit rule `not q["arrival"] < ts <
q["end"] or price > q["price"]` skipping a print (:213-215) and `basis = "through" if price < q["price"] else "touch_queue"` (:217), where arrival = submit_ts + submit_delay (:163), end is inf or
cancel + cancel_delay (:164), a cancel before submission raises (:166), a replacement is a new order whose submit time cancels the old subject to cancel latency (:171-188), queue_ahead_at_submit is
recorded per fill (:167,250) and the fee is a cumulative ceiling through fee_kalshi_maker (:235-253); (c) capture_book_adapter's docstring lines "Absent sizes omit that level, preserving the
simulator's unknown queue policy" and "no partial book is returned" (:1-7), with raw touch sizes from <prefix>_size_fp (:135-155); (d) touch_queue_sensitivity.MULTIPLIERS = (2, 4, 8) (:17);
(e) markout_causal.summary_strict (:182-268), DEFAULT_HORIZONS_S (30.0, 120.0, 300.0) (:24), DEFAULT_MAX_WAIT_S 30.0 (:28), the verdict line POSITIVE / NEGATIVE / INDISTINGUISHABLE / INSUFFICIENT
(:246-247), and the landed estimator entry_timing/study.py cluster_boot_ci, "95% CI for the mean, bootstrap resampling whole game clusters" (:30-32), returning (None, None) below five clusters
(:37-38) -- a mean, not a median; (f) quote_reservation.ReservationLedger's `ttl_s: int | str | Decimal = '30'` (:90) against scripts/platformkit/ingame/forward_capture_profile.json focus_tick_s 5
and reservation_ttl_s 5, and make_quotes_reserved (:196); (g) forward_replay_io._KINDS admitting {snapshot, snapshot_bulk, trade, trade_gap, host_gap, state, tape_watermark} (:17), the landed Kalshi
trade row from local_capture_runner_trades.trade_row (:36-40) over local_capture_runner_row.envelope (:44-50) -- record_type "trade", ticker, taker_side, count_fp, yes_price_dollars /
no_price_dollars, created_time, response_end_ts -- and tape_fill_adapters.from_s341_trade (:110-120), whose _normalize requires taker_side in ("yes", "no") (:85-90); (h) S397_spec.md AMENDMENT 3(a)
and AMENDMENT 8: the Polymarket trade row carries side and outcomeIndex and NEVER taker_side, so its aggressor mapping is unverified.

CHANGE (owned files: NEW scripts/platformkit/execution/fill_realism.py, NEW fill_realism_classify.py, NEW tests/platformkit/execution/test_fill_realism.py, NEW test_fill_realism_classify.py, NEW
tests/platformkit/execution/fixtures/s411_boundary_books.jsonl, s411_boundary_trades.jsonl, s411_boundary_state.jsonl, memo -- every landed module imported and byte-identical to master, none edited,
nothing wired into a runtime):
1. fill_realism_classify.py (<= 300 LOC): the state-change classifier ONLY -- no estimator, no markout arithmetic. Each fill is labelled state_changed / no_state_change / state_unavailable by whether
   a state row differing in content from the previous ACCEPTED one is available, ordered by response_end_ts receipt and never api_ts, inside a declared window around fill_ts; a refused or None receipt
   never resets the previous row; a row available only after the window is invisible.
2. fill_realism.py (<= 300 LOC): CLI --books --trades --state --ttl-s --window-s --out; an absent --ttl-s refuses (no default). Drives the landed chain (capture_book_adapter -> quote construction from
   the observed book only, anchor None through make_quotes_reserved -> simulate_fills -> summary_strict once per class) over WHOLE shards and emits counts only: (i) fills_credited total, by fill_basis
   (through / touch_queue), by side and by queue multiplier (1, 2, 4, 8 -- the unmultiplied 1 always present, the headline the MINIMUM over the grid); (ii) fills_refused_by_reason with the landed
   diagnostic keys verbatim (book_time_invalid, book_size_invalid, fee_input_invalid, quote_submit_ts_invalid, quote_cancel_ts_invalid, replacement_refused, duplicate_trade_ids, unscored_prints,
   print_time_invalid, scored_prints, all_prints_unscored) plus this row's own unknown_queue, queue_not_depleted, outside_quote_life, price_above_quote, poly_side_unmapped; (iii)
   queue_ahead_at_submit in fixed buckets (0; 1-9; 10-99; 100-999; 1000+; UNKNOWN = 1000000) per multiplier, the unknown-queue instant count printed beside EVERY fill-conditional number and the writer
   refusing to emit one without it; (iv) markout by state-change class: per horizon per class the landed fields n, n_clusters, mean_units, ci_95_units, verdict, largest_single_game_share,
   leave_one_game_out_range_units in probability points, counts only -- no cross-week pooling, no interval read as a result; (v) partial fills as filled/requested buckets, quote-life expiry counts at
   ttl_s 5 AND 30 side by side, replace and cancel counts, and cancel REJECTION emitted as unmodelled_cancel_rejection with the literal value UNMODELLED, never a number. Strict-int counts; Decimal
   prices and sizes; times only through parse_venue_time; order-independent over files and rows; first and last receipt timestamps and the total row count printed beside the totals.
3. Fixtures and tests. The tracked real pair tests/platformkit/execution/fixtures/s341_real_snapshots_2026-09-21.jsonl (30,974 bytes) and s341_real_trades_2026-09-21.jsonl (5,184 bytes), plus
   s389_native_books.jsonl (5,598) and s389_native_state.jsonl (790) for the classifier, drive the end-to-end test; the s411_* fixtures are constructed from those real row shapes and cover boundaries
   only. One test closes each false-PASS risk: (1) fills inflated by the 30 s reservation default instead of the declared 5 s -> an absent --ttl-s refuses and the fixture run prints counts at 5 s and
   at 30 s side by side; (2) unknown-queue instants dropping out silently -> an absent touch size yields zero fills AND a counted unknown_queue, and a fill-conditional number without that count
   refuses; (3) through-credit at or before the placement receipt -> a print stamped exactly at arrival and one before it are both refused; (4) head-slice sampling -> counts span the whole shard and
   the printed first / last receipt timestamps and row count are asserted; (5) look-ahead in a class label -> a state row whose response_end_ts follows the window is invisible and appending later
   state rows changes no earlier label; (6) a Polymarket trade given a YES aggressor by a guess -> every such row is refused and counted poly_side_unmapped with zero Polymarket fills; (7) reporting
   only the friendliest multiplier -> all of (1, 2, 4, 8) present and the headline equals the minimum fill count over the grid; (8) duplicate trade ids double-crediting -> a repeated trade_id
   increments duplicate_trade_ids and credits one fill; (9) a markout interval read as a result -> no verdict word outside the per-class count block and no cross-week aggregate; (10) order
   dependence -> shuffled file and row order give identical counts.
4. Memo docs/evidence/harness/S411_fill_realism_2026-09-22.md: every input named with full path and byte size, every headline count recomputable by the verifier from the artifact, the orchestrator's
   real run on the 2026-09-22 Kalshi shards recorded as counts verbatim, and a closing NOT VERIFIED list naming cancel rejection, real order-ack latency, documented matching priority (S399 not
   verified), any observation of our own queue position, and the Polymarket aggressor mapping.

CONTROLS: PREPARE only -- the builder reads no real archive, runs no capture and touches no path under data/; pure functions plus one CLI; no network; no runtime activation and no caller added; every
constant declared with its source line, none fitted; the frozen S362 qualification constants and every landed module stay byte-identical; the orchestrator alone runs the 2026-09-22 shards and records
the counts. ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC per new module; ASCII; contract Q6 vocabulary (a size is a unit count; a markout is a measurement in probability
points with an interval); the artifact is COUNTS ONLY and prints no fee-netted headline and no interval as a result; memo ends with NOT VERIFIED.
