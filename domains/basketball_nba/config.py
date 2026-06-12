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

__all__ = ["NBA_STAT_REGISTRY"]
