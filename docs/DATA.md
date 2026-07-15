# Data Layer — CourtVision

Sources, ingest pipeline, cache layout, and regeneration commands.

---

## Overview

The data funnel has two independent tracks that merge at the feature layer:

```
Track 1: Broadcast video
    yt-dlp / archive.org / local inbox
        ↓
    src/ingest/fetcher.py  (content-addressed SHA256 store)
        ↓
    src/pipeline/unified_pipeline.py  (YOLO → homography → Kalman+Hungarian → OSNet → EasyOCR)
        ↓
    data/tracking_data.csv  (~$0.10/game CV cost on consumer RTX 4060)

Track 2: Statistical / market data
    nba_api + BBRef + odds scrapers
        ↓
    src/data/  (TTL-cached JSON per source)
        ↓
    src/features/feature_engineering.py
        ↓
    Feature matrix → prop models + win-prob model
```

The two tracks join at `feature_engineering.py`. CV features are wired as
inputs but currently carry SHAP importance ≈ 0 in the production prop models
(the plumbing is complete; the signal is not yet demonstrated).

---

## Track 1: CV Pipeline from Broadcast Video

**Cost benchmark:** ~$0.10–$0.13 per game on a consumer RTX 4060, versus
six- or seven-figure annual contracts for Sportradar or Second Spectrum.
This is the moat thesis: not that broadcast CV is better than optical tracking
today, but that the cost barrier is dramatically lower.

**What the pipeline produces per game:**

| Output | Description |
|---|---|
| Player court coordinates | (x, y) in feet via perspective homography |
| Per-track behavioral fields | spacing, velocity, contested-shot proximity |
| Event detections | shots, fouls, rebounds, turnovers from frame context |
| Player identity | jersey color + re-ID resolution to real NBA player IDs |

**Honest CV status (from `docs/KNOWN_LIMITATIONS.md`):**

- Stable tracker slots: ~5–6 per frame on the calibration clip; reliable
  10-player tracking not yet demonstrated on broadcast footage.
- Player identity: 17,254 rows / 241 games / 252 distinct real NBA player IDs
  in `data/nba_ai.db cv_features`. Per-player CV attribution is ~4% of
  production data.
- Positional accuracy: output via homography; no ground-truth labels exist,
  so MOTA/IDF1/positional-RMSE are not benchmarked — only self-consistency
  gates.
- CV features in prod prop models: SHAP importance ≈ 0 (`cv_lift_report.json:
  has_cv_data = false`). Credible thesis, complete plumbing, no demonstrated
  predictive advantage yet.

**Key CV modules:**

| Module | Role |
|---|---|
| `src/pipeline/unified_pipeline.py` | Orchestrator: video → detections → features |
| `src/tracking/advanced_tracker.py` | 6D Kalman filter + Hungarian assignment |
| `src/tracking/court_detector.py` | HSV masking + HoughLinesP + getPerspectiveTransform |
| `src/tracking/osnet_reid.py` | OSNet omni-scale re-ID (ImageNet-pretrained weights) |
| `src/tracking/color_reid.py` | HSV-histogram appearance model (production) |
| `src/ingest/fetcher.py` | Content-addressed SHA256 video store, multi-source retry |
| `src/ingest/sources.py` | Source registry: youtube / archive.org / nba_condensed / inbox |

**Run the pipeline on a local video:**

