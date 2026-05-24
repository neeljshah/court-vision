# Per-Game Player Tracking Research — cycle 78b (loop 5)

**Date:** 2026-05-24
**Probe script:** `scripts/probe_player_tracking_pergame.py`
**Raw output:** `scripts/_results/probe_player_tracking_pergame.txt`
**Status:** RESEARCH ONLY — no production code modified.

## Question

Cycle 14 rejected prior-season tracking aggregates (5/7 stats regressed).
The thesis: season aggregates are stale and don't reflect tonight's role.
This cycle asks the orthogonal question — **does TRUE per-game tracking
data (game-by-game touches, distance, contested shots) provide a signal
that the existing per-game form features don't already capture?**

## Endpoints inventoried

| Endpoint | Per-game? | Per-season? | Currently used? |
|---|---|---|---|
| `leaguedashptstats` | NO | YES (season+measure type) | YES — `data/player_tracking.parquet` (DORMANT, prior-season-keyed) |
| `leaguehustlestatsplayer` | NO | YES — `games_played` averaged over a season | NO (cached at `hustle_stats_<season>.json`) |
| `leaguedashptdefend` | NO | YES (per-season-per-defender FG% allowed) | NO |
| `boxscoreplayertrackv2` | YES (per game) | n/a | NO (cycle 14 dormant); **v2 returns empty payload from stats.nba.com** — same failure mode as boxscoreadvancedv2 |
| **`boxscoreplayertrackv3`** | **YES (per game)** | n/a | **NO — works, schema confirmed below** |
| `boxscoreadvancedv3` | YES (per game) | n/a | YES — fetched into `boxscore_adv_*.json` (3685 games cached) and aggregated into `data/player_adv_stats.parquet`. **BUT `_ADV_FEATURE_COLS` is currently DISABLED** in `prop_pergame.py:191` |

Existing dormant wrappers in `src/data/nba_tracking_stats.py` use the
broken v2 endpoint — that file needs a v3 migration before it can be the
source.

## Schema sample (v3, real data, 3 stars × 2-3 games each)

Columns returned (35 total): `gameId, teamId, personId, minutes, speed,
distance, reboundChancesOffensive/Defensive/Total, touches,
secondaryAssists, freeThrowAssists, passes, assists,
contestedFieldGoalsMade/Attempted/Percentage,
uncontestedFieldGoalsMade/Attempted/Percentage, fieldGoalPercentage,
defendedAtRimFieldGoalsMade/Attempted/Percentage`.

Sample LeBron rows (game_id, min, speed, dist, touches, passes, ast, contFGA, rebChances):

```
0022400085   34:42  3.84  2.40   70   49   8   4    8
0022400137   36:15  3.68  2.43   79   56  10   4    9
0022400225   36:56  3.87  2.57  103   71  14   4   17
```

Sample Jokic rows:

```
0022400033   39:28  3.70  2.61  117   86  10  20   32
0022400113   40:31  3.82  2.80  100   74  16  10   23
0022400177   39:29  3.85  2.80  132   97  16  15   30
```

## Game-to-game variance (coefficient of variation, n=2-3 per star)

|  Stat | LeBron CoV | Jokic CoV | Curry CoV |
|---|---|---|---|
| speed | 0.027 | 0.021 | 0.008 |
| distance | 0.037 | 0.040 | 0.127 |
| touches | **0.203** | **0.138** | 0.085 |
| passes | **0.192** | **0.134** | 0.055 |
| contestedFGA | 0.000 | **0.333** | **0.157** |
| reboundChancesTotal | **0.435** | **0.167** | **0.530** |

**Reading:** speed and average distance are essentially traits (CoV
2-4%) — these are leaked into the model's `usg_pct`/`pace` columns
already and add little. **Touches, passes, contestedFGA, and
reboundChances vary 13-50% game-to-game** — that's *real* per-game signal
above the speed/distance baseline. Critically, "touches" and "passes"
are direct precursors of AST and pass-heavy stats not currently captured
by per-game form alone.

## Why this differs from cycle 14

Cycle 14 used PRIOR-SEASON aggregates (one row per player per season).
Those are stale role-snapshots, dominated by team context that has since
changed (trades, new coach, new lineup). Per-game v3 data updates after
*every* game — the L5 trend of "touches per minute" reflects tonight's
role within the past two weeks. That's the same recency principle that
beat 4-season fits in cycle 19 (data recency > data volume).

## Quick-win path already on the shelf

`boxscoreadvancedv3` per-game is ALREADY fetched (3685 games cached) and
ALREADY aggregated into `player_adv_stats.parquet` with USG/TS/AST_PCT/
REB_PCT/PIE columns. The `_ADV_FEATURE_COLS` block in
`prop_pergame.py:191` is **commented out** with the docstring note
"covariate shift + regression" from cycle 6 (which used L5/L10/EWMA over
those advanced stats). The right next experiment is probably **per-game
v3 player-track features + USG/TS/PIE as RAW prev-game values (not
rolling averages)** to avoid the covariate-shift problem cycle 6 hit.

## Recommendation

**INVESTIGATE-FURTHER.** Not ready to ship without a real cycle, but
the signal is clearly there. Concretely:

1. Pull `boxscoreplayertrackv3` for the 2-season corpus (~2500 games × 0.6s
   sleep ≈ 25 min, perpetual cache, runs in background once).
2. Aggregate to a `player_pergame_tracking.parquet` keyed by
   `(player_id, game_id, game_date)` with raw per-game `touches`,
   `passes`, `distance`, `contestedFGA`, `reboundChances`, plus
   `per_minute` normalizations.
3. Compute strictly-shifted L5 mean **and** prev-game value (per cycle-6
   lesson, raw prev-value avoided the rolling-average covariate shift).
4. Single-split + walk-forward on the same dual-gate as cycles 17-23.
   Primary candidates for lift: **AST, TOV, REB** (where `passes` and
   `reboundChances` are mechanically upstream of the target).

Pre-condition before wiring: when `_ADV_FEATURE_COLS` is re-enabled,
test it standalone first — it's a half-implemented predecessor and
probably the right baseline before adding v3 columns on top.

## Suggested cycle title

`cycle 79 (loop 5): per-game v3 player-tracking — touches/passes/contestedFGA as prev + L5`

## Risks / known traps

- nba_api timeouts: v3 endpoint hit ~5% transient `RemoteDisconnected`
  in the probe — needs the 3-retry pattern from `fetch_one`.
- Minute filter: rows include DNPs with `minutes='0:00'` and `comment` set
  ("DNP - Coach's Decision"). Filter these before aggregation or they
  poison rolling means.
- Pre-2014 games may not have tracking data; restrict fetch to 2014-15
  onward.
- Cycle 6's covariate-shift warning applies: prefer raw prev-game values
  over multi-game rolling means as the first wire-in.
