# S621 -- same-day, pre-start D1 revision (companion CLI) -- build memo 2026-09-30

Spec: docs/evidence/tracking/specs/S621_spec.md including AMENDMENT 1 (REVISE-FOLDED; it overrides the original where they differ) and AMENDMENT 2 (fix r1 -> r2, items B1-B7). Worktree h263, base master b2572a37f.
Scope: construct tests only (tmp roots, injected writer and clock, POINTER_ROOT moved to tmp). No archive read, no network, no pod, no real pointer write, no measured number.

## BINDING BEFORE-CONDITION (re-run 2026-09-30T02:29:05Z, read-only)

- `python -m scripts.platformkit.execution.schedule_d1 --help | grep -c -- "--day"` printed `0`: no --day flag.
- data/cache/schedule_pointers/maker_forward_pointer.json:
  `{"day": "2026-09-30", "schedule": "../../../docs/evidence/forward/schedules/2026-09-30_maker_forward.json", "sha256": "f34f8ac3723a1f8bc27e115d9f89c3b9dfbef3f4e0413d4e3797469de057bab9", "written_at": "2026-09-29T14:16:05.176507+00:00"}`
- docs/evidence/forward/schedules ends at 2026-09-30_run.json: D1(10-01) is NOT yet written.
- 2026-09-30_run.json: rewrite_reason None, superseded {}, mlb served 3 of full 3, mlb refused_by_reason {missing_directional_team_evidence 1, outside_utc_date 2}, nfl 0 of 0.
- Heartbeats (read-only): data/cache/ingame_books_local/kalshi/mlb/_heartbeat.json pointer_ok_at 2026-09-30T02:31:47.738904Z, pointer_day 2026-09-30, schedule_pointer_last_reason None, refusals_total 0; polymarket/mlb pointer_ok_at 2026-09-30T01:55:38.967049Z, same day, None, 0.

PREMISE (AMENDMENT 1 item 1): D1(10-01) serves BOS@NYY G2 only; CHC@SD G2 is alias-refused (missing_directional_team_evidence) unless S612 lands first. The revision exists for the G3s PHI@ATL 18:00Z and CWS@HOU 21:00Z on 10-01, at most 2 MLB games, each only if its series is 1-1.

## WHAT WAS BUILT

- NEW scripts/platformkit/execution/schedule_revise.py (companion CLI; edits no existing module). Imports the landed schedule_d1 helpers (_instant, _utc, _forbidden, _stage, _encode, _diagnostics, _receipts, _subset(...)[0], RULE, POINTER_ROOT, _clock), schedule_pointer._admit_capacity(carry, candidates, at, errors) and instant, schedule_pointer_writer.write_pointer(pointer_path, schedule_path, day, sha256=, now=), atomic_replace.replace_with_retry(temporary, target), forward_schedule_writer.build_schedule.
- Precondition order: invalid_now, now_in_future, stale_now (> 600 s), invalid_day, day_not_today, tick_still_validates_day (local date < D), next_d1_due (local time >= d1_not_before_local 07:00 minus 900 s = 06:45; both windows evaluate the local time of max(--now, clock), AMENDMENT 2 B3; local_tz and d1_not_before_local read from docs/operations/paper_desk_config.json, read-only), invalid_rewrite_reason, tz_mismatch (vs config), invalid_sports, invalid_family, out_dir_forbidden, publication_incomplete, publication_digest_mismatch (run.json D1, and exactly one files entry per data file matched by basename with an equal raw sha), tz_mismatch (any old census local_date_tz absent or different, AMENDMENT 2 B1), sports_mismatch (vs old run per_sport), pointer_not_at_day (only with --write-pointer; day, resolved target and sha).
- Selection as schedule_d1:189-211 with day = D (missing_schedule_receipt, future_selected_at, invalid_schedule_scope). Merge: a visible row matching exactly one old full row on both game_id and ticker keeps the OLD dict and counts carried_row_changed_upstream per field (selected_at excluded); a partial or multiple match refuses conflicting_reselection; a new row is a candidate only if start > selected + 1800 s, else counted revision_start_within_margin. No candidate refuses nothing_new.
- SERVED = _admit_capacity(OLD_SERVED, candidates, selected, errors), then refuses carried_row_dropped if any old served row were missing (a guard; the landed function never drops one). FULL = OLD_FULL + candidates sorted by (start, game_id, ticker). Counts in run.json per_sport, note served/not_served and writer_selected_at are over the MERGED rows; refused_by_reason / record_counts diagnostics and census.json come from the new build. note.capacity_subset_selected_at = selected, note.rule = schedule_d1.RULE, plus revision_rule. run.json keeps every schedule_d1 key plus `revision` {mode same_day_pre_start, revises_run_sha256, carried_served, carried_full, added_served, added_not_served, margin_s 1800, carried_row_changed_upstream}.
- Write (AMENDMENT 1 item 5): refuse superseded_exists if any `.superseded_<selected second>` name is taken; copy every original to its backup with _stage ('xb' + fsync); stage the five new files; re-read the five originals and refuse publication_changed if any byte differs from the start-of-run read (AMENDMENT 2 B4: a racing revision), unlinking every backup and staged file; replace with replace_with_retry in the order full, census, note, served, run.json LAST. A staging failure unlinks every file this run created and refuses io_error (originals byte-identical). A failure on the first replace does the same, backups included (AMENDMENT 2 B2, tested). A failure after a replace refuses partial_publication with the replaced list, removes staged files, keeps the backups, and writes no pointer (the runner then sees pointer_sha256_mismatch and keeps its state).
- Pointer: re-checked (day, target, old served sha) immediately before write_pointer; a moved pointer refuses pointer_moved_before_write with published=True and is NOT overwritten; a write_pointer error refuses pointer_write_failed with published=True. The WRITTEN line echoes added, added_served, added_not_served, carried_row_changed_upstream and served_sha256.

