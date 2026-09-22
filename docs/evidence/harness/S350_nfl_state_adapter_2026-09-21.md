# S350 -- NFL live-state adapter (prepare-only)

Vocabulary follows contract Q6; automated scan required.

## What shipped

Three NEW files, mirroring the as-of / receipt discipline of
`domains/soccer/ingest_soccer_states.py` and the bounded-poll shape of
`domains/basketball_wnba/ingame_live_cdn_poller.py` (the closer live-poller
analog; the soccer file is a historical-replay batch builder, not a live
poller, so the poll_once/receipt structure follows the WNBA file instead):

- `domains/nfl/ingest_nfl_states.py` -- polls the public ESPN scoreboard JSON
  (`site.api.espn.com/apis/site/v2/sports/football/{league}`, `league` in
  `{"nfl", "college-football"}`). Pure `normalize_scoreboard(payload, receipt)
  -> list[dict]` + `fetch_scoreboard(session, league)` + `poll_once(session=
  None, *, league="nfl")`. CLI: `--once --league {nfl,college-football} --out
  <jsonl>` appends normalized rows. No credentials. No model or probability
  output. Sends no custom `User-Agent` (see Live smoke below for why).
- `domains/nfl/kalshi_nfl_ticker_map.py` -- pure parse of a Kalshi NFL game
  ticker into `(date, away_abbr, home_abbr)`, then resolution to an ESPN
  event by date + both team abbreviations, with the LA/LAR, WSH/WAS, JAC/JAX
  alias table. Ambiguous or absent matches return `unmatched=True`, never a
  nearest guess.
- `tests/domains/nfl/test_ingest_nfl_states.py` -- 22 offline tests,
  ESPN-shaped fixtures only, no network (fake session/response classes stand
  in for `requests`). The pregame fixture now matches the live-confirmed
  shape (see below); in-progress/situation fixtures remain synthetic.

No `tests/domains/nfl/__init__.py` added -- checked sibling dirs
(`tests/domains/soccer/`, `tests/domains/mlb/`) and neither uses one.

## Before-condition (re-run, quoted)

`ls domains/nfl` in this worktree showed no `ingest_*_states` module (in fact
this worktree's checkout of `domains/nfl/` predates `feature_spec.py` /
`ingest_manifest.py` / `__init__.py` entirely -- confirmed via `git show
master:domains/nfl/...`; those master-only files were read for reference via
`git show`, never checked out into this worktree, and are untouched by this
diff).

## Tests

Command: `python -m pytest tests/domains/nfl/test_ingest_nfl_states.py -q -p
no:cacheprovider`
Result (after the round-2 verifier fixes below): `22 passed in 0.19s`

`python -m domains.nfl.ingest_nfl_states --help` -- confirmed working (prints
usage, exits 0).

## Live smoke: ran, root-caused a 403, fixed, re-ran successfully

