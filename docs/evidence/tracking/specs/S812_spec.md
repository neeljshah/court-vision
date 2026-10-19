# S812 -- an unmapped raw state status is counted per sport and recorded, never a silent pre (PAPER ONLY)

## Premise (measured 2026-10-09 20:5xZ on master 9b40bb209, read-only, in-process)
- local_state_capture_sources.py:130 `_status` = `_ESPN_STATUS.get(name, fallback="pre")` (nba, wnba and soccer rows all route
  through `_espn_scoreboard_states`, line 201); line 253 `_TENNIS_STATUS.get(rows[0].get("status"), "pre")`.
- Probe: `_status(event STATUS_SUSPENDED_NEW)` -> `pre`; `_TENNIS_STATUS.get("STATUS_RENAMED_LIVE", "pre")` -> `pre`. No counter.
- Real construct found while testing: soccer `STATUS_FINAL_AET` / `STATUS_FINAL_PEN` (a final after extra time / penalties) are
  outside the table and land as `pre` today (pinned by test_soccer_leagues.py::test_status_table).
- `_build_row` (local_state_capture.py:25, daemon, not owned) persists a fixed key list, so an extra top-level item key is dropped;
  `state` is persisted verbatim.

## Change (owned files only; capture side; no scoring code changed)
- NEW scripts/platformkit/ingame/local_state_capture_status.py: `espn_name(event)` (the exact expression `_status` read),
  `mapped(table, raw, get, sport)` and `recorded(state, raw)`. A non-empty `str` outside the table -> `report(get, sport,
  "status_unmapped")` (metrics.source(sport).drops_by_reason, i.e. the heartbeat) and status `unmapped`; the raw string is
  recorded as `state.status_raw`. Anything else (mapped string, None, "", non-str) keeps the landed `table.get(raw, "pre")`.
- local_state_capture_sources.py: the ESPN path (line 201) and the tennis path (line 253) call `mapped` / `recorded`.
  `_status(event, fallback)` keeps its signature and behaviour (soccer_leagues.soccer_status calls it) as a one-liner. 299 LOC.
- Counted once per observed event per poll (an event later dropped for another reason is still counted).
- Downstream: an `unmapped` row is neither pre nor live. observation_support_phases.phase raises invalid_status on it (fail
  closed, counted by its census). A sport whose only rows are unmapped polls at the `none` cadence. The capture watchdog
  reports `error_counter_growing:<sport>.drops_by_reason.status_unmapped` while one is observed -- that is the alert.

## Clauses
- V1 Real 10-09 rows (fixture s812_state_rows_2026-10-09.jsonl: tennis wta:185294 live, nba 401898392 live): the mapped
  string reproduces the real row's status and state exactly, with status_unmapped 0.
- V2 An unknown tennis / nba / wnba string gives status `unmapped`, state.status_raw = the raw string, status_unmapped
  counted under that sport only. Soccer FINAL_AET / FINAL_PEN give the same under soccer.
- V3 `_build_row` of an unmapped item persists status `unmapped` and state.status_raw, same key set as the real row.
- V4 Every string in _ESPN_STATUS and _TENNIS_STATUS maps exactly as before with no counter; None, "" and 7 keep `pre`.
- V5 The new tests fail on master's sources module (premise reproduced by test).
- V6 Existing per-file tests touching the sources module pass, except the three params that pin the premise
  (test_soccer_leagues FINAL_AET/FINAL_PEN -> pre, test_wnba_registration STATUS_UNRECOGNIZED -> pre): not owned, PROPOSED
  one-word diffs in S812_RESULT. local_state_capture.py, soccer_leagues.py untouched. <= 300 LOC.
- V7 No $/edge language; PAPER ONLY. Adoption: armed, pending the dispatcher's state2 relaunch.

## Fix round 1 (adversarial REJECT on 2b48c1233: M13 survived; M2/M14 survived only because get.source overrides the sport)
- V8 A competition status STATUS_IN_PROGRESS beside an event status STATUS_RENAMED_LIVE gives live, no status_raw, count 0
  (competition read first). The unmapped tests delete get.source so the sport argument itself names the counter.

ACCEPTANCE RULE: V1-V8 all hold on the branch diff + per-file test output.
