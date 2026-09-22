# S352 local state capture

CAPTURE ROW: no model, no probability, no measured calibration number. Public,
unauthenticated endpoints only; no credentials read, printed, or used.
Vocabulary follows contract Q6; automated scan required.

Before-condition (reproduced): `ls data/cache/ingame_books_local/` showed venue
dirs only (`kalshi/{mlb,nba,nfl,soccer,tennis}`), no `state/` tree.
`ls scripts/platformkit/ingame/local_state_capture.py` failed (absent).

## Change

NEW files only (verified: `git diff --stat` against tracked files is empty;
`git status --short` shows these four as untracked, plus this memo):

- `scripts/platformkit/ingame/local_state_capture.py` (268 LOC) -- `StateClient`
  (AIMD-paced GET, backoff + Retry-After honor on 429/403, no custom User-Agent),
  `capture_state_once` / `run_local_state_capture` (stop-file `STOP_STATE`,
  heartbeat JSON per sport, sha256-only raw-payload retention).
- `scripts/platformkit/ingame/local_state_capture_sources.py` (236 LOC) --
  per-sport discover/poll/normalize functions.
- `scripts/platformkit/ingame/game_market_link.py` (168 LOC) -- pure state-game
  <-> Kalshi-event linker (date + team-code overlap; alias tables; never a
  nearest guess).
- `tests/platformkit/ingame/test_local_state_capture.py` (214 LOC, 12 tests,
  offline fixtures only).

Reused by import (never re-derived): `ingame_gumbo_mlb.extract_state` (MLB GUMBO
normalizer -- domains/mlb has no live-feed normalizer, only historical
ESPN-summary ingesters, so this proven extractor -- fielding-position trap,
fullUpdate trap already solved there -- is the closest existing fit);
`domains.basketball_nba.live_state_nba.parse_scoreboard` (the exact module
named for this row); `domains.tennis.ingest_espn.parse_scoreboard` (adapter
exists, coarse); `local_capture_runner_row.{AIMDController, parse_retry_after,
archive_path, heartbeat_path, is_winner_series}`; `kalshi_book_row.{iso, append,
write_json_atomic}`. Re-normalized directly (no domains/soccer live-state
module exists -- `ingest_soccer_states.py` is a historical ESPN-summary ingest,
not a live poller): soccer reuses the SHARED ESPN event parser
`scripts.platformkit.frontend.live_board._parse_event` that `live_state_nba.py`
itself wraps, instead of duplicating that parsing logic a third time. NFL
(`domains.nfl.ingest_nfl_states.normalize_scoreboard`, row S350) is not on
master yet -- the import is wrapped in `try/except ImportError`; `"nfl"` is
absent from `SPORTS_AVAILABLE` and `nfl_poll()` returns `[]` cleanly (tested).

## Validation

Per-file test:
`python -m pytest tests/platformkit/ingame/test_local_state_capture.py -q -p no:cacheprovider`
-> **12 passed**.

Bounded foreground smoke (`timeout 90 python -m
scripts.platformkit.ingame.local_state_capture`), against the real archive
root, two runs:

- Run 1 caught a real bug: the tennis status mapper defaulted ANY unrecognized
  ESPN status string to `"live"` (7s cadence). Live WTA/ATP data on this date
  carries `STATUS_CANCELED` / `STATUS_WALKOVER` / `STATUS_RETIRED` (4 of 341
  matches), which hit that default and drove the WHOLE sport onto 7s polling --
  3069 tennis rows in 90s. Fixed: an explicit status table
  (`_TENNIS_STATUS`) defaulting any unrecognized value to `"pre"` (60s), never
  `"live"`.
- Run 2 (post-fix): tennis wrote exactly 682 rows in 90s (341 games x 2 polls
  at the correct 60s pregame cadence) -- `n_games_live: 0` in the heartbeat,
  matching the real slate (no in-progress WTA/ATP match at test time). Zero
  429/403/errors across both runs (`n_429_total`, `n_403_total`,
  `n_errors_total` all 0 in every per-sport heartbeat).

