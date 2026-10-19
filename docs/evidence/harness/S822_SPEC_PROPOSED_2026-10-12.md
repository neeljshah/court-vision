# S822 specification (PROPOSED) - polymarket steady-state props cadence
PAPER ONLY. Capture scheduling only: no orders, no venue writes, no pricing change; coverage / freshness language only.
Read-only spec lead (Sonnet), 2026-10-12 ~16:3xZ. No code written, no python/pytest/replay run; every claim is a grep/sed read.
Register row: S822 (docs/evidence/HARNESS_GAPS_2026-09-03.md). Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B1-B10, Q1-Q8.
Template: docs/evidence/harness/S787_EXTENDED_FOCUS_SPEC_2026-10-07.md. Builds on S795 (b) (docs/evidence/harness/S795_RESULT_2026-10-12.md "Scope (b)").
PREMISE VERDICT: TRUE WITH ONE CORRECTION. The cost is real and unaddressed by S795 (b) (S795_RESULT lines "What (b) does NOT fix"). But
the "player props" label is only half the derivative set: besides player-stat markets there are alt-line ladders (team totals, O/U
ladders, first-5 / first-inning lines) that are NOT player props. The classifier must therefore be three-way safe: unknown = core.

## 1. Premise (fresh reads)
1. select_due (polymarket_live_sources.py:159-194) groups units by game key (:165-170), classifies each unit with classify_event_state
   (:131-157: live -> scope.LIVE_CADENCE_SEC 10 s, pregame (start within 24 h) 120 s, idle 600 s; polymarket_scope.py:57-60), marks a GAME
   eligible when ANY of its units is non-idle (or scheduled) and `moment - last_polled[event_ticker] >= cadence` (:176-179), sorts by
   priority (:181-186), takes `[:budget]` GAMES (:187), and returns EVERY unit of each chosen game (:194, `games[key]`). So the 20 cap
   (polymarket_live_capture.py:28 MAX_UNITS_PER_TICK = 20, passed as `budget` at :129) counts games, not markets, and a chosen game
   brings all of its markets whether or not each is due. That is the whole cost: a live game's 10 s cadence is far below the tick
   wall, so every market is "due" every tick.
2. The tick loop (capture_once, polymarket_live_capture.py:~160-185) per returned unit: optional meta (meta_store.due), 2 book GETs,
   _group + drain_trades (up to TRADE_PAGE_BUDGET = 5 pages of 100, polymarket_live_trades.py:22-23), then `state["last_polled"]
   [unit["event_ticker"]] = clock()`. Per market about 4.2 governed requests (S795 memo: meta + 2 books + ~1.2 trade pages).
3. Measured weight (S795_RESULT step 0, 10-07 S793 trace, no python this lane): 301 markets of ONE game mlb-cle-cws-2026-10-07 = 27
   main + 274 player props (91%); 1,256 calls in 600 s (~2.1 req/s); un-staged first tick 1,881 s. Core-only would be 27 x 4.2 = ~113
   requests = ~54 s for that game; props add ~1,150 requests = ~550 s. Steady-state tick stays ~31 min today (row text).
4. Market TYPE is readable from the question string (archived market_meta rows, data/cache/ingame_books_local/polymarket/mlb/):
   moneyline 'Los Angeles Dodgers vs. Milwaukee Brewers'; spread 'Spread: Los Angeles Dodgers (-1.5)'; total '<A> vs. <B>: O/U 7.5';
   team total '<Team> Team Total...'; first-5 lines '1st 5 Innings Spread' / '<A> vs. <B>: 1st 5 Innings O/U 3.5'; first-inning
   'Will there be a run scored in the first inning?: <A> vs. <B>'; PLAYER PROP 'Ethan Salas: Hits + Runs + RBIs O/U 3.5' (10-07
   shard: 2,973 of the first 4,000 market_meta rows matched a stat/player pattern; 10-12 shard sample: 0, a different slate).
   The repo already owns the grammar: cross_venue_link.classify_market (cross_venue_link.py:215-235: spread prefix, ': O/U' mark,
   exact '<label0> vs. <label1>' moneyline) - seal-pinned S490 addendum file, so READ for shape, do NOT import or edit it.
   The gamma market dict (unit["market"], polymarket_live_sources.py:90-110) may carry a venue market-type field, but no archived row
   shows one (grep sportsMarketType in the 10-12 shard: 0 hits, and archived rows are CLOB meta, not gamma). UNESTABLISHED by
   reading; the builder greps a captured gamma fixture before trusting it, and falls back to the question grammar.
