# S814 -- soccer AET / PEN finals are finals; an MLB or NFL raw status outside its table takes the S812 unmapped path (PAPER ONLY)

## Premise (measured 2026-10-12 13:4xZ on master 81a741889, read-only)
- local_state_capture_sources.py:32-33 `_ESPN_STATUS` has no STATUS_FINAL_AET / STATUS_FINAL_PEN entry: since S812 a soccer match
  decided after extra time or penalties is recorded `unmapped` (status_unmapped counted) and before S812 it was `pre`.
  test_soccer_leagues.py::test_status_table pins ("FINAL_AET", "pre", "unmapped") / ("FINAL_PEN", ...) and
  test_local_state_capture_sources_s812.py::test_soccer_extra_time_finals_are_counted_not_pre pins `unmapped`; S812_RESULT
  (its two NEW GAP lines) named both as this row's retargets.
- :142 `mlb_discover` and :177 `_mlb_poll` use `_MLB_STATUS.get(abstractGameState, "pre")`; :287 `_nfl_league_poll` uses
  `_NFL_STATUS.get(row.get("status"), "pre")`, and domains/nfl/ingest_nfl_states.py:204 `normalize_scoreboard` emits
  `_STATUS_MAP.get(name)` = None for an ESPN status name outside its eight entries. So an unknown MLB abstractGameState or an
  unknown NFL / NCAAF ESPN name is recorded as `pre` with no counter (S812 named these sites as outside its scope).
- No shard holds a FINAL_AET / FINAL_PEN row to copy (the raw string was not stored before S812; S812 was adopted by the
  13:26Z 10-12 logon relaunch and no such match has been captured since). Fixture = three real FINAL rows copied verbatim
  (soccer ger.1:401884781 10-09, mlb 849826 10-07, nfl 401872964 10-06) plus the ESPN status names.

## Change (owned files only; capture side; no scoring code; soccer_leagues.py is seal-pinned by the S490 addendum and is NOT edited)
- `_ESPN_STATUS` gains STATUS_FINAL_AET -> final and STATUS_FINAL_PEN -> final (soccer_leagues.soccer_status reads this table
  through `_status`, so its answer for those two names changes from pre to final without an edit to the pinned file).
- `mlb_discover`: `mapped(_MLB_STATUS, abstractGameState, get, "mlb")[0]` -- a schedule row carries no state, so an unknown
  string is counted (status_unmapped under mlb) but not recorded.
- `_mlb_poll`: `status, raw = ("delayed", None) if delayed else mapped(_MLB_STATUS, abstractGameState, get, "mlb")`; the row
  state is `recorded(state, raw)`. The `delayed` precedence is unchanged and counts nothing. Two dict lines folded so the
  module stays at 300 lines.
- `_nfl_league_poll`: `mapped(_NFL_STATUS, row.status, get, source)` when the normalizer gave a status, else
  `mapped({}, _comp_status_name(event), get, source)` (source nfl or ncaaf): a raw ESPN name never meets the normalized
  table, so a competition name that happens to spell a normalized word ("final", "in") is counted unmapped too
  (contract tier correction 1). `_comp_status_name` reads competitions[0].status.type.name, exactly the field
  normalize_scoreboard reads (not the event-level name, so a known event-level name can never be recorded unmapped);
  the row state is `recorded(..., raw)`. A competition with no status name keeps `pre` as before.
- Counting: `status_unmapped` counts OBSERVATIONS, not distinct games -- each mlb_discover fetch (two dates per schedule
  refresh, so a game listed on both adds 2) and each GUMBO poll of a game in an unknown abstractGameState adds 1; this is
  S812's "once per observed event per poll" (contract tier correction 3).
- Downstream (S812's disclosed effects now also hold for mlb / nfl / ncaaf; adversarial tier correction 2):
  observation_support_phases.phase refuses an `unmapped` row as invalid_status (counted) where the old silent `pre` counted
  as the PRE phase; an nfl / ncaaf scoreboard whose only rows are unmapped polls at the `none` cadence (300 s instead of
  60 s); an mlb game in an unknown abstractGameState keeps its 60 s poll cadence and is never pruned as final; mlb_discover
  counts a game whose poll records it `delayed` (the discover row has no detailedState to check).
- `_ESPN_STATUS` is also the nba / wnba table, so STATUS_FINAL_AET / STATUS_FINAL_PEN map to final there too (ESPN does
  not emit them for basketball; disclosed, contract tier correction 4).
- `_MLB_STATUS` and `_NFL_STATUS` byte-identical. Retargets (named in S812_RESULT): test_soccer_leagues.py two params ->
  ("final", "final"); the S812 soccer AET test asserts final / no status_raw / count 0 (renamed ..._since_s814).
- Adoption: the next state2 relaunch (dispatcher or owner, own UTC date, between games); until then the running child
  (launched 13:26:55Z 10-12 from master 81a741889) records AET / PEN as unmapped and MLB / NFL fall-through as pre.

## Clauses
- V1 soccer STATUS_FINAL_AET / STATUS_FINAL_PEN: soccer_status == the poll row status == the real 10-09 row's status
  (final), the row's state key set equals the real row's, no status_raw, status_unmapped 0. Every other _ESPN_STATUS string
  maps as before; an unknown soccer name still gives unmapped + status_raw + count 1.
- V2 mlb poll: abstractGameState Final reproduces the real row's status with no counter and no status_raw; a string outside
  the table gives unmapped, state.status_raw = the raw string, status_unmapped +1 under mlb only; a detailedState containing
  "delay" keeps `delayed` with no counter and no status_raw.
- V3 mlb discover: the four table strings and None map as before with no counter; an unknown string gives unmapped + count 1;
  a discover row still carries no state key.
- V4 nfl: STATUS_FINAL through the real normalizer reproduces the real row's status and its exact state key set; a
  competition-level ESPN name outside the normalizer's map (STATUS_SUSPENDED_NEW, and the normalized words "final" / "in"
  used as raw names) gives unmapped, status_raw = that name, count under nfl (league nfl) or ncaaf (league college-football)
  only; a competition with no status name keeps pre with no counter whatever the event-level status says.
- V5 `_MLB_STATUS` / `_NFL_STATUS` byte-identical; the sources module <= 300 lines; local_state_capture.py,
  soccer_leagues.py, local_state_capture_status.py and domains/nfl untouched.
- V6 The new test file fails on master's sources module (premise reproduced by test); the two retargeted files and
  test_state_capture_sources.py pass on the branch.
- V7 No money or return language; PAPER ONLY; adoption named (state2 relaunch).

ACCEPTANCE RULE: V1-V7 all hold on the branch diff + per-file test output.
