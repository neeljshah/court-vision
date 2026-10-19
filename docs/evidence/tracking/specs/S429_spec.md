GAP S429 | sport all captured | worktree harness-h84 (master-based) | log cx_s429_schedule_d1
# D+1 schedule automation: one command writes tomorrow's prospective schedule, served subset, capacity note and run record
CONTRACT: VERIFIER_CONTRACT.md B1-B10, Q1-Q9, A9, S1, S2, S4 -- self-check before reporting. WHERE (S1): build + tests = local, small, stdlib; NO network in any test (inject the writer, stub urlopen). The live run (network: the writer's MLB statsapi / ESPN fetch) is the orchestrator's. Pod OFF.
PREMISE (S2, measured on master 2026-09-24 17:4xZ; the memo quotes each file:line): (a) `ls scripts/platformkit/execution/schedule_d1.py`
fails. (b) forward_schedule_writer.py:171-173 `build_schedule(day, sports, books_root, state_root, family, now=None, *,
schedule_source="live", opener=None) -> tuple[list[dict], dict]`; :191 stamps selected_at AFTER the fetch; :196 reads `Path(books_root)
/ "kalshi" / sport`, :210 `Path(state_root) / "state" / sport`; :66-67 count missing_book_archive; :294 census `<out>.census.json`.
(c) capture_scheduler.py:111 sorts (scheduled_start, game_id, ticker); :113 raises if any three consecutive starts span < 3600 s.
(d) NO landed module applies the capacity subset: `git grep capacity_note -- scripts` finds only a reader (focus_window_admission.py:210);
the 2026-09-23 served file + note were hand-written in commit e5941aa12. This row lands that rule as code. (e) forward_replay_qualification
.py:21 `WEEK_GAMES, SPORT_GAMES, FILL_GAMES = 4, 30, 30`, used only at :256 `verdict="PASS" if r["qualified_games"] >= WEEK_GAMES`: a
qualification bar over the week ledger; the writer holds no floor. (f) venue_time.py:45 parse_venue_time.
FALSE PREMISE CORRECTED: the 17:43Z zero (mlb no_kalshi_event_for_date_and_team 8, missing_book_archive 1) passed roots one level too
deep for (b). Re-run 17:50Z with `--books-root data/cache/ingame_books_local --state-root data/cache/ingame_state_local_v2`: 2026-09-24 mlb
written 5, nfl 0; 2026-09-25 mlb written 6 (duplicate_game_or_ticker 2, missing_directional_team_evidence 3, outside_utc_date 5), nfl 0.
kalshi/mlb/2026-09-23.jsonl (163,193,337 B) holds 30 KXMLBGAME 26SEP25 tickers: D+1 discovery is present although the capture is down.
CHANGE (NEW files only; writer, scheduler, replay NOT edited):
1. scripts/platformkit/execution/schedule_d1.py (<= 300 LOC): `--now <aware ISO|clock> --sports mlb,nfl,nba --books-root --state-root
 --family maker_forward --out-dir docs/evidence/forward/schedules [--rewrite <reason>]`. D1 = UTC date of --now (parse_venue_time;
 unzoned = invalid_now) + 1 day. Refusals, in order, each ONE printed JSON line, exit 2, NO file written: archive_root_missing (any
 `<books-root>/kalshi/<sport>` or `<state-root>/state/<sport>` absent); already_written (an output below exists, no --rewrite);
 discovery_absent (zero entries AND a sport has missing_book_archive or no_kalshi_event_for_date_and_team) else nothing_schedulable
 (zero entries), both copying every sport's refused_by_reason + record_counts VERBATIM. Else build_schedule(D1, ..., None,
 schedule_source="live") -- --now is never the cutoff. Write `<D1>_<family>_full_selection.json` (+ census); served `<D1>_<family>.json`
 = greedy over the (c) order keeping a row iff its start minus the second-last kept start >= 3600 s, then passed through
 capture_scheduler.schedule_rows; `<D1>_<family>.json.capacity_note.json` with the six 2026-09-23 keys, rule string verbatim,
 capacity_subset_selected_at = clock after the writer returns; `<D1>_run.json` = argv, now, D1, instants, sha256 + bytes per written
 file, schedule receipts' sha256, per-sport counts. --rewrite renames each prior file `*.superseded_<YYYYMMDDTHHMMSSZ>`, records the
 reason. Strict-int counts; refusals counted, never clamped. Commits NOTHING (the orchestrator commits by pathspec); never touches a
 capture, a STOP file or data/registry. 2. tests/platformkit/execution/test_schedule_d1.py (fake writer, fake archive dirs, frozen
 clock). 3. Memo docs/evidence/harness/S429_schedule_d1_2026-09-24.md (A9 paths + bytes); ends NOT VERIFIED (no live run here).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = enumerated cases passing / 13: D1 at 23:59:59.999999Z, 00:00:00Z, a -04:00 offset, unzoned refused; archive_root_missing;
                  discovery_absent reasons verbatim; nothing_schedulable; already_written; --rewrite superseded + reason; 2026-09-23 served +
                  not_served reproduced from a REAL-ROW literal equal to the committed full selection; run-record sha256 == files; 2
                  entries (< WEEK_GAMES) still written; writer called with now=None, live
  before = 0 / 13 (module absent; subset hand-applied e5941aa12) | bar = 13 / 13, one test file run alone | n = 13 (CONSTRUCT)
  eye check = n/a (S-row); reproduction = re-derive served / not_served from the committed full selection by hand
  must not move = the four modules of (b), (c), (e), (f) and every committed docs/evidence/forward/schedules/2026-09-2* file, byte-identical
