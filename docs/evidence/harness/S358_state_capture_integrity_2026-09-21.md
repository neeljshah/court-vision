# S358 state capture integrity - 2026-09-21

PASS for the offline checks below; live behavior is NOT VERIFIED. Pending independent review and owner restart.
Vocabulary follows contract Q6; automated scan required.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h16. All HTTP boundaries used synthetic payloads and fake sessions. No network request, service launch, service stop, deployment, or commit was performed. The input cases are embedded in the six test files listed below; no external dataset or video was opened. This is deterministic regression coverage, not a sampled performance result.

Authority: docs/evidence/tracking/specs/S358_spec.md, requirements Q1-Q9 and TESTS; docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q. Fresh source reads confirmed the original pre-wait receipt stamps, first-observation true flag, state-only comparison, one-team match, clock-derived NBA date, swallowed parser failures, and unbounded event maps.

| Requirement | Code references | Offline evidence (test names) |
| --- | --- | --- |
| Q1 | scripts/platformkit/ingame/local_state_capture_io.py:37, :73, :100 delegate HTTP timing to unchanged local_capture_client.py; scripts/platformkit/ingame/local_state_capture.py:28 sets capture_ts to response_end_utc and adds tick_start_ts. | test_request_stamp_after_limiter_wait_and_response_shard checks actual fake send time after a wait, midnight sharding, and raw HTTP-body digest. |
| Q2 | scripts/platformkit/ingame/local_state_capture.py:28 compares (status, normalized state), returns null without a baseline, and :80-88 promotes the persistent baseline only after append and sync; scripts/platformkit/ingame/local_state_capture_io.py:136 reads yesterday then today's unique valid rows while locked. | test_first_repeat_status_change_and_unseeded_restart; test_unseeded_restart_has_null_baseline; test_status_only_pre_live_final_transitions; test_archive_recovery_yesterday_then_last_today; test_yesterday_recovered_on_restart; test_final_repeat_compares_archive_after_pruning. |
| Q3 | scripts/platformkit/ingame/game_market_link.py:68 and :154 require both explicit directional teams, local date, and a unique explicit scheduled start for multiple candidates; scripts/platformkit/ingame/local_state_capture_dates.py:33 derives local date from payload evidence only. | test_link_both_directional_teams_required; test_link_one_team_near_miss_or_reversed_unmatched; test_ticker_suffixes_do_not_prove_direction; test_doubleheader_requires_start_time_and_selects_exact_start; test_local_date_is_not_utc_start_date; test_every_espn_sport_uses_payload_local_date_at_utc_midnight; test_tennis_receipt_attached_before_second_tour_fetch. |
| Q4 | scripts/platformkit/ingame/local_state_capture.py:48, :85-88, :97-103 prune final/day maps only on committed promotion; scripts/platformkit/ingame/local_state_capture_commit.py:51 publishes source counters and actual last_write_ts; scripts/platformkit/ingame/local_state_capture_io.py:18 extends the shared metrics with 403 windows; scripts/platformkit/ingame/local_state_capture_dates.py:15 attributes source failures. Import-time counters are exposed as startup_sources. | test_every_row_owned_exception_handler_records_a_counter; test_adapter_failure_preserves_last_write_and_counts; test_http_failures_named_per_source; test_invalid_retry_after_counted_per_source; test_final_and_day_boundary_prune_all_event_maps; test_mlb_final_poll_and_all_event_maps_pruned; source adapter failure tests; linker archive failure tests. |
| Q5 | scripts/platformkit/ingame/local_state_capture_io.py:115 and :126 adapt layout and inherit ArchiveWriter locking, torn-tail recovery, O_APPEND writes, sync and atomic heartbeat behavior; scripts/platformkit/ingame/local_state_capture.py:203-230 holds one writer lock until failure or runner exit, closing a failed writer before its replacement acquires the same lock. | test_single_writer_lock_refuses_second_owner; test_torn_tail_quarantined_before_recovery_and_append; test_one_append_write_per_record_and_one_sync_per_tick; test_short_write_counts_and_prevents_further_appends; test_sync_failure_counted; test_writer_failure_does_not_advance_baseline. |
| Q6 | scripts/platformkit/ingame/local_state_capture_io.py:59 uses GovernedClient and its unchanged AIMDController, with Retry-After support extended to 403; scripts/platformkit/ingame/local_state_capture_sources.py:44 explicitly maps known statuses and preserves delayed. | test_shared_limiter_cannot_burst_after_idle_or_late_wakeup; test_429_403_retry_after_both_forms_and_window_expiry; test_default_session_no_custom_user_agent_or_credentials; test_injected_shared_metrics_adapted_for_403; test_status_delayed_distinct_and_unknown_never_live; source status-name regression tests. |
| Q7 | scripts/platformkit/ingame/local_state_capture_dates.py:26 validates venue instants with scripts.platformkit.execution.venue_time.parse_venue_time and retains the fraction as Decimal; :38 validates date-only fields; :52 resolves fixed-grammar unzoned components with ZoneInfo; :70 validates the resulting zoned time. scripts/platformkit/ingame/game_market_link.py:37 uses the same helper for exact start matching. | test_named_zone_unzoned_midnight_regression; test_schedule_preserves_exact_fraction covers zero through nine digits with Z, offsets and named zones; test_schedule_date_only_fields_have_separate_validation; test_linker_refuses_invalid_venue_times; test_doubleheader_nanoseconds_remain_distinct_in_both_orders. |
| Q8 | scripts/platformkit/ingame/local_state_capture_sources.py:52, :87, :107, :153, :194 retain imported MLB, NBA, soccer, tennis, NFL and NCAAF normalization; scripts/platformkit/ingame/local_state_capture_io.py:37 hashes actual response bytes; scripts/platformkit/ingame/local_state_capture.py:188 and :237 retain STOP_STATE and bounded CLI controls. | test_mlb_poll_live_fixture_extracts_full_state; test_mlb_poll_pregame_fixture_preserves_empty_state; test_nfl_real_receipt_required_and_adapter_failure_reported; test_existing_row_fields_preserved; test_stop_file_and_max_ticks_zero_do_not_fetch; test_cli_flag_over_environment_and_sports; test_max_ticks_bounds_runner; --help command below. |
| Q9 | FIX 1b changes only local_state_capture.py, local_state_capture_io.py, their two test files, the new local_state_capture_commit.py and test_state_capture_commit.py, and this memo. Shared S341 and imported domain/frontend modules remain unchanged. All eleven row-owned Python files are at most 300 lines and ASCII. | Per-file tests below; automated contract preflight below. |

