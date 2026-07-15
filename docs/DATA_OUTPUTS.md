# Data Outputs

All data categories and fields produced by the NBA AI system.

---

## Game Metadata

- `game_id` — unique game identifier
- `season`, `season_type` — regular season / playoffs
- `game_date`, `home_team`, `away_team`
- `final_score`, `overtime_periods`
- `arena`, `attendance`
- `officials`

---

## Team Statistics

Per game, per half, per quarter:

- Points scored, field goals made/attempted, three-pointers, free throws
- Offensive / defensive rating
- Pace (possessions per 48 minutes)
- Assist rate, turnover rate, rebounding rates
- True shooting percentage
- Net rating, point differential

---

## Player Statistics

Per game and rolling averages (3-game, 7-game, season):

- Points, rebounds, assists, steals, blocks, turnovers, fouls
- Minutes played, usage rate
- Field goal %, three-point %, free throw %
- Plus/minus, on/off splits
- Box plus/minus (BPM), estimated impact metrics
- Distance covered (from tracking), average speed
- Time of possession

---

## Lineup Data

Per 5-man unit per game:

- Minutes together, possessions played
- Offensive rating, defensive rating, net rating
- Shot distribution and efficiency by zone
- Assist connections within lineup
- Spacing score (average convex hull area)

---

## Possession Data

Per possession:

- `possession_id`, `game_id`, `team_id`
- Start and end timestamps
- Possession type: half-court / transition / secondary break
- Play type: isolation, pick-and-roll, post-up, spot-up, cut, handoff
- Players involved (ball-handler, screener, shooter)
- Outcome: made field goal / missed field goal / free throws / turnover / foul
- Points scored on possession
- Duration (seconds)
- Shot taken: yes / no

---

## Shot Data

Per shot attempt:

- `shot_id`, `game_id`, `player_id`, `team_id`
- Court coordinates `(x, y)` — 2D mapped position
- Shot zone: restricted area, paint, mid-range, corner 3, above-break 3
- Shot type: catch-and-shoot, off-dribble, pull-up, floater, layup, dunk
- Nearest defender distance (feet)
- Time on shot clock
- Made / missed (from NBA API)
- Expected field goal % (xFG) — model output
- Shot quality score — model output

---

## Player Tracking Variables

Per frame (sampled at video frame rate):

- `frame`, `timestamp` (seconds from tip-off)
- `player_id`, `team_id`
- `x_position`, `y_position` — 2D court coordinates
- `speed` — pixels/frame (court units)
- `acceleration`
- `ball_possession` — boolean
- `event` — `dribble` / `pass` / `shot` / `none`
- `tracking_confidence` — 0.0–1.0

---

## Ball Tracking Variables

Per frame:

- `ball_x`, `ball_y` — 2D court coordinates
- `ball_speed`
- `ball_in_frame` — boolean
- `possession_player_id` — player holding ball
- `possession_team_id`
- `detection_method` — Hough / CSRT / optical flow

---

## Spatial Geometry Features

Per possession or per N-frame window:

- **Team spacing** — convex hull area of all 5 on-court players
- **Floor balance** — distribution of players across court thirds
- **Paint occupancy** — number of players in the lane
- **Corner occupancy** — players stationed in corner 3 zones
- **Defensive gap** — average distance between offensive and defensive players
- **Help defense proximity** — nearest help defender distance to ball-handler

---

## Passing Network Data

Per game or per stint:

- Pass sender ID → receiver ID
- Pass count between each player pair
- Average pass distance
- Assist chains (passer → assist → shot made)
- Ball movement rate (passes per possession)
- Skip pass frequency

---

## Screen and Pick-and-Roll Events

Per event:

- Screener player ID, ball-handler player ID
- Screen location (court coordinates)
- Coverage type: hedge / drop / switch / ICE
- Outcome: pull-up / drive / kick-out / turnover

---

## Defensive Rotation Events

Per event:

- Rotation trigger (drive, skip pass, cut)
- Rotating player ID, coverage assignment
- Rotation distance (feet) and time (frames)
- Outcome: contested / open / foul

---

## Transition Data

Per transition possession:

- Trigger: made basket / turnover / defensive rebound
- Lead defender ID, ball-handler ID
- Transition pace (frames from trigger to shot/stop)
- Numbers advantage: fast break / secondary / set

---

## Contextual Variables

Per game:

- Days rest (home and away team)
- Back-to-back flag
- Travel distance (miles) since last game
- Home / away / neutral court
- Season week, games played
- Opponent defensive rating (season-to-date)
- Win/loss streak

---

## Derived Analytics Features

Computed from the above for model input:

- Rolling offensive / defensive efficiency (3, 7, 14 game windows)
- Home/away splits
- Shooting efficiency by zone (rolling)
- Lineup net rating projections
- Fatigue index (minutes load, schedule density)
- Strength-of-schedule adjustment
- Clutch performance metrics (last 5 minutes, ≤5 point game)

---

## Multi-Sport Platform Outputs

The sport-blind platform (`domains/<sport>/` adapters +
`scripts/platformkit/odds_provider/`) produces, in addition to the NBA outputs
above, per-sport parquet corpora and captured market price-history. All outputs
are PAPER / measurement only and local-only (gitignored); no $-edge is claimed and
no price is ever fabricated.

### Per-sport feature-store parquet -- `data/domains/<sport>/`

One parquet per corpus stem named in `domains/<sport>/ingest_manifest.py`, tagged
with a `leak_class`:

- **Schedule / ratings spine** -- `games` / `matches` / `wta_matches` (carries the
  post-game label column: `home_win` / `target_home_win` / `target_over25` /
  `winner`).
- **Odds** -- keyless moneyline / O/U prices for devig + CLV join.
- **As-of features** (`asof_*`) -- leak-free by construction (snapshot-before-
  update): NBA box-extra + run-variance; MLB starting-pitcher form + park factor;
  soccer shots/SoT + xG-proxy; tennis serve hold% + return% per surface.
- **Post-game** -- player gamelogs / box scores (prop labels) + `postmortem`
  settlement artifact.

### Captured market price-history -- `data/cache/`

- **Pregame line history** -- `line_history/<sport>/<date>.jsonl`: per-tick decimal
  odds, Shin-devigged fair prob, `captured_at`, `commence_time`, book/side/market
  fields. The file never stamps a true-vs-proxy close flag; `line_store.
  get_close()` computes `is_true_close` downstream from timing relative to the
  lock window.
- **In-play tick history** -- `inplay_history/<sport>/<date>.jsonl`: flat YES-prob
  ticks `{sport, game_id, venue, market_type, side, ticker, prob, ts, phase}`
  captured every few seconds while a game is live; `_freshness.json` sidecar per
  sport.

### Normalized in-memory records (provider output)

- **`OddsEvent`** -- one team-market event: `{event_id, sport, home, away,
  commence_time, prices{venue:{home,away,[spread],[total]}}, source, as_of}`.
- **`PropLine`** -- one player prop: `{sport, event_id, match, player, team, stat,
  line, over_price, under_price, payout_type, source, as_of}`.

Full field tables: [data_schema.md](data_schema.md). Sources, SLAs, and the
ID-crosswalk landmine: [DATA.md](DATA.md).

See also: [DATA.md](DATA.md) - [data_schema.md](data_schema.md) -
[operations/data-pipeline.md](operations/data-pipeline.md) -
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) - [INDEX.md](INDEX.md)


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
