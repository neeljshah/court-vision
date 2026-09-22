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

AMENDMENT 1 (2026-09-22 23:0xZ; binding; the first codex build lane stopped correctly on a contradiction: CHANGE 1(i) defines the
lag from the first "snapshot" receipt at or after scheduled_start - 120 (a sole receipt at start - 60 yields lag -60), while
CHANGE 2 says zero IN-WINDOW rows yield 'no lag'). RULING: two windows, two names. The ADMISSION window is [scheduled_start - 120,
scheduled_start + WINDOW_S): the first record_type "snapshot" receipt inside it opens the window and defines focus_open_lag_s
(negative when it precedes scheduled_start); no "snapshot" receipt inside it -> no_focus_receipt_in_window, lag ABSENT. The
IN-WINDOW gap set stays [scheduled_start, scheduled_start + WINDOW_S). A game whose only focus receipts precede scheduled_start
therefore reports a (negative) lag AND an empty in-window set (quantile_absent incremented, meets_frozen_values all false), with
the distinct reason code in_window_focus_empty -- never no_focus_receipt_in_window. The test list changes to match: 'a receipt at
scheduled_start - 60 opens the window, yields lag -60, in-window set empty -> quantile_absent + in_window_focus_empty'; 'zero
"snapshot" receipts in the ADMISSION window -> no_focus_receipt_in_window and no lag'. The 120 s pre-open allowance is a declared
constant of this module (PREOPEN_S = 120, named in the artifact), not a frozen bar.

AMENDMENT 2 (2026-09-22 23:1xZ; binding; VERBATIM FACTS from the orchestrator's first real run of the built candidate, from
the worktree, over the real Kalshi mlb shard (323,207,242 bytes at run time) with the committed 2026-09-22 full selection (six
games) and its capacity note, run at about 23:09Z while the first two games were in progress; exit 0, wall clock about 2 s).
PER GAME: TORBAL (22:35Z start) focus_open_lag_s -118.755464, in-window receipt_count 382 (gap_count 383) with quantiles
median 5.173227 / p95 5.868722 / max 1547.427332 s (median and p95 meet the frozen values, max does not -- the window was still
in progress, so the trailing boundary gap to the window end is inside the max), covered_seconds 1908 of 3600; MILPHI (22:40Z)
lag -117.205747, receipt_count 328, median 5.171961 / p95 5.801679 / max 1852.003233, covered 1638; STLPIT and CLEBOS (unserved
by the capacity subset) in-window receipt_count 0, quantile_absent, covered 0, out-of-window gaps median about 249-256 s;
CINATL (23:15Z) and MIACHC (23:40Z) not yet started, in-window 0; first_seen_lag_s about -81,000 to -85,000 s for every game
(the markets were discovered the previous evening). REASON COUNTS (mlb): capacity_subset_excluded 3, no_focus_receipt_in_window 4,
two_per_hour_refused 6; the heartbeat snapshot (single_snapshot) copied verbatim: scheduled_games_total 3, scheduled_admitted 2,
scheduled_not_admitted 0, error_counters duplicate_trade_id 133911 / missed_deadline 1022 / schedule_refused 18. PROFILE
focus_tick_s 5, sha256 5bb818074c5083049e804bffda59c2b5b701706048983d32bbb313120ea3607c. PROGRAM FACT: for a SERVED game the
focus window opens about two minutes before scheduled_start and holds a 5 s cadence; an UNSERVED game gets no in-window
receipt at all -- the capacity subset, not the scheduler's timing, is what a FAIL on S390 will name; the S390 retrospective run
over this date must be made after every scheduled window has ended (the last, MIACHC, ends 2026-09-23 00:40Z) so that the
trailing boundary gap is real. The memo records these counts verbatim as the first real run; the verifier judges whether the
in-progress-window case must be labelled in the artifact (window_in_progress) and whether two_per_hour_refused counting every
game is the capacity rule as capture_scheduler.py implements it.

AMENDMENT 3 (2026-09-22 23:4xZ; binding; from the astra round-1 critique on the build, read with AMENDMENT 2's real run). (a)
WINDOW STATUS IS LABELLED: --as-of is a required zoned instant recorded in the artifact with each game's window bounds; each game
carries status not_started / in_progress / completed; for an in_progress window the trailing boundary gap is reported separately
(trailing_boundary_s) and the max quantile is given both with it (max_s) and, when completed, without it (max_completed_s); every
frozen comparison and the 3600 s denominator stay as S362 counts them. (b) MIDNIGHT: a window that crosses UTC midnight reads the
date's shard AND the next day's shard for the ticker (both paths and byte sizes recorded), so the 23:40Z game's receipts after
00:00Z count; a missing next-day shard for a crossing window is counted next_day_shard_absent, never silently zero. (c) The
heartbeat snapshot keeps its file mtime (heartbeat_captured_at) and is labelled source_heartbeat_counters, unrelated to this
audit's denominator. (d) The memo records AMENDMENT 2's first real run verbatim and labels two_per_hour_refused as a
full-selection capacity DIAGNOSTIC (it does not establish that the running scheduler refused six games; the scheduler's own
selection is visible only through the served subset and the heartbeat). NOTED: every line is JSON-decoded before the ticker
filter, memory holds one decoded row plus the selected timestamps (not constant memory); fetch_error rows may carry a book but
are not focus evidence.

AMENDMENT 4 (2026-09-23 00:5xZ; binding; from the sol round-2 REJECT of fix 1b and the astra round-2 ACCEPT notes). (a)
NON-FINITE STARTS AND A TORN ARTIFACT -- MEASURED: a schedule row whose scheduled_start is NaN (or Infinity) was counted
scheduled_start_unparseable 1 but the float was RETAINED in the audit dict, so the writer failed inside json.dump ("Out of range
float values are not JSON compliant"), exited 3 and left 1,076 characters of incomplete JSON on disk (focus_window_admission.py:117,
:253). RULING: a scheduled_start that is not a string parseable by parse_venue_time is REFUSED as a row -- counted, its raw value
recorded as TEXT (repr), never carried as a float; the artifact is written atomically (temp file in the output directory, flush +
fsync, os.replace) so no failure can leave a partial artifact, and a serialization failure is a REFUSED status naming the reason
with the previous artifact untouched; a test plants NaN and Infinity and asserts both the refusal and that the output path is
either absent or complete JSON. (b) THE MEMO'S NOT VERIFIED IS A LIST -- explicit entries: master-side test execution, the revised
real-shard run, AMENDMENT 2's measurements (transcribed, not reproduced). (c) HEARTBEAT ABSENCE AND AGE (astra notes): an absent
heartbeat file yields an explicit heartbeat_absent reason (never a silent empty list); heartbeat_age_s = as_of minus the file
mtime is reported as Decimal text beside heartbeat_captured_at (reported, never thresholded -- the audit's denominator is
unrelated). Everything else from fix 1b byte-identical in behaviour (the [start, end) boundary, the once-counted rollover
duplicate, the absent quantiles for a not_started window, the imported frozen values).