5. Governor: the request rate is enforced in client.get via the AIMD governor (client.aimd.stats_10min used at polymarket_live_capture.py
   _publish ~:196). select_due and the warm-up (polymarket_warmup.py docstring "The governor and the request RATE are untouched") never
   touch it; this row does the same.
6. Readers of prop rows: cross-venue linking reads MONEYLINE only and counts totals/spreads out (cross_venue_link.py:1,215-235,258:
   "totals markets are counted out and no moneyline counts moneyline_absent"). fill_realism.py:99-102 counts every polymarket trade as
   poly_side_unmapped / unscored_prints, so props never feed a score. coherence_scanner_inputs.py only reads fee constants (:88-89).
   No reader of player-prop rows was found under scripts/platformkit/execution or ingame; the archive-bound test and heartbeat fold
   (test_polymarket_archived_ids_bound.py, test_polymarket_heartbeat_ts.py) read counts and ids, so they must stay green. UNESTABLISHED:
   the frontend / site exports (grep scripts/platformkit/frontend and webapp readers of the polymarket shard) were not walked.
7. Existing pattern to copy: polymarket_warmup.py (77 LOC) is a pre-select_due admit filter with a state counter and a heartbeat
   `counters()` merged at polymarket_live_capture.py:228. polymarket_live_capture.py is at 300 LOC (no room), polymarket_live_sources.py at 194.