```bash
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

Output: `data/tracking_data.csv` + per-frame behavioral fields.

---

## Track 2: Statistical and Market Data

### NBA API (`nba_api` package — free)

All modules live in `src/data/`. Data is TTL-cached as JSON under `data/nba/`.

| Module | Endpoint | Output file | TTL | Coverage |
|---|---|---|---|---|
| `nba_stats.py` | LeagueDashPlayerStats | `player_avgs_{season}.json` | 24 h | 569 active players |
| `player_scraper.py` | PlayerGameLogs | `gamelogs_{season}.json` | 6 h | 622 players, 3 seasons |
| `shot_chart_scraper.py` | ShotChartDetail | `shots_{player_id}_{season}.json` | 24 h | 221,866 shots |
| `pbp_scraper.py` | PlayByPlayV2 | `pbp_{game_id}.json` | 48 h | 3,627 / 3,685 games |
| `nba_tracking_stats.py` | LeagueHustleStatsPlayer | `hustle_stats_{season}.json` | 24 h | 567 players × 3 seasons |
| `nba_tracking_stats.py` | PlayerDashPtShots | `shot_dashboard_all_{season}.json` | 24 h | Shot creation style / defender distance |
| `nba_tracking_stats.py` | LeagueDashPtDefend | `defender_zone_{season}.json` | 24 h | 566 players × 3 seasons |
| `nba_tracking_stats.py` | MatchupsRollup | `matchups_{season}.json` | 24 h | ~2,200 records × 3 seasons |
| `nba_tracking_stats.py` | SynergyPlayTypes | `synergy_offensive/defensive_{season}.json` | 24 h | 300 records × 2 sides |
| `nba_tracking_stats.py` | LeaguePlayerOnDetails | `on_off_{season}.json` | 24 h | 569 players × 3 seasons |

The 291,625-pair player-vs-player matchup matrix (`data/cache/coverage_faced_allseasons.parquet`)
is built from 2,214 raw per-game tracking files across three seasons via
`scripts/intel/build_coverage_allseasons.py`.

### Basketball Reference

**Module:** `src/data/bbref_scraper.py` — TTL 48 h

| Dataset | Output | Coverage |
|---|---|---|
| Advanced stats (VORP, WS/48, BPM, TS%) | `bbref_advanced_{season}.json` | 736 players × 4 seasons (2022-23 to 2024-25 complete, 2025-26 partial in-progress) |
| Player contracts / walk-year flag | `contracts_2024-25.json` | 523 players (171 walk-year) |

### Contextual and Market Sources

| Module | Source | Output | Notes |
|---|---|---|---|
| `src/ingest/injury_report.py` | NBA official PDF + ESPN RSS | `data/injuries_<date>.json` | 30-min polling |
| `src/ingest/ref_stats.py` | Referee assignment feeds | `data/nba/ref_assignments.json` | pace_tendency, foul_rate_tendency |
| `src/ingest/rest_travel.py` | Static schedule + arena coords | In-memory | rest_days, B2B flag, travel miles |
| `src/ingest/lineup_data.py` | RotoWire scrape | `data/lineups_<date>.json` | Projected starters |
| `src/ingest/vegas_lines.py` | The Odds API + DK direct scraper | `data/lines/<date>.csv` | Live props, 15-min TTL |
| `src/ingest/prop_line_movement.py` | Line-movement monitor | In-memory | Opening vs closing delta |

---

## Track 3: Multi-Sport Keyless Platform Sources

Beyond the NBA-specific feeds above, the sport-blind platform (`domains/<sport>/`
adapters + `scripts/platformkit/odds_provider/`) ingests four sports from
**keyless-first** sources, plus prediction markets and DFS prop feeds. No paid
odds-API key is required for the default slate; an optional bearer token for
Kalshi / Polymarket is read from ENV only and is **not** needed for public reads.

> **Honesty rails.** Everything below is PAPER / measurement only. The capture
> daemons record prices; they never place orders and no $-edge is claimed. We
> never fabricate a price: a feed/parse miss is logged and skipped, never filled
> with a guess. `data/` is local-only and gitignored (see
> [data/README.md](../data/README.md)); nothing here is published.

### Per-sport source ledger (have / missing / how acquired)

Each `domains/<sport>/ingest_manifest.py` is the authoritative provenance
contract: it maps every corpus file-stem to a `leak_class`
(pre_game / in_game / post_game / reference) and a freshness SLA in minutes.

| Sport | Have (keyless source) | How acquired | Missing / partial |
|---|---|---|---|
| `basketball_nba` | schedule+elo spine, moneyline odds, as-of features, per-quarter linescores, player+team box | ESPN site API + `nba_api` (see Track 2) | true sharp-book close (Pinnacle archive accrues from Oct 2026); CV depth (~85 games) |
| `mlb` | schedule spine, moneyline odds, starting pitchers, as-of SP form, park factor, player gamelogs | MLB StatsAPI + ESPN site API + SBR historical | full multi-season odds archive |
| `soccer` (EPL) | match spine (Poisson-goals), O/U 2.5 odds, match stats, as-of xG-proxy, club priors | football-data.co.uk + ESPN site API | shot-level event data (xG is a proxy) |
| `soccer_intl` (World Cup) | DFS player props, prediction-market two-way prices | Underdog (sport_id FIFA), PrizePicks, Kalshi (KXWC), Polymarket | book moneylines (DFS + PM only) |
| `tennis` | ATP+WTA match spine, player moneylines, serve/return box, as-of hold/return % per surface | Sackmann GitHub archives + tennis-data.co.uk + ESPN | live in-match point feed |
| `nfl` | manifest scaffolded only | (planned) | full ingest not yet built |

### Keyless team-odds providers (`scripts/platformkit/odds_provider/`)

| Provider | Module | Endpoint (keyless) | What it returns | Sport keys |
|---|---|---|---|---|
| ESPN | `espn.py` | `site.api.espn.com/.../scoreboard` + `summary?event=<id>` | `pickcenter[]` republishes ONE book's moneyline (+ spread/total when both line AND per-side odds present) | nba, mlb, soccer (eng.1), soccer_intl (fifa.world) |
| Kalshi | `kalshi.py` | `api.elections.kalshi.com/trade-api/v2/markets` | per-team YES contract -> implied prob; grouped by `event_ticker` (KXNBA / KXMLB / KXEPL / KXWC) | nba, mlb, soccer, soccer_intl |
| Polymarket | `polymarket.py` | `gamma-api.polymarket.com/markets` | two-way `outcomes`+`outcomePrices` (JSON-string arrays) -> implied prob; best-effort slug/keyword filter | nba, mlb, soccer, soccer_intl |

ESPN republishes a sportsbook line (we do NOT scrape the book directly).
Spread/total nodes are emitted **only** when ESPN supplies the line AND both-side
odds -- otherwise the node is omitted, never assumed. Kalshi/Polymarket prices are
implied probabilities in `[0,1]` converted to decimal odds via `1/prob`; a market
that cannot be confidently mapped to a two-team game is skipped, never guessed.
All three degrade to an explicit UNAVAILABLE sentinel on failure -- never a fake.

### DFS player-prop feeds (`prop_*.py`)

| Provider | Module | Endpoint (keyless) | Pricing handling |
|---|---|---|---|
| Underdog | `prop_underdog.py` | `api.underdogfantasy.com/beta/v5/over_under_lines` | uses `decimal_price` (true two-sided, `payout_type="sportsbook"`); falls back to `dfs_pickem` (price None) if absent |
| PrizePicks | `prop_prizepicks.py` | public projections JSON | flat pick'em multiple -> `payout_type="dfs_pickem"`, prices None |
| FanDuel | `prop_fanduel.py` | public sportsbook props JSON | two-sided decimal where quoted |
| DraftKings | `prop_dk.py` (planned) | public sportsbook props JSON | two-sided decimal where quoted |

`prop_base.py` normalizes raw source stat labels to a canonical cross-book
vocabulary via `canon_stat()` (an unknown label passes through unchanged so
nothing is silently dropped). DFS pick'em products that quote a flat profit
multiple set both prices to `None` -- we never derive a two-sided price we cannot
honestly source.

### The ID-crosswalk landmine (must be coverage-verified)

Source identifiers do **not** line up across feeds and must never be naively
joined:

- **ESPN `event_id` != NBA-stats `game_id`** -- the ESPN scoreboard event id is
  ESPN-internal, not the `00223...` NBA game id used by `nba_api`.
- **MLB `game_pk` != book `event_id`** -- the StatsAPI primary key is not the
  prediction-market/book event id.
- **ESPN `event_id` != Kalshi / Polymarket ids** -- this is the documented
  landmine that previously gated out *every* live in-play tick. The in-play
  daemon therefore decides liveness **venue-natively** (from each venue's own
  commence/close stamps), NOT via an ESPN id cross-join (see
  `inplay_feed.py` / `inplay_snapshot_daemon.py`).

Any join across these spaces is done by team-name + commence-time resolution
(`team_resolver.py`, `market_join.py`) and its **coverage must be verified**, not
assumed; an unmatched row is omitted rather than force-joined.

---

## Intelligence Layer

Beyond the feature matrix, the system maintains an 80-artifact intelligence
layer folded into 690-node Obsidian notes (660 player + 30 team).

| Artifact | Scale | Source |
|---|---|---|
| 291K-pair matchup matrix | 291,625 rows | `data/cache/coverage_faced_allseasons.parquet` |
| Player atlases (28 types) | 660 players | `scripts/intel/` auto-writers |
| Team atlases (16 types) | 30 teams | Same |
| Monte Carlo possession simulation | 10K samples/game | `src/sim/basketball_sim.py` |

The signal catalog is in `vault/Intelligence/_Simulation_Signals.md` (local
only; not in the public repo).

---

## As-of Stamping and the Leak-Free Rebuild Guarantee

Every derived feature corpus (`asof_*` stems in each `ingest_manifest.py`) is
leak-free **by construction**, not by after-the-fact filtering. The single shared
primitive is `scripts/platformkit/asof_common.py`, which implements the
snapshot-before-update pattern:

1. Sort events into a stable chronological order (stable mergesort, multi-key).
2. For each event, **snapshot** every entity's prior-only state and record it.
3. Only **after** all snapshots in that event, **update** each entity's state
   with that event's realized observation.

State is keyed by the global entity id, so a player/pitcher seen as `p1` in one
game and `p2` in another accumulates one shared history. A debut entity snapshots
to `NaN`; a built-in assertion enforces "debut row => NaN" so no row can ever see
its own current event. This is what lets the manifests label `asof_*` corpora as
`pre_game` even though they summarize history.

The label columns (`home_win`, `target_home_win`, `target_over25`, `winner`) are
the **post-game** training labels, never pregame features -- the manifest records
this explicitly per source. Because the as-of state is reconstructed from the raw
post-game box, a full rebuild from scratch reproduces the exact pregame feature
each entity would have seen at that point in time (walk-forward, truncation-
invariant).

## Freshness, SLA, and Staleness Handling

Two freshness mechanisms run in parallel:

**1. Manifest SLA (per source).** Each `IngestSource` carries an `sla_minutes`
target -- how recently it should have been refreshed before tip/first-pitch.
`sla_minutes=None` means a derived/reference corpus with no clock (rebuilt on
demand). Representative SLAs:

| Source class | Example | SLA (min) |
|---|---|---|
| schedule / spine | `games`, `matches` | 1440 |
| moneyline odds | `odds` | 120 |
| starting pitchers | `pitchers` (mlb) | 240 |
| in-game linescores | `linescores` (nba) | 10 |
| as-of / reference | `asof_*`, `players`, `asof_park` | None |

**2. Runtime staleness guard** (`odds_provider/freshness.py`). A quote is FRESH
when its `captured_at` is within `max_age_sec` of now. Defaults are per-market
because lines move at different speeds:

| Market type | Max age before "stale" |
|---|---|
| moneyline | 900 s (15 min) -- moves fast near tip |
| spread | 900 s (15 min) |
| total | 1800 s (30 min) |
| prop | 3600 s (60 min) -- rarely moves intraday |

`is_fresh()` / `freshness_status()` are pure (time injectable) and **never raise**.
A `None` or unparseable timestamp degrades to `status="unknown"` and is treated
conservatively as NOT fresh -- the daemon never silently trusts stale-or-unknown
data. Capture daemons advance their `_freshness.json` sidecar only on a successful
poll, so a supervisor/UI can detect a dead feed.

## Capture Daemon Cadence (pregame close + in-play)

Two always-on, paper-only capture daemons record price history. Both isolate
per-sport failures (one sport erroring never sinks the loop) and write atomically
(tmp file + `os.replace`).

**Pregame line/close daemon** (`line_snapshot_daemon.py`) -- phase-aware cadence:

| State | Interval | Why |
|---|---|---|
| a game within `NEAR_TIP_MIN` (45 min) of tip | 60 s (FAST) | land a tick inside the lock window so the last at-lock tick IS the true close |
| no game near tip | 900 s (15 min, SLOW) | polite to feeds |

There is no separate "mark the close" step: capturing the close == polling fast
enough that a tick lands in the 30-minute lock window before tip. That tick's
`commence_time` stamp is what lets `line_store.get_close` certify a TRUE close
(`is_true_close=True`) vs a last-observed proxy.

**In-play (live) daemon** (`inplay_snapshot_daemon.py`) -- liveness-aware cadence
over Kalshi / Polymarket (ESPN optional), default sports `nba, mlb, soccer_intl`:

| State | Interval | Why |
|---|---|---|
| >= 1 game live (any sport) | 5 s (FAST) | live in-game prices move every few seconds |
| no game live | 120 s (IDLE) | just polling for a new live game |
| repeated all-sport errors | exponential backoff, capped 300 s | rate-limit-safe |

Liveness is decided **venue-natively** from each tick's own commence/close stamps
(never an ESPN id cross-join -- see the crosswalk landmine above), so a pregame
(future-commence) or settled market is never captured as in-play. The canonical
in-play tick is a flat YES-prob record:
`{sport, game_id, venue, market_type, side, ticker, prob[0,1], ts(UTC), phase:"in_play"}`.
An out-of-range prob is skipped, never fabricated.

---

## Current capture cadences (2026-07)

Snapshot of the live cadence numbers as actually measured, not aspirational.
Each pipeline is documented in full (source, output row shape, failure mode +
guard) in [`docs/INGEST_PIPELINES.md`](INGEST_PIPELINES.md); the census of
what is captured vs still missing per sport, plus the latency audit that
produced these numbers, lives in [`docs/DATA_DEPTH.md`](DATA_DEPTH.md).

- **MLB GUMBO live poller** (`ingame/gumbo_mlb_poller.py`) -- diffPatch
  bootstrap-then-diff protocol against `statsapi.mlb.com feed/live`, ~10 s
  while a game is live (5 s hard politeness floor), 30 s idle tick. Schedule
  date defaults to the MLB **baseball date** (UTC-10h roll), not the raw UTC
  calendar date -- the old UTC default went blind every evening around 7pm CT
  once UTC rolled past midnight while 12 games were still in progress.
- **Kalshi in-play quotes** -- Kalshi's own quote feed refreshes at a
  measured median **~7 s** poll; our in-play capture (`inplay_snapshot_daemon.py`)
  runs 5 s while any game is live, 120 s idle, so it is not the coarseness
  bottleneck (gumbo's own historical ~54 s cadence was; see DATA_DEPTH.md
  latency section for the audit and why the lead/lag verdict stays
  NOT_ESTABLISHED).
- **Kalshi depth ladders** (`data/cache/depth_history/<sport>/<date>.jsonl`)
  -- every 15th live in-play tick, measured ~20 minutes per ticker. Coarse by
  design: fine for pricing a simulated fill against a recent order book, not
  for a latency race.
- **Pregame line/close capture** (`line_snapshot_daemon.py`) -- phase-aware
  poll (fast inside 45 min of tip, slow otherwise) with a **30-minute lock
  window** before `commence_time`: only a quote captured inside that window
  is ever certified a true close (`is_true_close=True`); anything else reads
  back as an explicit proxy, never a fabricated close.
- **2025-26 NBA player-box backfill** -- ESPN full-game player boxes now
  close the 74-of-1,156-game gap left by stats.nba.com being blocked from
  this box, written into the existing `quarter_box` cache under the `q0`
  convention (`<game_id>_q0.json`, `period: 0`, `source: "espn_fullgame"` --
  real quarters stay `_q1..q4`, so quarter-level consumers never see it and
  full-game consumers aggregate it naturally). Zero transform changes to the
  existing pure `ingest_boxscores.py` reader.

---

## Cache Directory Layout

```
data/
├── nba/                                   # NBA API cache (TTL-managed)
│   ├── gamelogs_{season}.json             # 622 players
│   ├── player_avgs_{season}.json
│   ├── shots_{player_id}_{season}.json    # 221K shots
│   ├── pbp_{game_id}.json                 # 3,627 games
│   ├── hustle_stats_{season}.json
│   ├── on_off_{season}.json
│   ├── defender_zone_{season}.json
│   ├── matchups_{season}.json
│   ├── synergy_offensive_{season}.json
│   ├── synergy_defensive_{season}.json
│   ├── prop_correlations.json             # 508 players, 3,447 pairs
│   ├── injury_report.json                 # Live, 30-min TTL
│   ├── ref_assignments.json
│   └── schedule_{season}.json
│
├── external/                              # Non-NBA-API sources
│   ├── bbref_advanced_{season}.json
│   ├── contracts_2024-25.json
│   └── props_live.json                    # DK/FD props, 15-min TTL
│
├── cache/
│   ├── pregame_oof.parquet                # ~51K held-out player-games, walk-forward OOF
│   ├── coverage_faced_allseasons.parquet  # 291,625-pair matchup matrix
│   └── profiles/                          # per-player signal registry
│
├── models/                                # Trained model weights
│   ├── win_probability.pkl
│   ├── props_pts.json … props_tov.json
│   ├── quantile_pergame_metrics.json       # canonical MAE numbers
│   ├── prop_corr_matrix.json
│   ├── bet_log.json
│   └── clv_log.json
│
└── videos/
    ├── by_sha/                            # content-addressed store (<sha256>.mp4)
    ├── full_games/                        # symlinked named copies
    └── _inbox/                            # drop new clips here for auto-ingest
