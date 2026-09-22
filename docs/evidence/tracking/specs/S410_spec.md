GAP S410 | sport all captured | worktree harness-h68 (master-based) | log cx_s410_focus_window_admission
# Focus-window admission audit: when the window opened per scheduled game, and the receipt cadence inside vs outside it (counts only)

SINGLE PROBLEM: execution_paper_path step 3 (.planning/direction/execution_paper_path_2026-09-22.md section 4, "Capture cadence before
focus") records, measured on the real Kalshi mlb shard, 45-49 snapshot receipts per ticker for the WHOLE day, a median receipt gap of
257 s and one gap of 45,164 s. A scheduled game produces usable receipts only inside a focus window that opens, and NOTHING measures
whether one opened, when relative to scheduled_start, the cadence inside it, or why it did not. The remedy is a better capture.

BINDING BEFORE-CONDITION: quote from master (a) scripts/platformkit/ingame/capture_scheduler.py:123 `if start - 120 <= now < start +
3600: priority.append(game); ids[game] = row["game_id"]` -- the window opens 120 s before scheduled_start and closes 3600 s after it;
(b) capture_scheduler.py:113 `if any(b - a < 3600 for a, b in zip(starts, starts[2:])): raise ValueError("schedule exceeds two games
per hour")` -- the WHOLE schedule is refused, so the committed served file is a capacity SUBSET of the denominator of record
(docs/evidence/forward/schedules/2026-09-22_maker_forward.capacity_note.json: 3 served, 3 not_served of six games, its rule text citing
line 113); (c) capture_scheduler.py:116-135 (scheduled_games_total, scheduled_admitted, scheduled_not_admitted,
scheduled_market_unavailable, scheduled_pair_refused); (d) local_capture_runner.py:207-210 (`kind == "focus_books"` -> `_book`) and :63
(a focus receipt is appended with record_type "snapshot") against local_capture_runner_row.py:58 (the bulk class writes
"snapshot_bulk") -- an in-focus receipt is identifiable in the archive; (e) local_capture_runner.py:236 with
local_capture_runner_row.py:146-148 `heartbeat_path` -- ONE `_heartbeat.json` per sport, atomically replaced, so NO append-only
scheduler journal exists and the open instant must be inferred from the receipt stream; (f) scripts/platformkit/ingame/
forward_capture_profile.json (focus_tick_s 5, reservation_ttl_s 5, maximum_scheduled_games_per_hour 2); (g) scripts/platformkit/
execution/forward_replay_qualification.py:17-19 (WINDOW_S 3600, BOOK_MEDIAN_S / BOOK_P95_S / BOOK_MAX_S = 45 / 90 / 120) and :47
`nearest` (nearest-rank, no interpolation).

CHANGE (owned files: NEW scripts/platformkit/execution/focus_window_admission.py, NEW tests/platformkit/execution/
test_focus_window_admission.py, NEW tests/platformkit/execution/fixtures/s410_books.jsonl + s410_schedule.json, memo below):
1. focus_window_admission.py (<= 300 LOC): `--schedule <committed full-selection json> --capacity-note <json or absent> --books-root
   <dir> --date <YYYY-MM-DD> --out <json>`. Streams every shard line (never loads a shard into memory; the 2026-09-22 mlb shard is
   266,797,679 bytes); parses time only through scripts.platformkit.execution.venue_time.parse_venue_time; IMPORTS WINDOW_S,
   BOOK_MEDIAN_S, BOOK_P95_S, BOOK_MAX_S and `nearest` from forward_replay_qualification (never re-declared). Per schedule entry
   (sport, game_id, ticker, scheduled_start) it records: (i) focus_open_lag_s -- the first record_type "snapshot" response_end_ts for
   that ticker at or after scheduled_start - 120, minus scheduled_start (Decimal seconds as text; a negative value is legal and is
   reported as measured); (ii) two gap sets -- IN-WINDOW "snapshot" receipts with response_end_ts in [scheduled_start,
   scheduled_start + WINDOW_S) and OUT-OF-WINDOW, every other "snapshot" receipt for that ticker on the date's shard -- with
   consecutive-receipt gaps per set, the in-window set including the leading and trailing boundary gaps exactly as S362 Q-2 counts
   them, median / p95 / max through `nearest`, and an empty set yielding NO quantile and incrementing quantile_absent (never a zero);
   (iii) meets_frozen_values -- three strict bools per set, the imported comparisons, reported BESIDE the raw quantiles and never
   instead of them; (iv) covered_seconds -- whole seconds of the window lying within focus_tick_s (5, read from the profile and
   echoed with its SHA-256) after some in-window receipt, emitted with window_seconds 3600 as two strict ints, the fraction never
   pre-divided; (v) the reason a window did not open, as counted reason codes per game and per sport: capacity_subset_excluded (the
   ticker is in the capacity note's not_served list), two_per_hour_refused (three consecutive committed starts span < 3600 s under
   (b)), market_undiscovered (no row of ANY record_type for the ticker before scheduled_start; first_seen_lag_s recorded),
   no_focus_receipt_in_window, shard_absent, scheduled_start_unparseable; (vi) the per-sport `_heartbeat.json` counters
   (scheduled_games_total, scheduled_admitted, scheduled_not_admitted, error_counters) copied VERBATIM and labelled a single
   snapshot, never differenced and never read as a time series (per (e)). Output: strict-int counts, Decimal seconds as text, ASCII
   JSON, plus the NOTICE 'counts only; a window that did not open is a capture finding, never a reason to change a frozen value'.
   Refuses (exit 3, named reason) a missing schedule file, an unreadable books root, a schedule whose sports have no shard for --date.
2. Tests (construct fixtures only): a ticker with 5 s in-window and 300 s pre-window receipts (the two sets report different quantiles,
   both present); zero in-window "snapshot" rows -> no_focus_receipt_in_window and no lag; a ticker present only in not_served ->
   capacity_subset_excluded; a first row of any record_type after scheduled_start -> market_undiscovered with first_seen_lag_s;
   "snapshot_bulk" rows never counted as focus receipts; a receipt at scheduled_start - 60 opens the window and yields a negative lag;
   order independence over shuffled lines and over two shard files; streaming (monkeypatch open); every refusal.
3. Memo docs/evidence/harness/S410_focus_window_admission_2026-09-22.md: the before-condition quotes with file:line, the output
   schema, and the statement that no scheduler journal exists so the open instant is inferred from the receipt stream; NOT VERIFIED.

CONTROLS: PREPARE only -- construct tests; no network; no real shard run by the builder (the orchestrator runs it on the 2026-09-22
shards and the committed 2026-09-22 full-selection schedule and records the counts); never edit capture_scheduler.py,
local_capture_runner.py, forward_replay_qualification.py or any other landed module; never write under data/ or data/cache; never touch
the live captures, the capture output roots or any STOP file. ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC;
ASCII; contract Q6 vocabulary; memo ends with NOT VERIFIED.
