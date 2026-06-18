# 04 -- Freshness Architecture: keep the betting board ALWAYS up to date

> Goal: the board self-populates with today's REAL events per sport, carries current
> lines, updates live in-play, refreshes automatically, and NEVER shows a silently
> stale number. Honest contract throughout: every feed that is down degrades to
> `status="unavailable"` with an as-of timestamp -- never a fabricated number, never a
> claimed money edge. All new code lives under `scripts/platformkit/` or `domains/`
> (src/kernel/api are human-gated), each file <=300 LOC, with a per-file test note.

Date: 2026-06-17. ASCII only.

---

## 0. Where we are today (the gap)

The board is honest but FROZEN:

- `scripts/platformkit/frontend/slate.py` -> `_DEFAULT_MATCHUPS` is a HARD-CODED list
  per sport (e.g. `nba: [{BOS,LAL},{DEN,GSW}]`, a fixed MLB 5-game slate, a fixed World
  Cup slate). The board does NOT discover today's real fixtures. `build_slate` already
  takes injectable `matchups=`, `market_lookup=`, `odds_lookup=` callbacks -- the seams
  to make it live exist; nothing fills them.
- `scripts/platformkit/odds_shop.py` -> `fetch_odds(sport_key)` pulls multi-book odds
  from The Odds API `/v4/sports/{key}/odds` using `ODDS_API_KEY` (env only), degrades to
  `unavailable`. But: no `/events` discovery call, no `commence_time` window filter, no
  quota accounting, no caching/TTL, no per-sport key map.
- `domains/mlb/ingest_current.py` already pulls the free official
  `statsapi.mlb.com/api/v1/schedule` (no key; browser UA via curl) -- but FINAL games
  ONLY (leak-free results ingest). The same endpoint returns today's SCHEDULED and LIVE
  games; we just never ask for them on the serving path.
- Live machinery EXISTS and is validated: `scripts/platformkit/live_read.build_live_read`
  + each `predictor.predict_live(...)`, driven by `live_repricer.GameState`;
  `predict_matchup.build_result` already emits an in-game block when a live state is
  supplied. Nothing currently FEEDS it a live score.
- No scheduler wires any of this on a cadence. `scripts/loop/run_loop.py` is the existing
  daemon pattern; the `schedule` skill (cloud cron) and the `CronCreate` tool exist.

So: the predictor and the repricer are live-capable; the **board's data plumbing is
static**. This doc specifies the plumbing.

---

## 1. Daily fixture auto-fetch (per sport)

A new module `scripts/platformkit/frontend/fixtures.py` exposes one function per the
slate's seam:

```
todays_fixtures(sport, *, on_date=None, http_get=_http_get_json) -> dict
  -> {"status": "ok"|"unavailable", "as_of": iso8601, "source": str,
      "fixtures": [{"home","away","event_id","commence_time","state","surface?"}, ...],
      "reason"?: str}
```

It NEVER raises, NEVER fabricates a fixture, and stamps `as_of` (UTC) on every payload.
`build_slate` is then called with `matchups=todays_fixtures(sport)["fixtures"]`.

Source per sport (free/official first, The Odds API as the universal fallback):

