GAP S386 | sport all captured | worktree harness-h46 (master-based) | log cx_s386_forward_schedule_writer
# Prospective schedule writer: the forward series can only qualify games selected BEFORE they start (S362 AMENDMENT 2, Q-2)

SINGLE PROBLEM: the landed forward replay (row S362) refuses any game whose schedule entry was selected at or after its scheduled
start, and no tool writes such a schedule. On 2026-09-22 the first live NFL game could not even be examined because nobody had
written its entry beforehand. Every future qualifying week starts with a schedule file written the day before.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/execution/forward_schedule_writer.py` fails. Read on master and quote the
signatures you rely on: scripts/platformkit/execution/forward_replay.py (`--schedule`: a JSON list of game_id, ticker, sport,
family, scheduled_start, selected_at; selection no later than scheduled_start; duplicate games / tickers refuse),
scripts/platformkit/ingame/game_market_link.py (index_kalshi_events, load_kalshi_rows, link_game, team_code_from_ticker),
scripts/platformkit/ingame/local_state_capture_sources.py (how the MLB statsapi schedule and the ESPN scoreboards are fetched;
the NFL / NCAAF week shape), scripts/platformkit/ingame/local_capture_runner_trades.py (classify_state and
expected_expiration_time). REAL SNAPSHOT ROW KEYS (from data/cache/ingame_books_local/kalshi/<sport>/<date>.jsonl): record_type
"snapshot", ticker "KXNFLGAME-26SEP21NYGLAR-LAR", event_ticker "KXNFLGAME-26SEP21NYGLAR", venue_status, response_end_ts, close_time
(administrative, far-future), raw_market (dict; carries expected_expiration_time). The two sides of one game are two tickers that
share the event_ticker; the suffix is the side's team code.

CHANGE (NEW files only):
1. scripts/platformkit/execution/forward_schedule_writer.py (<= 300 LOC, stdlib + the landed link module; NO network -- it reads
   the capture ARCHIVE and the state archive only): `--date <YYYY-MM-DD> --sports mlb,nfl,... --books-root <dir> --state-root <dir>
   --family <name> --out <json> [--now <iso>]`. For each sport: enumerate games whose scheduled start (from the state archive's
   pre-game rows: scheduled_start_utc / game date + venue schedule; quote the field) falls inside the UTC date; link each to its
   event_ticker through the landed link module (a game with no link, or with a link to more than one event, is REFUSED and
   counted, never guessed); CANONICAL TICKER RULE, deterministic and prospective: the side whose team code equals the HOME team's
   alias (fallback: the lexically smaller ticker; state which rule fired); selected_at = --now (default: the wall clock, timezone
   aware); every entry with scheduled_start <= selected_at is REFUSED and counted (never back-dated); output the JSON list in the
   exact shape S362 consumes plus a sidecar `<out>.census.json` with counts per sport: games seen, linked, refused by reason,
   written. Strict-int counts; every except clause counts or re-raises; results independent of archive row order; times parsed
   only with scripts.platformkit.execution.venue_time.parse_venue_time.
2. tests/platformkit/execution/test_forward_schedule_writer.py: synthetic archives; both canonical-ticker rules; a game starting
   before --now refused; an unlinked game refused; a doubly-linked game refused; duplicate games refused; the S362 loader accepts
   the output (import forward_replay's schedule reader and feed it); order independence; timezone-aware selected_at.
3. docs/operations/FORWARD_SCHEDULE_RUNBOOK.md: the one command to run each day BEFORE the first game (with --now omitted), where
   the file goes (docs/evidence/forward/schedules/<date>_<family>.json, TRACKED, committed before the first scheduled start so
   the git commit time proves prospective selection), and what to do when a game is refused (nothing: it does not qualify).
4. Memo docs/evidence/harness/S386_forward_schedule_writer_2026-09-22.md.

CONTROLS: PREPARE only, NEW files only, construct tests, no network, no real archive run by the builder (the orchestrator runs
it). ACCEPTANCE: per-file test passes; --help works; diff = NEW files only; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo
ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-22; binding). scripts/platformkit/execution/forward_replay_qualification.py (about line 108) ACCEPTS
selected_at == scheduled_start; the frozen rule is strictly BEFORE. That file joins this row's owned files for that one change:
equality is refused with a counted reason, a test covers selected_at == scheduled_start (refused) and one microsecond earlier
(accepted), and the two landed S362 test files still pass. The writer's own rule (scheduled_start <= selected_at is refused) is
unchanged.

AMENDMENT 2 (2026-09-22 01:2xZ; binding; from the first real run). The state archive rows carry NO scheduled start (keys: date,
game_key, home_abbr, away_abbr, status, source_ts, state...), so the writer refused all 484 games of 2026-09-22 as invalid_time --
correct fail-closed behaviour, and useless. Rule: add `--schedule-source live|archive` (default live). LIVE mode fetches the
public schedule the state capture already polls -- MLB statsapi schedule?sportId=1&date=<date> (gameDate per game, game_pk =
game_key) and the ESPN scoreboards used by local_state_capture_sources.py for nfl / ncaaf / nba / soccer / tennis (event date +
competition id) -- with default headers, one request per sport per run, timezone-aware receipts, the response SHA-256 and byte
length recorded in the census, and a network failure counted per sport (never a guess). scheduled_start = the venue-published
start converted to UTC through parse_venue_time. ARCHIVE mode stays as built for the day the capture persists scheduled_start_utc
in every state row (row S393). Linkage to the book archive (event_ticker, canonical side) is unchanged and still archive-only.
Tests: an injected opener for both schedule shapes; the network-failure count; the receipt fields; the date filter in UTC. The
runbook names the live mode as the daily command.

AMENDMENT 3 (2026-09-22 01:3xZ; binding; from the second real run, live mode, 2026-09-22: 0 entries written -- MLB 16 games seen,
10 refused missing_directional_team_evidence and 6 outside_utc_date; NFL 16 refused invalid_time). Verbatim payload facts probed by
the orchestrator: (a) the MLB schedule endpoint WITHOUT hydration returns team objects with keys id / link / name only -- no
abbreviation; with `&hydrate=team` the same objects carry `abbreviation` (e.g. NYY / TB). Rule: request `hydrate=team` and link on
the abbreviation through the landed alias table; a game whose abbreviations cannot be resolved stays refused and counted.
(b) The ESPN scoreboard publishes `date` as "2026-09-27T17:00Z" -- minute precision, no seconds -- which the shared venue-time
parser correctly refuses. Rule: an ESPN-specific pre-normalization, applied ONLY to that provider's `date` field and ONLY when
the string matches exactly `YYYY-MM-DDTHH:MMZ`, appends ":00" before the shared parser; every other shape still goes to the parser
untouched; the normalization is counted (`espn_minute_precision_normalized`) so the census shows how many starts needed it.
(c) `outside_utc_date` for MLB is correct behaviour when a game's UTC start falls on the next UTC date (late West-coast starts):
keep it, and print in the runbook that a UTC date is what the writer schedules. Tests: an MLB payload with and without
hydration; an ESPN event with the minute-precision date and one with seconds; the normalization counter.

AMENDMENT 4 (2026-09-22 01:4xZ; binding; from the third real run: MLB 10 of 16 still refused missing_directional_team_evidence
after hydration). Cause, read from the landed linker: index_kalshi_events keeps home_abbr / away_abbr only when the CAPTURE rows
carry them; the local capture's snapshot rows carry only ticker / event_ticker, so the linker holds an UNORDERED team-code set
per event (e.g. {NYY, TB} from KXMLBGAME-26SEP221305TBNYYG1) and refuses for lack of direction. The landed linker is NOT edited.
Rule for the writer: direction comes from the venue schedule (home / away abbreviations through the landed alias table); an event
is linked when its ticker date equals the game's LOCAL date and its team-code set equals {home, away} exactly; if more than one
event on that date has the same set (doubleheaders: the G1 / G2 suffix), the game is REFUSED as ambiguous_doubleheader and counted
(never guessed from the ticker's embedded local time); the canonical ticker is the event's ticker whose suffix equals the HOME
alias (fallback rule unchanged and recorded). Record which path linked each game (`linker` or `team_set`) in the census. Tests:
a two-team event linked by team set with home from the schedule; a doubleheader refused; a set mismatch refused; the linker path
still preferred when a capture row does carry directional metadata.

AMENDMENT 5 (2026-09-22 01:5xZ; binding; from the fourth real run: 1 MLB game written -- MIA at CHC 23:40Z, canonical CHC by the
home rule, link path team_set -- but 5 refused ambiguous_doubleheader and 4 missing_directional_team_evidence). The archive holds
SEVERAL series per game: KXMLBGAME (game winner) and KXMLBF5 (first five innings) share the date and the team set, so the
AMENDMENT 4 ambiguity rule counted a derivative series as a doubleheader. Rule: linkage and the doubleheader check consider ONLY
the game-winner series for the sport (the series classify_state treats as winner: KXMLBGAME, KXNFLGAME, ... -- quote the
landed list); derivative series are ignored for scheduling and counted `derivative_series_ignored`. For the remaining
missing_directional_team_evidence games the census must list, per refused game, the venue abbreviations and the team-code sets
that were compared (codes only, no guess), so the alias table can be extended in a later row; the writer itself never guesses.

AMENDMENT 6 (2026-09-22 02:3xZ; binding; after the first full verifier round). (a) selected_at is captured AFTER every live
schedule response has been received (fetch first, then stamp); with an explicit --now, any response whose receipt ends after
that cutoff is refused and counted; archive loading and every start comparison use that cutoff. (b) BOTH link paths require the
selected winner event's team-code set to equal {alias(home), alias(away)} exactly; a one-sided or extra-code event is a counted
refusal listed in refused_team_evidence. (c) TENNIS: the state capture polls the ATP and WTA scoreboards as two requests; the
writer does the same (two requests, both receipts recorded), keys events tour-qualified (atp:<id>, wta:<id>), and never omits a
tour -- the one-request-per-sport wording of AMENDMENT 2 is relaxed to one request per tour for tennis only.