## INVENTORY (generated: `python docs/evidence/harness/S621_memo_inventory.py`, output verbatim)

```
LINES scripts/platformkit/execution/schedule_revise.py 206
LINES tests/platformkit/execution/test_schedule_revise.py 284
LINES tests/platformkit/execution/test_schedule_revise_e2e.py 248
REFUSAL_REASONS 29 carried_row_dropped conflicting_reselection day_not_today future_selected_at invalid_day invalid_family invalid_input invalid_now invalid_rewrite_reason invalid_schedule_scope invalid_sports io_error missing_schedule_receipt next_d1_due nothing_new now_in_future out_dir_forbidden partial_publication pointer_moved_before_write pointer_not_at_day pointer_write_failed publication_changed publication_digest_mismatch publication_incomplete sports_mismatch stale_now superseded_exists tick_still_validates_day tz_mismatch
CASE test_real_0930_rows_end_to_end WRITTEN
CASE test_case_01_02_window day_not_today,next_d1_due,tick_still_validates_day
CASE test_case_03_now invalid_now,now_in_future,stale_now
CASE test_case_04_margin nothing_new
CASE test_case_05_started_carried_row_and_realistic_shape WRITTEN
CASE test_case_06_07_carried_row_kept WRITTEN
CASE test_case_08_conflicting_reselection conflicting_reselection
CASE test_case_09_capacity WRITTEN
CASE test_case_10_nothing_new nothing_new
CASE test_case_11_publication_and_pointer pointer_not_at_day,publication_digest_mismatch,publication_incomplete
CASE test_tz_and_sports_bound_to_old_run sports_mismatch,tz_mismatch
CASE test_digest_by_basename_relative_absolute_and_tmp_copy WRITTEN
CASE test_case_17_invalid_writer_start invalid_input
CASE test_case_18_rewrite_and_required_args invalid_rewrite_reason
COLLECTED tests/platformkit/execution/test_schedule_revise.py 31 tests collected
CASE test_case_12_fresh_process_pointer_union_and_night_plan WRITTEN
CASE test_case_14_tick_has_moved_to_next_day WRITTEN
CASE test_writer_order_does_not_change_bytes WRITTEN
CASE test_pointer_moved_during_selection_is_not_overwritten pointer_moved_before_write
CASE test_case_15_second_revision_and_same_second superseded_exists
CASE test_case_16_staging_failure_leaves_originals io_error
CASE test_case_16_replace_failure_is_partial_and_pointer_untouched partial_publication
CASE test_remaining_refusals_write_nothing future_selected_at,invalid_day,invalid_family,invalid_schedule_scope,invalid_sports,out_dir_forbidden
CASE test_missing_schedule_receipt_writes_nothing missing_schedule_receipt
CASE test_old_census_tz_absent_or_different_refuses tz_mismatch
CASE test_window_uses_clock_when_now_lags next_d1_due
CASE test_first_replace_failure_writes_nothing io_error
CASE test_concurrent_revision_between_read_and_publish_refuses publication_changed
COLLECTED tests/platformkit/execution/test_schedule_revise_e2e.py 22 tests collected
TEST_FUNCTIONS 27
CASE12 status=WRITTEN added=KXMLBGAME-26OCT011400PHIATL-ATL,KXMLBGAME-26OCT011700CWSHOU-HOU served=4 full=4
CASE12 served_sha256 3747ac779bdf189188caeed2f5b93517167abf0ba99b9714be917be209b3ec9d
CASE12 fresh_process ok=True forward=KXMLBGAME-26OCT011400PHIATL-ATL,KXMLBGAME-26OCT011700CWSHOU-HOU,KXMLBGAME-26OCT011800NYMMIA-MIA planning_errors=0 mlb_scheduled_games=4
CASE12 pointer_day 2026-10-01
```

