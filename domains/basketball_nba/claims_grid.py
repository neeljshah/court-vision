"""NBA claims-factory GRID -- pure DATA config (spec sec 1, CLAIMS_FACTORY_SPEC_2026-07-06).

Zero logic, zero branching, zero I/O, ZERO import of the factory or any
scripts.platformkit module. This dict is read BY the factory; it never reads
anything itself. Every dim's source column is verified to exist on the real
on-disk parquet (test_claims_grid.py's drift guard); a phantom column here is
a review FAIL per the spec.

Two families, ONE shared source (data/domains/basketball_nba/player_boxscores.parquet,
27,816 rows, 627 distinct players / 30 distinct teams / seasons 2024-25 + 2025-26,
verified this session):
  - nba_player_box_rate: entity_key=player_id, per-player-per-game rate dims.
  - nba_team_box_rate:   entity_key=team, same source rolled up to team-game
    rows (team is already a column on player_boxscores -- no join needed).

Formula grammar is safe_formula's AGGREGATE dialect (sum/mean/count/
count_distinct(col) + arithmetic) exactly as scripts/platformkit/intel_
validation/safe_formula.py:103-169 defines it. `agg.num`/`agg.den` are two
whitelisted aggregate-grammar expression strings the factory divides
(criteria.formula = f"({num})/({den})"); this module never builds that
string itself, it only declares the two operands.

NO rest-day / B2B split: player_boxscores.parquet carries no rest/gap column
(only games.parquet does, at GAME grain, home/away-wide -- joining it in
would require logic in this module, forbidden by spec sec 1). Declaring a
rest dim without a real column would be exactly the "phantom column = review
FAIL" case the spec warns against, so it is left out rather than faked.

Floors reuse the shipping claim modules' precedent values (grounding reads):
  - season min_games=20            (nba_canonical_shooter_claims.py QUALIFY_MIN_GAMES)
  - career min_games=40            (2x the season floor, same convention)
  - home/away split min_games=15   (context_shooting_claims.py rest-split floor
                                     family; team-level clears this at 40+/side)
  - team-window min_games=20 (season) / 15 (split) -- team plays every game its
    roster does, so team-grain uses the SAME thresholds as player-grain.

FIX-ROUND NOTE (blocking findings from the first review, both fixed by
REMOVAL not by adding a floor):
  (1) The precedent modules this file's floors are modeled on never gate a
      shooting-PERCENTAGE dim on games alone -- they ALWAYS pair the games
      floor with a VOLUME floor: nba_canonical_shooter_claims.py's
      QUALIFY_MIN_FGA=200 always applies alongside QUALIFY_MIN_GAMES=20
      (quality_indices.py:48-49), and context_shooting_claims.py:30-36 uses
      ">=30 3PA EACH side" / "fg3a>=100". PROVEN on the real 2024-25 parquet
      that a games-only floor breaks this: under game_id>=20 alone, the
      fg3_pct leaderboard is topped by Drew Eubanks (.500 on 6 3PA) and Taj
      Gibson (.500 on 2 3PA), OUTRANKING Seth Curry (182 3PA); 101/456 kept
      players have <50 total 3PA, 127/456 have <200 FGA.
  (2) That volume floor is NOT expressible with the current factory: every
      floor column in claims_grid.py's `floors` dict is recomputed by the
      factory as `count_distinct({col})` ONLY (claims_factory.py:133,
      `_build_dim_claim`'s `floor_cols` comprehension) -- there is no
      sum-based floor path. `count_distinct(fg3a)` does not count total 3PA;
      it counts DISTINCT per-game-attempt values seen (e.g. Eubanks's own
      game log has fg3a in {0.0, 1.0}, so count_distinct(fg3a)=2 -- a floor
      on that number floors nothing real). Adding a sum-based volume-floor
      path is an L-A (claims_factory.py) change and is explicitly OUT OF
      SCOPE for this grid-only fix round (and would need its own review
      before the sanctioned generation run).
  RESOLUTION: the 5 player-grain shooting-PERCENTAGE dims that need a volume
  floor to be defensible (fg_pct, fg3_pct, ft_pct, ts_pct, efg_pct) are
  REMOVED from _PLAYER_DIMS rather than shipped under a floor that cannot
  actually gate low-volume outliers. fg3a_rate (a shot-selection RATE, not a
  make/attempt percentage -- same "junk on low n" risk) is removed for the
  identical reason. Team-grain dims (_TEAM_DIMS) are UNCHANGED: verified on
  the real parquet that team-grain FG3A has a season-floor minimum of 2,606
  attempts (30 teams, 2024-25) -- team rollups cannot produce a low-volume
  leaderboard the way one thin player can, so the review's finding does not
  apply there and nothing there needed a fix.

  HONEST RE-MEASUREMENT after removal (real 2024-25/2025-26 data, replaying
  the exact factory floor+groupby logic): post-floor player-family claims =
  34,650 (14 dims x up to 627 entities x 9 window-slots, floor-gated);
  post-floor team-family = 1,440; TOTAL post-floor = 36,090 against a
  cartesian ceiling of 69,276 (ratio 0.52). Removing the ungated dims lowers
  the ABSOLUTE count (was 50,940 pre-fix) but does NOT change the floor's
  throttle RATIO -- a games-only floor keeps ~80% of 2024-25 players (456/569
  clear game_id>=20) regardless of how many dims are declared, since dim
  count is a pure multiplier on both the kept and excluded sides. Bringing
  the ratio itself toward "an order of magnitude below ceiling" needs a
  stricter/volume-aware floor, which is the SAME out-of-scope L-A factory
  change as above -- reported here honestly rather than silently claimed.

CLI: none -- this module is imported, never run directly.
"""
from __future__ import annotations