Peak RSS (`powershell -NoProfile -Command "(Get-Process -Id <pid>).WorkingSet64/1MB"`),
sampled repeatedly across the smoke run, the RSS probe run, and the persistent
run: stable at **~97-99 MB** for the actual capture process (`python.exe`) --
well under the 150 MB target. The `pythonw.exe` hidden-launch wrapper adds
~17.6 MB separately.

## Left running

Started as a persistent hidden process (pythonw + `~/bin/hidden_launch.py`, no
console window), separate from and never touching the S341 book-capture
process or its `STOP` file:

- launcher (`pythonw.exe`): PID 31064
- capture-runner (`python.exe -m scripts.platformkit.ingame.local_state_capture`): PID 17232
- log: `C:\Users\neelj\AppData\Local\Temp\capture_state_local.log`
- output: `data/cache/ingame_books_local/state/<sport>/<date>.jsonl` + `_heartbeat.json`
- stop file: `data/cache/ingame_books_local/STOP_STATE`
- start/stop commands appended to `C:\Users\neelj\AppData\Local\Temp\capture_runbook.txt`

Confirmed alive and growing continuously from launch through this memo
(~10 minutes; heartbeat `last_success_ts` advancing every tick, zero errors,
RSS 98-102 MB across repeated samples): row counts as of this memo (UTC
2026-09-21T19:24) -- mlb 48, nba 16, soccer 24, tennis 7843
(`data/cache/ingame_books_local/state/<sport>/2026-09-21.jsonl`, cumulative
across this session's smoke + probe + persistent runs, all against the same
date file; the process is left running and these will keep growing).

## Which sports had live/scheduled games today (2026-09-21, ~19:00-19:17 UTC)

- **mlb**: 3 games discovered, all `Preview`/`pre` (first pitch 22:35-01:45
  UTC, none live during this session).
- **nba**: 1 game discovered -- a preseason fixture dated 10/3, not today;
  ESPN's default (no `?dates=`) scoreboard returned it since nothing is
  scheduled today. `status: pre`.
- **soccer** (eng.1): 4 matches, all `final` (already played 2026-09-20/21,
  none live or later-today).
- **tennis** (atp+wta): 341 matches -- 187 `pre` (scheduled), 150 `final`, 4
  terminal-but-not-final (`STATUS_CANCELED`/`STATUS_WALKOVER`/`STATUS_RETIRED`,
  now correctly bucketed `final`). No match was `STATUS_IN_PROGRESS` at test time.
- **nfl**: adapter absent (row S350 not landed) -- not polled.

## Linker match rate vs today's Kalshi capture (`data/cache/ingame_books_local/kalshi/<sport>/2026-09-21.jsonl`)

Computed via `game_market_link.link_rate()` over every distinct `game_key`
this session's state files captured for 2026-09-21, against
`index_kalshi_events(load_kalshi_rows(sport, "2026-09-21"))`:

| sport  | games seen | Kalshi rows | matched | unmatched | unmatched reason(s) |
|--------|-----------:|------------:|--------:|----------:|----------------------|
| mlb    | 3          | 2555        | 3       | 0         | -- |
| nba    | 1          | 315         | 0       | 1         | `no_kalshi_event_for_date_and_team` (the game is Oct 3, not today -- see above) |
| soccer | 4          | 0           | 0       | 4         | `no_kalshi_event_for_date_and_team` (S341 captured zero soccer rows today -- nothing to link against) |
| tennis | 341        | 2110        | 0       | 341       | 278 `no_kalshi_event_for_date_and_team`, 63 `no_team_codes` -- see NOT VERIFIED |

mlb's 3/3 match confirms the date + team-code-suffix + winner-series-preference
design works end to end against real S341 data (including correctly resolving
a matchup that also had F3/F5/F5SPREAD/F7 sibling events sharing the same date
and team codes).

## Addendum: S352 integration defect (row S350 landed, reported by the coordinator, fixed same session)

After this memo's initial delivery, row S350 (`domains/nfl/ingest_nfl_states.py`) landed
on master and the orchestrator restarted this capture (PID 24088, ~19:33Z). The
coordinator reported a defect verified from the live archive: `state/nfl/_heartbeat.json`
showed `last_success_ts` advancing with zero errors, but `n_games_tracked: 0`,
`rows_written_total: 0`, and no `nfl/<date>.jsonl` file at all, despite ESPN's NFL
scoreboard returning 16 real events that day.

