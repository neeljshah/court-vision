"""NBA sport-context configuration stub.

This module will hold ALL NBA literal values VERBATIM and assemble the
``NBA_SPORT_CONTEXT`` mapping consumed by the sport-agnostic kernel.
Planned content (to be filled by tasks P0-D-012 through P0-D-017):

- stat_registry       : canonical stat-name → dtype / unit / direction mapping
- clock               : period count, period length, OT length, shot-clock rules
- court               : dimensions, zone polygons, paint / arc / mid-range regions
- roster              : position taxonomy, min/max roster size, two-way limits
- game_state          : score, fouls, timeouts, bonus thresholds
- speed               : pace / possession-length distribution parameters
- pbp_event_map       : raw play-by-play event codes → normalised action tokens
- entity_tables       : team IDs, conference/division memberships (static per season)

P0-D-012: ``NBA_STAT_REGISTRY`` is fully implemented below (7 counting stats in
historical tuple order, verbatim sigma + calibration-slope literals, priced=True for
all, loop_targets byte-identical to ``src.loop.signal.TARGETS``).  No heavy imports —
this module imports ``kernel.config.stats`` only.
"""
from __future__ import annotations

from kernel.config.stats import SportStatRegistry, StatSpec

# ---------------------------------------------------------------------------
# NBA stat registry — P0-D-012
# ---------------------------------------------------------------------------
# Stat order is LOAD-BEARING (R3 ordering invariant): positional array code
# (routed-ensemble heads, correlation matrices, model pickle feature order)
# depends on this exact sequence.  The conformance test
# tests/conformance/nba/test_nba_stat_registry.py enforces byte-identity.
#
# Literal values are verbatim from three source-of-truth files (never inferred):
#   sigma_default          ← src/prediction/decision_engine.py  _STAT_SIGMA
#   calibration_fallback_slope ← src/prediction/edge_calibration.py _FALLBACK_SLOPES
#   priced / priced_order  ← src/prediction/betting_portfolio.py _PROP_STATS_ORDER
# ---------------------------------------------------------------------------

NBA_STAT_REGISTRY: SportStatRegistry = SportStatRegistry(
    sport_id="basketball_nba",
    stats={
        "pts": StatSpec(
            name="pts",
            kind="count",
            display="Points",
            sigma_default=5.0,
            priced=True,
            higher_is_better=True,
            settle="official_box",
            correlated_with=("reb", "ast"),
            calibration_fallback_slope=0.277,
        ),
        "reb": StatSpec(
            name="reb",
            kind="count",
            display="Rebounds",
            sigma_default=2.2,
            priced=True,
            higher_is_better=True,
            settle="official_box",
            correlated_with=("pts",),
            calibration_fallback_slope=0.235,
        ),
        "ast": StatSpec(
            name="ast",
            kind="count",
            display="Assists",
            sigma_default=1.6,
            priced=True,
            higher_is_better=True,
            settle="official_box",
            correlated_with=("pts",),
            calibration_fallback_slope=0.366,
        ),
        "fg3m": StatSpec(
            name="fg3m",
            kind="count",
            display="3-Pointers Made",
            sigma_default=1.1,
            priced=True,
            higher_is_better=True,
            settle="official_box",
            correlated_with=("pts",),
            calibration_fallback_slope=0.461,
        ),
        "stl": StatSpec(
            name="stl",
            kind="count",
            display="Steals",
            sigma_default=0.9,
            priced=True,
            higher_is_better=True,
            settle="official_box",
            correlated_with=("blk",),
            calibration_fallback_slope=0.651,
        ),
        "blk": StatSpec(
            name="blk",
            kind="count",
            display="Blocks",
            sigma_default=0.6,
            priced=True,
            higher_is_better=True,
            settle="official_box",
            correlated_with=("stl",),
            calibration_fallback_slope=0.228,
        ),
        "tov": StatSpec(
            name="tov",
            kind="count",
            display="Turnovers",
            sigma_default=1.1,
            priced=True,
            higher_is_better=False,
            settle="official_box",
            correlated_with=("ast",),
            calibration_fallback_slope=1.0,
        ),
    },
    box_score_mapping={
        "PTS":  "pts",
        "REB":  "reb",
        "AST":  "ast",
        "FG3M": "fg3m",
        "STL":  "stl",
        "BLK":  "blk",
        "TOV":  "tov",
    },
    score_stat="pts",
    minutes_equiv="minutes",
)

