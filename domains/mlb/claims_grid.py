"""MLB claims-factory GRID -- pure DATA config (spec sec 1, CLAIMS_FACTORY_SPEC_2026-07-06).

Zero logic, zero branching, zero I/O, ZERO import of the factory or any
scripts.platformkit module. This dict is read BY the factory; it never reads
anything itself. Every dim's source column is verified to exist on the real
on-disk parquet (test_claims_grid.py's drift guard); a phantom column here is
a review FAIL per the spec.

ONE shared source (data/domains/mlb/player_gamelogs.parquet, 321,012 rows,
2,531 distinct player_id / 33 distinct team, dates 2022-04-07..2026-07-02 --
CURRENT ERA ONLY, verified this session):
  - mlb_batter_rate:  entity_key=player_id, is_pitcher==False rows only.
  - mlb_pitcher_rate: entity_key=player_id, is_pitcher==True rows only.
  - mlb_team_rate:    entity_key=team, all rows (batters+pitchers on that
    team's roster), rolled up to team-game grain -- team is already a column
    on player_gamelogs (no join needed), identical pattern to the NBA
    team_box_rate family reusing the player-grain source.

ERA COVERAGE CAVEAT (mandatory per task brief -- read BEFORE trusting any
count here): the richest MLB corpora on this disk are actually TWO DISJOINT
eras with DIFFERENT schemas, not one file splittable by a filter:
  - 2010-2021 (frozen archive): games.parquet / pitchers.parquet, WIDE
    game-grain (one row per game, home_team+away_team as separate columns,
    home_innings/away_innings packed as a CSV-string of per-inning outs).
    Verified on disk: 27,983 games, season range 2010-2021 (2020 partial,
    897 games). NOT player-grain -- no per-player-per-game row exists in
    this era's files, so no batter/pitcher rate family can be built from it
    without a join + CSV-parse (both = logic, forbidden in this module).
  - 2022-2026 (current era): player_gamelogs.parquet, the ONLY genuinely
    long-format per-player-per-game table on disk, used below. Verified:
    321,012 rows, 1,114 distinct batters / 1,621 distinct pitchers / 33 teams.
This grid therefore covers the CURRENT ERA ONLY. A 2010-2021 batter/pitcher
rate family is NOT buildable from what exists on disk today; building one
would need a new leak-free per-player extractor from the archive box source,
out of scope for a grid-only (pure-data) change.

NO season/year WINDOW: player_gamelogs.parquet carries `date` (datetime64)
but NO `season`/`year` equality-matchable column (unlike NBA's
player_boxscores.parquet, which has a literal `season` string column). The
factory's window filter (_slice_rows, claims_factory.py:96-107) is
STRICT-EQUALITY only (`out[col] == val`) -- no range/`>=` support -- so a
year-window needs a real per-row column that already equals the target year,
which does not exist here. games.parquet DOES carry `season` but is the
disjoint wide 2010-2021 archive (see above), and joining its season column
onto player_gamelogs by date/team would be logic, forbidden by spec sec 1.
RESULT (same discipline as the NBA rest-day removal): only ONE honest window
is declared, `career_to_date` (empty filter = the whole corpus). Declaring a
fake "season_2024" filter with no matching column would be exactly the
"phantom column = review FAIL" case the spec warns against.

NO context_splits: player_gamelogs.parquet has no home/away/venue boolean
column (checked: only home-run-count column contains the substring "home").
`is_pitcher` is consumed as the batter/pitcher family SPLIT-BY-FAMILY filter
(folded into each family's window filter dict below, not a context_splits
entry -- context_splits crosses an EXTRA axis into windows per spec sec 1,
whereas is_pitcher partitions which FAMILY a row belongs to at all). No other
boolean/2-valued column exists to declare a real split; omitted rather than
faked, same as NBA's rest-day-split omission.

NO percentage/ratio-of-sum dims (avg, era, whip, k_per_9, bb_per_9, obp,
slg): same trap PROVEN on the real 2022-2026 data that broke NBA's fg3_pct --
under a games-only floor (>=20 games), batting-average leaderboard is topped
by a player with 6 total at-bats across 25 mostly-bench games (.333 avg),
ahead of qualified regulars with 2,600+ AB. The factory's floor mechanism is
count_distinct(col)-ONLY (claims_factory.py:132, `_build_dim_claim`'s
`floor_cols` comprehension) -- there is no sum-based (min-AB/min-IP/
min-batters-faced) floor path, the identical gap NBA's fix-round documented.
RESOLUTION: only per-game COUNTING-rate dims are declared (hits_per_game,
hr_per_game, etc.) -- these are bounded by the games floor itself (a player
cannot inflate hits_per_game via one small-sample game the way a ratio dim
can), so no volume-floor gap exists for them. Ratio dims are OUT OF SCOPE
until a sum-based floor path lands in claims_factory.py (an L-A change,
same as NBA's note).

Formula grammar is safe_formula's AGGREGATE dialect (sum/mean/count/
count_distinct(col) + arithmetic) exactly as scripts/platformkit/intel_
validation/safe_formula.py:105-171 defines it. `agg.num`/`agg.den` are two
whitelisted aggregate-grammar expression strings the factory divides
(criteria.formula = f"({num})/({den})"); this module never builds that
string itself, it only declares the two operands.

Floors reuse shipping MLB precedent values (grounding reads):
  - season min_games=20   (mirrors NBA's QUALIFY_MIN_GAMES convention; this
                            grid has only one window type so "season" is the
                            floor key the factory looks up for career_to_date
                            -- see _window_type: only names starting with
                            "career" map to the "career" bucket, so
                            "career_to_date" here actually resolves to
                            "career" floor type; both are declared identical
                            below to avoid a fail-closed gap either way)
  - career min_games=40    (2x season floor, same convention as NBA; used as
                            the actual applied floor since this grid's sole
                            window is named career_to_date)
  - team-window min_games=20/40 -- reused from atlas_playstyles.py's
    _MIN_GAMES=100 would exclude too few of 33 real teams to matter; the
    smaller NBA-precedent value is kept since every team here already clears
    both games floors by a wide margin (verified: 31/33 teams clear 40
    games), so raising it further would gate nothing real.
  - no 'split' floor key: no context_splits declared (see above), so the
    'split' floor is intentionally absent -- test_every_window_type_has_a_
    required_floor only requires 'split' WHEN context_splits is non-empty.

RANK-7 CENSUS FAMILY ADDED (claims-scale lane): mlb_bullpen_fatigue_chains,
entity_key=player_id, source=data/domains/mlb/bullpen_relief_chains.parquet
-- a DERIVED parquet (domains/mlb/ingest_bullpen_relief_chains.py), not
player_gamelogs.parquet directly, because the starter/reliever split and the
rest-day/rolling-appearance cadence features are temporal/row-level
computations the pure-data grid format cannot express (see that module's
own docstring). This family carries its OWN `year` window (2022-2026) even
though the "NO season/year WINDOW" note above still applies to the OTHER two
families' raw source -- the derived parquet legitimately has a year column,
computed once in the prep step, not faked here. DISTINCT from the CLOSED
SP-velocity class (see ingest_bullpen_relief_chains.py docstring) -- this is
appearance CADENCE (rest days, back-to-back rate), never a within-outing
pitch-count/velocity metric.

HONEST RE-MEASUREMENT (real on-disk data via the prep script's build(),
replaying the exact factory floor+groupby logic, this session): 71,523
relief-appearance rows / 1,565 distinct relievers. career_to_date: 752/1,565
clear >=15 appearances. 5 year windows (2022-2026): 1,513 (player,year)
cells clear >=15 (of 3,662). 4 dims x these window-slots -> ~9,060 post-floor
exploded claims (3,008 career + 6,052 year-split).

CLI: none -- this module is imported, never run directly.
"""
from __future__ import annotations

