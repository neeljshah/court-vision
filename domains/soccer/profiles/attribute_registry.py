"""domains.soccer.profiles.attribute_registry -- declared spec for every team
style attribute the profile builder computes. One dict entry per attribute:

    description            -- what it measures, one line
    entity                 -- always "team" (this package is team-only)
    corpus                 -- "statsbomb_event" (400-match event corpus, window=
                               "statsbomb_2015_2021") or "footballdata_season"
                               (25.8k-match corpus, window=footballdata_<season>)
    ingredients             -- names of the raw components build_profiles.py
                               records in the per-row `ingredients` json
    formula                 -- human-readable derivation of raw_value
    status                  -- VALIDATED_MECHANISM (counter_threat -- the counter
                               xG premium is REPLICATED, see
                               domains.soccer.prereg_possession_chains ledger rows
                               for hypothesis=counter_attack_xg_premium,
                               replication_verdict=REPLICATED), VALIDATED_CLAIM
                               (formation_flexibility comes from the claims_formation
                               claim family; buildup_quality/set_piece_threat come
                               from the possession-chain descriptive claim family --
                               both already streaming-validated elsewhere), or
                               DESCRIPTIVE (new, not independently validated)
    floor                   -- min sample (see `floor_basis`) to appear in the profile
    floor_basis             -- what `n` counts for this attribute (matches vs possessions
                               vs home-matches) -- declared per-attribute, not always 30,
                               per the task note ("floor >=30 unless declared otherwise")
    higher_is_better         -- percentile direction (defensive_solidity is a "lower raw
                               = better" metric: xG conceded per possession)
    weight_ledger_family     -- free-text family tag for future intel_weighting hookup

No BLOCKED attribute writes rows; BLOCKED_ATTRIBUTES documents why, for the
build report.
"""
from __future__ import annotations

from typing import Any, Dict

REGISTRY: Dict[str, Dict[str, Any]] = {
    "counter_threat": {
        "description": "Counter-attack goal threat: how often a team counters, weighted "
                        "by how dangerous its counters are.",
        "entity": "team",
        "corpus": "statsbomb_event",
        "ingredients": ["counter_share", "counter_xg_per_poss", "counter_n", "total_n"],
        "formula": "sum(xg | pattern_group=='counter') / count(all_possessions) "
                   "(algebraically = counter_share * counter_xg_per_poss; the sum/count form "
                   "avoids a 0*NaN edge case if a team never counters)",
        "status": "VALIDATED_MECHANISM",
        "floor": 30,
        "floor_basis": "team_matches",
        "higher_is_better": True,
        "weight_ledger_family": "soccer_possession_profile",
    },
    "buildup_quality": {
        "description": "Regular-play (non-counter, non-set-piece) attacking output per possession.",
        "entity": "team",
        "corpus": "statsbomb_event",
        "ingredients": ["regular_xg_sum", "regular_poss_n"],
        "formula": "mean(xg | pattern_group == 'regular')",
        "status": "VALIDATED_CLAIM",
        "floor": 30,
        "floor_basis": "team_matches",
        "higher_is_better": True,
        "weight_ledger_family": "soccer_possession_profile",
    },
    "set_piece_threat": {
        "description": "Share of a team's total expected-goal output that comes from "
                        "set-piece-derived possessions (corner/free kick/throw-in/goal "
                        "kick/keeper/kick-off/other -- everything besides From Counter and "
                        "Regular Play, mirroring the possession-chain claim family's bucketing).",
        "entity": "team",
        "corpus": "statsbomb_event",
        "ingredients": ["set_piece_xg_sum", "total_xg_sum", "total_n"],
        "formula": "sum(xg | pattern_group == 'set_piece_derived') / sum(xg | all)",
        "status": "VALIDATED_CLAIM",
        "floor": 30,
        "floor_basis": "team_matches",
        "higher_is_better": True,
        "weight_ledger_family": "soccer_possession_profile",
    },
    "formation_flexibility": {
        "description": "How much a team varies its starting formation match to match "
                        "(1 - share of matches using its single most-used formation).",
        "entity": "team",
        "corpus": "statsbomb_event",
        "ingredients": ["n_distinct_formations", "primary_formation", "share_primary_formation"],
        "formula": "1 - share_primary_formation",
        "status": "VALIDATED_CLAIM",
        "floor": 30,
        "floor_basis": "matches_with_detected_formation",
        "higher_is_better": True,
        "weight_ledger_family": "soccer_formation_profile",
    },
    "defensive_solidity": {
        "description": "Expected-goals conceded per opponent possession in regular play "
                        "(mirror of buildup_quality, opponent side).",
        "entity": "team",
        "corpus": "statsbomb_event",
        "ingredients": ["opponent_regular_xg_conceded_sum", "opponent_regular_poss_n"],
        "formula": "sum(opponent regular-play xg conceded) / sum(opponent regular-play possessions)",
        "status": "DESCRIPTIVE",
        "floor": 30,
        "floor_basis": "team_matches",
        "higher_is_better": False,  # lower xG conceded per possession = better defense
        "weight_ledger_family": "soccer_possession_profile",
    },
    "finishing_overperformance": {
        "description": "Goals scored minus shots-based expected-goals proxy, per match, "
                        "averaged over a season (hot/cold finishing level, not a rate).",
        "entity": "team",
        "corpus": "footballdata_season",
        "ingredients": ["goals_minus_proxy_xg_sum", "match_n"],
        "formula": "mean(goals - proxy_xg) where proxy_xg = K_SOT*sot + K_OFF*(shots-sot) "
                   "(domains.soccer.asof_xg_proxy weights, realized not as-of)",
        "status": "DESCRIPTIVE",
        "floor": 20,
        "floor_basis": "team_season_matches",
        "higher_is_better": True,
        "weight_ledger_family": "soccer_season_profile",
    },
    "home_strength": {
        "description": "Home points-rate per season (3/1/0 points per win/draw/loss, home "
                        "matches only, normalized to 0-1).",
        "entity": "team",
        "corpus": "footballdata_season",
        "ingredients": ["home_points_sum", "home_match_n"],
        "formula": "mean(home_points) / 3",
        "status": "DESCRIPTIVE",
        "floor": 10,
        "floor_basis": "team_season_home_matches",
        "higher_is_better": True,
        "weight_ledger_family": "soccer_season_profile",
    },
}

# Declared-but-not-built: registry entries the task asked for that are BLOCKED,
# with the reason, so the build report can say why they don't appear.
BLOCKED_ATTRIBUTES: Dict[str, Dict[str, str]] = {
    "press_resistance": {
        "description": "Possessions lost in a team's own third (proxy for press resistance).",
        "reason": "StatsBomb event `location` is pitch-absolute (0-120 x 0-80), not "
                  "normalized to attacking direction, and attacking direction flips at "
                  "half-time/period boundaries. No attacking-direction resolver exists "
                  "anywhere in this codebase (grepped domains/soccer -- nothing). Deriving "
                  "'own third' correctly needs per-period end-swap logic that is not cheap "
                  "or safe to improvise here; a wrong-sided proxy would silently invert the "
                  "attribute. BLOCKED rather than shipped wrong.",
    },
}