```

Only `data/seeds/` (SQL seed data) and small model metadata files are
version-controlled. All large data files are gitignored and must be regenerated
locally.

### Multi-sport platform feature store

The sport-blind platform writes per-sport parquet under `data/domains/<sport>/`,
one file per corpus stem named in that sport's `ingest_manifest.py`, plus the
captured price history:

```
data/domains/
  basketball_nba/   # games, odds, asof_features, asof_box_extra, asof_runvar,
                    # linescores, player_boxscores, espn_boxscores, postmortem
  mlb/              # games, games_current, odds, pitchers, asof_features,
                    # asof_park, player_gamelogs, espn_boxscores, postmortem
  soccer/           # matches, odds, match_stats, asof_features, asof_xg_proxy,
                    # espn_*, espn_club_priors, postmortem
  tennis/           # matches, wta_matches, odds, match_stats, asof_features,
                    # asof_hold, asof_return, players, postmortem

data/cache/
  line_history/<sport>/<YYYY-MM-DD>.jsonl     # pregame line+close ticks
  inplay_history/<sport>/<YYYY-MM-DD>.jsonl   # live in-play YES-prob ticks
                                              # + _freshness.json sidecar per sport
```

All of `data/domains/` and `data/cache/` is gitignored and local-only -- it is
never committed and never published (see
[data/README.md](../data/README.md) and the data-vault no-commit rule).

---

## Regenerating Data from Scratch

```bash
# 1. NBA API statistical data
python scripts/ingest_fetch.py --count 80