NON-TAUTOLOGY: the fixture is the committed selection, no row excluded. Q6: calibration language only, no words for a betting advantage.

AMENDMENT 1 (2026-09-24 19:2xZ; binding; round 1 on the codex build: codex gpt-5.6-sol REJECT (three blockers; its sandbox could not run the tmp_path tests -- the orchestrator ran the file: 29 passed), Opus tier 2 ACCEPT with four NEW GAP lines): (a) OUTPUT LOCATION: --out-dir is resolved (os.path.abspath AND Path.resolve) and refused with out_dir_forbidden (exit 2, nothing written, no writer call) when it lies beneath the registry directory or the cache directory under data, either archive root passed on the command line, or any directory containing a capture lock (_capture.lock) or a *.heartbeat.json; regression per forbidden location. (b) TRANSACTIONAL WRITE: every output (full selection, census, served subset, capacity note, run record) is staged to <name>.staging_<instant> first; only when EVERY staged write has succeeded and been fsynced are they renamed into place in one pass; on any failure before the rename pass all staged files are removed and the refusal io_error is printed with nothing else written; regression: inject a failure at each write position (1..5) and assert the output directory listing and every existing file's sha256 are unchanged afterwards. (c) EVERY INSTANT THROUGH THE PARSER: started_at, completed_at and selection instants are validated through scripts.platformkit.execution.venue_time.parse_venue_time immediately when produced (including an injected clock), and any invalid value refuses invalid_now before any write; regression: an injected clock returning NOT-A-TIMESTAMP for started_at refuses invalid_now with nothing written. (d) from the tier 2 NEW GAPs: a writer row whose selected_at is later than the post-fetch clock is REFUSED as future_selected_at with the count (no longer silently dropped); a census with no schedule_receipt is counted and refused as missing_schedule_receipt; the exact-3600 s boundary (22:00 / 22:30 / 23:00 all kept; 22:59:59 drops the third) gets a test; two --rewrite runs within one UTC second refuse superseded_exists (documented, not fixed).

AMENDMENT 2 (2026-09-24 18:3xZ real clock; binding; round 2: codex sol REJECT (one blocker, one memo correction); sol independently reproduced the six-row capacity subset and passed every other focused item): (a) STAGING CLEANUP COVERS THE PARTIAL FILE: _stage records its path as soon as the exclusive open succeeds and unlinks that path on ANY subsequent OSError (write, flush or fsync), so a failure after creation never leaves <name>.staging_<instant> behind and the directory listing is unchanged; the five-position regression injects the failure INSIDE the real _stage after creation (os.fsync patched to raise at position k), not before the call. (b) MEMO line 119: five outputs are encoded and staged; four non-self-referential payloads are hashed into the run record (the run record cannot hash itself); every staged file is removed on failure.
