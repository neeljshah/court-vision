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

AMENDMENT 1 (2026-09-22 22:5xZ; binding; the first codex build lane stopped correctly because before-condition (h) names a file
that lives only in the MAIN tree: data/ is gitignored and absent from every worktree). MEASURED BY THE ORCHESTRATOR on the main
tree (pandas, read-only): data/nfl/schedules.parquet has 7,548 rows; columns game_id, season, game_type, week, gameday, weekday,
gametime, away_team, away_score, home_team, home_score, location, result, total, overtime, old_game_id, gsis, nfl_detail_id, pfr,
pff, espn, ftn, away_rest, home_rest, away_moneyline, home_moneyline, spread_line, away_spread_odds, home_spread_odds,
total_line, under_odds, over_odds, div_game, roof, surface, temp, wind, away_qb_id, home_qb_id, away_qb_name (40 shown);
gameday is text from 1999-09-12 to 2027-01-10; season int32 1999..2026; week int32 1..22; game_type text with values
including REG, CON, WC; game_id text such as 2026_18_TEN_HOU; home_team / away_team text codes ARI..WAS; espn is present
(game_key = str(espn) where non-null, else refused as game_key_unavailable and counted). RULING: (h) is satisfied by the facts
above; the lane builds and tests against a CONSTRUCT parquet fixture with exactly these column names and dtypes (written by
the test through pandas into tmp_path; no parquet is committed); a missing parquet at run time refuses nfl_schedule_missing
(counted, exit 3) and never falls back to the network; the orchestrator's real run over 2026-09-28 .. 2026-12-31 happens from
the MAIN tree after landing and is recorded as counts in the memo by amendment.

AMENDMENT 2 (2026-09-22 22:5xZ; binding; the second codex lane stopped correctly on a contradiction: the landed sources module
may change ONLY its ESPN URL date parameter, yet CHANGE lines 29-31 also placed new refusal behaviour in it, which would change
landed assertions at tests/platformkit/execution/test_forward_schedule_sources.py:127 and :290 (invalid_time,
outside_utc_date) through the writer's _refusal propagation at forward_schedule_writer.py:97). RULING: every NEW behaviour lives in
the NEW module (scripts/platformkit/execution/forward_schedule_supply.py): it calls the landed fetchers with the requested day,
compares every returned event's date to the requested day and counts day_mismatch itself, reads the NFL parquet, and emits the
per-ISO-week counts; the landed sources module changes in exactly ONE place -- the ESPN URL gains the requested date -- and the
landed writer is untouched; the landed refusal vocabulary (invalid_time, outside_utc_date) and every landed assertion stay
byte-identical EXCEPT the single URL-format assertion named in CHANGE (its before / after quoted in the memo). WORKTREE RULE
(for every lane): the lane must run from a worktree fast-forwarded to master; a git diff master that shows only the orchestrator's
spec commits means the worktree is behind master, not that unowned files changed -- the orchestrator fast-forwards before
dispatch.

AMENDMENT 3 (2026-09-22 23:1xZ; binding; the third codex lane stopped correctly: the parquet contract defines neither the
timezone of gameday + gametime nor the NFL status rule). RULING: (a) TIMEZONE -- data/nfl/schedules.parquet follows the nflverse
convention: gameday is the local date and gametime the local wall-clock time in America/New_York (Eastern, daylight saving
handled by the zoneinfo database); the row's start_utc is built by localizing gameday + gametime to America/New_York with
zoneinfo, converting to UTC and rendering ISO text with an explicit offset, which is then parsed through parse_venue_time (an
unzoned text is never handed to the parser); a row with gametime missing or unparseable is counted time_unknown, keeps its ISO
week from gameday alone, and carries start_utc absent. (b) STATUS -- the supply module derives no venue or feed status: pre means
start_utc is later than the --as-of instant, not_pre means start_utc is at or before it (a counting split for the supply table
only, never a game result; a row with start_utc absent is counted status_unknown). (c) ISO WEEK -- from the UTC date of
start_utc (or gameday when start_utc is absent), ISO-8601 week numbering; the table reports per (family, iso_year, iso_week)
the counts scheduled, pre, not_pre, time_unknown. (d) The construct fixture carries at least one row on a DST boundary week
(the first Sunday of November) and one with gametime missing; tests assert the UTC conversion on both sides of the boundary.

AMENDMENT 4 (2026-09-22 23:2xZ; binding; VERBATIM FACTS from the orchestrator's first real OFFLINE run of the built candidate,
from the worktree, NFL only, --start 2026-09-28 --end 2026-12-31 --as-of 2026-09-22T23:15:00Z, the main tree's
data/nfl/schedules.parquet; exit 0). Per ISO week of 2026: week 40: 16 scheduled, 41: 15, 42: 14, 43: 14, 44: 14, 45: 15,
46: 14, 47: 13, 48: 16, 49: 14, 50: 15, 51: 16, 52: 16, 53: 2 (the 28-31 December remainder); every game pre at the as-of,
not_pre 0, time_unknown 0, status_unknown 0, refusals {} in every week, unassigned_refusals none. Example row: gameday 2026-09-27
gametime 20:20 (America/New_York) -> scheduled_start_utc 2026-09-28T00:20:00+00:00, requested_day 2026-09-28, game_key 401872962.
READING: NFL supplies 13-16 scheduled games in every ISO week 40-52, so an NFL family can carry the 8-consecutive-week target with
a wide margin (WEEK_GAMES 4); the ESPN sports were NOT enumerated in this run (network; the real enumeration for nba / soccer /
ncaaf happens from the main tree after landing and is recorded by a later amendment). The memo records these counts verbatim.

AMENDMENT 5 (2026-09-22 23:5xZ; binding; from the astra round-1 critique on the build, read with AMENDMENT 4). (a) THE ET / UTC
BOUNDARY HOLE: MEASURED on constructs -- ESPN keys its scoreboard by Eastern date while this row keys weeks by UTC date, so a
Sunday-evening game that starts Monday 00:20Z was returned under the Sunday request (counted day_mismatch and dropped) and
absent from the Monday request: zero scheduled games across both days for a real game. RULING: for each requested UTC day the
supply module fetches the ESPN scoreboard for that date AND the previous date (both requests recorded), keeps every event whose
start_utc falls on the requested UTC date from EITHER payload, dedupes by event id (a duplicate across the two payloads is
counted event_seen_twice, never twice scheduled), and counts day_mismatch only for an event whose start_utc date matches
neither the requested day nor its previous day (a genuinely stale payload); the landed writer's own single-date fetch is NOT
changed by this row (its boundary exposure is recorded as a follow-up for S403's owner in the memo). (b) The memo records
AMENDMENT 4's counts verbatim (weeks 40-52: 16 / 15 / 14 / 14 / 14 / 15 / 14 / 13 / 16 / 14 / 15 / 16 / 16; week 53: 2, the
December 28-31 partial; all pre; zero refusals; as-of 2026-09-22T23:15:00Z) attributed to the orchestrator's run. (c) NOTED,
unchanged: scheduled includes unknown-time games and the weekly threshold measures supply only (not qualification); the ESPN
fixture yields date None / missing_local_timezone under the landed writer's linkage, so the constructs show inventory, not S403
schedule emission.

AMENDMENT 6 (2026-09-23 00:0xZ; binding; from the codex sol round-1 verdict on the build). STATUS BY THE CLOCK, NEVER BY THE
FEED: MEASURED -- non-NFL rows took their status from the feed's own status field instead of --as-of, so a past game the feed
labelled pre and a future game it labelled post produced [pre 1 / not_pre 0] and [pre 0 / not_pre 1], exactly reversed
(forward_schedule_supply.py:153) -- hindsight through the feed. RULING: every timed accepted row of EVERY sport is pre when
start_utc is later than --as-of and not_pre otherwise; the feed's status field is never read for the counts (it may be
recorded verbatim beside the row as feed_status, never used); a test proves inverted feed statuses cannot move the counts. The
memo carries AMENDMENT 4's counts verbatim (AMENDMENT 5(b)) and cites AMENDMENTS 1-6.

