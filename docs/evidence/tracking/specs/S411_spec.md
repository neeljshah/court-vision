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

AMENDMENT 1 (2026-09-23 16:2xZ; binding; orchestrator ruling on the build lane's finding, VERIFIED on master: venue_fees.py
:71-180 computes every fee through float (fee_kalshi_maker(contracts: float, price: float) -> float), quote_engine.py:82
returns float(fee), tape_fill_sim.py:252 serializes fee_units=float(fee_units), markout.py:29 converts through float). The
landed fee chain is float end to end and venue_fees.py is OWNER-ONLY (never edited by a lane); the candidate therefore refused
every fill's fee as fee_decimal_unavailable and produced no markout block. RULING -- measurement proceeds with a named, exact
guard instead of a blanket refusal: a fee the landed chain returns as a float is ACCEPTED only when (i) math.isfinite, (ii)
0 <= fee <= 1 in probability units, and (iii) Decimal(repr(fee)) round-trips EXACTLY with at most six decimal places (the
venue's fee schedule is cent-granular; a float that does not round-trip is refused as fee_float_inexact and counted). Accepted
fees are converted through Decimal(repr(fee)) once, at the boundary, and every downstream arithmetic in this row is Decimal;
each such fill is counted under fee_source_float_exact, printed beside every markout number, so a reader always sees how many
fees came through the float chain. A fee of exactly zero from the chain is still refused (a zero, negative or non-finite fee
is never trusted). The markout block is then emitted per class per horizon as the spec's CHANGE 2(iv) requires. The Decimal
fee chain itself is a SEPARATE row (S422, proposed the same day: venue_fees as a PROPOSED diff for the owner, quote_engine /
tape_fill_sim / markout as the row's owned changes); S411 does not wait on it. The memo names this boundary in NOT VERIFIED
until S422 lands. ORCHESTRATOR REAL RUN: the 2026-09-22 MLB shards (books and trades from the same Kalshi shard, state from the
v2 root) are run by the orchestrator at --ttl-s 5 and --window-s 30 and the counts appended to the memo VERBATIM under
'Orchestrator archive run' with the full paths and byte sizes; the fix lane preserves that section byte for byte.

AMENDMENT 2 (2026-09-23 16:3xZ; binding; MEASURED by the orchestrator's real run of the build candidate: python -m
scripts.platformkit.execution.fill_realism --books <kalshi mlb 2026-09-22 shard, 359,982,871 bytes> --trades <the same shard>
--state <state v2 mlb 2026-09-22 shard, 8,369,460 bytes> --ttl-s 5 --window-s 30, started 16:13:28Z). The process reached a
5,670 MB working set at 16:2xZ (measured with Get-Process; the box has 15 GB and the codex lane gate refuses below 2,500 MB
free) without finishing, and was STOPPED by the orchestrator at 16:3xZ; no artifact was produced. The candidate materializes
the whole shard as Python objects. RULING: memory is BOUNDED by construction -- the tool processes one market (ticker) at a
time: it streams the books shard once to build a ticker -> byte-offset index (or one streaming pass per ticker over a
pre-filtered temporary file), then for each ticker loads only that ticker's snapshot rows, its trade rows and the state rows of
its linked game, calls the landed chain (make_quotes_reserved -> simulate_fills -> summary_strict) for that market alone, folds
the counts into the totals, and releases the rows; the per-ticker results are folded in ticker order so the artifact is
byte-identical under any input order (tested). The tool declares a memory ceiling in the memo and the real run records the
peak working set (measured, not estimated) beside the wall time and the row count; a run that exceeds the declared ceiling is
a refusal named memory_ceiling_exceeded, never a silent success. The whole-shard totals, the first and last receipt timestamps
and the row count remain printed beside every total as CHANGE 2 requires. Counts must be identical to a single-pass
implementation on the construct fixtures (a differential test pins it).

AMENDMENT 3 (2026-09-23 18:3xZ; binding; from round 1 on fix 1b -- codex sol REJECT (three blockers) and Opus tier 2 ACCEPT WITH
CORRECTIONS (six corrections); the orchestrator's 28-minute real run stands as the BEFORE record). RULINGS. (1) THE LANDED
ESTIMATOR IS CONSUMED, NEVER REIMPLEMENTED: fill_realism_markout.py:39 discards summary_strict's result and recomputes the
statistics in _numbers / _render (an injected mean_units sentinel never reached the artifact). RULING: summary_strict is called
once per class per horizon exactly as CHANGE 2(iv) says and its fields (n, n_clusters, mean_units, ci_95_units, verdict,
largest_single_game_share, leave_one_game_out_range_units) are emitted UNCHANGED; the row's own Decimal work stops at the fee
guard and the per-fill inputs it hands the landed function; the S422 facade (LANDED 95bb1253a: venue_fees_decimal,
markout_decimal) may be imported for per-fill Decimal markouts reported BESIDE the landed summary, never in place of it. (2) THE
BLOCK IS markout_by_class with the THREE classes populated (state_changed, no_state_change, state_unavailable) per horizon --
the code emitted markout_by_state and the memo recorded markout_by_class null. (3) EVERY REAL FILL WAS state_unavailable
(state_comparison_unavailable == n_fills at both TTLs) -- a MEASURED result the memo states as such, with the cause NAMED: the
classifier's fill-to-game join must use the LANDED keyed linkage (the committed schedule's game_key -> ticker mapping through
forward_capture_bridge, as S404 / S409 attest it), and the memo reports fills_linked / fills_unlinked with the reason per unlinked
fill; if the join is right and the state window still holds no row, that count is the finding. (4) fee_zero INCREMENTS ARE
FILLS: the landed cumulative cent ceiling legitimately yields a 0.00 increment on a small fill (S422 AMENDMENT 1(b)); refusing
them biases the markout sample. RULING: a zero increment from the landed cumulative fee is ACCEPTED as a zero-fee fill and counted
fee_zero_increment; fee_zero (refused) is reserved for a schedule fee of zero at an interior price on a positive count, which the
landed twins never return. (5) fills_refused_by_reason is SPLIT BY UNIT into named blocks: accepted_outcomes (fee_source_float_exact,
fee_zero_increment), input_counts (input_prints, scored_prints, replace_count, input_role_filtered), quote_print_pairs
(outside_quote_life, price_above_quote, queue_not_depleted, quote_already_filled), fill_state_rows (state_after_window and kin) --
each block declares its unit; unknown_queue and n_intents are reported ONCE at market level and referenced, never repeated per
class; cancel_count is renamed quotes_placed (filled quotes included, as the memo already declares). (6) MEMORY: a
memory_ceiling_exceeded refusal still writes <out>.resources.json (peak, ceiling, row_count so far) before refusing. (7) THE
MEMO: absolute input paths with byte sizes; every stale 'NOT RUN' / 'not measured' claim removed; every helper module listed with
its byte size (fill_realism.py 16,556; fill_realism_classify.py 5,387; _io; _markout); the test that pinned the 'NOT RUN'
placeholder asserts the real-run fields instead; the real-run artifact is COMMITTED at docs/evidence/forward/fill_realism/
2026-09-22_ttl5.json with its SHA-256 (counts only; no price values) and the resources sidecar beside it. (8) The fix's real re-run
by the orchestrator (about 28 minutes) is the AFTER record; the headline minima (12 at ttl 5, 34 at ttl 30) are expected to
reproduce unless ruling (3) or (4) changes the fill set, and any change is explained by name.

AMENDMENT 4 (2026-09-23 18:4xZ; binding; MEASURED by the orchestrator's real AFTER run of fix 1c over the 2026-09-22 MLB shards from
the candidate worktree: 34 minutes wall, peak working set 639,451,136 bytes (under the 1,073,741,824 ceiling), exit 0, 201,666 rows,
window 30 s, grid ttl {5, 30} x size {1, 2, 4, 8}). WHAT THE RUN SHOWS (descriptive counts, the record for the memo): quotes_placed
44,668 per cell; credited fills 12 at ttl 5 (6 yes / 6 no, all 'through', all full) and 34-35 at ttl 30 (32 through / 2-3
touch_queue); quote_life_expiry 39,882 / 18,466; input refusals inconsistent_touch 4,367, one_sided_book 4,857, price_out_of_range
3,288, input_role_filtered 6,141 of 121,060 prints; queue_ahead_at_submit UNKNOWN 58,605 and 1000+ 31,390 (size 1); EVERY credited
fill is fills_unlinked / state_identity_missing with unlinked reason schedule_entry_absent -- no credited fill fell on any of the
six served tickers of the 2026-09-22 selection (the fills sit on EXTRAS markets, other games and the TB@NYY game-1 ticker), so
fill_state_rows.state_rows_accepted is 0 and every markout class over the served schedule has n 0. THREE DEFECTS, RULED:
(a) THE ARTIFACT IS NOT COUNTS-ONLY IN SIZE: 63,420,355 bytes, because markout_by_class emits a per-market block (14 horizon
fields, null CIs) for all 627 markets x 3 classes x 4 sizes x 2 ttls although only 2 markets carry any fill. RULING: a market
block is emitted ONLY for a market with n > 0 in that class; markets with n 0 are COUNTED (markets_without_fills per class) never
listed; market_context lists only referenced markets; the artifact stays under 1,000,000 bytes on this real day and a construct
test with 700 empty markets asserts the bound; the memo records the AFTER size. (b) STDOUT PRINTED THE WHOLE ARTIFACT (31,748,790
bytes): the program prints ONE summary line (row_count, fills per ttl, artifact path and bytes) and nothing else; a test asserts
the stdout length under 400 bytes. (c) RECORDED PATHS ARE ABSOLUTE (inputs[].path under the main checkout and the worktree):
the same ruling as S406 AMENDMENT 7 / S421 AMENDMENT 6 -- an optional --repo-root (default the checkout the module lives in),
every recorded path relpath with forward slashes, a path outside the root refused by name (path_outside_repo_root, exit 3, no
artifact), and the orchestrator's real runs carry --repo-root <main checkout> with the schedule read from the main checkout.
(d) THE LINK CAUSE IS NAMED PER FILL AND SUMMARISED: state_identity_missing already names the cause; the artifact adds, per
ttl, the count of credited fills on served tickers vs not-served tickers and the list of not-served tickers with fills (a
ticker list is bounded by the fill count, not the market count). (e) The memo states plainly that on 2026-09-22 the served
selection produced no credited fill under this quoting policy at either ttl, that the markout classes are therefore all n 0
over the served schedule, and that this is a MEASUREMENT of fill scarcity on the served games (a NEXT-ROW question: how many
served-game fills a week of capture yields), never a verdict on the state classes. The fix (1d) is re-run by the orchestrator
(AFTER-2) with --repo-root and the resulting artifact (under 1 MB) committed under docs/evidence/forward/fill_realism/ with the
fix-1b ttl5 record kept as the BEFORE artifact.