_PLAYER_BOX = "data/domains/basketball_nba/player_boxscores.parquet"

_PLAYER_DIMS = [
    # scoring / volume
    {"metric": "pts_per_game", "agg": {"num": "sum(pts)", "den": "count(game_id)"}},
    {"metric": "min_per_game", "agg": {"num": "sum(min)", "den": "count(game_id)"}},
    {"metric": "fga_per_game", "agg": {"num": "sum(fga)", "den": "count(game_id)"}},
    {"metric": "fta_per_game", "agg": {"num": "sum(fta)", "den": "count(game_id)"}},
    # NOTE: shooting-PERCENTAGE dims (fg_pct/fg3_pct/ft_pct/ts_pct/efg_pct)
    # and fg3a_rate are REMOVED this fix round -- see FIX-ROUND NOTE above.
    # They need a sum-based volume floor (min_fga/min_fg3a) the factory
    # cannot express yet (count_distinct-only floors); shipping them under
    # a games-only floor produces low-volume junk leaderboards, proven above.
    # playmaking / defense rate stats
    {"metric": "ast_per_game", "agg": {"num": "sum(ast)", "den": "count(game_id)"}},
    {"metric": "ast_to_tov", "agg": {"num": "sum(ast)", "den": "sum(tov)"}},
    {"metric": "reb_per_game", "agg": {"num": "sum(reb)", "den": "count(game_id)"}},
    {"metric": "oreb_per_game", "agg": {"num": "sum(oreb)", "den": "count(game_id)"}},
    {"metric": "dreb_per_game", "agg": {"num": "sum(dreb)", "den": "count(game_id)"}},
    {"metric": "stl_per_game", "agg": {"num": "sum(stl)", "den": "count(game_id)"}},
    {"metric": "blk_per_game", "agg": {"num": "sum(blk)", "den": "count(game_id)"}},
    {"metric": "tov_per_game", "agg": {"num": "sum(tov)", "den": "count(game_id)"}},
    {"metric": "pf_per_game", "agg": {"num": "sum(pf)", "den": "count(game_id)"}},
    {"metric": "plus_minus_per_game", "agg": {"num": "sum(plus_minus)", "den": "count(game_id)"}},
]

_TEAM_DIMS = [
    # team-rolled-up rate stats -- same columns, entity_key=team instead of player_id
    {"metric": "team_pts_per_game", "agg": {"num": "sum(pts)", "den": "count_distinct(game_id)"}},
    {"metric": "team_fg_pct", "agg": {"num": "sum(fgm)", "den": "sum(fga)"}},
    {"metric": "team_fg3_pct", "agg": {"num": "sum(fg3m)", "den": "sum(fg3a)"}},
    {"metric": "team_ft_pct", "agg": {"num": "sum(ftm)", "den": "sum(fta)"}},
    {"metric": "team_ts_pct", "agg": {"num": "sum(pts)", "den": "2*(sum(fga)+0.44*sum(fta))"}},
    {"metric": "team_ast_per_game", "agg": {"num": "sum(ast)", "den": "count_distinct(game_id)"}},
    {"metric": "team_tov_per_game", "agg": {"num": "sum(tov)", "den": "count_distinct(game_id)"}},
    {"metric": "team_reb_per_game", "agg": {"num": "sum(reb)", "den": "count_distinct(game_id)"}},
]

_SEASON_WINDOWS = [
    {"name": "season_2024_25", "filter": {"season": "2024-25"}},
    {"name": "season_2025_26", "filter": {"season": "2025-26"}},
    {"name": "career_to_date", "filter": {}},
]

_HOME_AWAY_SPLITS = [
    {"name": "home", "col": "is_home", "eq": 1},
    {"name": "away", "col": "is_home", "eq": 0},
]

GRID: dict = {
    "sport": "basketball_nba",
    "families": [
        {
            "family": "nba_player_box_rate",
            "source": _PLAYER_BOX,
            "grain": "per_game",
            "entity_key": "player_id",
            "entity_name_col": "player_name",
            "dims": _PLAYER_DIMS,
            "windows": _SEASON_WINDOWS,
            "context_splits": _HOME_AWAY_SPLITS,
            "floors": {
                "season": {"game_id": 20},
                "career": {"game_id": 40},
                "split": {"game_id": 15},
            },
        },
        {
            "family": "nba_team_box_rate",
            "source": _PLAYER_BOX,
            "grain": "per_game",
            "entity_key": "team",
            "entity_name_col": "team",
            "dims": _TEAM_DIMS,
            "windows": _SEASON_WINDOWS,
            "context_splits": _HOME_AWAY_SPLITS,
            "floors": {
                "season": {"game_id": 20},
                "career": {"game_id": 40},
                "split": {"game_id": 15},
            },
        },
    ],
}
