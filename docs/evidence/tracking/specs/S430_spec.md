GAP S430 | sport nfl (ESPN ROUTES sports nfl / ncaaf / nba / soccer; mlb, tennis untouched) | worktree harness-h87 (master-based) | log cx_s430_nfl_utc_day
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md B, Q1-Q9, A9, S1, S2, S4. WHERE (S1): every step LOCAL in the worktree; no pod, no network in build or tests.
SINGLE PROBLEM: ESPN lists a game on its US (Eastern) date; the writer asks ESPN for --date alone and keeps a game only when its UTC start is on --date, so every
primetime NFL game (Thu / Sun / Mon night, 20:xx ET = the next UTC date) is refused under one date and absent under the next: unreachable.
BINDING BEFORE-CONDITION (S2, re-verified on master 7300afdb5 2026-09-24), quote with file:line: (a) forward_schedule_sources.py:18 ESPN_URL `...scoreboard?dates={date}`,
:124-126 one URL per call `ESPN_URL.format(path=ROUTES[sport], date=day.replace("-", ""))`; (b) forward_schedule_writer.py:191 `fetched[sport] = fetch_schedule(sport, day,
records, opener)`, :193 `lower = _stamp(day + "T00:00:00Z")`, :219-221 `start = _stamp(game.get("scheduled_start_utc"))` / `if not lower <= start < lower + 86400:` /
`raise ValueError("outside_utc_date")`; (c) forward_schedule_sources.py:87-89 the LANDED minute-precision step (`YYYY-MM-DDTHH:MMZ` gets ":00Z", counted
espn_minute_precision_normalized); (d) the writer is exactly 300 LOC and its local _Metrics class duplicates the one in sources; (e) landed assertions pinning ONE ESPN
request per writer run: tests/platformkit/execution/test_forward_schedule_sources.py:108, :122, :174 (and :146, two calls for mlb+nfl) -- hence the opt-in flag.
PROBE (orchestrator, 2026-09-24T18:23Z, live ESPN, empty scratch book/state roots, --sports nfl --family maker_forward --schedule-source live): --date 2026-09-24 -> games_seen
1, refused_by_reason {"outside_utc_date": 1}, record_counts {"espn_minute_precision_normalized": 1, "missing_book_archive": 1, "missing_state_archive": 1}, written 0 (url
?dates=20260924, 22789 bytes, sha256 d29a1038b8c422c8345870ee87b5ad58509e8da4d17d4943a5e1184ec0ef8617); --date 2026-09-25 -> games_seen 0, refused {}, written 0 (?dates=
20260925, 5193 bytes, sha256 d32bdedc9f799a39a5728d8bd0c52d81096c889f596fde3cdd8b5d43bf46a8c5). Event 401872948 (= competition id) "Atlanta Falcons at Green Bay Packers",
date "2026-09-25T00:15Z", pre / STATUS_SCHEDULED, home GB, away ATL, no timeZone. PREMISE CORRECTIONS: (i) the WRITER already parses minute-precision starts (c; the probe
counted it and reached outside_utc_date); the S413 "unavailable" is the CAPTURE path (local_state_capture_dates.venue_instant("2026-09-25T00:15Z") is None, measured),
untouched here, a follow-up for its owner; the parse item is a regression pin. (ii) docs/evidence/forward/schedules/2026-09-23_maker_forward_full_selection.json (6 MLB
rows, selected_at 2026-09-22T17:03:57.979979+00:00) was written with schedule_source live, its statsapi body uncommitted: "reproduce from the archive" becomes test 4g.
CHANGE (owned: forward_schedule_sources.py + forward_schedule_writer.py MODIFIED additive; NEW tests/platformkit/execution/test_forward_schedule_utc_day.py + fixtures/s430_espn_nfl_atl_gb.json; memo):
1. sources: NEW fetch_schedule_utc_day(sport, day, counts, opener), ROUTES sports only (mlb / tennis raise ValueError): previous US date FIRST, then the requested date, each
   via the landed _fetch_schedule unchanged; rows gain schedule_query_date (YYYYMMDD); previous-date rows kept only when parse_venue_time(scheduled_start_utc) is in
   [day 00:00Z, +86400) (counted listed_on_previous_us_date), else counted previous_us_date_other_day and dropped (never a refusal); requested-date rows pass exactly as
   fetch_schedule returns them. Dedupe by game_key across payloads: same start = one row (espn_listed_twice); differing starts = one row _refusal event_start_conflict,
   both texts kept; byte-identical under either order. Receipt = the requested-date receipt's keys verbatim, response_end_utc = the LATER of both ends (the writer's :202
   cutoff then covers both), plus query_receipts {YYYYMMDD: receipt} and kept_from {game_key: YYYYMMDD}.
