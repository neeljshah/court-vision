# DATASOURCE -- MLB Stats API (schedule + boxscore batting/pitching)

_Deep per-datasource spec. Part of the edge-intelligence corpus (_scrapers/deep/). The
free, official, KEYLESS MLB Stats API is the single host that feeds three things: (a)
the CURRENT team-game results that extend the frozen 2010-2021 SBR corpus (mainline ML,
EFFICIENT -- decision-support), (b) the per-player per-game batting + pitching boxscore
that is the MLB PROP corpus (P1 pocket), and (c) the MISSING probable-pitcher freshness
lever (A3) reachable from the SAME schedule endpoint. Markets are efficient; this adds
DATA DEPTH + freshness, not an asserted edge. ASCII only._

STATUS: WIRED (team results `ingest_current.py`; per-player `ingest_player_stats.py`).
KEY: KEYLESS. EDGE-UNLOCK: team ML = efficient (CUT 1); per-player boxscore = P1
substrate; probable pitcher = A3 freshness (highest-ROI MISSING extension). TIER: team =
CALIBRATION; props/freshness = HYPOTHESIS.

---

## Host + the four endpoints

Base: `https://statsapi.mlb.com/api/v1` -- no key, no auth. The endpoint 406s a
non-browser UA, so a browser `User-Agent` header is REQUIRED (`ingest_current.py:82`,
`ingest_player_stats.py:40`). On this box WebFetch 406s it; `ingest_current` shells out
to `curl` with the UA (`:102`), the player ingest uses urllib with the UA header.

1. SCHEDULE (season range, team results):
```
GET /schedule?sportId=1&startDate=YYYY-01-01&endDate=YYYY-12-31&gameType=R
```
2. SCHEDULE (single date, gamePk discovery):
```
GET /schedule?sportId=1&date=YYYY-MM-DD
```
3. SCHEDULE + PROBABLE PITCHER (the A3 freshness lever -- MISSING ingest):
```
GET /schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher
   -> dates[].games[].teams.{home,away}.probablePitcher.{id,fullName}
```
4. BOXSCORE (per-player batting + pitching):
```
GET /game/{gamePk}/boxscore
```

## Schedule payload schema (team results, `ingest_current.py`)

```
payload["dates"][]                 # one per calendar day
  day["date"]  ("YYYY-MM-DD")
  day["games"][]
    g["gamePk"]                    # stable game id (the boxscore key)
    g["status"]["detailedState"]   # "Final"/"Game Over"/"Completed Early" => settled
    g["status"]["abstractGameState"]  # "Final" => settled (used by player ingest)
    g["season"]
    g["teams"]["home"]["team"]["name"]   g["teams"]["away"]["team"]["name"]
    g["teams"]["home"]["score"]          g["teams"]["away"]["score"]
    g["teams"][side]["probablePitcher"]  # ONLY when &hydrate=probablePitcher
```
`_FINAL` filter sets enforce settled-only (`ingest_current.py:86`,
`ingest_player_stats.py:48`). FINAL games only = leak-free (no in-progress scores).

Team-result row schema (`ingest_current._parse_season`, `:109`) matches the frozen
`games.parquet` EXACTLY so the two concatenate: `event_id`
(`{date}-{home}-{away}-{seq}`), `date`, `season`, `home_team`, `away_team`, `home_runs`,
`away_runs`, `target_home_win`, `game_seq`, `home_league`. Full team name -> non-standard
SBR 3-letter code via `NAME_TO_CODE` (`:33`; CUB/SDG/SFO/KAN/TAM/WAS/CWS, OAK covers the
"Athletics" rebrand) so `walk_forward_elo` replays across both corpora.

## Boxscore payload schema (per-player, `ingest_player_stats.py`)

Confirmed 2026-06-18 against gamePk 823451 (PHI vs MIA):
```
payload["teams"]["home"|"away"]
  block["team"]["abbreviation"]  (or name)
  block["players"]               # dict keyed "ID{personId}"
    pl["person"]["id"]  pl["person"]["fullName"]
    pl["position"]["abbreviation"]   # pitchers "P"
    pl["battingOrder"]               # "100"=slot 1, "200"=slot 2,... or None
    pl["stats"]["batting"]           # batter stats (empty if did not bat)
    pl["stats"]["pitching"]          # pitcher stats (empty if did not pitch)
```

## Per-player fields emitted (the consumed schema)

`_player_row` (`ingest_player_stats.py:129`) writes one row per player with batting OR
pitching stats:

| group | columns | source key |
|---|---|---|
| id | `game_pk`, `date`, `team`, `player_id`, `player`, `position`, `is_pitcher`, `batting_order` | `_batting_order` (`:115`) maps "100"->1 |
| batting | `atBats, hits, totalBases, rbi, runs, homeRuns, doubles, triples, baseOnBalls, strikeOuts, stolenBases, hitByPitch` | `_BAT_FIELDS` (`:51`) |
| pitching | `outs, earnedRuns, battersFaced, pitch_strikeOuts, hits_allowed, baseOnBalls_allowed, inningsPitched` | `_PITCH_FIELDS` (`:57`) |