# 2. Feature matrix
python -m src.features.feature_engineering

# 3. Train prop models
python -m src.prediction.player_props --retrain

# 4. Train win-prob model
python -m src.prediction.win_probability --retrain

# 5. Run CV pipeline on a video (requires GPU recommended)
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

---

## Adding a New Data Source

1. Create `src/data/new_source.py` with the TTL-cache pattern:

```python
def get_data(season: str, force: bool = False) -> dict:
    cache_path = f"data/nba/new_source_{season}.json"
    if not force and cache_fresh(cache_path, ttl_hours=24):
        return json.load(open(cache_path))
    data = fetch_from_api(season)
    json.dump(data, open(cache_path, "w"))
    return data
```

2. Add feature extraction in `src/features/feature_engineering.py`.
3. Wire into `predict_props()` in `src/prediction/player_props.py`.
4. Add test in `tests/`.
5. Retrain: `python -m src.prediction.player_props --retrain`.

---

See also: [docs/BETTING.md](BETTING.md) · [docs/DEMO.md](DEMO.md) ·
[PREDICTIONS_QUICKSTART.md](../PREDICTIONS_QUICKSTART.md) ·
[DATA_OUTPUTS.md](DATA_OUTPUTS.md) · [data_schema.md](data_schema.md) ·
[operations/data-pipeline.md](operations/data-pipeline.md) ·
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) ·
[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) · [INDEX.md](INDEX.md)


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
