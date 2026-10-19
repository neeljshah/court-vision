# S550 execution-quality audit receipt -- build memo (2026-09-29)

Row S550 (mlb first, execution-quality ruler). Spec `docs/evidence/tracking/specs/S550_spec.md`
including AMENDMENT 1, which makes `docs/evidence/harness/exec2/prebuild/S550_prebuild_opus.md`
(B1-B7, N1-N11) binding. Worktree nba-harness-h221, base 4045f96c0. PAPER / ARCHIVE-READ ONLY;
calibration and execution-quality language only. Built without git (files on disk).

## Result

- Pure core `exec_quality_audit.py`, pure `exec_quality_audit_pool.py` (definitions, row parsers,
  pooling, the game bootstrap; B7), and `exec_quality_audit_io.py` (streaming loaders, identity,
  receipt + sidecar writers, CLI with `--books-root --state-root --sched-root --out-dir`).
- Per-file tests: `test_s550_exec_quality_audit.py` 36 passed (18 functions, parametrized);
  `test_s550_exec_quality_audit_real.py` 5 passed. Run one file at a time, never the suite.
- On the verbatim fixture the fresh-process receipt equals the r2 probe oracle exactly: every pool
  entry, every per-game census field and `stats`, `engine_construction`, `source_receipt_lag_s`;
  the renamed 3-game variant (the >= 3-game path) equals the probe's pools with numbers
  (bootstrap intervals included).

## BINDING BEFORE-CONDITION (re-run by the builder, 2026-09-29, inputs still growing)

Command: the r2 probe over `2026-09-22 2026-09-23 2026-09-24 2026-09-25 2026-09-26 2026-09-29`
(probe files unchanged, BOOKS/STATE pointed at the main checkout archive, a wrapper stream that
aborts above 400 MB RSS; stderr `peak_wset_mb 95.2`). Output:
- `tape_mo_print|60s` = mean 0.2363, ci90 [-0.1791, 0.6499], games 7, n 15654.0 (equals the spec)
- `touch|60s|fill` = mean 0.3358, ci90 [0.2503, 0.4241], games 8, n 2064.0 (equals the spec)
- `ev_play|before_receipt` = mean 0.5041, ci90 [0.4448, 0.5549], games 10, n 982 (equals the spec)
- `ctl|before_matched_lag` = mean 0.4306, ci90 [0.3938, 0.4667], games 10, n 1203 (spec 0.4273
  [0.3872, 0.4644]: moved because the 09-29 shards grew; B5 anticipated this)
- census: 22 served = mlb NO_LIVE_STATE 10, OK 8, TAPE_MISSING 2, NO_DEPTH 1, nfl TAPE_MISSING 1;
  engine reasons quoted 922 / stale_book 49 / state_change 61; source-to-receipt lag p10 12.934 /
  p50 21.228 / p90 33.311.

Builder smoke diff (NOT the acceptance measurement; the bracketed A / probe / B run stays with the
orchestrator): one module run immediately followed by one probe run over the same six days gave
every pool entry equal, every per-game census field and `stats` equal, engine table equal, lag
quantiles equal (12.948 / 21.235 / 33.304 at that moment); sidecar peak_wset_mb 95.6, elapsed
7.6 s. Output kept only in the builder scratchpad.

## Intentional definition changes vs the probe (each counted; none moves a pooled value on the week)

- (i) `no_final_row` is a per-game boolean field (the probe counted it in a per-game event counter).
- (ii) a print whose capture receipt precedes its created_time is counted `receipt_before_created`
  and KEPT (its negative lag stays in the lag quantiles, as in the probe).
- (iii) a truthy non-dict `state` is refused and counted `state_not_dict` (the probe would raise);
  whole-dict state comparison is unchanged.
- (iv) a trade whose `trade_id` is not a string (None included) is refused
  (`trade_unparsed_or_unknown_side`); the probe used the first None-id print.
- Counter splits only: unparseable timestamps are counted `timestamp_rejected` (the probe folded
  them into the snapshot / trade counters); `snapshot_bulk` -> `bulk_rows_ignored`, other record
  types -> `other_record_type_ignored`; a parsed row naming a different ticker / game_key ->
  `row_key_mismatch`.