The S341 client is wrapped to retain the SHA-256 of the actual consumed body, retry 403 responses with the shared limiter, and add per-source forbidden-response rates. The S341 writer cannot directly address the required state layout: its hard-coded venue child is remapped by _StateLayout to state/<sport>/<response-end-date>.jsonl. The exclusive lock lives at <output-root>/state/_capture.lock, separate from the book-capture lock. Its append, recovery and synchronization implementations are inherited without replacement. Archive sync runs once per touched shard per tick; atomic heartbeat files retain the shared writer's own durability behavior.

The existing row fields remain present. Added fields include tick_start_ts, scheduled_start_utc, date_reason and the shared writer's response_end_ts alias. last_success_ts remains present and now means the last completed record write. Final-state comparisons can recover from disk after the event maps have been pruned. MLB discovery checks yesterday and today, retaining games spanning UTC midnight long enough to poll their final state.

A local scheduled date requires officialDate/localDate, a payload timezone, or an explicit nonzero schedule offset. Missing evidence produces date=null with date_reason, while the scheduled UTC instant remains available. Unordered ticker suffixes cannot establish home/away direction. Missing directional metadata remains unmatched; no live coverage is implied. Reader survey found this row's tests and S352 documentation as direct local-state consumers; similarly named aggregate columns in gate_a0_ingame_vs_market.py refer to a separate dataset.

Validation commands were run sequentially, one test file at a time:

```powershell
python -m pytest tests/platformkit/ingame/test_local_state_capture.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_state_capture_io.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_state_capture_sources.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_state_market_link.py -q -p no:cacheprovider
python -m pytest tests/platformkit/ingame/test_state_capture_commit.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.local_state_capture --help
```

