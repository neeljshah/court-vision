"""domains.basketball_nba.atlas — NBA intelligence-vault section catalog.

Holds the verbose ``NBA_ATLAS`` AtlasSchema instance so that config.py
stays within its 300-LOC budget.

Section names are verbatim from the Obsidian vault:
  vault/Intelligence/_Simulation_Signals.md (§player and §team atlas headers)

Zero heavy imports: kernel.config.atlas_schema only.
Python 3.9 floor.
"""
from __future__ import annotations

from kernel.config.atlas_schema import AtlasSchema

# ---------------------------------------------------------------------------
# NBA_ATLAS — P0-D-017
# ---------------------------------------------------------------------------
# 28 player sections + 16 team sections, verbatim from the vault catalog.
# dim_to_section maps a representative set of error-miner context-dimension
# keys to the atlas section best suited to explain systematic bias in that
# dimension.  A small representative mapping is sufficient for launch;
# the error-miner falls back to returning None for unmapped dims.
# ---------------------------------------------------------------------------

NBA_ATLAS: AtlasSchema = AtlasSchema(
    sport_id="basketball_nba",
    player_sections=(
        "catch_shoot_vs_pullup",
        "clutch_scoring",
        "defensive_profile",
        "durability_load",
        "form_streak_dynamics",
        "foul_drawing",
        "foul_tendency",
        "ft_profile",
        "isolation_profile",
        "matchup_splits",
        "monthly_form",
        "pace_fit",
        "pick_and_roll_profile",
        "playmaking_network",
        "post_up_profile",
        "quarter_shape_fatigue",
        "rebounding_profile",
        "rest_b2b_splits",
        "score_margin_splits",
        "scoring_creation",
        "shot_clock_scoring",
        "shot_profile",
        "situational_splits",
        "spacing_gravity",
        "transition_scoring",
        "turnover_profile",
        "usage_role",
        "vs_scheme_splits",
    ),
    team_sections=(
        "bench_production",
        "clutch_team",
        "defensive_scheme",
        "ft_foul_environment",
        "halfcourt_offense",
        "lineup_synergy",
        "matchup_adjustments",
        "offensive_scheme",
        "pace_identity",
        "paint_defense",
        "rebounding_scheme",
        "rotation_patterns",
        "three_pt_defense",
        "transition_defense",
        "transition_halfcourt_splits",
        "turnover_forcing",
    ),
    entity_frontmatter={
        "sport_id":   "str",
        "entity_id":  "str",
        "entity_kind": "str",
        "season":     "str",
        "last_updated": "str",
    },
    dim_to_section={
        # game-state dimensions → player sections
        "game_state:clutch":        "clutch_scoring",
        "game_state:blowout":       "score_margin_splits",
        "game_state:garbage":       "score_margin_splits",
        # shot-location dimensions → player sections
        "shot:zone":                "shot_profile",
        "shot:catch_shoot":         "catch_shoot_vs_pullup",
        "shot:pullup":              "catch_shoot_vs_pullup",
        "shot:clock":               "shot_clock_scoring",
        # quarter / time dimensions → player sections
        "quarter:Q4":               "quarter_shape_fatigue",
        "quarter:Q3":               "quarter_shape_fatigue",
        # play-type dimensions → player sections
        "play_type:iso":            "isolation_profile",
        "play_type:pnr_ball":       "pick_and_roll_profile",
        "play_type:post":           "post_up_profile",
        "play_type:transition":     "transition_scoring",
        # workload / rest dimensions → player sections
        "rest:b2b":                 "rest_b2b_splits",
        "load:high":                "durability_load",
        # pace / scheme dimensions → team sections
        "team:pace":                "pace_identity",
        "team:defense":             "defensive_scheme",
        "team:offense":             "offensive_scheme",
        "team:clutch":              "clutch_team",
        "team:transition":          "transition_halfcourt_splits",
        "team:rebounding":          "rebounding_scheme",
    },
)

__all__ = ["NBA_ATLAS"]