- Stricter field refusals (the probe would accept or raise): bool, non-finite or non-numeric
  price / count / size / ladder values are refused (`snapshot_unparsed`,
  `trade_unparsed_or_unknown_side`); a trade price outside (0, 100) cents or a count <= 0 is
  refused `trade_price_or_count_out_of_range`. All zero on the fixture and on the smoke run.
- Shards are read only up to the byte size recorded in their identity (a line crossing it is
  counted `lines_skipped_partial`), so a growing live shard cannot make identity and content disagree.
- N6 (paired per-game difference) and N9 (definition-sha assertion) are CUT per AMENDMENT 1.

## Design notes the verifier should know

- Numbers stay binary floats (prices in cents rounded to 4 dp, `count_fp` as float) because the
  bar is exact numeric equality with the probe; Decimal arithmetic would change pooled values at the
  4th decimal in places. Validation (finite, non-bool, range) happens before any arithmetic.
- Every timestamp read from an input row goes through `venue_time.parse_venue_time`; the engine arm
  formats instants with `datetime.fromtimestamp(t, timezone.utc).isoformat()` exactly as the probe,
  and `quote_freshness.py:60` parses them inside the landed engine path (N2 exemption). Day keys are
  checked against `^\d{4}-\d{2}-\d{2}$` and advanced with `date(...) + timedelta(1)`.
- Stable sorts: snapshots and prints by time, state rows by receipt; exact-time ties keep file order
  (N10), so a same-instant pair of prints at different prices is order-dependent by design.
- Dedupe by trade_id runs before field validation, first copy in file order wins, scope = one
  (sport, day pair) load across all served tickers and both day files (N3).
- Seeds: join/engine grid Random(seed), event-control grid Random(seed + 1), control lags
  Random(seed + 2) with one draw per control instant, seed = crc32(ticker) % 100000 (B3); pool
  bootstrap one Random(7) per pool (B4). Python hash() is not used; receipts of two fresh processes
  with PYTHONHASHSEED 1 and 2 are byte-identical (tested).
- Receipt: strict JSON (allow_nan False), sort_keys, indent 1, ASCII, LF, temp + fsync +
  os.replace; no memory, elapsed time, host, path prefix or git sha. Paths are root-relative labels
  (`books/<sport>/<day>.jsonl`, `state/...`, `schedules/...`); schedules are hashed LF-normalised.
  Sidecar `<first>_<last>.resources.json` = peak_wset_mb, elapsed_s, python, platform.
- RSS guard: every 10,000 lines read the loader checks RSS (psutil, imported lazily) and exits 5
  with no receipt above 400 MiB. psutil is the only non-stdlib leaf of the import closure.
- Fixture edit: the orchestrator-built schedule fixture had one line (`selected_at`, a field no
  reader uses) that tripped the preflight bare-integer vocabulary check; that line was removed. The
  book and state fixture files are untouched and byte-verbatim.
- The input field name `yes_price_dollars` is read verbatim from capture rows (an identifier, not
  prose); the preflight vocabulary gate passes on it.

## Case map (spec CASES: 22 construct + 3 real-row)

Item 2 time: `test_time_goes_through_venue_parser_only` (parse, grep, day arithmetic). Item 3:
`test_marks_and_prior_book_boundaries`, `test_snapshot_validity`, `test_load_books_dispatch_...`
(bulk / other types, both file orders). Item 4 (B1 text): `test_censoring_walk` (6 rows incl. the
move-then-gap and exactly-10 cases). Item 5 (B3): `test_control_grid_seeds_and_lag_draws`. Item 5a
(B2): `test_event_typing_source_clock_and_state_guard` (score / period / play, src == receipt
accepted, src == receipt - 900 rejected, non-dict state, final before any event ignored). Item 6:
`test_tape_duplicates_conflicts_and_malformed_types` (dup, None id, conflict, absent outcome side,
negative lag kept, count None, taker_side 5, response_end_ts list, yes_bid "abc", bool, NaN,
out of range). Item 7: `test_status_ladder_and_six_hour_cap` (19/20, TAPE_MISSING keys, 21600
kept / 21600.001 cut, no_final_row). Item 8: `test_markout_print_and_contract_weighting` (0.0 and
-1.6). Item 9: `test_fill_scan` (7 rows). Item 10: `test_engine_reasons`. Item 11:
`test_pool_threshold_and_bootstrap`. Item 12: `test_stream_identity_and_line_counters`. Item 13:
the fresh-process test in the _real file. Item 14: `test_strict_json_nan_...`,
`test_missing_schedule_...`, `test_malformed_schedule_...` (4 shapes + bad day). Item 15:
`test_import_closure_...` (static AST walk incl. function-level imports). Orchestrator addition:
`test_rss_cap_exit_5_no_receipt`. Real-row: (a) fixture receipt equals the pinned probe oracle,
(b) renamed 3-game variant pools equal, (c) all 574 created_time values parse (5- and 4-digit
fractions), (d) the real print 07238660... keeps its positive receipt lag.