FIX 1b results: 17 + 13 + 31 + 17 + 11 = 89 passed. The help command exited 0. These are constructed regression cases, not live observations.

Exact automated scan command:

```powershell
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/local_state_capture.py scripts/platformkit/ingame/local_state_capture_sources.py scripts/platformkit/ingame/game_market_link.py scripts/platformkit/ingame/local_state_capture_io.py scripts/platformkit/ingame/local_state_capture_dates.py scripts/platformkit/ingame/local_state_capture_commit.py tests/platformkit/ingame/test_local_state_capture.py tests/platformkit/ingame/test_state_capture_io.py tests/platformkit/ingame/test_state_capture_sources.py tests/platformkit/ingame/test_state_market_link.py tests/platformkit/ingame/test_state_capture_commit.py docs/evidence/harness/S358_state_capture_integrity_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S358_spec.md
```

Preflight result for FIX 1b: exit 0; all nine checks PASS over twelve files (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication). A separate byte scan confirmed ASCII over all twelve files. The command reported every selected file as untracked; schema checks do not substitute for independent code review.

Exact side-by-side smoke command, documented for the owner and NOT EXECUTED here. Run from this worktree while the existing S341 capture continues. The separate smoke root avoids the running state capture's archive and lock:

```powershell
python -m scripts.platformkit.ingame.local_state_capture --output-root C:/Users/neelj/nba-harness-h16/data/cache/ingame_books_local/S358_smoke --max-ticks 12 --sports mlb,nba,soccer,tennis,nfl,ncaaf
```

## FIX 1b

The Amendment 1 premise was reproduced by source inspection: append errors were swallowed and could prune FINAL games, and sync errors were swallowed after advancing the baseline. The implementation now stages the complete tick separately, retains its exact rows on failure, and commits the staged maps only after append and sync succeed. No changes were made to the S341 modules, HTTP timing, limiter, adapters, linker, field names, CLI options, or STOP_STATE behavior.

The following quotes reproduce each binding clause from AMENDMENT 1. Line references identify the implementation in this worktree; test names identify constructed evidence, including both parametrized append/sync cases.

| Exact amendment clause | Satisfying code lines | Required offline evidence |
| --- | --- | --- |
| "within a tick, (1) rows are appended; (2) writer.sync() is called; (3) ONLY IF both succeed are the per-game remembered state (the state_changed baseline) promoted and final games pruned." | scripts/platformkit/ingame/local_state_capture_commit.py:30-48 appends then syncs; scripts/platformkit/ingame/local_state_capture.py:73-88 retains the candidate separately and promotes/prunes only after commit_rows returns. | test_final_failure_retries_same_game_before_pruning inspects the original baseline and all event maps inside sync, before it succeeds; test_partial_append_failure_promotes_neither_game covers a partly appended tick. |
| "On an append or sync failure the failure is COUNTED in the heartbeat (named counter + last error text) and then RE-RAISED to the tick loop" | scripts/platformkit/ingame/local_state_capture_commit.py:18-22, :37-47 records state_write_errors / state_sync_errors and last_write_error; scripts/platformkit/ingame/local_state_capture.py:81-84 publishes the failure heartbeat and re-raises; :213-215 counts failed ticks. | test_final_failure_retries_same_game_before_pruning reads both failure heartbeats from disk; test_writer_failure_does_not_advance_baseline checks propagation and last error; test_every_row_owned_exception_handler_records_a_counter now includes the new helper. |
| "which (a) does not promote state and does not prune" | scripts/platformkit/ingame/local_state_capture.py:74 builds an isolated draft; :81-84 exits before :85-88 can replace the committed state and prune final games. | test_final_failure_retries_same_game_before_pruning; test_partial_append_failure_promotes_neither_game; test_failed_day_transition_preserves_committed_maps. |
| "(b) rebuilds the writer on the next tick (a permanently failed writer is never reused)" | scripts/platformkit/ingame/local_state_capture.py:208-210 constructs/enters a writer only when absent; :216-218 closes and discards the failed instance; scripts/platformkit/ingame/local_state_capture_commit.py:25-27 is the row-owned fresh-instance factory. | test_runner_rebuilds_writer_and_recovers_one_unique_row verifies two distinct instances, closure before replacement, and a fake writer that refuses all appends after failure. |
| "(c) retries the same games" | scripts/platformkit/ingame/local_state_capture.py:73-77 retains _pending_tick across failure and reuses its rows without re-polling or rebuilding their timestamps or baselines. | test_final_failure_retries_same_game_before_pruning verifies the identical MLB FINAL record on the next tick; test_runner_rebuilds_writer_and_recovers_one_unique_row proves exactly one fake HTTP request across failure and retry. |
| "(d) after N consecutive failed ticks (default 5) exits nonzero with a clear message so a supervisor or the watchdog can see it -- a process that cannot write must not look alive." | scripts/platformkit/ingame/local_state_capture.py:191 defaults max_failed_ticks to 5; :213-224 counts failures, raises SystemExit with error text at the limit, and resets the consecutive count after success; :231-233 also refuses a successful bounded exit with a pending tick. | test_consecutive_failed_ticks_exit_nonzero enumerates the default five and configured two; test_success_resets_consecutive_failure_limit; test_bounded_run_cannot_report_success_with_pending_tick. SystemExit is caught in-process; no subprocess is launched. |
| "A row that was appended but whose sync failed may be re-appended on the retry: de-duplicate on (sport, game_key, response_end_utc) at recovery time and state that rule." | scripts/platformkit/ingame/local_state_capture_io.py:143-166 yields each receipt identity once; :136-141 builds the baseline only from those unique rows. | test_runner_rebuilds_writer_and_recovers_one_unique_row verifies one recovered row after both failure modes; test_recovery_deduplicates_receipts_without_reverting_later_state retains distinct sports/games/timestamps and prevents a repeated old receipt from replacing a newer state. |