## 2. Constructs (testable)
C1. NEW polymarket_props.py (`kind(unit) -> 'core'|'prop'`): 'prop' ONLY for a player-stat market (question '<Person>: <Stat> O/U <n>' or the
    venue market-type field if proven); moneyline, spread, total, team total, period lines, first-inning, extra-innings and anything
    unrecognised = 'core'. Test table from the real question strings in item 4; every unknown string -> 'core' (fail-safe = today's behaviour).
C2. `admit(state, units, now, moment) -> units`: a prop unit is DROPPED from the tick when it HAS been polled and
    `moment - state["last_polled"][unit["event_ticker"]] < PROPS_CADENCE_SEC[game state]`; core units, never-polled props, and props of
    idle games pass untouched. PROPS_CADENCE_SEC = live 900 s, pregame/imminent 1,800 s (see C7). No new persisted state: last_polled is
    already written per polled unit. Dropped props never reach select_due, so they cost no game slot and no game ageing (the S795 (b)
    adversarial finding A applies identically: filter BEFORE select_due, never after).
C3. Order in `_due`: props.admit first, then warmup.admit (cold-start staging still governs never-polled props), then select_due.
    A never-polled prop of a live or imminent game is polled on its first tick (warm-up already lets live / imminent through).
C4. Counters: state["props_counts"] reset each tick (NOT state["book_counts"], which warmup.admit resets at its start); heartbeat adds
    props_deferred / props_polled per sport, appended after book_polled, via a `counters(state, sport)` merged next to
    polymarket_live_capture.py:228. props_polled counts prop units returned by select_due; props_deferred counts units dropped by C2. Extend the 1d
    heartbeat fold regex exactly as S795 did.
C5. Archive row schema and bytes unchanged: no new record_type or field, only fewer calls; the same writer paths. Test: for a
    tick where nothing is deferred (cadence 0 or first tick) the written rows are byte-identical to the pre-change run.
C6. Governor and request RATE untouched: no edit to client / aimd / MAX_UNITS_PER_TICK / scope cadences; a test asserts the diff
    touches neither file and the AIMD constants are equal.
C7. Cadence rationale (from the data): a live game's core set is ~27 markets (~55 s of governed calls) and its props ~274 (~550 s).
    Props every 900 s means a prop is re-polled about every 15 min (a few ticks once ticks are ~5 min) against today's ~31 min: strictly
    fresher than today AND the tick wall falls to core cost. Pregame / imminent props at 1,800 s because their lines are static far
    from start. Both are knobs (constants, one place); the measured proof sets the final value. If the first measured warm tick is
    still above 600 s, the builder lowers cadence demand (more deferral), never touches the rate.
C8. Trade-drain safety: a deferred prop also defers its trade pages. drain_trades is offset/watermark based (live_shadow reads
    group.backfill; polymarket_live_trades.py:181-215) so a later poll resumes, but a prop with more than TRADE_PAGE_BUDGET x 100 = 500
    prints in one cadence window would leave a backlog. Test: a prop with 600 prints over a 900 s window drains across two ticks with no
    dropped id (existing trades tests show the contract); counters for any backlog stay visible.

## 3. Files owned (when built)
New: scripts/platformkit/ingame/polymarket_props.py, tests/platformkit/ingame/test_s822_props_cadence.py.
Edit (minimal): polymarket_live_capture.py `_due` (one line, and the counters merge at :228; LOC stays at or under 300: net zero
by folding the existing S795 comment lines) and the 1d fold regex file S795 touched (grep 'book_deferred' in tests/ and the fold module).
NOT touched: polymarket_live_sources.py (select_due unchanged; the row text said "inside select_due" but the pre-filter keeps that
file and its tests byte-stable), client/aimd, scope, archive writers, any seal-pinned file, data/registry/.

## 4. Tests (per file, named; never the full suite)
- python -m pytest tests/platformkit/ingame/test_s822_props_cadence.py -q (C1 table, C2 drop rules, C3 order, C4 counters, C5 parity, C8 drain)
- python -m pytest tests/platformkit/ingame/test_s795_book_warmup.py -q (warm-up unchanged)
- python -m pytest tests/platformkit/ingame/test_polymarket_live_capture.py -q
- python -m pytest tests/platformkit/ingame/test_polymarket_heartbeat_ts.py -q
- python -m pytest tests/platformkit/ingame/test_schedule_pointer_startup_union_1d.py -q (byte parity, heartbeat fold)
- python -m pytest tests/platformkit/ingame/test_polymarket_archived_ids_bound.py -q (75 s; run alone)

## 5. Measured proof (recipe; NOT run here)
Same recipe as S793 / S795 step 0: the scratchpad tracer (S793_POLYMARKET_HOT_PATH_2026-10-07.md "Tracer": one process, live read roots,
OUTPUT ROOT = scratch with COPIES of the 10-07 shard so the live shard and lock are untouched), 600 s run, requests-body table for
call counts, awk classification of rows appended to the copy. Run twice on identical inputs: BEFORE = master at the S795 (b) tip,
AFTER = the S822 branch. Report: (a) calls per 600 s by kind (meta / book / trade) and by market kind (core / prop); (b) wall per
tick, in particular the first full warm tick and the second tick (the second is where deferral shows: props polled in tick 1 are
skipped until 900 s); (c) props_deferred / props_polled in the heartbeat; (d) rows written per record_type, unchanged schema; (e)
request rate (calls / elapsed) within noise of ~2.1 req/s. Gate: hold until a night has finished, free RAM >= 2.5 GB, no focus hour
(feedback: focus-hour quiet rule, night RAM findings). Adoption is a polymarket-capture restart only (owner or session cron window).

## 6. Risks / landmines
- A misclassified core market deferred (moneyline read late) is the real harm: C1 fails safe to core; keep the table-driven test.
- The 10-07 slate (player props) differs from the 10-12 slate (alt ladders): measure on 10-07 inputs as the row says, and ALSO report
  the 10-12 shard's core/prop split so the cadence is not tuned to one slate.
- last_polled is process memory: a restart re-polls every prop once (cold start; warm-up staging covers far games).
- Held props leave gaps in the prop series: coverage language only; no reader consumes them today (item 6), but state it in the receipt.
- polymarket_live_capture.py is at 300 LOC; a net-positive edit there breaks the LOC pin: move code to polymarket_props.py.

## 7. Verifier contract
Contract tier: A and B1-B10 on the diff, Q1-Q8 on the tests; confirm select_due, client/aimd and archive writers are byte-unchanged
(git diff --stat), counters appended AFTER book_polled, and the proof receipt carries both traces.
Adversarial tier mutants (each must be killed): (m1) drop applied AFTER select_due (starves games / burns slots); (m2) unknown question
-> 'prop'; (m3) moneyline classified as prop; (m4) cadence compared with `>` vs `>=` at the boundary; (m5) never-polled prop deferred;
(m6) props_counts written into book_counts (reset by warmup.admit); (m7) cadence keyed on wall clock instead of the injected moment;
(m8) deferral also drops the unit's trade drain AND its watermark advance (lost prints); (m9) governor / MAX_UNITS_PER_TICK edited;
(m10) archive row gains a field; (m11) idle-unscheduled prop pulled into the poll set; (m12) wording drift to edge / ROI terms.