Spec case map: 1-2 window + next_d1_due (11:44:59Z accepted, 11:45:00Z refused); 3 now; 4 margin (selected+1800 excluded and counted, +1801 added); 5 + AMENDMENT item 8 realistic shape (OLD = [BOS G2 00:00Z], writer [G3 18:00Z, G3 21:00Z], now 06:00Z: SERVED 3, FULL 3, BOS byte-equal, pointer day D and sha = served); 6-7 carried rows; 8 conflicting_reselection both ways with all five files and the pointer unchanged; 9 capacity (s+3599 refused and counted pointer_capacity_refused 1, s+3600 served, s-1 not served); 10 nothing_new; 11 publication and pointer (a pointer at D+1 without --write-pointer is accepted); 12 fresh process: LANDED read_schedule_pointer with forward_schedule = OLD_SERVED and now = completed_at + 1 s returns non-None, no conflicting_schedule_rows, forward = open OLD_SERVED rows plus the added rows; then LANDED paper_night_inputs.plan_inputs(tmp_root, D, "2026-10-02T06:00:00Z", producer_args with {date}, paper_night_budget.json) gives planning_errors 0 and mlb scheduled_games = mlb rows in FULL; 13 check_publication in every WRITTEN case (served in full dict-equal, sorted note.served = served tickers, per_sport sums = len(FULL) and len(SERVED), ASCII strict JSON); 14 at 05:00Z the tick day is 2026-10-02 and schedule_state(root, 2026-10-02, now) = absent with the pointer unchanged; 15 second revision adds one row, same-second revision refuses superseded_exists; 16 staging failure on the third staged file (io_error, originals and pointer byte-identical) and replace failure on the 2nd replace (partial_publication, run.json still the old one, backups kept, pointer untouched); 17 start None / NaN / True gives invalid_input; 18 blank rewrite and argparse exit 2. AMENDMENT 2: B1 old census tz America/New_York or absent refuses tz_mismatch (nothing written); B2 PermissionError on the 1st replace refuses io_error with the out-dir and pointer unchanged and no .superseded_/.staging_ file; B3 --now 600 s behind the clock: clock 11:44:59Z runs, clock 11:45:00Z refuses next_d1_due, --now 04:50Z with clock 05:00Z runs; B4 a second revision completing inside the writer call makes the first refuse publication_changed with the files equal to the racing revision's output; B6 a pointer whose schedule field targets the full-selection file refuses pointer_not_at_day. The first test consumes the REAL 2026-09-30 served rows verbatim (asserted equal to the committed file, and the schedule_d1-rebuilt served file hashes to f34f8ac3...bab9). Both writer orders give identical served/full bytes.

## OPERATOR RUNBOOK (first use; run by hand)

WINDOW: 2026-10-01 05:00:00Z to 11:44:59Z (00:00 to 06:44:59 CDT). Before 05:00Z the CLI refuses tick_still_validates_day; from 11:45:00Z it refuses next_d1_due. The 12:51Z morning run and the 14:07Z improve run are too late (the pointer is at 10-02 by then; pointer_not_at_day).