Expected-file generator: `tests/platformkit/execution/fixtures/s550_make_expected.py` (runs the
r2 probe functions on the fixture with patched roots; the tests never import the probe).

## .gitattributes lines added (3; all others untouched)

- `tests/platformkit/execution/fixtures/s550_real/** text eol=lf`
- `tests/platformkit/execution/fixtures/s550_expected.json text eol=lf`
- `docs/evidence/forward/exec_quality/*.json text eol=lf`

## Inventories (generated from the candidate files by a script)

### Files (LOC = len(text.splitlines()), sha256 of working bytes)

- `scripts/platformkit/execution/exec_quality_audit.py` LOC 282 sha256 e9565bfe5d5fbbe992cc512748b9646180477b5669fd44b75c2b91b03df54f0d
- `scripts/platformkit/execution/exec_quality_audit_pool.py` LOC 176 sha256 409b7c41dbdc89edd667cc3a97679fcf7c531ec2d2c542c5c509a27985b1bc9b
- `scripts/platformkit/execution/exec_quality_audit_io.py` LOC 260 sha256 770f4e962314b15fa35f68474503944a1e594cf46accc61263c4560cd3a23902
- `tests/platformkit/execution/test_s550_exec_quality_audit.py` LOC 298 sha256 6575f097ba662e6e079c84c4e07c7860a22592e9937ed84272141d03ecd11009
- `tests/platformkit/execution/test_s550_exec_quality_audit_real.py` LOC 154 sha256 f3d8f4eed72a0822dfb9c0bd22c2d49b320d25f22a21b758af5194567743c000
- `tests/platformkit/execution/fixtures/s550_make_expected.py` LOC 71 sha256 4233b06444dfe49e99569c5e37a6625154b5b656cde05b4f48fc6a15da7af7fa
- `tests/platformkit/execution/fixtures/s550_expected.json` LOC 1559 sha256 da44f38adada851178fe9498a1afca13fb943d40db436fb013d3206823e30eb0
- `tests/platformkit/execution/fixtures/s550_real/kalshi/mlb/2026-09-24.jsonl` LOC 648 sha256 e71009c769e140d9c285dc5c2f8d6bb8f136263617cc689835c9382621f7a72a
- `tests/platformkit/execution/fixtures/s550_real/state/mlb/2026-09-24.jsonl` LOC 10 sha256 12a0e971380bbc7b29b6e50f21c1a0adee6b4fd5ba16907a188246f39ef94813
- `tests/platformkit/execution/fixtures/s550_real/schedules/2026-09-24_maker_forward.json` LOC 10 sha256 e28ae960e15f9be1e6ed16fde5cadc95a9f53a3d0f93c356d5fc1f56ac69b095

### Test inventory (function names; parametrized cases expand at run time)

- `tests/platformkit/execution/test_s550_exec_quality_audit.py`: test_time_goes_through_venue_parser_only, test_marks_and_prior_book_boundaries, test_snapshot_validity, test_censoring_walk, test_control_grid_seeds_and_lag_draws, test_event_typing_source_clock_and_state_guard, test_tape_duplicates_conflicts_and_malformed_types, test_load_books_dispatch_and_order_independence, test_status_ladder_and_six_hour_cap, test_markout_print_and_contract_weighting, test_fill_scan, test_engine_reasons, test_pool_threshold_and_bootstrap, test_stream_identity_and_line_counters, test_strict_json_nan_refused_without_partial_file, test_missing_schedule_is_partial_failure, test_malformed_schedule_exit_2_no_receipt, test_rss_cap_exit_5_no_receipt
- `tests/platformkit/execution/test_s550_exec_quality_audit_real.py`: test_fixture_fresh_process_receipts_equal_probe_and_each_other, test_three_game_renamed_variant_pools_equal_probe, test_real_trade_times_parse_including_short_fractions, test_real_print_keeps_positive_receipt_lag, test_import_closure_has_no_venue_network_or_order_route