Recovery rule (updated by FIX 1c below): de-duplicate on (sport, game_key, response_end_utc), comparing timestamps as exact UTC instants. Identical retries produce one logical row; conflicting identities are counted and refused in full. Recovery selects the maximum eligible timestamp per game, independent of archive order. A sync failure can leave two physical JSONL records after retry; raw shards are not rewritten or claimed to contain no repeated records.

The required test clauses are covered as follows: "append failure on a FINAL game -> the game is retried next tick and only then pruned" and "sync failure -> no state promotion, no pruning, the writer is rebuilt" are the paired final-failure and runner tests; "N consecutive failures -> nonzero exit" is the limit test; "heartbeat counters for both" is checked against the persisted per-source heartbeats; "no duplicate row after a failed-then-successful tick" is checked at recovery under the identity rule above.

Heartbeat fields remain additive. tick_committed distinguishes failed ticks; last_write_error preserves the named failure text. If the same disk fault also prevents heartbeat publication, state_heartbeat_errors is counted and the error is emitted to stderr before the original write failure propagates; test_disk_fault_in_heartbeat_keeps_original_failure verifies this. rows_written_tick, rows_written_total and last_write_ts still describe complete append writes, including writes awaiting a successful sync; they do not claim committed durability.

FIX 1b file lengths: local_state_capture.py 253; local_state_capture_io.py 169; local_state_capture_commit.py 83; test_local_state_capture.py 263; test_state_capture_io.py 194; test_state_capture_commit.py 197. The pre-existing source and linker tests also passed unchanged. A separate read-only review found no Amendment 1 blocker; independent master verification remains pending.

## FIX 1c

Authority: _verdict_s358_1c.md and the complete S358 spec, including Amendment 1.
The local and master spec copies both contain Amendment 1. Changes in this pass:
scripts/platformkit/ingame/local_state_capture_io.py,
tests/platformkit/ingame/test_state_capture_recovery.py, and this memo only.
The five existing test files and the write-path behavior confirmed by finding 4
remain unchanged. All inputs are temporary constructed JSONL fixtures in this
worktree; no real archive was opened.