ROOT CAUSE (confirmed by reading the landed adapter): `nfl_poll` called
`normalize_scoreboard(payload)` with ONE argument; the landed signature is
`normalize_scoreboard(payload: dict, receipt: dict) -> List[dict]`. The resulting
`TypeError` was swallowed by a bare `except Exception: return []` inside `nfl_poll`
itself -- a process that ran, advanced its heartbeat timestamp, and collected nothing,
invisible until someone read the archive directly.

FIX (in this row's own files only -- `domains/nfl/*` untouched, no other pre-existing
module edited, S341 never touched):

1. **Real receipt, never a stub.** `local_state_capture.ReceiptGetter` (a callable
   `GetFn` wrapper around `StateClient`) now records `request_start_utc`/
   `response_end_utc`/`http_status` of its most recent call on `.last_receipt`.
   `_nfl_league_poll` reads that and passes it as `normalize_scoreboard`'s second
   argument -- real measured values, confirmed via
   `test_nfl_poll_receipt_wiring_and_absent_module_fallback`. NFL rows carry the same
   `game_key` convention as every other sport (`espn_event_id`), plus the same
   `state_changed`/receipt/heartbeat fields `_build_row` already gives every sport.
2. **SILENT FAILURE RULE.** `nfl_poll`'s internal try/except is REMOVED (not narrowed --
   that catch was the bug); every poller's exception now surfaces either by propagating
   to `capture_state_once`'s `run_task`, or via an explicit `on_error` callback for a
   poller's own internal per-item catch (soccer's per-event ESPN parse guard). Both
   paths increment a per-sport counter now in the heartbeat:
   `n_adapter_errors_total` + `last_adapter_error` (`"<ExceptionType>: <first 120 chars>"`).
   Covered by `test_adapter_exception_is_counted_in_heartbeat_not_swallowed` (nfl-shaped
   TypeError via a monkeypatched poller) and `test_soccer_per_event_parse_error_is_also_counted`
   (proves the rule isn't nfl-only).
3. Added `test_nfl_poll_real_adapter_pregame_and_inprogress_rows`: the REAL
   `domains.nfl.ingest_nfl_states.normalize_scoreboard` against a minimal ESPN payload
   (one `STATUS_SCHEDULED`, one `STATUS_IN_PROGRESS` with a `situation` block) -- asserts
   both rows come back correctly normalized (score, down/distance, possession, status
   mapped `'in'` -> `'live'`).
4. **ncaaf wired** (two-line addition, as scoped): `_nfl_league_poll(..., league=
   "college-football")`, `ncaaf_poll`, added to `SPORTS_AVAILABLE`/`POLLERS`. Covered by
   `test_ncaaf_poll_reuses_same_adapter_different_league`.

Per-file test after the fix: **16 passed** (12 original + 5 new for this defect, net +4
after one nfl test was replaced rather than added -- see the file's own header for the
full list). LOC after the fix: `local_state_capture.py` 296, `local_state_capture_sources.py`
299, `test_local_state_capture.py` 300 -- all at or under the 300 cap.

Restart proof (stop-file `STOP_STATE` -> waited for PID 24088 to exit -> removed the
stop file -> relaunched hidden exactly per `Temp/capture_runbook.txt`, new PIDs
21812/16208):

```
$ grep -c "" data/cache/ingame_books_local/state/nfl/2026-09-21.jsonl
16
$ python -c "import json; print(json.load(open('data/cache/ingame_books_local/state/nfl/_heartbeat.json'))['n_games_tracked'])"
16
$ head -n 1 data/cache/ingame_books_local/state/nfl/2026-09-21.jsonl
{"away_abbr": "NYG", "capture_ts": "2026-09-21T19:46:45.878234Z", "capture_version":
"local_state_capture_v1", "date": "2026-09-22", "game_key": "401872947", "home_abbr":
"LAR", "http_status": 200, "raw_sha256": "4143630bd2615a...", "request_start_utc":
"2026-09-21T19:46:45.987337Z", "response_end_utc": "2026-09-21T19:46:46.551472Z",
"source_ts": null, "sport": "nfl", "state": {"away_score": 0, "away_timeouts": null,
"clock_seconds_remaining": 0, "distance": null, "down": null, ... "period": 0,
"possession_team": null, ...}, "state_changed": true, "status": "pre"}
```

`ncaaf` also confirmed live: `_heartbeat.json` shows `n_games_tracked: 18`,
`rows_written_total: 18`. RSS of the new capture-runner PID (16208) at ~15s: ~104 MB,
under the 150 MB target. Runbook updated with the new PIDs.

Note: the "Which sports had live/scheduled games" and "Linker match rate" sections
above, and the file/LOC counts in **Change**, reflect the state at this memo's ORIGINAL
delivery (before row S350 landed and before this fix) -- they are not re-run here for
every sport; the fix's own scope (nfl/ncaaf rows now populated, adapter errors now
counted) is proven above instead.