### MUST-NOT-MOVE pins (git blob sha at base 4045f96c08a3f5b0c0914d17970f8e5de9a754bf)

- `scripts/platformkit/execution/quote_engine.py` 230bb399237d8ff3f0d4bc3c3f7bc59248e6f32e
- `scripts/platformkit/execution/venue_time.py` 21c4cd3c485c63d5d4e335051e75075f73add54e
- `scripts/platformkit/execution/venue_fees.py` 59e0d183806bf02990c569ba62f9550f84906301
- `scripts/platformkit/execution/markout_causal.py` f9863255eededbab22ce7be622b44de071727400
- `scripts/platformkit/execution/tape_fill_sim.py` 7c27b8a76c5fe5329a3ebc4d832e946c87202544
- `docs/evidence/harness/exec2/exec2_audit_probe.py` b3f186d5ec75886d27133112572e1fc9f324b6d1
- `docs/evidence/harness/exec2/exec2_audit_measure.py` 7f93e8271f881cf437e44aa460bdceb81c0673ee
- `docs/evidence/harness/exec2/exec2_audit_cluster.py` b7b6f849bc145f65717921e20a1cd97a2cb9ee24
- `docs/evidence/harness/exec2/exec2_audit_2026-09-22_2026-09-29.json` 06ff2a80bbe48de7bc6535b91d1412a9a5011001
- `docs/evidence/harness/exec2/exec2_audit_r2_2026-09-22_2026-09-29.json` 87974675818a335a8ed55a7596f890e488d4289f
- `docs/evidence/harness/exec2/critique_astra_r1.md` ac774e76f46acb5a69555e325b70ecb580a271a0
- `docs/evidence/harness/exec2/critique_opus_r1.md` 94212952b1e68c2b274b2ed78de0ca225802746b
- paper_desk_* and S515-S519 family: 70 tracked paths, sha256 of the sorted `ls-tree` lines = 916f577fe6912f471be80f94227909de3fc672eaf17810e10728fceaa1edf861

### Refusal counters (receipt `refusals`, zero counts included)

`timestamp_rejected`, `bulk_rows_ignored`, `other_record_type_ignored`, `row_key_mismatch`, `snapshot_unparsed`, `snapshot_invalid_or_crossed`, `duplicate_trade_id`, `trade_unparsed_or_unknown_side`, `trade_price_or_count_out_of_range`, `taker_side_conflict`, `receipt_before_created`, `state_not_dict`, `source_clock_absent_or_rejected`, `schedule_missing`, `control_lag_absent`, `no_prior_book`, `mark_missing`, `depth_unknown_through_only`, `censored|before_lag`, `censored|5s`, `censored|15s`, `censored|30s`, `censored|60s`, `censored|120s`

### Definitions: 53 entries (50 estimand keys + notes ['note:fee', 'note:identity', 'note:joins'])

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

- The acceptance bar itself: the bracketed real-week run (module A, probe, module B; A == B bytes;
  every pool entry equal to the probe) and the peak working set on the real week are the
  orchestrator's measurement. The builder smoke diff above is one unbracketed pair, not the bar.
- Mid-shard identity limit: a change inside the middle of a shard that keeps its size and both end
  megabytes is not detected (stated in `definitions["note:identity"]`).
- Parser scope: built and tested on Python 3.10 only; the 3.12 behaviour of the receipt (RunPod) was
  not run.
- One development week only: exploratory numbers, no confirmatory claim.
- Focus depth exists only in the first focus hour of each game; later in-window instants are
  mostly unmarked (`mark_missing`, `no_prior_book`).
- In-game prints arrive by backfill (replay-labelled tape); receipt lags are capture lags.
- Join instants overlap and may share prints: fill shares are counterfactuals, not a policy
  throughput.
- Paths the real fixture cannot exercise (construct-only): duplicate trade_id, None trade_id,
  taker_side_conflict, depletion fills (exercised on the renamed 3-game variant and in construct
  cases), state_change pulls (variant + construct), score / period events, no_final_row, NO_DEPTH,
  TAPE_MISSING, the 6 h cap, the RSS cap.
- The RSS guard samples every 10,000 lines; a spike between samples is not seen.
- A same-instant pair of prints at different prices is resolved in file order (stable sort).