_GAMELOGS = "data/domains/mlb/player_gamelogs.parquet"
_BULLPEN_CHAINS = "data/domains/mlb/bullpen_relief_chains.parquet"

_BULLPEN_DIMS = [
    {"metric": "avg_rest_days", "agg": {"num": "sum(rest_days)", "den": "count(rest_days)"}},
    {"metric": "b2b_rate", "agg": {"num": "sum(is_b2b)", "den": "count(is_b2b)"}},
    {"metric": "appearances_last_3d_avg", "agg": {"num": "sum(appearances_last_3d)", "den": "count(game_pk)"}},
    {"metric": "bf_per_relief", "agg": {"num": "sum(battersFaced)", "den": "count(game_pk)"}},
]

_BULLPEN_WINDOWS = [{"name": "career_to_date", "filter": {}}] + [
    {"name": f"year_{y}", "filter": {"year": y}} for y in range(2022, 2027)
]

_BATTER_DIMS = [
    {"metric": "hits_per_game", "agg": {"num": "sum(hits)", "den": "count(game_pk)"}},
    {"metric": "tb_per_game", "agg": {"num": "sum(totalBases)", "den": "count(game_pk)"}},
    {"metric": "rbi_per_game", "agg": {"num": "sum(rbi)", "den": "count(game_pk)"}},
    {"metric": "runs_per_game", "agg": {"num": "sum(runs)", "den": "count(game_pk)"}},
    {"metric": "hr_per_game", "agg": {"num": "sum(homeRuns)", "den": "count(game_pk)"}},
    {"metric": "bb_per_game", "agg": {"num": "sum(baseOnBalls)", "den": "count(game_pk)"}},
    {"metric": "so_per_game", "agg": {"num": "sum(strikeOuts)", "den": "count(game_pk)"}},
    {"metric": "sb_per_game", "agg": {"num": "sum(stolenBases)", "den": "count(game_pk)"}},
    {"metric": "hbp_per_game", "agg": {"num": "sum(hitByPitch)", "den": "count(game_pk)"}},
    # NOTE: avg/obp/slg (ratio-of-sum PERCENTAGE dims) are REMOVED -- see
    # module docstring "NO percentage/ratio-of-sum dims" for the proof.
]

