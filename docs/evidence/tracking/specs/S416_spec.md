GAP S416 | sport all captured | worktree harness-h69 (master-based) | log cx_s416_forward_schedule_dates
# Forward schedule sources honour the requested day: the ESPN fetchers take the date, NFL from the offline parquet, per-ISO-week counts

SINGLE PROBLEM: the landed source takes a `day` argument and DROPS it for four sports, so nfl / ncaaf / nba / soccer always return
today's scoreboard; the landed writer (forward_schedule_writer.py:279-296, `--date`) can therefore write a prospective schedule for mlb
and tennis only (.planning/direction/game_supply_2026-09-22.md, "The forward schedule path, and its hard limit"). TARGET_WEEKS is 8 and
nfl is the only family with an authoritative count, in an offline file nothing reads (.planning/DIRECTION_2026-09-22.md sections 4, 8).

BINDING BEFORE-CONDITION: quote from master (a) scripts/platformkit/execution/forward_schedule_sources.py:17-21 -- MLB_URL
`...schedule?sportId=1&date={date}&hydrate=team`, ESPN_URL `https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard`,
TENNIS_URL `.../tennis/{league}/scoreboard?dates={date}`, ROUTES with soccer "soccer/eng.1"; (b) :112-116 VERBATIM --
`def _fetch_schedule(sport: str, day: str, counts: Counter,` / `url = (MLB_URL.format(date=day) if sport == "mlb" else` /
`TENNIS_URL.format(league=tour, date=day.replace("-", "")) if sport == "tennis" else` / `ESPN_URL.format(path=ROUTES[sport]))` -- the
ESPN branch never consumes `day`; (c) :100-110 fetch_schedule (tennis loops atp + wta and merges both receipts); (d) :52-98 _game (the
ESPN key is raw["id"], tennis comp["id"]; `pre` from the status block) with scripts/platformkit/ingame/local_state_capture_dates.py
schedule():99-100 (`scheduled_start_utc`, the only per-game UTC start); (e) forward_schedule_writer.py:279-296 main (--date, --sports,
--schedule-source live|archive) and :24-31 WINNER_SERIES with `"ncaaf": ()`; (f) forward_replay_qualification.py:21 `WEEK_GAMES,
SPORT_GAMES, FILL_GAMES = 4, 30, 30` and family_week_ledger.py:18 `TARGET_WEEKS = 8`; (g) tests/platformkit/execution/
test_forward_schedule_sources.py:86 `assert calls == [sources.ESPN_URL.format(path=sources.ROUTES[sport])]` -- the ONE landed
assertion that pins the day-blind URL; (h) data/nfl/schedules.parquet columns game_id, season, game_type, week, gameday, gametime,
home_team, away_team, espn (7,548 rows; gameday 1999-09-12 .. 2027-01-10; season 2026 game_type REG = 272 rows, gameday 2026-09-09 ..
2027-01-10) -- the `espn` column holds the ESPN event id, the same identifier _game derives.

CHANGE (owned files: forward_schedule_sources.py (MODIFIED, additive), NEW scripts/platformkit/execution/forward_schedule_supply.py,
tests/platformkit/execution/test_forward_schedule_sources.py (MODIFIED, the single assertion at :86), NEW tests/platformkit/execution/
test_forward_schedule_dates.py, NEW tests/platformkit/execution/fixtures/s416_espn_scoreboard.json + s416_nfl_rows.json, memo below):
1. forward_schedule_sources.py: ESPN_URL gains the `?dates={date}` parameter TENNIS_URL already carries and the branch at :116 passes
   `date=day.replace("-", "")`. That is the ONLY change to the landed module -- ROUTES, _rows, _game, fetch_schedule's signature and
   every receipt field stay as they are. Every returned game whose `scheduled_start_utc` UTC date differs from the requested day is
   marked `_refusal` "day_mismatch" and counted `day_mismatch` in the caller's Counter (never dropped silently, never adjusted); a
   game with no `scheduled_start_utc` is counted `day_unverifiable` and refused the same way.
2. The landed assertion at (g) pins the defect and MUST change to the dated URL; it is quoted before and after in the memo. Every other
   assertion in that file and every line of test_forward_schedule_game_key.py, test_forward_schedule_team_set.py,
   test_forward_schedule_fix1f.py and test_forward_schedule_writer.py stays BYTE-IDENTICAL and passing; if any of those four also pins
   the ESPN URL text, STOP and report a spec conflict rather than editing it.
3. forward_schedule_supply.py (<= 300 LOC): `--start <YYYY-MM-DD> --end <YYYY-MM-DD> --sports <list> --nfl-parquet <path or absent>
   --out <json>`. NFL is read from the parquet where present (game_type "REG", the columns quoted in (h), game_key = str(espn) where
   present else counted nfl_espn_id_absent) and needs NO network; every other sport calls the landed fetch_schedule once per day.
   Emits, keyed by (sport, ISO year, ISO week) taken from each game's `scheduled_start_utc`: games_pre (status "pre"), games_not_pre,
   and refusals by reason (day_mismatch, day_unverifiable, game_key_unavailable, schedule_network_failure,
   invalid_schedule_http_status, invalid_schedule_payload, schedule_game_parse_failure, duplicate_schedule_game), plus weeks_total and
   weeks_at_or_above_week_games computed with the IMPORTED WEEK_GAMES, never a local copy. Strict-int counts; ASCII JSON; order-
   independent over days; the NOTICE 'counts of scheduled games only; scheduled supply is not qualification'. Refuses (exit 3, named
   reason) an end before the start, nfl requested with no readable parquet, a sport outside ROUTES / mlb / tennis.
4. Tests: fixtures constructed from RECORDED payload shapes; no network in any test (the opener is injected, as the landed tests
   already do). Cases: the URL built for a requested day contains `dates=20261005` for each ESPN sport; an event whose date is another
   day -> one day_mismatch and a refused row; an event with no parsable start -> day_unverifiable; the per-ISO-week counts over a
   constructed three-week span; a constructed NFL frame reproduces one week's count and game_key equal to the espn id;
   weeks_at_or_above_week_games reads the imported constant (assert the identity); order independence over days; each refusal reason.
5. Memo docs/evidence/harness/S416_forward_schedule_dates_2026-09-22.md: the before-condition quotes with file:line, the emitted
   schema, the before/after of the one changed assertion, and the statement that the ESPN scoreboard's acceptance of `dates=` is
   UNVERIFIED until the orchestrator's real run; ends with NOT VERIFIED.

CONTROLS: PREPARE only -- construct fixtures from recorded payloads; NO network in any test and none by the builder (the orchestrator
runs the real enumeration over 2026-09-28 .. 2026-12-31 and records the counts); the only landed module edited is the additive ESPN
date parameter in item 1 and the single assertion in item 2 -- never forward_schedule_writer.py, forward_capture_bridge.py,
capture_scheduler.py or forward_replay*.py; never write under data/ or data/cache; never touch the live captures or any STOP file.
ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC per file; ASCII; contract Q6 vocabulary; the four untouched
landed schedule test files byte-identical and passing; memo ends with NOT VERIFIED.