__all__ = [
    "NBA_STAT_REGISTRY",
    "NBA_CLOCK",
    "NBA_ROSTER",
    "NBA_GAME_STATE",
    "NBA_COURT",
    "NBA_SPEED",
    "NBA_SPORT_CONTEXT",
    "SPORT_CONTEXT",
]

# ---------------------------------------------------------------------------
# NBA clock configuration — P0-D-013
# ---------------------------------------------------------------------------
# Source-of-truth literals (verbatim, never inferred):
#   period_len_sec  ← src/sim/live_game_simulator.py:58  REG_PERIOD_SEC = 720
#   ot_len_sec      ← src/sim/live_game_simulator.py:59  OT_PERIOD_SEC = 300
#   play_clock_sec  ← src/tracking/possession_classifier.py:50  SHOT_CLOCK_MAX = 24.0
#   penalty_threshold ← src/sim/possession_model.py:106  BONUS_FOULS = 5
#   regulation_sec() == 4 × 720 = 2880 (asserted by conformance test)
# ---------------------------------------------------------------------------
from kernel.config.clock import GameClockConfig
from kernel.config.court import CourtConfig
from kernel.config.game_state import GameStateConfig
from kernel.config.roster import PositionSchema, RosterConfig
from kernel.config.speed import SpeedConfig

NBA_CLOCK: GameClockConfig = GameClockConfig(
    n_periods=4,
    period_len_sec=720,
    ot_len_sec=300,
    untimed=False,
    play_clock_sec=24,
    penalty_threshold=5,
    max_ot_periods=None,  # NBA plays until decided (unlimited OT)
)

# ---------------------------------------------------------------------------
# NBA roster configuration — P0-D-013
# ---------------------------------------------------------------------------
# Source-of-truth literals:
#   on_field_count  ← src/sim/live_game_simulator.py:61  PLAYERS_ON_COURT = 5
#   foul_out_limit  ← src/prediction/foul_trouble_predictor.py:37  _FOUL_OUT_LIMIT = 6
#   reach_ft        ← src/analytics/space_control.py:21  BASE_REACH_FT = 6.0
#   roster_size=15, season_length_games=82 — NBA rules (no named constant in src/)
#   positions — NBA standard (no named tuple constant in src/)
# ---------------------------------------------------------------------------

_NBA_POSITION_SCHEMA: PositionSchema = PositionSchema(
    positions=("PG", "SG", "SF", "PF", "C"),
    archetypes={
        "guard": ("PG", "SG"),
        "forward": ("SF", "PF"),
        "center": ("C",),
    },
)

NBA_ROSTER: RosterConfig = RosterConfig(
    on_field_count=5,
    roster_size=15,
    season_length_games=82,
    positions=_NBA_POSITION_SCHEMA,
    substitution_model="free",
    foul_out_limit=6,
    reach_ft=6.0,
)

# ---------------------------------------------------------------------------
# NBA game-state configuration — P0-D-013
# ---------------------------------------------------------------------------
# Primary values (canonical per-sport threshold):
#   blowout_margin          = 15.0  game_models.py:100 (training threshold)
#   clutch_margin           =  6.0  live_game_simulator.py:279 (wider of two)
#   clutch_remaining_sec    = 360.0 live_game_simulator.py:279 (sec<=360)
#   garbage_margin          = 18.0  garbage_time_detector.py:157 (live detect)
#   competitive_margin      = 12.0  upper bound "~5-12 pts competitive" (no named const)
#   final_margin_sigma      = 13.5  universal_winprob.py:28  SIGMA_FULL_DEFAULT
#   winprob_promotion_period=  4    universal_winprob.py:33  MIN_PERIOD_FOR_UNIVERSAL
#
# legacy_overrides — DISAGREEMENTS verbatim (never unified; see NBA_LITERALS.md §9):
#   D-1: blowout — game_models training=15 vs garbage_time_detector live=18
#         vs live_game_simulator live=18
#   D-2: clutch margin — live_game_simulator=6 vs game_clock_sim=5
#         clutch_remaining_sec — live_game_simulator=360 vs game_clock_sim=300
# ---------------------------------------------------------------------------

