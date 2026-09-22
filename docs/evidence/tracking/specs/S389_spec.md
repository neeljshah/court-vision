GAP S389 | sport all captured | worktree harness-h49 (master-based) | log cx_s389_capture_bridge
# Native capture-to-qualification bridge (design: ASTRA_ROUND14 row 3)

SINGLE PROBLEM: the forward replay (row S362) qualifies games from inputs shaped by its own fixtures, while the production capture
now writes different native evidence: trades carry backfill_open + a backfill id with a trade_backfill_closed record (row S374),
the state capture links games by game_key (rows S352 / S358), and the supervisor (row S376) writes host_gap records in its own
journal. Until the replay consumes those natively, a daily qualification would either fail every game or, worse, pass one on
incomplete evidence (treating the newest trade time as tape completeness).

BINDING BEFORE-CONDITION: quote, from master, (a) scripts/platformkit/execution/forward_replay_io.py: how it reads books, state,
trades and gaps today (field names, incl. any `tape_watermark`), (b) scripts/platformkit/ingame/local_capture_runner_trades.py:
the exact records it writes (trade with backfill_open / backfill id, trade_gap, trade_backfill_closed), (c)
scripts/platformkit/ops/capture_supervisor.py: the host_gap record shape and journal path, (d) scripts/platformkit/ingame/
game_market_link.py: link_game. REAL ROW KEYS: snapshot rows as in the S386 spec; state rows as in the S380 spec.

CHANGE (owned files: NEW scripts/platformkit/execution/forward_capture_bridge.py, forward_replay_io.py, forward_replay.py, NEW
tests/platformkit/execution/test_forward_capture_bridge.py, memo; the qualification module and its frozen constants are NOT
touched):
1. forward_capture_bridge.py (<= 300 LOC): `load_native(books_paths, state_paths, trade_paths, supervisor_journals, schedule) ->
   NativeEvidence` that (a) links each scheduled game to its state rows by exact game_key through the landed linker (ambiguous or
   absent linkage -> LINKAGE_INVALID for that game, counted), (b) reads book snapshots through capture_book_adapter only, (c)
   reads trades and establishes TAPE COMPLETENESS through the window ONLY from trade_backfill_closed records (or a trade_gap that
   declares the gap): the newest trade time is NEVER a completeness endpoint; an open backfill at window end is TAPE_INCOMPLETE,
   (d) merges host_gap windows from every supervisor journal and trade_gap windows into the gap list the qualification reads
   (any positive overlap disqualifies, as frozen), (e) counts everything it refuses. Strict-int counts; Decimal sizes; times only
   through parse_venue_time; order independence over files and rows.
2. forward_replay_io.py / forward_replay.py: `--native` mode uses the bridge; the CLI gains `--trades` and `--supervisor-journal`
   inputs; the non-native fixture path stays byte-identical (test).
3. Tests: native fixtures built from the REAL row shapes (copy at most 30 rows of each kind, verbatim, into
   tests/platformkit/execution/fixtures/s389_native_*.jsonl -- public game state and venue quotes only); a scheduled game whose
   backfill never closed -> TAPE_INCOMPLETE; a game whose newest trade is inside the window but backfill open -> still
   TAPE_INCOMPLETE; a host_gap overlapping the window by 1 ms -> HOST_GAP; ambiguous linkage -> LINKAGE_INVALID; both landed
   S362 test files pass unchanged.
4. Memo docs/evidence/harness/S389_capture_bridge_2026-09-22.md.

CONTROLS: construct tests only, no network, no real archive run by the builder beyond copying the fixture rows named above.
ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.
