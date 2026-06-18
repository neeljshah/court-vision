# SOCCER-CLUB -- data sources (HAVE / MISSING / HOW-TO-GET)
_What data the club-soccer edge pipeline needs at each stage, what is on disk, what is missing,
and how to get the missing pieces keyless. The same-day freshness gap is called out. ASCII._

## HAVE (on disk, paths + rows + freshness)

### Team / scoreline substrate (DEEP -- this is the club asset)
- data/domains/soccer/matches.parquet -- 25,834 rows, 11 cols. Cols: event_id, date, season,
  div, home_team, away_team, fthg, ftag, total_goals, target_over25, ftr. Div in
  {E0,E1,SP1,I1,F1,D1} = EPL, EFL Championship, La Liga, Serie A, Ligue 1, Bundesliga.
  Seasons 2015..2025 (11). Date 2015-08-07..2026-05-24. over2.5 base rate 0.5154.
  Source: ingest_footballdata.py (football-data.co.uk CSVs, keyless).
- data/domains/soccer/match_stats.parquet -- 25,834 rows, 25 cols. Shots, SOT, corners, fouls,
  yellow/red, half-time, referee, sot_ratio. The team-stat depth for corners/cards/fouls
  team markets. Source: ingest_footballdata_matchstats.py.
- data/domains/soccer/odds.parquet -- 16,322 rows, 25 cols, 2019-08..2026-05. ou_open_over/under
  AND ou_close_over/under + Pinnacle (p_*), B365, Avg, Max, plus the closing variants (pc_*,
  avgc_*, b365c_*, maxc_*). THIS IS THE CLOSING LINE -> enables real CLV on totals. The single
  most valuable club asset for proof.
- data/domains/soccer/asof_features.parquet -- 25,834 rows, 19 cols: leak-free as-of rolling
  shots/SOT for/against (asof + L10). Feeds the ratings/lambda model.

### Player substrate (THIN today -- the gap to close)
- data/domains/soccer/espn_player_stats.parquet -- 1,241 rows, 23 cols, but ALL fifa.world (WC),
  date 2026-06-11..06-17, every player exactly 1 match. Schema (the template): totalShots,
  shotsOnTarget, foulsCommitted, foulsSuffered, yellowCards, redCards, goalAssists, offsides,
  totalGoals, saves, minutes, starter, position. NO club per-player rows yet.
- data/domains/soccer/espn_club_priors.parquet -- 8,741 rows, 6 cols, 960 players, as_of
  2026-06-17. Per (player, canonical stat): total, starts, per_start. 960 outfield x 9 stats +
  101 keepers x Saves. This is a club-SEASON aggregate (per_start denominator), used as a PRIOR
  in player_rates, NOT a per-match series -> carries documented mild lookahead + per_start->per90
  over-estimate bias (deep-dive sec 5).
- data/domains/soccer/espn_matchstats.parquet -- 185 rows, 66 cols, leagues eng.1/esp.1/ita.1/
  ger.1/fra.1, dates 20260411..20260504. TEAM-level club box (possession, passes, crosses,
  longballs, saves, SOT, corners). Proves the club ESPN summary endpoint works; per-player
  extraction from the SAME summary is the missing ingest.
- data/domains/soccer/prop_calibration.json -- MEASURED WC prop cache (n=6,620 pooled). The tier
  source. Club props are UNMEASURED until a club cache is built.

## MISSING (needed to make club props real)
1. PER-PLAYER CLUB BOX, MULTI-SEASON. The single biggest gap. We have the team box (185 rows)
   and the WC per-player schema (1,241 rows) but NO club per-player match history. Without it,
   club rates ride the club-season prior (per_start approximation) exactly like the WC stack
   rode it -- we never get the deep leak-free per-match per-player series that makes calibration
   real. This is THE unlock.
2. RICHER STAT FIELDS. CANON_TO_COLS (player_rates.py:35-46) maps only 10 stats. The ESPN club
   summary payload has 28 team fields (passes, crosses, longballs, tackles-adjacent) and the
   athlete box exposes more per-player than the 10 canonical -- tackles, passes, interceptions,
   key passes are UNINGESTED. These are higher-volume, more-stable per-player stats (better prop
   candidates than rare Goals/Cards).
3. CLOSING PROP LINES. prop_paper/prop_loop do NOT capture a closing-line snapshot (deep-dive
   sec 5 "No CLV capture" -- the single biggest proof gap). We have team-total closes
   (odds.parquet) but NO prop closes. Cannot graduate any prop calibration to CLV-proven.
4. PROJECTED LINEUPS / MINUTES SIGNAL. player_minutes projects E[min] from prior starts only;
   no injury/rotation/predicted-XI feed. The backtest is handed REALIZED minutes (props_eval
   feeds e_minutes=realized), so live-board minute error is UNMEASURED.
5. PER-PLAYER CLUB PRIORS AS A TRUE AS-OF SERIES. espn_club_priors is a single-snapshot
   aggregate -> mild lookahead. A point-in-time per-round series is needed for strict leak-free
   club calibration.

## HOW-TO-GET (keyless first)
- Per-player club box: REUSE ingest_espn_box.py's summary endpoint
  (site.api.espn.com/.../soccer/{league}/summary?event={id}) and extract the boxscore.players
  block exactly as ingest_espn_players.py does for WC. Same keyless API, same 5 leagues. Backfill
  prior seasons by walking scoreboard?dates=YYYYMMDD over each season. NO key required.
- Richer stats: extend CANON_TO_COLS + the ESPN field parse to add tackles/passes/interceptions/
  keyPasses where the summary exposes them (28-field payload confirmed in ingest_espn_box header).
- Closing prop lines: add a closing snapshot to prop_line_history (deep-dive quick-win #2) by
  re-scraping PrizePicks/Underdog near kickoff; store taken-vs-close so prop_paper can compute CLV.
- Lineups: predicted-XI scrape (e.g. team news pages) is keyless-ish but brittle; medium priority.

## THE SAME-DAY FRESHNESS GAP
Per the project north star, the one unmodeled lever everywhere is SAME-DAY freshness. For club
soccer specifically:
- Team markets: the model prices off as_of rolling features (asof_features.parquet) but the SHARP
  CLOSE already integrates same-day team news (injuries, suspensions, manager rotation, weather).
  We CANNOT see that -> we match, never beat, the close (cut-list CUT 1). Freshness is exactly
  the gap we cannot close, which is WHY team markets are CUT.
- Player props: the live-board edge depends on knowing the STARTING XI and minutes before the
  soft/DFS line fully adjusts. The freshness lever here is REAL and beatable -- a confirmed-XI
  scrape minutes before kickoff (vs a DFS line set off projected minutes) is the most actionable
  club-prop freshness signal, and the one place same-day data plausibly creates edge.