Step 1 -- rehearsal on a tmp copy (no --write-pointer; writes only into the copy; it makes the same live schedule fetch as the real run):

```
cd /c/Users/neelj/nba-ai-system && R="$(mktemp -d)" && for f in 2026-10-01_maker_forward_full_selection.json 2026-10-01_maker_forward_full_selection.json.census.json 2026-10-01_maker_forward.json 2026-10-01_maker_forward.json.capacity_note.json 2026-10-01_run.json; do cp "docs/evidence/forward/schedules/$f" "$R/"; done && python -m scripts.platformkit.execution.schedule_revise --day 2026-10-01 --now "$(python -c "from datetime import datetime,timezone;print(datetime.now(timezone.utc).isoformat())")" --rewrite "S621 rehearsal" --sports mlb,nfl --local-date-tz America/Chicago --books-root data/cache/ingame_books_local --state-root data/cache/ingame_state_local_v2 --out-dir "$R"
```

STOP RULE: read the one stdout line. `"reason": "nothing_new"` means STOP: that is an honest null (no G3 listed or both started/within 1800 s); do not run step 2. Any other REFUSED line means STOP and read the reason. Only a WRITTEN line with added_served 1 or 2 (and the expected G3 tickers in "added") proceeds to step 2.

Step 2 -- the real run (spec EVIDENCE command, verbatim):

```
cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.execution.schedule_revise --day 2026-10-01 --now "$(python -c "from datetime import datetime,timezone;print(datetime.now(timezone.utc).isoformat())")" --rewrite "S621: WC G3 PHI@ATL/CWS@HOU listed after D1(10-01)" --sports mlb,nfl --local-date-tz America/Chicago --books-root data/cache/ingame_books_local --state-root data/cache/ingame_state_local_v2 --write-pointer
```

Step 3 -- verify the pointer and the runners (at least 60 s after step 2, one pointer poll period):

```
cd /c/Users/neelj/nba-ai-system && python -c "
import hashlib, json
p = json.load(open('data/cache/schedule_pointers/maker_forward_pointer.json'))
s = hashlib.sha256(open('docs/evidence/forward/schedules/2026-10-01_maker_forward.json', 'rb').read()).hexdigest()
print('pointer', p['day'], p['sha256'] == s, p['written_at'])
for v in ('kalshi', 'polymarket'):
    h = json.load(open('data/cache/ingame_books_local/%s/mlb/_heartbeat.json' % v))
    print(v, h.get('pointer_ok_at'), h.get('pointer_sha256') == s, h.get('schedule_pointer_last_reason'), h.get('schedule_pointer_refusals_total'))
"
```

Expected: `pointer 2026-10-01 True <completed_at>`; for kalshi and polymarket, pointer_ok_at later than the step-2 completed_at, pointer_sha256 True, last_reason None and refusals_total unchanged. Then: no owner_intervention_required row for day 2026-10-01 in data/cache/paper_desk/journal/2026-10-01.jsonl (`grep owner_intervention_required data/cache/paper_desk/journal/2026-10-01.jsonl` should show no row whose day is 2026-10-01); after the 10-01 night (06:05Z 10-02) the night's inputs list the G3 tickers.

RECOVERY (AMENDMENT 2 B5):
- (a) An exit-2 line with `"published": true` (pointer_moved_before_write or pointer_write_failed) means the files are revised but the pointer was not written. Before 11:45Z, and ONLY if the pointer day is still 2026-10-01, rerun the pointer writer by hand: `cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.execution.schedule_pointer_writer --pointer data/cache/schedule_pointers/maker_forward_pointer.json --schedule docs/evidence/forward/schedules/2026-10-01_maker_forward.json --day 2026-10-01`. If the pointer day is already 2026-10-02, do nothing: D1(D+1) owns the pointer and the night reads D by path.
- (b) After partial_publication, or a crash that leaves `.staging_*` files: copy each `<path>.superseded_<sec>` back over `<path>` for all five files, delete every `<path>.staging_<sec>`, then rerun the step-1 rehearsal (a new second). NEVER rerun the real command on a mixed publication (it refuses publication_digest_mismatch anyway, fail-closed).
- (c) The rehearsal copies the five files from the MAIN checkout (/c/Users/neelj/nba-ai-system, LF bytes as D1 wrote them), never from a worktree: a worktree checkout can be CRLF and refuses publication_digest_mismatch (fail-closed).