NBA_GAME_STATE: GameStateConfig = GameStateConfig(
    blowout_margin=15.0,
    clutch_margin=6.0,
    clutch_remaining_sec=360.0,
    garbage_margin=18.0,
    competitive_margin=12.0,
    final_margin_sigma=13.5,
    winprob_promotion_period=4,
    legacy_overrides={
        # --- D-1: blowout disagreements ---
        # game_models.py:100 — training/prediction label threshold
        "game_models.blowout_margin": 15.0,
        # garbage_time_detector.py:35 — training-mode blowout threshold
        "garbage_time_detector.blowout_margin_training": 15.0,
        # garbage_time_detector.py:157 — live detect_blowout threshold
        "garbage_time_detector.blowout_margin": 18.0,
        # live_game_simulator.py:185 — blowout+sec_remaining<=480 check
        "live_game_simulator.blowout_margin": 18.0,
        # --- D-2: clutch margin disagreements ---
        # live_game_simulator.py:279 — margin<=6 AND sec<=360 AND period>=4
        "live_game_simulator.clutch_margin": 6.0,
        # game_clock_sim.py:171 — margin<=5 AND period>=4 AND clock<300
        "game_clock_sim.clutch_margin": 5.0,
        # --- D-2: clutch remaining-seconds disagreements ---
        # live_game_simulator.py:279 — sec<=360 (6 minutes)
        "live_game_simulator.clutch_remaining_sec": 360.0,
        # game_clock_sim.py:171 — clock<300 (5 minutes)
        "game_clock_sim.clutch_remaining_sec": 300.0,
    },
)

# ---------------------------------------------------------------------------
# NBA court configuration — P0-D-013
# Source-of-truth: space_control.py:17-18 (94×50 ft), unified_pipeline.py
# (basket/rectify/fps/3pt literals). cv2/torch heavy — constants AST-extracted.
# ---------------------------------------------------------------------------

NBA_COURT: CourtConfig = CourtConfig(
    surface_w=94.0,
    surface_h=50.0,
    unit="ft",
    goal_x_left=0.045,
    goal_x_right=0.955,
    goal_y=0.5,
    key_zones={},       # zone polygons deferred to P0-D-014
    rectified_px=(940, 500),
    fps_native=30.0,
    speed_tiers={
        "drive_min": 10.0,   # ft/s — drive to basket (unified_pipeline speed tier)
        "cut_min":   14.0,   # ft/s — off-ball cut (_DRIBBLE_MAX_VEL, event_detector.py:18)
    },
    three_pt_dist=23.75,
)

# ---------------------------------------------------------------------------
# NBA speed configuration — P0-D-013
# Source-of-truth: unified_pipeline.py (fps/drive_min), event_detector.py:18
# (_DRIBBLE_MAX_VEL=14), space_control.py:21 (BASE_REACH_FT=6).
# ---------------------------------------------------------------------------

NBA_SPEED: SpeedConfig = SpeedConfig(
    video_fps=30.0,
    thresholds_ft_s={
        "drive_min": 10.0,
        "cut_min":   14.0,
    },
    screen_dist_ft=6.0,
)

# ---------------------------------------------------------------------------
# NBA SportContext assembly — P0-D-017
# Adapter imports are deferred to here (not module top) — all three adapters
# are offline-safe at instantiation.  Verbose atlas lives in atlas.py.
# ---------------------------------------------------------------------------
from pathlib import Path  # noqa: E402
from kernel.config.context import SportContext  # noqa: E402
from kernel.config.registry import register_sport  # noqa: E402
from .atlas import NBA_ATLAS  # noqa: E402
from .entity_registry import NBAEntityRegistry  # noqa: E402
from .league_client import NBALeagueClient  # noqa: E402
from .pbp_mapper import NBAPBPEventMapper  # noqa: E402

NBA_SPORT_CONTEXT: SportContext = SportContext(
    stats=NBA_STAT_REGISTRY,
    clock=NBA_CLOCK,
    roster=NBA_ROSTER,
    game_state=NBA_GAME_STATE,
    court=NBA_COURT,
    speed=NBA_SPEED,
    pbp_mapper=NBAPBPEventMapper(),
    league_client=NBALeagueClient(),
    entities=NBAEntityRegistry(),
    source_tiers={"cdn_livedata": 4, "stats_api": 3, "bbref": 2, "broadcast_cv": 1},
    atlas_schema=NBA_ATLAS,
    artifact_root=Path("data"),
)

#: ``load_sport("basketball_nba")`` discovers this attribute by name.
SPORT_CONTEXT: SportContext = NBA_SPORT_CONTEXT

# Idempotent — setdefault in registry; re-importing never errors.
register_sport(NBA_SPORT_CONTEXT)
