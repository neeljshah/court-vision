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
    # ================================================== 07-08 expansion (18)
    # ------------------------------------------------------- statsbomb (8)
    "defensive_counter_threat": {
        "description": "xG conceded per opponent possession from counter-attacks against "
                        "(defensive mirror of counter_threat).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["counter_xg_sum", "total_n"],
        "formula": "sum(opponent counter-pattern xg conceded) / count(all opponent possessions)",
        "status": "DESCRIPTIVE", "floor": 30, "floor_basis": "team_matches",
        "higher_is_better": False, "weight_ledger_family": "soccer_possession_profile",
    },
    "defensive_set_piece_threat": {
        "description": "Share of xG a team concedes that comes from opponent set-piece-derived "
                        "possessions (defensive mirror of set_piece_threat).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["set_piece_xg_sum", "total_xg_sum"],
        "formula": "sum(opponent set_piece-pattern xg conceded) / sum(opponent xg conceded, all patterns)",
        "status": "DESCRIPTIVE", "floor": 30, "floor_basis": "team_matches",
        "higher_is_better": False, "weight_ledger_family": "soccer_possession_profile",
    },
    "first_half_xg_share": {
        "description": "Share of a team's total xG output created in the first half (period==1).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["half_xg_sum", "total_xg_sum"],
        "formula": "sum(xg | period==1) / sum(xg)",
        "status": "DESCRIPTIVE", "floor": 30, "floor_basis": "team_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_possession_profile",
    },
    "second_half_xg_share": {
        "description": "Share of a team's total xG output created in the second half or later "
                        "(period>=2, covers extra-time periods 3-5 too).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["half_xg_sum", "total_xg_sum"],
        "formula": "sum(xg | period>=2) / sum(xg)",
        "status": "DESCRIPTIVE", "floor": 30, "floor_basis": "team_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_possession_profile",
    },
    "possessions_per_match": {
        "description": "Mean number of statsbomb possessions per match (tempo proxy).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["total_n", "team_matches"],
        "formula": "count(possessions) / count_distinct(match_id)",
        "status": "DESCRIPTIVE", "floor": 30, "floor_basis": "team_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_possession_profile",
    },
    "shots_per_possession": {
        "description": "Shot attempts per possession (directness proxy).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["total_shots", "total_poss"],
        "formula": "count(Shot events) / count(possessions)",
        "status": "DESCRIPTIVE", "floor": 30, "floor_basis": "team_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_possession_profile",
    },
    "formation_primary_xg": {
        "description": "xG per possession restricted to matches where a team used its single "
                        "MOST-used detected starting formation (that formation needs "
                        ">=10 matches to qualify).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["formation", "xg_sum", "poss_n", "match_n"],
        "formula": "sum(xg | formation==primary) / count(possessions | formation==primary)",
        "status": "DESCRIPTIVE", "floor": 10, "floor_basis": "matches_with_that_formation",
        "higher_is_better": True, "weight_ledger_family": "soccer_formation_profile",
    },
    "formation_secondary_xg": {
        "description": "xG per possession restricted to matches where a team used its SECOND "
                        "most-used detected starting formation (needs >=10 matches to qualify).",
        "entity": "team", "corpus": "statsbomb_event",
        "ingredients": ["formation", "xg_sum", "poss_n", "match_n"],
        "formula": "sum(xg | formation==secondary) / count(possessions | formation==secondary)",
        "status": "DESCRIPTIVE", "floor": 10, "floor_basis": "matches_with_that_formation",
        "higher_is_better": True, "weight_ledger_family": "soccer_formation_profile",
    },
    # ------------------------------------------------------ footballdata (10)
    "home_goal_rate": {
        "description": "Mean goals scored per HOME match, per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(fthg | is_home)",
        "status": "DESCRIPTIVE", "floor": 10, "floor_basis": "team_season_home_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "away_goal_rate": {
        "description": "Mean goals scored per AWAY match, per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(ftag | is_away)",
        "status": "DESCRIPTIVE", "floor": 10, "floor_basis": "team_season_away_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "away_strength": {
        "description": "Away points-rate per season (mirror of home_strength, away matches only).",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["pts_sum", "match_n"],
        "formula": "mean(away_points) / 3",
        "status": "DESCRIPTIVE", "floor": 10, "floor_basis": "team_season_away_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "clean_sheet_rate": {
        "description": "Share of matches (home+away) a team concedes zero goals, per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(goals_conceded==0)",
        "status": "DESCRIPTIVE", "floor": 20, "floor_basis": "team_season_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "comeback_rate": {
        "description": "Of matches a team trailed at half-time, share it went on to win or draw.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(won_or_drew | trailed_at_HT)",
        "status": "DESCRIPTIVE", "floor": 5, "floor_basis": "team_season_matches_trailing_at_HT",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "shot_conversion_rate": {
        "description": "Goals scored per shot attempted (home+away), per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["num_sum", "den_sum", "match_n"],
        "formula": "sum(goals_for) / sum(shots_for)",
        "status": "DESCRIPTIVE", "floor": 20, "floor_basis": "team_season_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "shot_accuracy": {
        "description": "Shots on target per shot attempted (home+away), per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["num_sum", "den_sum", "match_n"],
        "formula": "sum(sot_for) / sum(shots_for)",
        "status": "DESCRIPTIVE", "floor": 20, "floor_basis": "team_season_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
    },
    "discipline_rate": {
        "description": "Mean cards (yellow+red) per match, per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(yellow_cards + red_cards)",
        "status": "DESCRIPTIVE", "floor": 20, "floor_basis": "team_season_matches",
        "higher_is_better": False, "weight_ledger_family": "soccer_season_profile",
    },
    "foul_rate": {
        "description": "Mean fouls committed per match, per season.",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(fouls)",
        "status": "DESCRIPTIVE", "floor": 20, "floor_basis": "team_season_matches",
        "higher_is_better": False, "weight_ledger_family": "soccer_season_profile",
    },
    "corner_rate": {
        "description": "Mean corners won per match, per season (attacking-territory proxy).",
        "entity": "team", "corpus": "footballdata_season",
        "ingredients": ["value", "match_n"],
        "formula": "mean(corners)",
        "status": "DESCRIPTIVE", "floor": 20, "floor_basis": "team_season_matches",
        "higher_is_better": True, "weight_ledger_family": "soccer_season_profile",
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
    "lead_trail_score_state": {
        "description": "xG-per-possession splits by whether a team was leading/trailing/tied at "
                        "the start of the possession (statsbomb corpus, 07-08 expansion ask).",
        "reason": "Requires reconstructing a running score timeline per match from Shot (outcome="
                  "'Goal') and Own Goal events, then attributing each possession's pre-possession "
                  "score state -- but Own Goal events credit the scoring side to the OPPONENT of "
                  "the event's own `team` field (a flip easy to get backwards), and knockout "
                  "matches carry extra-time periods 3-5 whose continuation of the running score "
                  "must not reset. Same class of silent-wrong-side risk that already got "
                  "press_resistance BLOCKED above -- not attempted rather than shipped wrong.",
    },
    "late_goal_share": {
        "description": "Share of a team's goals scored in the closing minutes (footballdata "
                        "season corpus, 07-08 expansion ask).",
        "reason": "No goal-minute column exists anywhere in the footballdata corpus -- "
                  "match_stats.parquet/matches.parquet carry only match-level aggregate counts "
                  "(fthg/ftag/hthg/htag, shots, cards), never a per-goal minute. The statsbomb "
                  "corpus DOES carry per-event minutes but is a different (400-match) corpus than "
                  "the one this attribute was asked against; BLOCKED rather than silently "
                  "substituting a different corpus's window.",
    },
}