1. BLOCKING: archive order changed the recovered baseline. The verifier's
   two-record reproduction was run before editing the implementation:

   ```text
   forward: {'nba:g': ('live', {'score': 2})}
   reversed: {'nba:g': ('live', {'score': 1})}
   conflict forward: {'nba:g': ('live', {'score': 2})}
   conflict reversed: {'nba:g': ('live', {'score': 3})}
   drops: {}
   ```

   local_state_capture_io.py:153 (recover_states) now selects the maximum parsed
   timestamp per game. At :164, recover_rows buffers identities before yielding,
   rejects every variant of a
   conflicting identity, and increments archive_receipt_conflicts once per
   conflicting identity per recovery call. Eligible receipts are emitted in
   timestamp/sport/game order. Equal UTC instants share an identity even when
   represented with different offsets. The unchanged minimal reproduction now
   prints:

   ```text
   forward: {'nba:g': ('live', {'score': 2})}
   reversed: {'nba:g': ('live', {'score': 2})}
   conflict forward: {}
   drops: {'archive_receipt_conflicts': 1}
   conflict reversed: {}
   drops: {'archive_receipt_conflicts': 1}
   ```

   Regression evidence: test_recovery_selects_latest_independent_of_archive_order
   also checks state_changed=False against the latest state;
   test_recovery_conflicts_refused_and_counted_for_every_permutation checks all
   24 permutations including an identical retry; the no-baseline and equivalent
   offset tests cover complete refusal when only conflicting receipts exist.

2. BLOCKING: recovery admitted a receipt after the restart time. The exact
   noon restart / 13:00 receipt fixture initially printed:

   ```text
   future: {'nba:g': ('live', {'score': 9})}
   drops: {}
   ```

   Every recovered receipt is now validated by
   scripts.platformkit.execution.venue_time.parse_venue_time. Invalid times
   increment archive_timestamp_errors; receipts later than now increment
   archive_future_receipts and are skipped. At local_state_capture_io.py:130,
   _receipt_time retains the validated
   fraction as Decimal and parses whole seconds through that same shared parser,
   preserving all nine fractional digits during ordering and cutoff comparisons.
   No shared module was edited. The unchanged minimal reproduction now prints:

   ```text
   future: {}
   drops: {'archive_future_receipts': 1}
   ```

   Regression evidence: test_recovery_refuses_future_as_of_restart;
   test_recovery_nanosecond_order_and_inclusive_as_of_boundary enumerates all
   24 permutations around the cutoff, admits equality, rejects one nanosecond
   after it, and orders two observations within one microsecond. Additional
   constructs cover missing/invalid/non-finite times, unzoned rejection, offsets,
   and every fractional length from zero through nine.

3. CORRECTION: the verifier reported "no test body executed" because its
   environment lacked a writable temporary directory. That environment failure
   was not reproduced here: fixture setup succeeds in this writable worktree.
   TEMP and TMP were set to C:/Users/neelj/nba-harness-h16/.tmp_s358_1c and
   PYTHONDONTWRITEBYTECODE=1. All five original commands above were rerun
   unchanged, sequentially: 17 + 13 + 31 + 17 + 11 = 89 passed. No test changes
   were needed for this correction.

4. NOTE: the confirmed Amendment 1 write path, adapters, limiter, linker, CLI,
   source counters and STOP_STATE were left unchanged. Their existing tests
   passed as listed above; no additional behavior is claimed.

New regression command (also used before the implementation fix):

```powershell
python -m pytest tests/platformkit/ingame/test_state_capture_recovery.py -q -p no:cacheprovider
```

Before: 13 failed, 12 passed. After: 25 passed. Total final per-file results:
17 + 13 + 31 + 17 + 11 + 25 = 114 passed (CONSTRUCT).
The row's --help command exited 0; no self-check CLI is defined by this row.
Independent review and owner restart remain pending.

Final automated command, excluding the verdict file:

```powershell
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/local_state_capture.py scripts/platformkit/ingame/local_state_capture_sources.py scripts/platformkit/ingame/game_market_link.py scripts/platformkit/ingame/local_state_capture_io.py scripts/platformkit/ingame/local_state_capture_dates.py scripts/platformkit/ingame/local_state_capture_commit.py tests/platformkit/ingame/test_local_state_capture.py tests/platformkit/ingame/test_state_capture_io.py tests/platformkit/ingame/test_state_capture_sources.py tests/platformkit/ingame/test_state_market_link.py tests/platformkit/ingame/test_state_capture_commit.py tests/platformkit/ingame/test_state_capture_recovery.py docs/evidence/harness/S358_state_capture_integrity_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S358_spec.md
```