## MANDATORY DISCLOSURES

- The G3 listing time is INFERRED, not observed: no G3 event was in kalshi/mlb/2026-09-30.jsonl at the spec probe.
- The revision needs the G3 Kalshi event in the books archive and a real ESPN start time; a TBD placeholder gives nothing_new or outside_utc_date.
- A restarted runner does NOT lose the revision: seed_cli_schedule runs before the pointer read in the same pass (capture_schedule_loader.py:28-39), and the next pointer read unions the revised file.
- The revised publication is invalid by paper_desk_schedule's rules by design (rewrite_reason and superseded are set; run.now is on D, not D-1). It is never re-validated, because at local date >= D the tick validates D+1 only (case 14).
- census.json and the refused_by_reason / record_counts diagnostics describe the NEW build only, not the union (OQ5, accepted, observational); every row count is over the merged rows.
- run.json `files` keys are the --out-dir as given: the real run writes relative keys even when the original D1 was tick-written with absolute keys; the next revision matches by basename (tested both ways).
- carried_row_changed_upstream (for example a moved start) is recorded and echoed, never a refusal (OQ3); the carried row keeps its old start.

## DEVIATIONS

- One extra owned file beyond the spec's CHANGE list: docs/evidence/harness/S621_memo_inventory.py (the memo script the EVIDENCE section names). No fixture files.
- Refusal names added beyond the spec text: tz_mismatch, sports_mismatch, next_d1_due (AMENDMENT 1), partial_publication (AMENDMENT 1), pointer_moved_before_write (the AMENDMENT 1 item 2 re-check; files are already published when it fires), pointer_write_failed, carried_row_dropped (guard), invalid_sports, invalid_family (schedule_d1 parity).
- archive_root_missing (a schedule_d1 check) is not repeated; build_schedule reports missing archives through its census.
- The module is 206 lines; AMENDMENT 2 B7 raised the spec cap from 200 to 260 (house rail <= 300). New refusal publication_changed (AMENDMENT 2 B4).

## OWNED PATHS

- scripts/platformkit/execution/schedule_revise.py (NEW, 206 lines)
- tests/platformkit/execution/test_schedule_revise.py (NEW, 284 lines, 31 tests)
- tests/platformkit/execution/test_schedule_revise_e2e.py (NEW, 248 lines, 22 tests)
- docs/evidence/harness/S621_memo_inventory.py (NEW, 57 lines; matched by .gitignore:588 docs/evidence/harness/**, so it needs git add -f, as S625_terminal_probe.py was)
- docs/evidence/harness/S621_schedule_revise_2026-09-30.md (this memo)

No new JSON seal or fixture, so no .gitattributes line. No existing module was edited. Tests pin no git ref; the only committed-byte assertion is the 2026-09-30 served file sha f34f8ac3...bab9, which is dated evidence, not a module.

## NOT VERIFIED

- No real run: the CLI was never executed against data/cache roots, the real out-dir or the real pointer; build_schedule was always an injected writer, so the live ESPN/Kalshi selection path for 10-01 is exercised only by the landed schedule_d1 tests.
- Whether the G3 events are listed and whether either series is 1-1 before 11:45Z 10-01 is unknown.
- The runners' actual pickup (heartbeat pointer_ok_at advancing) and the 10-01 night scoring the G3 rows are not observed; case 12 runs the landed reader and planner once in a fresh process on tmp files only.
- The Windows open-handle race on os.replace against a live runner read is covered only by an injected PermissionError, not a real sharing violation.
- carried_row_dropped and pointer_write_failed still have no test that reaches them (the landed _admit_capacity never drops a carried row; write_pointer failure was not injected).
- Behaviour after S531 lands: cases 9 and 12 must be re-run then.
- Commit, landing and the contract verifier pass are outside this lane. SHA: NOT CREATED (sandbox); files ready for lane_commit.