| Sport        | Primary source (free, no key)                                   | Endpoint / shape | Fallback |
|--------------|------------------------------------------------------------------|------------------|----------|
| `mlb`        | **MLB Stats API** `statsapi.mlb.com/api/v1/schedule`            | `?sportId=1&date=YYYY-MM-DD` -> `dates[].games[]` with `status.abstractGameState` in {Preview, Live, Final}. Reuse `NAME_TO_CODE` from `ingest_current.py` to map to SBR codes the predictor expects. Browser UA required. | The Odds API `/events` (`baseball_mlb`) |
| `nba`        | **ESPN scoreboard** `site.api.espn.com/.../basketball/nba/scoreboard` (already the source for `data/cache/spreads/`) | `?dates=YYYYMMDD` -> `events[].competitions[].competitors[]` (abbr -> canonical via the `_ALIAS` map already in `ingest_espn_odds.py`); `status.type.state` in {pre, in, post} | The Odds API `/events` (`basketball_nba`) |
| `soccer` (club) | **football-data**-style scoreboard already wired in `domains/soccer/ingest_espn_box.py` (ESPN soccer scoreboard per competition/date) | per-league scoreboard JSON | The Odds API `/events` (`soccer_epl`, etc.) |
| `soccer_intl` | **ESPN** FIFA/World-Cup scoreboard (`.../soccer/fifa.worldcup/scoreboard?dates=YYYYMMDD`) -- there is no local intl fixture fetcher today; this is net-new | scoreboard JSON; neutral-site flag from venue | The Odds API `/events` (`soccer_fifa_world_cup`) |
| `tennis`     | **The Odds API `/events`** is the pragmatic primary (Sackmann/tennis-data feeds in `domains/tennis/` are historical CSVs, not a live daily card). Sport keys `tennis_atp_*` / `tennis_wta_*`. | `/v4/sports/{key}/events` -> `[{id, commence_time, home_team, away_team}]` | none (mark unavailable) |

The Odds API `/events` endpoint (`/v4/sports/{key}/events?apiKey=...`) is the universal
fallback and the tennis primary: it returns the upcoming card WITHOUT consuming odds
quota cost the same way (events-only is cheaper -- see Section 2). Add a
`SPORT_KEY` map (`{"nba":"basketball_nba","mlb":"baseball_mlb", ...}`) to `odds_shop.py`
and an `fetch_events(sport_key)` sibling of `fetch_odds`.

Honesty: a fixture row from a free schedule API is a FACT (game exists at time T). It is
NOT a prediction or a price. If the schedule feed is down, the sport's slate degrades to
`status="unavailable"` with `as_of` and the prior cached fixtures (clearly flagged
"as of <ts>, feed down") rather than the old hard-coded list. The hard-coded
`_DEFAULT_MATCHUPS` is retained ONLY as the offline/demo fallback (fresh clone, no
network), labelled as such.

Name normalization is the load-bearing risk: each source emits its own team labels and the
predictors expect specific codes (SBR for MLB, canonical abbr for NBA, full names for
soccer_intl). Reuse the existing maps (`NAME_TO_CODE`, `_ALIAS`); add a small
`resolve_entity(sport, raw_name)` with an explicit alias table and an UNRESOLVED ->
drop-with-log path (never guess a mapping).

---

## 2. Live odds polling cadence + The Odds API quota budget

The Odds API bills per request, weighted by `regions x markets`. The free tier is ~500
req/month; paid tiers 20k+/month. We budget for a **single always-on box serving one user**,
and we must never exhaust credits silently.

Design rules:

1. **Two call classes.** `/events` (fixture discovery) is cheap (1 credit, no
   region/market multiplier). `/odds` (priced board) costs `len(regions) x len(markets)`
   credits per call. Discover fixtures often; pull odds sparingly.
2. **Cache with TTL.** A new `scripts/platformkit/frontend/odds_cache.py` wraps
   `odds_shop.fetch_odds` with an on-disk JSON cache under
   `data/frontend/odds_cache/{sport}.json` (gitignored). Each entry stores
   `{fetched_at, ttl_s, payload}`. A read inside TTL serves cache (0 credits) and the
   board shows the cached `as_of`. The cache is the single choke point where every credit
   is spent.