CRITICAL collision guard: a pitcher's strikeOuts/hits/baseOnBalls are RENAMED
(`pitch_strikeOuts` / `hits_allowed` / `baseOnBalls_allowed`) so they never clobber the
batting columns (`:57`, docstring `:19`). `inningsPitched` "6.2" -> 6.667 via
`_innings_to_float` (`:96`, thirds-correct). Every row carries the FULL stat-column set
(`_ALL_STAT_COLS`, `:68`) with None for the unused role -- no ragged schema.

## Output artifacts

- Team results: `data/domains/mlb/games_current.parquet` (10,826 rows, 2022-04-07 ..
  2026-06-16; concatenates with frozen `games.parquet` 27,983 rows 2010-2021).
- Per-player: `data/domains/mlb/player_gamelogs.parquet` (`_DEFAULT_OUT`, `:45`;
  dedup on `(game_pk, player_id)` keep last, `ingest_range` `:219`).
- Starting pitchers (frozen 2010-2021 only): `pitchers.parquet` from `ingest_pitchers.py`
  (a PURE TRANSFORM of cached SBR CSVs, zero network). GAP: current MLB (2022-26) runs
  PITCHER-BLIND (deep-dive 12 sec 5) -- extending pitcher identity to 2022-26 via the
  `hydrate=probablePitcher` schedule call (endpoint 3) is the highest-ROI MISSING ingest
  (A3 / data-acquisition.md plan item 6).

## Which engine consumes it

- Team results: `domains/mlb/ratings.py` / `walk_forward_elo` (the Elo predictor),
  `domains/mlb/predictor.py`. Mainline ML -- EFFICIENT, decision-support.
- Per-player gamelogs: `domains/mlb/player_rates_mlb.py` -- `MLB_CANON` maps canonical
  prop stats -> these columns with a per-role exposure unit (batters per-PA, pitchers
  per-BF / per-start; `player_rates_mlb.py:30,53,77`); produces leak-free shrunk rates.
  Then `domains/mlb/prop_engine_mlb.py` (`rate x exposure -> lambda -> NegBin/Poisson`,
  `:4`) prices the prop board; `negbinom_engine.py` / `negbinom_sim.py` realize the dist.
  NOTE: `player_rates_mlb` takes the gamelogs DataFrame as an ARG (caller reads the
  parquet), so the leak-free as-of cut is applied by the caller, not inside the rate fn.

## Refresh cadence

- Team results: idempotent, finals-only. `ingest_current.build_current` re-fetches the
  current season each run (cached year files for prior seasons). Loop/manual driven.
- Per-player: post-game per date (`ingest_player_stats.ingest_range(dates=[...])`).
  Run after a slate finals.
- Probable pitchers (when wired): MORNING-OF and re-poll until first pitch (announced
  rotations can change; a scratch flips the prior).

## Leak rules (as-of, binding)

1. Team + player rows are REALIZED post-game (`_FINAL` only) -> a player's own row for
   game G is NEVER a feature for G. To price game G use only rows with `date <
   firstPitch(G)`; the caller applies this cut before passing to `player_rates_mlb`.
2. Line scores / innings (`ingest_pitchers`) are OUTCOME data -> descriptive context
   only, NEVER a pregame feature (`ingest_pitchers.py:14-19`).
3. Probable-pitcher IDENTITY is published pre-game (announced rotations) so capturing
   the NAME/id is leak-free by nature; any pitcher FORM/RATING must be built downstream
   from the pitcher's PRIOR starts only -- never from the current game.
4. `batting_order` from the boxscore is the REALIZED order (post-game); the PROBABLE
   lineup (pre-game) is a separate, flip-prone signal -- stamp `confirmed_at`.

## Honest caveats / gaps

- Team ML is EFFICIENT (CUT 1): keep as calibration yardstick, not an edge hunt.
- The PROP board (P1) is the pocket, but the current pitcher-blind 2022-26 window caps
  pitcher-prop calibration; close it with endpoint 3 + a downstream pitcher-form builder.
- Underdog/PrizePicks already publish MLB props on their keyless endpoints under
  different sport ids -- wiring those (data-acquisition.md D2) gives a devig-able price to
  measure this corpus's prop calibration against, which is the unlock that makes the MLB
  prop edge claim TESTABLE rather than model-view only.
- Boxscore exposes far more than the whitelisted fields (RISP, pitch counts, spray);
  expanding `_BAT_FIELDS`/`_PITCH_FIELDS` is cheap if a prop market needs them.
