# Ingest pipelines: how data gets in, at what cadence -- CourtVision

> Every prediction, paper bet, and CLV number downstream of this page is only as
> good as the capture that fed it. This doc walks each ingest pipeline: the
> source, the cadence, the exact output path and row shape, and -- most
> importantly -- the failure mode each one has already hit and the guard that now
> catches it. For where the data goes next see
> [`docs/PAPER_TRADING_STACK.md`](PAPER_TRADING_STACK.md) and [`docs/DATA.md`](DATA.md).

All feeds are keyless public endpoints, fetched politely (descriptive
User-Agent, request pacing, exponential backoff), append-only on disk, and
error-isolated per game/ticker/provider -- one bad fetch never sinks a pass.
Nothing here claims an edge; this is measurement infrastructure.

---

## The map

| Pipeline | Source | Cadence | Output |
|---|---|---|---|
| MLB GUMBO live poller | statsapi.mlb.com feed/live + diffPatch | 10 s while live (5 s floor), 30 s idle tick | `data/domains/mlb/gumbo_live/<gamePk>.jsonl` |
| In-play price snapshots | Kalshi (primary) + ESPN/Polymarket corroborators | 5 s live / 120 s idle | `data/cache/inplay_history/<sport>/<date>.jsonl` |
| Kalshi depth ladders | Kalshi `/markets/{ticker}/orderbook` | every 15th live tick (~5 min/pass, ~20 min/ticker measured) | `data/cache/depth_history/<sport>/<date>.jsonl` |
| Pregame odds snapshots | Sportsbook/exchange providers via the aggregate stack | continuous scan cycles, date-rolled files | `data/cache/line_history/<sport>/<date>.jsonl` |
| NBA quarter/player boxes | ESPN site.api summary | backfill runs, >=1.5 s pacing | `data/cache/quarter_box/<game_id>_q<n>.json` |
| Finals / outcome labels | ESPN scoreboards, league results pages | bounded refresh per settle tick (900 s) | `data/domains/<sport>/*.parquet` |
| Feed health scoreboard | the same live provider stack | ~10 min probe | `data/frontend/ops/feed_health.json` |

---

## 1. MLB GUMBO live poller -- `scripts/platformkit/ingame/gumbo_mlb_poller.py`

The richest live feed in the system: MLB's GUMBO `feed/live` object (every
pitch, base state, and score change) via a bootstrap-then-diffPatch protocol.

- **Bootstrap once, then deltas.** First contact GETs the full `feed/live`
  snapshot and caches `metaData.timeStamp`; steady state polls
  `feed/live/diffPatch?startTimecode=<ts>` and applies the JSON patch to the
  cached snapshot. A failed patch falls back to a fresh bootstrap. Per-game
  state (`{ts, snapshot}`) persists across runs in
  `gumbo_live/_poller_state.json`, so a restart resumes instead of re-fetching.
- **Cadence.** While at least one game is live, `run_live_window()` fast-polls
  at `CV_GUMBO_LIVE_SEC` (default 10 s, hard politeness floor 5 s) with
  exponential backoff to 60 s on all-error passes; the idle tick stays at the
  runner's 30 s. Disk cost at the 10 s cadence is roughly 400-1,200 rows/game
  at ~350 bytes/row -- under 0.5 MB/game, absorbed by the existing 30-day
  retention policy with large headroom.