3. **Adaptive cadence by game state** (the lever that makes the budget fit):
   - No games live today: refresh odds **every 30-60 min** (pregame lines drift slowly).
   - T-60min to tip-off: **every 10-15 min** (line movement matters near close).
   - Any game LIVE in the sport: **every 60-120 s** for that sport only (in-play lines
     move fast) -- but capped (see #4).
   - Overnight / no card: **paused** (0 credits).
4. **Hard monthly budget guard.** `scripts/platformkit/frontend/quota.py` tracks spend in
   `data/frontend/odds_quota.json` (count + reset date, and read the
   `x-requests-remaining` response header The Odds API returns to true-up). A configurable
   `ODDS_MONTHLY_BUDGET` (default conservative, e.g. 450 on free tier) with a soft
   threshold (80% -> widen all TTLs 2x) and a hard stop (100% -> serve cache only, board
   flags "odds budget reached, lines as of <ts>"). NEVER blow the cap to refresh.
5. **Minimize the multiplier.** Default `regions=us`, `markets=h2h` only on the auto
   path (the board's core number). Totals/spreads pulled on-demand per matchup, not for
   the whole slate. One region.

Indicative monthly spend (paid 20k tier, ~6 games/day across 4 sports, in-season):
discovery ~4 sports x 48 calls/day x 30 ~= 5.8k (cheap, 1 credit each); pregame odds at
h2h/us ~4 x 24 x 30 ~= 2.9k; live bursts dominate only when games are actually live and
are auto-paused otherwise. Comfortably inside 20k. On the FREE 500 tier the adaptive
cadence + cache + hard guard keep one or two sports' h2h refreshed a few times a day and
degrade the rest to cache -- honestly flagged, never faked.

---

## 3. In-game live updates (detect live games, reprice the board)

Detection comes FREE from Section 1: every fixture row carries a `state`
(pre / in / post). The fixture feeds also carry the live SCORE and clock:

- MLB `statsapi` schedule -> `linescore.currentInning`, `inningHalf`,
  `teams.home/away.score`, `status.abstractGameState == "Live"`.
- NBA / soccer ESPN scoreboard -> `competitions[].status.type.state == "in"`,
  `competitions[].competitors[].score`, `status.displayClock` / `period`.
- Tennis (Odds API has no score; ESPN tennis scoreboard or the per-match feed gives
  set/game state) -- if no live score source is available, tennis stays pregame-only and
  is flagged "live state unavailable", never invented.

New module `scripts/platformkit/frontend/live_board.py`:

```
live_rows(sport, fixtures) -> list[row]
  for each fixture whose state == "in":
    map the feed's score/clock -> live_repricer.GameState (sport-specific:
       nba elapsed_minutes+scores; mlb inning/half/runs; soccer minute/goals;
       tennis set state)
    call predict_matchup.build_result(...) WITH the live kwargs (reuses
       live_kwargs() mapping already in predict_matchup.py) OR
       live_read.build_live_read(sport, GameState) for the concept layer.
    attach the in-game block to the slate row + a live as_of timestamp.
```

This REUSES the validated path -- no new prediction math. `build_result` already returns
an `ingame` block when a complete live state is supplied; `live_kwargs()` already maps the
generic flags onto each sport's `predict_live`. We are only supplying it real live state
from the fixture feed instead of CLI args.

Board behavior: a live row shows the in-game re-priced number with a `live` badge and a
fresh-seconds-ago timestamp; a pregame row shows the pregame number; a final row shows
the settled result and stops refreshing. The honest framing string already in
`slate.HONEST_NOTE` and `live_read._BANNER` carries through unchanged (in-game ADDS the
realized state; no $ edge claimed).

Score-feed lag is real -- stamp the live row with the FEED's timestamp, not wall-clock, so
the UI shows true data age, and flag rows whose feed timestamp is older than (e.g.) 3x the
poll interval as STALE.

---

## 4. Staleness indicators (never silently old)

Every number on the board carries provenance. Standardize one block, attached to each
slate row and to the slate envelope:

```
"freshness": {
   "as_of": "2026-06-17T18:42:05Z",   # when this datum was produced/fetched
   "source": "the-odds-api|statsapi|espn|cache|model",
   "age_s": 73,                         # server now - as_of
   "stale": false,                      # age_s > threshold for this datum class
   "status": "ok|cached|unavailable"
}
```

Per-datum thresholds (datum class -> stale-after): live odds 180s, live score 30s,
pregame odds 1800s, fixtures 6h, ratings 36h. The UI (`static/index.html`) renders a green
/ amber / red dot per cell from `freshness.stale` + `status`, and a "Lines as of HH:MM:SS,
N min ago" caption. A feed that is down shows `status="unavailable"` and the LAST known
`as_of` in amber, explicitly captioned "feed down since <ts>" -- the old number is never
shown as if current. This is the binding honesty rule from the no-edge/no-fabrication
contract, surfaced visually.

The slate envelope also carries a top-level `generated_at` and a `feeds` health map
(`{odds: ok, fixtures: ok, live: degraded}`) so the user sees board-wide health at a
glance.

---

## 5. Scheduling / automation (always-on box)

The serving box is a single Windows always-on machine. Recommended concrete mechanism, in
order of preference:

**P0 (chosen): a self-contained refresh daemon** -- `scripts/platformkit/frontend/refresh_daemon.py`,
modeled on `scripts/loop/run_loop.py`. One process, an `asyncio`/`schedule`-style loop with
the adaptive cadence from Section 2:

- tick every 60s; decide per sport what is due (fixtures? pregame odds? live burst?);
- write the computed board to `data/frontend/board/{sport}.json` (the cache the FastAPI
  `serve.py` reads, so the HTTP path never blocks on network);
- honor the quota guard; on any feed error, write `status="unavailable"` + keep last good
  payload with its `as_of`.

`serve.py`'s `/api/slate` then serves the daemon's last-written board (with freshness
stamps) instead of computing synchronously. This decouples the (rate-limited, fail-prone)
network from the (must-be-instant, must-be-honest) HTTP response. Run the daemon under
Windows Task Scheduler "at log on / restart on failure" or `nssm` as a service.

**Alternative mechanisms (documented, not chosen):**
- `CronCreate` tool / the `schedule` skill (cloud cron) -- good for the once-daily
  fixture pull and ratings refresh, but session/cloud-scoped, not ideal as the always-on
  in-play poller on a local box.
- A SessionStart hook (`scripts/update_vault.py` is the precedent) can KICK the daemon if
  it is not already running, so opening a session guarantees freshness -- but the daemon,
  not the hook, owns the cadence.

Concretely: **daemon for in-play + intraday odds; one cron/Task-Scheduler entry at ~06:00
local for the daily fixture pull + ratings refresh.**

---

## 6. Ratings refresh cadence

Ratings are the predictor's memory of results; they go stale as games finish.

| Sport        | Refresh module / path                                   | Cadence | Notes |
|--------------|----------------------------------------------------------|---------|-------|
| `mlb`        | `domains/mlb/ingest_current.py` (FINAL games) -> `refresh_ratings.py` (concat frozen+current) | **daily ~06:00** (after the prior day's games settle) | already non-destructive; bump the `end_date` default to "today" instead of the frozen `2026-06-16` literal -- a small parameterization, see P1 |
| `nba`        | `domains/basketball_nba/ingest_schedule.py` + `ingest_boxscores` | **daily in-season** | results-only; same leak-free pattern |
| `soccer`     | `domains/soccer/ingest_espn_box.py` / footballdata     | **daily** | per active league |
| `soccer_intl`| `domains/soccer_intl/ratings.py` (needs a results ingest sibling -- net-new, mirror MLB's pattern) | **daily during a tournament**, else weekly | |
| `tennis`     | `domains/tennis/ingest_espn.py`                          | **daily during active tournaments** | |

Cadence rationale: a single day adds at most ~1-2 games per team, so daily post-settlement
refresh is sufficient -- ratings do not need intraday updates. The refresh is a separate,
RESULTS-ONLY job (FINAL games only) so it stays leak-free; it must NEVER ingest in-progress
scores into the ratings corpus (the live board reads live scores; the ratings corpus reads
only finals). The daily job runs AFTER all of the prior day's games are Final (the ~06:00
slot covers late West-coast / international finishes).

---

## 7. Phased implementation plan

Every module <=300 LOC, lives under `scripts/platformkit/` or `domains/`, degrades to
`unavailable`+timestamp, never fabricates, never claims edge. Per-file tests only
(`python -m pytest <one_file> -q`); never the full suite (freezes the box).

### P0 -- self-populating board with current lines + freshness (the core ask)

1. `scripts/platformkit/odds_shop.py` -- ADD `SPORT_KEY` map + `fetch_events(sport_key)`
   (sibling of `fetch_odds`, hits `/v4/sports/{key}/events`; same env-only key, same
   degrade-never-raise contract). *Test:* `test_odds_shop.py` -- add canned-`/events`
   parse + missing-key -> unavailable cases (network-free, injected `http_get`).
2. `scripts/platformkit/frontend/fixtures.py` -- `todays_fixtures(sport, on_date,
   http_get)` per Section 1 (MLB statsapi + NBA/soccer ESPN + Odds-API `/events` fallback;
   reuse `NAME_TO_CODE`/`_ALIAS`; stamp `as_of`). *Test:* `test_fixtures.py` -- canned
   statsapi + ESPN payloads -> normalized rows; feed-down -> unavailable+as_of.
3. `scripts/platformkit/frontend/odds_cache.py` + `quota.py` -- TTL disk cache wrapping
   `fetch_odds`, monthly budget guard reading `x-requests-remaining`. *Test:*
   `test_odds_cache.py` -- TTL hit/miss, budget soft/hard thresholds (no network).
4. `scripts/platformkit/frontend/freshness.py` -- the `freshness` block builder + stale
   thresholds (Section 4). *Test:* `test_freshness.py` -- age/stale/status transitions.
5. Wire-up: call `build_slate(sport, matchups=todays_fixtures(...)["fixtures"],
   odds_lookup=<cache-backed>)` and attach `freshness` to each row. (Touches `slate.py`
   via its EXISTING injectable seams -- no signature change.) *Test:* extend the slate
   test with a stubbed `todays_fixtures`/`odds_lookup`.

P0 outcome: opening the board on any day shows today's REAL fixtures with current h2h
lines and a freshness dot per cell; feeds-down degrade honestly. No daemon yet (manual or
cron-triggered rebuild).

### P1 -- live in-play + automation

6. `scripts/platformkit/frontend/live_board.py` -- detect `state=="in"` fixtures, map feed
   score/clock -> `GameState`, reprice via `predict_matchup.build_result` /
   `live_read.build_live_read`; attach in-game block + live `as_of`. *Test:*
   `test_live_board.py` -- canned live-score payload -> in-game row via a stubbed predictor.
7. `scripts/platformkit/frontend/refresh_daemon.py` -- the adaptive-cadence loop (Section
   5) writing `data/frontend/board/{sport}.json`; quota-aware; last-good-on-error. *Test:*
   `test_refresh_daemon.py` -- one tick with stubbed fetchers writes a board file; error
   tick preserves last-good.
8. `serve.py` -- `/api/slate` reads the daemon's last-written board file (fallback to
   synchronous `build_slate` if absent). Small change to the existing endpoint. *Test:*
   extend `serve.py` test: board-file present -> served; absent -> synchronous fallback.
9. MLB `refresh_ratings.py` / `ingame_current.py` -- parameterize `end_date` to "today"
   (remove the frozen `2026-06-16` literal default) so the daily ratings job is real.
   *Test:* extend the existing MLB ingest test with an explicit `end_date`.

### P2 -- breadth + polish

10. `soccer_intl` results-ingest sibling (mirror `mlb/ingest_current.py`) so intl ratings
    refresh during tournaments; tennis live-score source eval (ESPN tennis scoreboard) or
    keep pregame-only-flagged.
11. UI (`static/index.html`) -- green/amber/red freshness dots, "lines as of" caption,
    board-wide `feeds` health strip, live badge + seconds-ago on in-play rows.
12. On-demand totals/spreads per matchup (extra markets pulled only when the user expands a
    row -- keeps the auto-path multiplier at h2h/us).

---

## 8. Honesty invariants (binding, restated)

- Every datum carries an `as_of` + `source`; stale data is FLAGGED, never shown as current.
- Any feed down -> `status="unavailable"` + last `as_of`, never a fabricated number.
- Fixtures are facts; odds are book prices; the model number MATCHES the devigged close
  (calibration/sharpness). NO $ edge is claimed anywhere on the board.
- The ratings corpus ingests FINAL games only (leak-free); the live board reads live scores
  but never folds them into ratings.
- Quota guard is hard: never blow the monthly cap to refresh -- degrade to cache + flag.
- New code only under `scripts/platformkit/` or `domains/`; <=300 LOC/file; per-file tests
  only; ASCII stdout; no secrets (key from `ODDS_API_KEY` env only).
```