## NOT VERIFIED

- Tennis linking: 0/341 matched. Root cause understood, not fixed here --
  `local_state_capture_sources.tennis_poll` carries ESPN's full player names
  as `home_abbr`/`away_abbr`, while Kalshi's tennis tickers embed short
  surname-derived codes (e.g. `KXATPMATCH-26SEP21FARATM-FAR`); no name-to-code
  alias table was built for tennis (`game_market_link.ALIASES["tennis"] == {}`).
- The `mlb`/`nba` alias tables (`_MLB_ABBR`/`_NBA_ABBR`, reused from
  `scripts.platformkit.frontend.live_board`) are NOT independently verified
  against Kalshi's own team-code vocabulary -- they were vetted for a
  different purpose (mapping ESPN abbreviations onto this repo's predictor
  corpora). Today's live data only exercised identity-mapped codes (TOR, BAL,
  BOS, DET, MIA); none of the tables' actual alias entries (SD->SDG, SF->SFG,
  KC->KAN, TB->TAM, WSH->WAS, AZ->ARI, CHW->CWS for mlb; SA->SAS, NY->NYK,
  GS->GSW, NO->NOP, UTAH->UTA, PHO->PHX for nba) were exercised against a real
  Kalshi ticker this session.
- No game was actually `live` (in-progress) during this session for any sport,
  so the 7s live-cadence path, the GUMBO in-play field extraction (balls,
  strikes, base occupancy, batter/pitcher, last-play id) against a REAL live
  game, and `state_changed` transitions on real data were exercised only via
  the offline GUMBO fixture in the test file, not against a live network
  response.
- `nba_poll`'s `date` field is the poll date (today), not a per-event date --
  correct for same-day games, but demonstrably wrong for a future/non-today
  fallback game (the Oct 3 case above); `domains.basketball_nba.live_state_nba`
  does not carry a per-event date, so a true fix would need to read it from
  the raw ESPN event separately, not attempted here.
- NFL/ncaaf are now proven against the REAL `normalize_scoreboard` (see Addendum)
  and against the live archive (16 real nfl rows, 18 ncaaf), but no NFL/NCAAF game
  was actually `STATUS_IN_PROGRESS` during this session -- the `situation`-block
  (down/distance/possession) live-extraction path is exercised only via the
  offline fixture in the test file, not a real in-progress payload (same caveat
  `domains/nfl/ingest_nfl_states.py`'s own docstring already carries).
- `game_market_link` was not re-run against nfl/ncaaf this session. `ALIASES["nfl"]`
  is `{}` (identity passthrough, untested against a real Kalshi NFL ticker); `ncaaf`
  has no key at all and falls through to `alias()`'s default `{}` -- also untested.
- Multi-day / doubleheader disambiguation for MLB is deliberately conservative
  (`ambiguous_multiple_kalshi_events`, tested) -- not exercised against a real
  doubleheader today (none on today's slate).
- Long-duration (multi-hour) memory/disk-growth behavior of the persistent
  process is unverified beyond the ~10-minute observation window in this memo.
- Automated Q6 vocabulary scan: performed manually with a case-insensitive
  grep for the four contract-Q6 disallowed terms over all five new files
  (zero matches) -- not wired into a CI/automated gate.
