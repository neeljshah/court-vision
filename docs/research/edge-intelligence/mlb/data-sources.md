# MLB DATA SOURCES -- have / missing / how to get (keyless first)
_Part of the edge-intelligence corpus. Every source the MLB pipeline needs, with real paths/shapes/
freshness from the repo. The binding gap is SAME-DAY freshness, not history. ASCII only._

## HAVE (on disk, verified 2026-06-18)

| Source / parquet | Path | Shape / span | Freshness | Role |
|---|---|---|---|---|
| Player gamelogs | `data/domains/mlb/player_gamelogs.parquet` | **6,558 x 27**, 2026-06-01..06-17 (17 days), 220 games, 920 players, median **6** games/player, 1,874 pitcher rows | thin slice; rebuilt 2026-06-18 | **THE prop substrate** -- batting+pitching box rows. 27 cols incl atBats/hits/totalBases/rbi/runs/homeRuns/baseOnBalls/strikeOuts/outs/earnedRuns/battersFaced/pitch_strikeOuts/hits_allowed/inningsPitched. |
| Frozen team games | `data/domains/mlb/games.parquet` | 27,983 x 10, 2010-2021 | frozen | Team-game corpus for ratings; prop engine does NOT use it. |
| Current team games | `data/domains/mlb/games_current.parquet` | 10,826 x 10, 2022-04..2026-06-16 | as-of 06-16 | Extends frozen for live ratings (`refresh_ratings.refreshed_predictor`). |
| SP linescores | `data/domains/mlb/pitchers.parquet` | 27,983 x 11, 2010-2021 | frozen | Per-game SP line-score strings -> `asof_sp_form` first-6-IP feature. |
| Park feature | `data/domains/mlb/asof_park.parquet` | ~783KB | built | Leak-free park factor (`asof_park.py`); available for the prop rate, NOT yet wired into props. |
| As-of features | `data/domains/mlb/asof_features.parquet` | ~738KB | built | Team-level leak-free features. |
| ESPN boxscores | `data/domains/mlb/espn_boxscores.parquet` | ~96KB | built | Cross-feed (`ingest_espn_box`) -- settlement / alt box source. |
| Odds | `data/domains/mlb/odds.parquet` | ~599KB | frozen-ish | Historical team odds (SBR) -> beat-the-close devig. |
| Prop calibration cache | `data/domains/mlb/prop_calibration.json` | **n=0, all null** | 2026-06-18 | EMPTY -- no scored prop predictions yet. |

## MISSING (the gap to the ceiling)
1. **A full-season+ player gamelog corpus.** 17 days -> need >=1-2 seasons. Without it the walk-forward
   skips nearly every player-game for lack of a strict prior, so `prop_calibration.json` stays n=0. This
   is THE unlock for any prop edge claim.
2. **Season-level per-player rates / splits** (season per-PA/per-BF, vs-L/vs-R platoon, home/road). Today
   the rate pools ALL prior rows into one league baseline (`_league_per_exposure`, coarse). MLB's full
   season makes a season-prior genuinely informative (unlike NBA recency>volume).
3. **Confirmed daily lineups + batting order + scratches** (same-day). The book sees these; the model
   does not, faster. This is the unmodeled freshness gap that caps the ceiling.
4. **Probable / confirmed starting pitcher per game** (same-day) for the live slate -- needed to deliver
   the SP lever live, not just measure it historically.
5. **Live odds / closing lines for props.** `prop_line_history.jsonl` has **1 line** (per area-06):
   closing-line capture is essentially unstarted -> prop CLV currently undefined.
6. **Weather / park-day conditions** (wind, temp) -- large run-environment effect, not ingested.
7. **Bullpen availability / usage** -- affects late-inning run rate; absent.

## HOW TO GET (keyless where possible)
- **Gamelog backfill (PRIORITY):** `domains/mlb/ingest_player_stats.ingest_range(start, end)`
  (`ingest_player_stats.py:219`) walks `statsapi.mlb.com/api/v1/schedule?sportId=1&date=...`
  (`:42`) -> `/game/{pk}/boxscore` (`:43`). **No API key**, browser UA already set. Backfill
  2024-2025 (or 2022-2025) into `player_gamelogs.parquet`. This is a pure data-acquisition run, no
  modeling change. Watch the scale-guard gap (backfill path differs from the pipeline guards) and the
  INSERT-OR-REPLACE gap (only touched rows overwrite) -- verify row counts after.
- **Season stats / splits:** statsapi `people/{id}/stats?stats=season,statSplits` (keyless) -> a
  season-prior parquet to shrink toward (the highest-ceiling structural rate improvement).
- **Daily lineups / probable SP:** statsapi `schedule?hydrate=probablePitcher,lineups` (keyless) for the
  live slate. Feeds exposure (batting order -> `_LINEUP_PA`) and the live SP lever.
- **Prop lines:** the keyless odds layer (ESPN / soft books) the corpus targets; log to
  `prop_line_history.jsonl` via `prop_line_history.log_board_lines` up to first pitch for true CLV.
- **Weather/park:** park identity already in `asof_park.py`; day weather needs a keyless weather feed
  (e.g. open-meteo) joined on park lat/lon + game time.
- **Kalshi MLB:** keyless public market data for prediction-market-vs-book divergence (P4).

## The same-day-freshness gap (binding)
Per the deep-dive ceiling: MLB history is at-ceiling once a season is loaded; the unpriced gap is
**same-day information** -- confirmed lineup, late scratch, pitcher change, weather, bullpen state --
that the book integrates faster than we can. History backfill makes us CALIBRATED (the real win);
freshness is what would make us competitive on timing, and we currently cannot see it faster than the
book. So: backfill -> calibration (achievable); freshness -> timing edge (hard, execution-bound).