2. writer: `--utc-day-window` (default OFF = byte-identical); build_schedule kw utc_day=False; :191 picks it for ROUTES sports; import _Metrics from sources (<= 300 LOC).
3. fixture: ATL at GB VERBATIM from the probe body (sha above): id, date, name, competitions[0] id/date/status/competitors, keyed {"20260924": [...], "20260925": []}.
4. tests (fake opener keyed on dates=, clock injected as landed tests do): (a) --date 2026-09-25 + flag -> ATL at GB WRITTEN once (tmp books KXNFLGAME-26SEP24ATLGB-GB /
   -ATL, state row game_key 401872948 date 2026-09-24 home GB away ATL), kept_from 20260924, listed_on_previous_us_date 1; (b) --date 2026-09-24 + flag -> outside_utc_date
   1, written 0; (c) flag OFF both dates -> the probe counts; (d) "T00:15Z" and "T00:15:00Z" same scheduled_start_utc via the real parser; (e) identical / conflicting
   duplicate, both orders; (f) previous-date game on its own UTC date -> other_day; (g) MLB: statsapi construct from the six committed rows (gamePk = game_key, gameDate =
   scheduled_start, officialDate 2026-09-23, home = ticker suffix) + books, --now = committed selected_at, flag ON and OFF -> rows equal the file; (h) tennis + flag
   unchanged; (i) mlb / tennis raise. Memo docs/evidence/harness/S430_nfl_utc_day_2026-09-24.md: quotes, probe verbatim, both corrections, receipt schema, A9 (path,
   bytes, sha256 of fixture and committed file); ends NOT VERIFIED (the live Sunday / Monday slate with the flag from the main tree; the capture-path defect).
ACCEPTANCE RULE: metric = ATL at GB rows written / refused per requested UTC date; before = probe (0 written on both dates); bar = written exactly once, 2026-09-25 only,
  2026-09-24 outside_utc_date 1; n = 15 (CONSTRUCT: 4a1 4b1 4c2 4d1 4e4 4f1 4g2 4h1 4i2); eye check = n/a (S-row); reproduction = run the new test file alone, read its
  printed census per case; must not move = test_forward_schedule_{sources,writer,game_key,team_set,fix1f,dates}.py byte-identical and passing one file at a time;
  _rows, _game, _fetch_schedule, fetch_schedule byte-identical; every refusal reason keeps its meaning; no bar moved.
CONTROLS: NON-TAUTOLOGY -- every event in either payload is covered, none excluded, previous-date off-day events counted. PREPARE; no capture code, forward_replay*, runbook or
data/ writes; no STOP files; per-file tests only; --help works; ASCII; Q6 calibration language only, no words for a betting advantage. COMMIT: explicit pathspec, no push; NEVER PARK.

AMENDMENT 1 (2026-09-24 19:1xZ real clock; binding; round 1 on the codex build (249 tests across seven files in the worktree; ATL at GB written for 09-25 and refused for 09-24): Opus tier 2 ACCEPT WITH CORRECTIONS; sol pending): (a) PARSE FAILURES ARE NOT "OTHER DAY": in the previous-US-date pass a row whose start is None keeps its existing _refusal (so invalid_schedule_game still surfaces with the flag on); a row with no refusal and an unparseable start is counted previous_us_date_start_unparsed and dropped; previous_us_date_other_day is reserved for rows whose start parses and falls outside the requested UTC day; one test each. (b) MEMO: state that venue_instant("2026-09-25T00:15Z") -> None on the capture path is recorded as a follow-up for the capture code's owner and is NOT fixed here. (c) recorded NEW GAPs: the fixture is a 749-byte extract of the spec-quoted fields, not the verbatim ESPN body (disclosed); a failed previous-date query is only counted (schedule_network_failure) so primetime games go missing silently under the requested date's HTTP 200 -- a follow-up row; a previous-date listing outside the window is dropped before de-duplication so a start conflict with the requested-date listing is not flagged (matches the spec).
