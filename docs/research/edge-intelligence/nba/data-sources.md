# NBA DATA SOURCES -- HAVE vs MISSING vs HOW-TO-GET

_Sport = NBA. The honest inventory of every data source the NBA edge pipeline needs, what is
on disk (path/rows/freshness), what is missing, and how to acquire it keyless. The single
binding gap is SAME-DAY FRESHNESS. Grounded in real parquet inspection + deep-dives 07/08/09/10/11.
ASCII only._

## HAVE (on disk, verified this session)

| Source | Path | Shape / coverage | Freshness | Notes |
|---|---|---|---|---|
| Player boxscores | `data/domains/basketball_nba/player_boxscores.parquet` | 27,816 rows x 26 cols | 2024-10-22 .. 2026-01-19; seasons 2024-25, 2025-26 | the honest prop-model corpus (`domains/.../player_props.py`); pts/reb/ast/stl/blk/tov/min/starter |
| Games (team-level) | `.../games.parquet` | 4,846 x 12; seasons 2022-23..2025-26 | 2022-10-18 .. 2026-04-12 | home_win, rest, b2b, travel -- win-prob feature base |
| Odds (closing-ish) | `.../odds.parquet` | 1,317 x 7 | 2025-10-21 .. 2026-05-24 | home_ml/away_ml/total/spread; ALL 1317 rows have total+spread -- the devig-the-close yardstick |
| Odds snapshots | `.../odds_snapshots/snapshots.jsonl` | jsonl | intraday | the line-MOVEMENT capture needed for CLV; thin |
| Linescores (per-quarter) | `.../linescores.parquet` | 1,313 x 12 | 2025-10-21 .. 2026-05-24 | home/away q1-q4 -- the in-game proof corpus (11 cites 1313 games) |
| ESPN boxscores (team, rich) | `.../espn_boxscores.parquet` | 1,977 x 73 | 2024-10-22 .. 2026-05-24 | keyless ESPN; team aggregates |
| As-of features (leak-free) | `.../asof_features.parquet` | 1,299 x 14 | per-game | ast_rate/pace/oreb/tov computed from PRIOR games only -- the leak-free team feature spine |
| As-of box extra / runvar | `.../asof_box_extra.parquet`, `asof_runvar.parquet` | 125KB / 41KB | per-game | additional as-of aggregates |
| Postmortem | `.../postmortem.parquet` | 128KB | per-game | realized-vs-pred grading store |
| Player season rates | `data/cache/team_system/player_rates.parquet` | 507 x 28 | full-season (in-sample) | the MC-sim parameter base (08:38) |
| Player ratings (2K-style) | `.../player_ratings.parquet` | 927 x 20 | season | 87 attr -> 13 cat -> OVERALL/INT_D/PERIM_D feed sim defense |
| Recency rates | `.../recency_rates.parquet` | **39 rows -- NYK/SAS ONLY** | HL~10 games | the deepest signal is a 2-team artifact (08:197) |
| PBP knowledge / assist net | `.../pbp_player_knowledge.parquet` (30), `assist_network.parquet` (428 pairs) | **NYK/SAS ONLY** | season | real unassisted share + feeder network; league-shallow |
| Team defense env | `.../team_defense.parquet` | **2 rows -- NYK/SAS** | season | tov_force/ft_force/oreb_strength |
| CV tracking features | `data/nba_ai.db` `cv_features` | 17,254 rows / 241 games / 252 pids | static | geometry asset; ~50% noise/missing (10); mostly REJECT as features |
| Atlases | `data/cache/atlas_*.parquet` | 28 player + 16 team = 44 | snapshot ~2026-06-02 | DEAD FUNNEL: unread by served model, point-lift ~0 (09) |
| Prop model artifacts | `data/models/*.json|joblib|lgb` | 7 stats x base+q50+conformal+calib | static | `props_pergame_metrics.json` is the honest scoreboard |
| In-play win-prob models | `data/models/inplay_winprob_endq{1,2,3}*.lgb` | endQ heads + variants | static | many stranded variants (11:319) |

## The ONE binding gap: SAME-DAY FRESHNESS
The historical box model is at its ceiling because it cannot see what changes on game day:
- **Projected minutes** per player for tonight's slate.
- **Confirmed starting lineup** (who actually starts, who is OUT).
- **Late scratch / load management / injury status** at slate-lock time.
- **Rotation/role changes** (a starter promoted, a usage bump from an injury elsewhere).

This is the decisive unmodeled lever (07 sec7, 08 ceiling, 09 ceiling all converge on it). The
MC sim already has the HOOK: `TeamModel.from_cache(out_ids=...)` drops same-day-unavailable
players so minutes/usage re-route (08:88) -- but nothing feeds `out_ids` from a live source.

## MISSING (needed for the beatable pockets)

| Missing source | Why it matters | Pocket it unlocks |
|---|---|---|
| **Keyless PLAYER-PROP line feed** | props are NOT wired to any prop feed; we price props but cannot compare to a book line at scale | P1 soft/DFS props (the PRIMARY pocket) -- TOP get-to-edge step |
| DFS projection lines (PrizePicks / Underdog) | the lazy lines we model against | P1 + DFS pick'em calibration |
| Same-day minutes / lineup / scratch feed | the freshness lever above | freshness on all props + team totals |
| Real SGP price capture | to validate joint ROI (none on disk, 08:206) | P5 correlated SGP |
| Live PBP / substitution feed (not just box snapshots) | in-game sees strictly less than a live book today | in-game props ceiling (11:399) |
| League-wide recency / PBP / team_defense | only NYK/SAS exist -> sim deepest signal is 2-team | sim coherence for all 30 teams |
| Prediction-market odds (Kalshi NBA) | two-crowd divergence vs sportsbook | P4 (cross-sport corpus has PM venues; NBA-specific TBD) |

## HOW-TO-GET (keyless first)
- **ESPN keyless scoreboard / boxscore / odds**: already used (`espn_boxscores.parquet`,
  `live_board` reads ESPN keyless period/clock/score, 11:54). Extend to scrape ESPN's
  player splits + projected starters where exposed. KEYLESS, free.
- **PrizePicks / Underdog projections**: public JSON endpoints; scrape on a schedule into a
  `prop_lines_<book>.parquet` keyed (date, player, stat, line). Build under `domains/basketball_nba/`
  or `scripts/platformkit/_scrapers/` (human-gated dirs -> propose, don't auto-edit src).
- **Same-day lineup/scratch**: ESPN/NBA injury report + projected-lineup pages; keyless scrape
  -> feed `out_ids` and a minutes-prior at slate lock.
- **League-wide recency/PBP/team_defense**: re-run `build_recency_rates.py` / `build_pbp_knowledge.py`
  / `build_team_defense.py` over the FULL game cache instead of `nyk_sas_games.json` (08 quick-win 1).
- **Kalshi NBA**: keyless public markets endpoint (the PM-trading stack already touches venues).

## Freshness discipline (binding)
Any freshness feature MUST be wired in BOTH the train and inference builders (train/inference
parity -- the most expensive bug class; new features silently read 0.0 at inference). Snapshot
the feed AT SLATE-LOCK with a timestamp < tip, and store per-date so backtests see real history
(the atlas leak-guard drops single-snapshot rows, 09:188 -- do not repeat that mistake). Validate
as a leak-free WF lift vs the close, not vs the prior model.