_PITCHER_DIMS = [
    {"metric": "ip_per_game", "agg": {"num": "sum(inningsPitched)", "den": "count(game_pk)"}},
    {"metric": "k_per_game", "agg": {"num": "sum(pitch_strikeOuts)", "den": "count(game_pk)"}},
    {"metric": "bb_allowed_per_game", "agg": {"num": "sum(baseOnBalls_allowed)", "den": "count(game_pk)"}},
    {"metric": "hits_allowed_per_game", "agg": {"num": "sum(hits_allowed)", "den": "count(game_pk)"}},
    {"metric": "er_per_game", "agg": {"num": "sum(earnedRuns)", "den": "count(game_pk)"}},
    {"metric": "bf_per_game", "agg": {"num": "sum(battersFaced)", "den": "count(game_pk)"}},
    # NOTE: era/whip/k_per_9/bb_per_9 (ratio-of-sum PERCENTAGE dims) are
    # REMOVED for the identical reason as batter avg/obp/slg above.
]

_TEAM_DIMS = [
    {"metric": "team_hits_per_game", "agg": {"num": "sum(hits)", "den": "count_distinct(game_pk)"}},
    {"metric": "team_hr_per_game", "agg": {"num": "sum(homeRuns)", "den": "count_distinct(game_pk)"}},
    {"metric": "team_runs_per_game", "agg": {"num": "sum(runs)", "den": "count_distinct(game_pk)"}},
    {"metric": "team_bb_per_game", "agg": {"num": "sum(baseOnBalls)", "den": "count_distinct(game_pk)"}},
    {"metric": "team_so_per_game", "agg": {"num": "sum(strikeOuts)", "den": "count_distinct(game_pk)"}},
    {"metric": "team_er_per_game", "agg": {"num": "sum(earnedRuns)", "den": "count_distinct(game_pk)"}},
]

# Sole honest window: no season/year column exists on this source (see
# docstring). Both floor-type keys ("season" and "career") are populated
# identically below so the factory's _window_type lookup (career_to_date ->
# "career" bucket) resolves either way without a fail-closed gap.
_CAREER_WINDOW = [
    {"name": "career_to_date", "filter": {}},
]

GRID: dict = {
    "sport": "mlb",
    "families": [
        {
            "family": "mlb_batter_rate",
            "source": _GAMELOGS,
            "grain": "per_game",
            "entity_key": "player_id",
            "entity_name_col": "player",
            "dims": _BATTER_DIMS,
            "windows": [{"name": "career_to_date", "filter": {"is_pitcher": False}}],
            "floors": {
                "season": {"game_pk": 20},
                "career": {"game_pk": 40},
            },
        },
        {
            "family": "mlb_pitcher_rate",
            "source": _GAMELOGS,
            "grain": "per_game",
            "entity_key": "player_id",
            "entity_name_col": "player",
            "dims": _PITCHER_DIMS,
            "windows": [{"name": "career_to_date", "filter": {"is_pitcher": True}}],
            "floors": {
                "season": {"game_pk": 20},
                "career": {"game_pk": 40},
            },
        },
        {
            "family": "mlb_team_rate",
            "source": _GAMELOGS,
            "grain": "per_game",
            "entity_key": "team",
            "entity_name_col": "team",
            "dims": _TEAM_DIMS,
            "windows": _CAREER_WINDOW,
            "floors": {
                "season": {"game_pk": 20},
                "career": {"game_pk": 40},
            },
        },
        {
            "family": "mlb_bullpen_fatigue_chains",
            "source": _BULLPEN_CHAINS,
            "grain": "per_relief_appearance",
            "entity_key": "player_id",
            "entity_name_col": "player",
            "dims": _BULLPEN_DIMS,
            "windows": _BULLPEN_WINDOWS,
            "floors": {
                "season": {"game_pk": 15},
                "career": {"game_pk": 15},
            },
        },
    ],
}