**First attempt** (browser-like `_UA`, mirroring `domains/soccer/
ingest_soccer_states.py`'s Chrome-style string) got HTTP 403 from ESPN's
Akamai front door (`Server: AkamaiGHost`, "Access Denied" page). A
coordinator follow-up measured from this same box that curl's default UA
gets 200 and a Chrome-like UA gets 403 -- the opposite of the usual
anti-bot pattern. Diagnosed directly (several UA strings tried against the
live endpoint to isolate the cause, since the first fix attempt -- a plain
custom string `"courtvision-ingest/1.0"` -- *also* got 403):

| User-Agent sent | Result |
|---|---|
| Chrome-like (`Mozilla/5.0 ... Chrome/124.0.0.0`) | 403 |
| `courtvision-ingest/1.0` | 403 |
| `Wget/1.21` | 403 |
| empty (`-A ""`) | 403 |
| `curl/8.21.0`, `curl/7.0`, `curl/` (any curl-prefixed string) | 200 |
| `python-requests/2.34` (requests' own default UA) | 200 |
| **no `User-Agent` header set at all** (requests' actual default) | **200** |

Conclusion: this isn't a "looks like a bot" filter, it's closer to an
allow-list of a small number of known client signatures (curl, plain
`python-requests`) with everything else denied, including a made-up tool
name. The fix applied: `ingest_nfl_states.py` no longer sets any custom
`User-Agent` -- `fetch_scoreboard`/`poll_once` let `requests` send its own
default. `_UA` and the header-setting line were removed entirely.

**Re-ran the one required `--once` smoke** with the fix:

```
REQUESTS_CA_BUNDLE=/c/Users/neelj/bin/winroots.pem python -m domains.nfl.ingest_nfl_states --once --out tmp/s350_smoke_nfl.jsonl
```

Result: `{"league": "nfl", "n_events": 16}` -- HTTP 200, 16 events returned
(Week 3 NFL slate, run 2026-09-21 ~14:39 EDT). The smoke output file
(`tmp/s350_smoke_nfl.jsonl`) and one saved raw-payload copy
(`tmp/s350_live_payload.json`, fetched via the module's own
`fetch_scoreboard` for field-path inspection) both live under the
worktree's local `tmp/`, neither committed.

### Statuses observed live

15 games already `final` (one went to `period=5`, i.e. overtime; ESPN still
reports `status.type.name == "STATUS_FINAL"` for that game, not a distinct
OT status name -- the `STATUS_FINAL_OVERTIME` entry that was in the
draft `_STATUS_MAP` has been removed since real data contradicts it), 1 game
still `pre` (Monday Night Football, kickoff 8:15 PM EDT, later that day than
the smoke run). **No game was `in` (in-progress) at smoke time** -- Monday's
early/afternoon slate had already finished and the night game hadn't
started.

### Field paths reconciled against the real payload

Confirmed exactly as coded (no changes needed):
`event.id`, `event.date`, `competitions[0].status.clock` (float seconds,
e.g. `0.0`), `competitions[0].status.period` (int -- **0 for a scheduled
game, not null/absent**), `competitions[0].status.type.name` (e.g.
`"STATUS_SCHEDULED"`, `"STATUS_FINAL"`), `competitors[].score` (a **string**,
e.g. `"0"`, `"41"`), `competitors[].team.id`, `competitors[].team.
abbreviation`. `competitions[0].status.displayClock` also exists (e.g.
`"0:00"`) but is not part of this adapter's output schema, so it is not
mapped.

One fixture-vs-reality gap found and fixed: the draft pregame test fixture
used `period=None, clock=None, score=None` to exercise the None-handling
path, but the **real** pregame payload does not omit these -- it reports
`period=0`, `clock=0.0`, `score="0"` (placeholder zeros, not absence).
`normalize_scoreboard`'s existing `period < 1` guard already turns that into
`game_seconds_remaining=None` correctly, so no code change was needed there,
but `test_pregame_no_situation_all_none` was rewritten as
`test_pregame_matches_live_confirmed_shape` to assert the real zeros
(`period == 0`, `clock_seconds_remaining == 0`, scores `== 0`,
`game_seconds_remaining is None`) instead of `None`s. A new, explicitly
synthetic `test_genuinely_absent_fields_are_none_not_zero` was added
alongside it to keep exercising the true-absence None-handling path (a
hand-built payload that omits the score/period/clock keys outright, which
was never observed live and is not claimed to be).

**`competitions[0].situation` was absent from every event in this smoke**
(confirmed both for the one `pre` event and for `final` events) -- consistent
with it only appearing while a game is actually in progress. Because no game
was live, the `situation.{down,distance,yardLine,possession,isRedZone,
homeTimeouts,awayTimeouts,lastPlay.id}` field paths remain **NOT VERIFIED**
against real data (see below); `normalize_scoreboard`'s `.get("situation")
or {}` fallback is confirmed to behave correctly when the key is fully
absent (every dependent field comes out `None`, tested both via the live
pregame/final rows and the synthetic postponed fixture).

## Verifier rejection fixes (round 2)

Independent verifier (codex gpt-5.6-sol) REJECTED the first commit; it could
not run pytest (read-only sandbox), so this session's test run is the only
test evidence. Five findings, each fixed in a new commit (no amend):

1. **BLOCKING, `yardline_100`** -- was copying ESPN's raw `situation.yardLine`
   straight into `yardline_100` while the memo already admitted the
   own-goal-vs-opponent-goal semantics were unverified: a guessed field is
   worse than a missing one. Fixed: `yardline_100` is now always `None` with
   a new `yardline_100_status="semantics_unverified"` field, alongside
   untouched raw fields `yard_line_raw`, `possession_text_raw`,
   `down_distance_text_raw`, `possession_team_id_raw`. The real conversion
   now lives as a SEPARATE pure function `yardline_100_from(raw_yard_line,
   possession_side, field_side)` (own-20 -> 80, opponent-20 -> 20), tested in
   isolation but NOT called from `normalize_scoreboard` -- it stays unwired
   until a live in-progress game confirms which raw ESPN field actually
   supplies `field_side`.
2. **BLOCKING, `source_ts`** -- was hardcoded `None`. Checked the saved live
   payload (`tmp/s350_live_payload.json`) for every candidate the coordinator
   named: no top-level `timestamp` key, no `status.lastUpdated` key (the
   payload's only `lastUpdated` occurrences are unrelated league-logo asset
   cache-bust dates from 2018/2024); `date`/`startDate` are kickoff schedule
   times, not a snapshot timestamp, so they were deliberately not
   repurposed. **Timestamp field used: none exists in this ESPN payload
   family** -- `_source_ts()` checks both candidate paths (so a future
   payload that does carry one is picked up without a code change) and
   returns `None` when both are absent, which is the real, confirmed
   behavior for this payload. Tests cover both the confirmed-absent real
   shape and (synthetically) the present case for each candidate path.
3. **BLOCKING, `kalshi_nfl_ticker_map.py` side-matching** -- `_event_abbrs`
   reduced both competitors to an unordered `set`, so a ticker with home/away
   reversed still matched. Fixed: `_event_sides` now returns a side-keyed
   dict and `resolve_espn_event` requires `sides["home"] == parsed.home_abbr`
   AND `sides["away"] == parsed.away_abbr` specifically -- a new
   `test_resolve_espn_event_swapped_sides_is_unmatched` proves the same two
   teams with sides swapped no longer match. Also fixed: an event whose `id`
   is absent/falsy now returns `unmatched=True` instead of the literal
   string `"None"` (`str(None)`) -- new
   `test_resolve_espn_event_absent_id_is_unmatched_not_string_none`.
4. **CORRECTION, date validation** -- `iso_date = f"{year:04d}-{mon:02d}-
   {day:02d}"` was wrapped in a `try/except ValueError` that can never fire
   (f-string formatting doesn't validate calendar dates -- `2024-02-31`
   passed through). Fixed: constructs a real `datetime.date(year, mon, day)`
   and catches its `ValueError`. New `test_ticker_parse_invalid_calendar_
   date_is_unmatched` (Feb 31) confirms it's now rejected.
5. **CORRECTION, OT test coverage** -- the only OT test used 300s (mid-OT)
   and never referenced `_OT_SECONDS`, leaving the constant unused/
   undertested. `_game_seconds_remaining` now actively bounds OT
   `clock_remaining` to `[0, _OT_SECONDS]` (an out-of-window reading is
   dropped, not propagated) -- a real functional use, not just a
   documentation constant. `test_overtime_clock_arithmetic` now covers
   mid-OT (300s), the exact 600s boundary (asserts no regulation-quarter
   carry), and 700s (out-of-window -> `game_seconds_remaining is None`,
   `clock_seconds_remaining` still passed through raw).

## contract_preflight

`scripts/platformkit/tracking/contract_preflight.py` (+ its
`contract_preflight_extra.py` / `g334_seal.py` dependencies) did not exist in
this worktree's stale checkout either (same staleness as `domains/nfl/`, see
Before-condition); fetched read-only via `git checkout master -- <path>` for
each, run against this lane's 4 files, then unstaged (never added to this
lane's commit -- they are pre-existing master files, not new).

Command: `python -m scripts.platformkit.tracking.contract_preflight --paths
domains/nfl/ingest_nfl_states.py domains/nfl/kalshi_nfl_ticker_map.py
tests/domains/nfl/test_ingest_nfl_states.py
docs/evidence/harness/S350_nfl_state_adapter_2026-09-21.md --base master`

## NOT VERIFIED

- **`situation.*` field paths** (down, distance, yardLine, possession,
  isRedZone, home/awayTimeouts, lastPlay.id) -- no game was in progress at
  either smoke run, so the `situation` object itself was never observed live,
  only its documented-convention shape (unchanged from the first pass).
- **`yardline_100` semantics** -- no longer guessed (see round-2 fix #1
  above): the row always carries `yardline_100=None` +
  `yardline_100_status="semantics_unverified"` plus the untouched raw
  fields. The conversion function `yardline_100_from` exists and is unit
  tested but is NOT wired into `normalize_scoreboard` -- which raw ESPN
  field actually supplies `field_side` (whose territory the ball is in) is
  still unknown without a live in-progress snapshot. The orchestrator plans
  to resume this lane during a live NFL game to check the real payload and
  wire it.
- **`STATUS_IN_PROGRESS` / `STATUS_HALFTIME` / `STATUS_END_PERIOD` /
  `STATUS_DELAYED` / `STATUS_POSTPONED` / `STATUS_CANCELED`** -- only
  `STATUS_SCHEDULED` and `STATUS_FINAL` were live-confirmed this run; the
  rest follow the documented ESPN convention, unconfirmed.
- **Kalshi series prefix `KXNFLGAME`** -- no saved Kalshi NFL ticker sample
  existed under `data/cache/depth_history` or `data/cache/inplay_odds` at
  build time (checked via `ls`; only kbo/mlb/npb/soccer_intl/tennis dirs and
  kbo/mlb/nba/soccer_intl/tennis price-series files were present, no NFL
  entries) -- kept as a parameter, default unverified.
- **Kalshi ticker date/team-code-order convention** -- the
  `<PREFIX>-<YY><MON><DD><TEAMS>` regex and away-then-home ordering are a
  best-effort guess at Kalshi's game-ticker format, not confirmed against a
  real ticker string.
- **College-football (`ncaaf`) league-slug behavior against the live ESPN
  endpoint** -- only the `nfl` slug was smoked live; `college-football` was
  only exercised offline (URL-construction test via a fake session).
- **`DEFAULT_SPORTS` in `inplay_capture_loop.py` still omits `nfl`** -- out
  of rails for this lane (that file is not in the NEW-files list); wiring
  this adapter into the capture loop is a separate future lane.