- **Row shape.** One extracted tick per pass, appended to
  `<gamePk>.jsonl`: score/inning/base-out state plus two timestamps -- `ts`
  (MLB's own `metaData.timeStamp`, the event wall-clock) and `captured_at`
  (our poll receive time). Keeping both is what makes latency measurable
  instead of assumed.

**The design lesson: the UTC-blindness bug.** The poller's default schedule
date was originally "today, UTC". Every evening at about 7 pm CT the UTC date
rolled to tomorrow, so the schedule query returned the *next* day's
all-Preview slate -- 0 live games found while 12 were actually in progress. The
poller was not broken; it was asking a correct question about the wrong day.
The fix (`list_live_game_pks()`): default to the MLB **baseball date** --
UTC minus 10 hours -- so the slate date rolls at ~5-6 am ET, after the last
West Coast game ends, not at midnight UTC. Verified live the same evening
(12 live games, 12 rows) and pinned by a regression test. The general rule:
a sports "day" is a domain concept, never a calendar-UTC one; any default that
silently substitutes the latter will go blind exactly when the data matters
most (evenings -- when the games are on).

## 2. In-play price capture -- `scripts/platformkit/odds_provider/inplay_snapshot_daemon.py`

Kalshi is the primary in-play venue (liquidity-gated, tradeable prices); ESPN
and Polymarket ride along as corroborators explicitly marked
`tradeable=False` and never persisted as executable prices.

- **Cadence.** `FAST_INTERVAL_SEC = 5` while any game is live,
  `IDLE_INTERVAL_SEC = 120` otherwise, exponential backoff capped at 300 s.
- **Row shape** (`data/cache/inplay_history/<sport>/<date>.jsonl`):
  `{sport, game_id, venue, market_type, side, ticker, prob, ts, phase:
  "in_play", source_ts}`.
- **Liveness is venue-native.** A market counts as in-play from its own
  status/commence/close fields -- an earlier design that cross-joined to ESPN
  ids gated out every real live tick. Grace windows: 5 min after scheduled
  start, 6 h maximum game length. Unknown liveness -> not live (fail closed).
- **The frozen-feed guard.** A tradeable tick must carry a fresh `source_ts`
  (the feed's own timestamp, never re-stamped). A cached or frozen upstream
  body that keeps returning the same stale quote is dropped rather than
  recorded as a sequence of "fresh" prices.

**The shared-wall guard: the Kalshi rate governor**
(`odds_provider/kalshi_rate_governor.py`). Two daemons hitting the same venue
with only per-process pacing produced a measured 1,678 429s/day from the
unpaced one. The governor is a cross-process token bucket: a conservative
shared ceiling (`BASE_RPS = 15`, half the documented keyless tier) split into
registered per-caller shares -- capture 0.35, snapshot 0.65, feed_health 0.15,
close_capture 0.15, backfill 0.10 (added after an unpaced backfill fleet
tripped a 1,254-count 429 penalty), aggregate 0.15 (added after the
`default_providers()` stack hit Kalshi ungoverned and stormed the venue,
n_429_total=2606). Any 429 writes a pressure record to a shared state file;
every caller (this process or the other daemon on its next read) halves its
refill rate for a 30 s decay window. Fail-open throughout: a corrupt state
file or broken clock never blocks a fetch, and `KALSHI_GOVERNOR_OFF=1` makes
it a no-op. The lesson from the close-capture incident: an *unregistered*
caller falls to a default share that can over-subscribe the ceiling on a full
slate -- every new Kalshi caller registers a share up front.

## 3. Kalshi order-book depth -- `scripts/platformkit/odds_provider/depth_capture.py`

Full price ladders, not top-of-book -- the accrual asset that makes the paper
stack's realistic fill simulation possible (see
[`PAPER_TRADING_STACK.md`](PAPER_TRADING_STACK.md), section 2).

- **Cadence.** Piggybacks the in-play capture loop, firing on every 15th tick
  (`DEPTH_CAPTURE_EVERY_N_TICKS = 15`): ~5 min per pass at the 20 s live
  cadence, ~20 min per ticker measured across a slate. Depth is a slow-moving
  accrual asset, not a decision input, so it deliberately never rides every
  fast tick.
- **Row shape** (`data/cache/depth_history/<sport>/<date>.jsonl`,
  `capture_version: 1`):

```jsonc
{
  "ts": "2026-07-08T00:03:45Z",          // snapshot-cycle time (shared per pass)
  "sport": "mlb",
  "ticker": "KXMLBGAME-26JUL101940ATHCWS-CWS",
  "event_ticker": "KXMLBGAME-26JUL101940ATHCWS",
  "yes_bids": [[0.01, 5410.0], [0.02, 6600.0], ...],
  "yes_asks": [[0.01, 5485.0], ...],      // the RAW no_dollars ladder, never a derived 1-p
  "depth_totals": {"yes_bid_total": 13108.0, "yes_ask_total": 13063.0},
  "source": "kalshi", "source_url": "...",
  "fetched_at": "...",                     // TRUE per-ticker network-fetch time
  "capture_version": 1
}
```

  `ts` and `fetched_at` are distinct on purpose: a lagged per-ticker fetch
  inside one pass stays honestly visible instead of being re-stamped "now".
- **Guards.** Per-ticker and per-series isolation (one 429 or malformed body
  skips that ticker, never zero-fills it); atomic append (tmp + `os.replace`)
  so a reader never sees a torn line; failure of the whole depth hook is
  caught by the host loop -- the live pairing and paper decisions never see it.

## 4. Pregame odds history -- `data/cache/line_history/<sport>/<date>.jsonl`

Written by `odds_provider/snapshot.write_quotes` from the aggregate provider
stack (ESPN-embedded books, Pinnacle, FanDuel, Kalshi, Polymarket), read back
by `odds_provider/line_store.py`. One row per (game, market, side, book)
observation:

```jsonc
{"sport": "nba", "game_id": "401859967", "home": "San Antonio Spurs",
 "away": "New York Knicks", "market_type": "moneyline", "side": "home",
 "line": null, "odds": 1.5208, "book": "espn:DraftKings",
 "devigged_prob": 0.6365, "captured_at": "2026-06-18T18:32:04+00:00",
 "commence_time": "2026-06-14T00:30Z"}
```

The honesty rail lives in the reader, not the writer: `line_store.get_close()`
returns a **true close** (`clv_is_proxy=False`) only for a quote captured
inside the 30-minute lock window before `commence_time`. Anything else is
returned as an explicit proxy -- a close is never fabricated, and a row without
a `commence_time` can never be a true close because it cannot be proven at
lock. This single distinction is what keeps every downstream CLV number
labelable as true-close vs proxy.

## 5. NBA player boxes -- `domains/basketball_nba/ingest_espn_player_box.py`

The 2025-26 season had a 74-of-1,156-game player-box gap: stats.nba.com is
blocked from this box, ESPN site.api is the documented working route. The
backfill writes ESPN full-game player boxes into the **existing** quarter-box
cache in the exact record shape the existing pure transform
(`ingest_boxscores.py`) already consumes -- zero transform changes.

- **The `q0` convention.** Real quarter files are `<gid>_q1.json` ..
  `_q4.json`; the ESPN full-game file is `<gid>_q0.json` with `period: 0` and
  `source: "espn_fullgame"`. Quarter-level consumers glob q1-q4 and never see
  it; full-game consumers aggregate it naturally. Honest gap, stated in the
  file: ESPN has no per-quarter player box and its minutes are whole-integer
  strings.
- **Name -> NBA-id mapping.** The parquet uses NBA player ids; ESPN uses its
  own athlete ids. Joined via accent-stripped, suffix-dropped lowercase names
  (`_norm_name`: NFKD strip, drop Jr/Sr/II-V) against the existing 627-player
  table -- verified collision-free. A player absent from the table (a
  post-cutoff debut) gets a **synthetic negative id** `-espn_id` with
  `player_id_mapped: false` and a log line: usable within the season,
  deliberately un-joinable across seasons, and never a silently wrong id.
- **Event matching.** ESPN events map to NBA game ids by
  (date, home_abbr, away_abbr) against `games.parquet` through the bridge
  tricode normalizer; a game with no unique event match is counted and
  skipped, not guessed.
- **Resume safety.** A game with *any* existing `<gid>_q*.json` is skipped --
  this both makes the backfill re-runnable from any interruption point and
  protects the 74 games that already have real quarter files from double
  counting. Only FINAL-status games are written; >=1.5 s sleep before every
  call, exponential backoff on errors.

Row shape per player (sampled from a real `_q0.json`): `{player_id,
player_id_mapped, espn_player_id, player_name, team_abbreviation,
start_position, min, fgm, fga, fg3m, fg3a, ftm, fta, pts, reb, oreb, dreb,
ast, stl, blk, to, pf, plus_minus}`.

## 6. Finals and outcome labels -- `scripts/platformkit/autonomy/label_finals_refresh.py`

The settlement layer (see [`PAPER_TRADING_STACK.md`](PAPER_TRADING_STACK.md))
resolves final scores from local parquets -- which means those parquets going
stale silently strands open bets. This module is the bounded, sport-blind
keeper: for each `RefreshSpec` (soccer_intl finals, MLB ESPN boxscores, WNBA
scoreboard, NPB/KBO season results) it reads the parquet's own max date,
computes the missing UTC dates, and calls that sport's ingest for just those
dates. Bounds everywhere: at most `max_dates_per_tick = 10` dates per tick, a
3-day bootstrap window for a brand-new parquet (never a full-history pull),
and per-spec isolation so one failing fetch never blocks a sibling.

**The design lesson: the partial-day lockout.** The obvious refresh rule --
"fetch from (max existing date + 1)" -- has a subtle trap when the ingest
persists only games already FINAL at fetch time. The first final of day D
advances the watermark to D, and the pure-watermark rule then never re-fetches
D: every game that finished later that day is locked out forever. Observed in
production: exactly 1 of ~14 MLB games per day landed over a four-day stretch,
leaving 129 in-game paper bets unsettleable. The fix is `refetch_days = 3`:
the trailing three days are *always* re-fetched even when present. Because
every wired ingest dedupes on its event/game id, the re-fetch is idempotent --
the guard costs a few redundant requests and eliminates the failure class.
The general rule: a watermark is only valid over data that is complete at
write time; partially-complete days need a trailing refetch window, not a
higher watermark.

## 7. Feed health -- `scripts/platformkit/odds_provider/feed_health.py`

The aggregate provider stack tolerates a down provider by design (that venue
just drops out of the merged slate) -- which means nobody notices a dark
scraper unless something watches. The health probe fetches through the *same*
provider objects the live slate uses (never a synthetic ping) for each
(provider, sport) pair across nba/mlb/soccer/soccer_intl/tennis/wnba/npb, and
classifies each result:

- **GREEN** -- real data returned, *or* an honest benign degrade
  ("unsupported sport", "no events"): a provider with nothing to say is
  healthy, not broken. Known structural gaps (Pinnacle has no NPB league
  mapping) are classified benign rather than paging forever.
- **RED** -- an error-shaped degrade: 401/403/auth, timeout, parse failure,
  unexpected shape, exception. A RED with an auth/block-shaped reason
  additionally marks that provider's host stealth-first for its next fetch
  (`heal()`), escalating the transport tier instead of retrying the same
  blocked path.

Output: `data/frontend/ops/feed_health.json` -- per-row
`{provider, sport, status, reason, n_events}` plus an overall verdict, feeding
the ops freshness SLA. The probe's own Kalshi calls are governor-registered
(`governor_caller="feed_health"`, 0.15 share) after it once 429'd itself.

---

## Failure modes and the guard that catches each

| Failure mode | Where it bit | Guard |
|---|---|---|
| Calendar-UTC date != sport's game day | GUMBO poller blind every evening | Baseball-date default (UTC-10h roll) + regression test |
| Watermark advanced by a partially-complete day | 129 unsettleable in-game bets | `refetch_days=3` trailing re-fetch, idempotent by id-dedup |
| Two daemons sharing one venue's rate wall | 1,678 unpaced 429s/day | Cross-process token-bucket governor with registered shares |
| Frozen upstream feed replaying a stale quote | in-play capture | `source_ts` freshness requirement on every tradeable tick |
| Stale quote mistaken for a closing line | CLV grading | 30-min lock window; proxy closes labeled, never fabricated |
| One bad game/ticker/provider killing a pass | every poller | per-item exception isolation, error counted and skipped |
| Torn JSONL line under concurrent read | depth capture | atomic tmp + `os.replace` append |
| Backfill interrupted mid-season | ESPN player-box backfill | skip-if-any-cache resume; FINAL-status gate |
| Name-join misassigning a player id | ESPN -> NBA id mapping | collision-verified normalized join; unmatched -> synthetic negative id, flagged and logged |
| Dark scraper vanishing silently from the slate | provider aggregate | feed_health GREEN/RED scoreboard + stealth-first heal |

---

*Related: [`docs/PAPER_TRADING_STACK.md`](PAPER_TRADING_STACK.md) -
[`docs/DATA.md`](DATA.md) - [`docs/operations/data-pipeline.md`](operations/data-pipeline.md) -
[`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-07-07*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
