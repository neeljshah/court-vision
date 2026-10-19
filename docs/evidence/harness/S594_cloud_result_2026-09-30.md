# S594 cloud result, 2026-09-30 (desk-improve routine, cloud Ubuntu clone)

Row: S594. The serial state tick lets one slow sport (tennis) stall every live poll.
Branch: `cloud/S594-2026-09-30`. Base: trunk a60dcb09a. NOT landed, NOT adopted.
Spec: `docs/evidence/harness/S594_spec_2026-09-30.md` (spec plus AMENDMENT 1).
PORTABLE: yes for the code and tests. Adoption is WINDOWS: a state2 restart on the recorder box.

## What changed

Both options are OPT-IN and default OFF. With both off, behaviour equals the old blob (case 5).

- `--slow-lane-sports tennis` (`slow_sports`): tennis polls on a daemon worker thread with its own StateClient (own session, pacer, metrics and S535 holds). The main thread submits the poll when it is due and keeps ticking. It harvests on a later tick, where the metrics are merged once and the items go through the unchanged per-item loop; `tick_start_ts` is the tick that submitted the poll. A result still in flight across a UTC rollover is dropped and counted as `lane_stale_day_drops`. A failed submit is counted as `lane_submit_errors`, and `last_polled` is stamped just as for a failed serial poll.
- `--wake-on-due` (`wake_on_due`): the loop sleeps until the earliest due time among idle tasks (with a 0.01 s guard), instead of fixed 5 s ticks. After a failed commit it keeps the legacy sleep.
- Always on, additive heartbeat keys: `task_split` gives per-sport task seconds (main, plus lane seconds and lane_rate for a lane sport) as a fixed-bin histogram. `tick_split` gives the prepare and commit seconds. They measure the per-sport tick-duration split the row asks for once the change is adopted.
- `_merge_schedule` moved verbatim (byte-identical body) to `local_state_capture_merge.py` to stay within the line limit, and is re-imported.
- Files and lines: `local_state_capture.py` 274, `local_state_capture_lanes.py` 201 (new), `local_state_capture_merge.py` 32 (new), `local_state_capture_commit.py` 84.
- Tests (new): `tests/platformkit/ingame/test_state_capture_lanes.py`, `test_state_capture_lanes_units.py`, and the fixture `s594_lane_fixture.py`. The spec named one test file; it became two plus a fixture to keep every file within 300 lines.
- Seal-pinned files (`local_capture_writer.py`, `capture_watchdog.py`) are untouched. No `PREREG*.json` names any changed file. No constants moved: `_CADENCE`, `TICK_SEC`, `ROUTE_DEADLINE_SEC` and `ROUTE_HOLD_MIN_SEC` are unchanged.

## Acceptance: 16 of 16 construct cases, n = 16 (CONSTRUCT)

The headline case (case 1): a tennis poll blocked for 40 s with live nba, over 16 ticks.
- **With the lane plus wake:** 8 nba polls with every gap exactly 7.01 s, and every one committed on its own tick.
- **Old blob a60dcb09a (loaded via git show):** every nba gap is 40 s or more. The old blob therefore fails the cadence bound, and the new serial path matches it.
- **Lane without wake:** 10.0 s gaps, the same as a fast serial tick, so tennis adds nothing.

Case 6: with wake on, a live poll comes every 7.01 s; the old blob polls every 10.0 s (two ticks). An mlb wake unit case was added in the fix pass.

Where each case lives:

| File | Cases |
|---|---|
| lanes file | 01 (x3), 02, 05 (x2), 06, 08, 10, 11, 12 (x2) |
| units file | 03 (x2), 04, 06-mlb, 07, 09, 13, 14, 15 (x3), 16 |

## Per-file test commands

Each command is `python3 -m pytest <file> -q -p no:cacheprovider`, one file per process. The first counts are on the final tree; the file list was also run via `tools/desk_bin/run_files.py`.

New files:
- `test_state_capture_lanes.py`: 13 passed.
- `test_state_capture_lanes_units.py`: 12 passed.
- Both were run 10 times more after the fix, and 25 times more before it: all clean.

Existing files, all passed:

| File | Result |
|---|---|
| test_local_state_capture | 19 |
| _differential | 5 |
| _schedule | 367 |
| test_state_capture_commit | 11 |
| test_state_capture_sources | 240 |
| test_state_route_deadline | 16 (1 skipped: base sha absent in the shallow clone) |
| _real_caller | 7 |
| _pacer | 4 |
| test_state_rollover_carry | 13 |
| test_tennis_start_strip | 4 |
| tests/platformkit/test_loc_rail_scope | 1 |