FIX 1c preflight: exit 0; all nine checks PASS over thirteen row-owned files.
A separate byte scan found all thirteen ASCII and at most 300 lines each.
The modified implementation has 207 lines; the new regression file has 106.
Preflight reports the selected files as untracked; it is a mechanical scan,
not independent acceptance of this candidate.

## FIX 1d

Authority: _verdict_s358_1d.md and S358_spec.md including Amendment 1.
Only local_state_capture_dates.py, game_market_link.py, their existing source
and linker test files, and this memo changed in this pass.

1. BLOCKING (finding 1): the exact unzoned midnight input was reproduced before
   changing the implementation: schedule({'date': '2026-09-21T00:30:00',
   'timeZone': 'America/Chicago'}). Failing output:

   ```text
   schedule: {'date': '2026-09-20', 'scheduled_start_utc': '2026-09-21T00:30:00.000000Z', 'date_reason': None}
   shared parser: None
   midnight regression: FAIL
   ```

   Venue instants now use parse_venue_time, with all validated fractional digits
   retained as Decimal for exact start comparisons. Named-zone unzoned values
   use fixed-grammar components plus ZoneInfo, then shared-parser validation.
   Ambiguous/nonexistent local times are refused and counted. Date-only evidence
   is validated separately. Q7 mapping above identifies implementation lines.
   The unchanged reproduction now prints:

   ```text
   schedule: {'date': '2026-09-21', 'scheduled_start_utc': '2026-09-21T05:30:00.000000Z', 'date_reason': None}
   shared parser: None
   midnight regression: PASS
   ```

   Regression tests are embedded in test_state_capture_sources.py and
   test_state_market_link.py. Before the implementation fix, the exact per-file
   commands above reported respectively `25 failed, 48 passed` and
   `4 failed, 19 passed`. After: `73 passed` and `23 passed`.
   Coverage includes the midnight input, missing zones, invalid date-only
   evidence, non-finite inputs, all ten fractional lengths, DST ambiguity,
   and exact nanosecond doubleheader matching in both input orders.

2. CORRECTION (finding 4): the initial documentation probe printed
   `memo claims five: True` and `actual test files: 6`.
   The opening paragraph now says six. The same probe after the edit prints
   `memo claims five: False`, `actual test files: 6`; the six-file claim matches.

3. NOTES (findings 2 and 3): the confirmed archive recovery and Amendment 1
   write path were not edited. Their existing per-file tests passed unchanged.

Validation used TEMP and TMP=C:/Users/neelj/nba-harness-h16/.tmp_s358_1d and
PYTHONDONTWRITEBYTECODE=1. All six commands ran separately, one file at a time:
local_state_capture 17; state_capture_io 13; state_capture_sources 73;
state_market_link 23; state_capture_commit 11; state_capture_recovery 25.
Total: 162 passed (CONSTRUCT). CLI --help exited 0; no self-check CLI is defined.
Only constructed fixtures were used; the documented live smoke was not run.
The thirteen-file preflight command in FIX 1c was rerun for FIX 1d, excluding
the verdict file: exit 0, all nine checks PASS. Both modified implementation
files, both modified test files and this memo are ASCII and below 300 lines.
The memo count reproduction prints `memo count regression: PASS`.

SHA: NOT CREATED (sandbox); files ready for lane_commit

NOT VERIFIED:
- Live endpoint behavior, real source timestamps, 403/429 behavior, latency, memory use, or coverage.
- Live availability of payload local-zone evidence, market directional metadata, and distinct doubleheader start times.
- Cross-process lock contention or recovery after an actual process crash or power interruption; tests use same-process competing writer handles and a constructed torn record.
- Execution under a separately selected Python 3.10 interpreter; shared timestamp parsing is reused and no new datetime.fromisoformat parser was added.
- Side-by-side smoke execution, deployment, or restart of the currently running capture.
- Independent review on master and creation of a commit SHA.