AMENDMENT 7 (2026-09-23 01:0xZ; binding; from the sol round-2 REJECT of fix 1b). ORDER-INDEPENDENT CROSS-PAYLOAD DEDUPE --
MEASURED: the same event id in both the requested-date and the previous-date payloads with DIFFERENT start times (11:00Z vs
13:00Z for 401772801 under --as-of 12:00Z) gave (scheduled, pre, not_pre) = (1, 0, 1) in one fetch order and (1, 1, 0) in the
other; with dates a week apart, reversal moved day_mismatch 1 -> 0 and weeks_total 2 -> 1 (forward_schedule_supply.py:135).
RULING: events are collected per id across BOTH payloads before any decision; identical copies (same id, same start_utc) count
once; copies whose start_utc DIFFER are a payload disagreement -- the event is REFUSED with reason event_start_conflict, counted,
both starts recorded as text, never silently resolved by order; the result is byte-identical under either fetch order and either
row order (a test asserts it). The memo's NOT VERIFIED is an explicit list (live ESPN enumeration; master re-runs; superseded
timings) and the marker-only assertion at test_forward_schedule_dates.py:292 checks for the list. Everything from fixes 1b
(AMENDMENTS 5-6) byte-identical in behaviour.

AMENDMENT 8 (2026-09-23 01:2xZ; binding; from the astra round-2 critique of fix 1b). (a) THE FEED STATUS STILL CONTROLS
ADMISSION THROUGH THE PARSER -- MEASURED: with identity and a future start held constant, comp.status {"type":{"state":"post"}}
gave scheduled 1 / pre 1 (correct, by the clock) but {"type":"post"} (a malformed status) gave scheduled 0 /
schedule_game_parse_failure 1 (forward_schedule_sources.py:90 reached through forward_schedule_supply.py:125): a malformed feed
status drops the event, so the feed still moves the counts; the clock test replaced the fetcher and never exercised the parser.
RULING: S416 may make ONE additive change in forward_schedule_sources.py beyond the URL date parameter -- the status extraction
is tolerant: a missing, non-dict or otherwise malformed status yields feed_status_malformed (counted) and the landed status key
falls to "not_pre", never a parse failure; every other parser behaviour and the landed writer's use of that key stay byte-identical
(the writer's own feed-derived status is S403's and is recorded as a follow-up for S403's owner). The supply's counts come from
the clock alone; a test drives the REAL parser (not a replaced fetcher) with the malformed status and asserts the event is
admitted and counted by --as-of. (b) UNTIMED REFUSED ROWS CARRY NO STATUS -- MEASURED: start null, "bad" and date-only
"2026-09-28" each produced day_unverifiable 1 / scheduled 0 but still emitted status "pre" (supply.py:147). RULING: a refused
row's status is null; the feed's value, when present, is retained separately as feed_status text; a date-only start establishes
no UTC instant and gets no midnight or requested-day fallback (refused, counted, recorded as text). Fixes 1b-1c byte-identical in
behaviour otherwise.