Also run on candidate 3b644277, per the verifiers, all green: test_state_capture_recovery 25, test_mlb_live_feed_state 73, test_nba_pbp_source 68, and 16 more files. 18 test ids fail identically on trunk a60dcb09a and on the branch in this shallow clone (stale sha256 pins or missing git history), so this box cannot judge them:
- test_state_capture_io: 2
- test_wnba_registration: 4
- test_local_state_recovery_growth: 3
- test_nba_pbp_starters and test_nba_pbp_starters_census: 3
- test_state_capture_fix_1q: 1
- execution/test_registry_scorer_e_s471 and _1b: 5

Some of these are capture byte-identity pins, so a laptop session must re-run them on a full clone before landing.

## Verdicts (codex unavailable; independent Opus sub-agents for every tier)

- **Pre-build critic (astra):** REVISE, 14 items, all folded as AMENDMENT 1. The notable changes: both options became opt-in, the wake falls back to the legacy sleep after a failed tick, a daemon thread replaced the executor, and a synthetic LIMIT profile was added.
- **CONTRACT tier:** ACCEPT WITH CORRECTIONS. The one correction was that this memo was missing; C1-C14 were verified as implemented and `_merge_schedule` as verbatim.
- **ADVERSARIAL tier:** ACCEPT WITH CORRECTIONS. 27 mutants were tried and killed, apart from the inert ones and these four survivors:
  - g: `WAKE_GUARD_SEC` 0.0, because the assert was circular;
  - o3: production lane factory untested;
  - o6: mlb wake untested;
  - o7: `defer_schedule` unpinned.
- **Fix pass (one, as allowed):**
  - hard-coded the 7.01 s literal;
  - pinned `defer_schedule`;
  - added the production-factory test;
  - added the mlb wake unit case;
  - the session guard now also compares the raw session;
  - `last_polled` is now stamped on a submit failure (the contract-tier gap: with wake on, a failing submit would otherwise retry every 0.5 s).

  After the fix, mutants g, o3, o6, o7 and "no stamp" each turn a test red. The corrections were checked by re-running both files and a targeted mutant re-check by the builder. The tiers did not re-run; this is disclosed.

## LIMIT (C1, synthetic timing receipt absent)

No reproducible timing receipt is archived; this synthetic limit is NOT VERIFIED.

## MANDATORY DISCLOSURES

- No live figure is measured here: the 40 s tennis stall is modelled, not observed. ESPN, MLB and NBA hosts are blocked in this box, and there is no capture archive.
- The main-thread tennis ingest and commit cost is NOT PROFILED; no timing receipt is archived.
- GIL: worker contention can delay the main thread; recorder-side scheduling delay is NOT VERIFIED.
- With wake on, live request cadence follows configured due times and there can be more ticks (each with a deepcopy, a sync and heartbeat writes).
- The lane adds a second ESPN pacer for tennis (2 requests per poll). A host-wide 429 on one pacer does not slow the other.
- A lane poll in flight at exit or across a UTC rollover is dropped: at most one poll of the ending day.
- If `_prepare_tick` raises after a harvest, that one poll is lost after its metrics were merged. This path is not enumerated (contract NEW GAP).
- Rows remain at-least-once after a failed sync, as on the serial path (case 13).
- The worker touches only the lane client, its session and metrics, its getter, the POLLERS dict (read only) and the pure tennis parser. SOURCE_METRICS is untouched (case 16).
Calibration and execution-quality language only.

## NOT VERIFIED

- The live poll-gap improvement: MLB, NFL, NCAAF and NBA p50/p90 against the 7 s cadence. It needs a live state2 capture after adoption, and the S592 census re-run on a post-adoption window.
- Tennis ingest cost on the main thread with real ESPN payloads; the recorder box's CPU and GIL behaviour on Windows.
- The production `lane_client_for` against real ESPN (the unit test pins policy carry-over only).
- The 18 trunk-red ids above, on a full clone.
- Whether the live 36 s tail is tennis at all. The new `task_split` and `tick_split` heartbeat keys are how to measure that after adoption.

## ADOPTION (laptop session, WINDOWS)

1. Land the branch after review.
2. Restart state2 on the recorder box between games (06:00Z-16:00Z, no served game within 60 min), adding `--slow-lane-sports tennis --wake-on-due` to the state argv. This is a copy of `relaunch_state2_s535_2026-09-29.ps1` with a new tag; it is not written here. Turning the options on is the owner's flag decision; this routine cannot restart the box.
3. After the restart, check:
   - the tennis heartbeat `task_split.lane.n` rises;
   - `lane_submit_errors` and `lane_stale_day_drops` stay at about 0;
   - re-run the S592 census on a window after adoption.

## NEW GAPS (from the verifiers, not fixed here)

- There is no heartbeat signal for a hung lane worker (no in-flight age or timeout); add `lane_inflight_s`.
- The old-blob cases skip in a clone that lacks a60dcb09a; the acceptance run should count a skip as a fail.
- The `_prepare_tick` raise after a harvest loses one poll (above).
- The production factory has no end-to-end test through `_main`.
