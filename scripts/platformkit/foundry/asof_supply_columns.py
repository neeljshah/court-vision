"""S85/S111 -- the CLOSED column lists the as-of bridge may serve, and nothing else.

Split out of `asof_supply.py` (which is at its 300-line cap) purely so the registry's
declarations and its rules stay in one readable file. Pure data: no logic, no imports.
A column absent from these tuples is refused by `asof_supply.declared` exactly as before.
"""
from __future__ import annotations

# The gate corpus's MLB abbreviations predate two relocations and several style choices; the
# bullpen table uses the modern set. The EVENT side is mapped into the source vocabulary so the
# source stays untouched. 24 of the 34 corpus abbreviations already match verbatim.
MLB_ALIAS = {"ARI": "AZ", "BRS": "BOS", "CUB": "CHC", "KAN": "KC", "LOS": "LAD", "OAK": "ATH",
             "SDG": "SD", "SFG": "SF", "SFO": "SF", "TAM": "TB", "WAS": "WSH"}
# Named, and deliberately NOT supplied: an identifier is not a signal, and a prior-mean of one
# would be noise wearing a plausible name.
IDENTIFIERS = frozenset(("year", "season", "game_pk", "is_p1", "player_id", "catcher_id"))

_NBA_QUARTER = ("home_q1_margin_asof", "away_q1_margin_asof", "diff_q1_margin_asof",
                "home_first_half_margin_asof", "away_first_half_margin_asof",
                "diff_first_half_margin_asof", "home_second_half_margin_asof",
                "away_second_half_margin_asof", "diff_second_half_margin_asof",
                "home_q4_margin_asof", "away_q4_margin_asof", "diff_q4_margin_asof",
                "home_quarter_volatility_asof", "away_quarter_volatility_asof",
                "diff_quarter_volatility_asof")
_PIT = ("opp_pts_allowed_asof", "opp_reb_allowed_asof", "opp_ast_allowed_asof",
        "opp_fg3m_allowed_asof", "opp_stl_allowed_asof", "opp_blk_allowed_asof",
        "opp_tov_allowed_asof", "n_games_asof", "opp_pts_allowed_vs_league",
        "opp_reb_allowed_vs_league", "opp_ast_allowed_vs_league", "opp_fg3m_allowed_vs_league",
        "opp_stl_allowed_vs_league", "opp_blk_allowed_vs_league", "opp_tov_allowed_vs_league")
_STYLE = ("shot_share", "sot_ratio", "fouls_committed_pm", "fouls_drawn_pm", "corners_pm",
          "cards_pm", "ppg", "n_matches", "z_shot_share", "z_sot_ratio", "z_fouls_committed_pm",
          "z_fouls_drawn_pm", "z_corners_pm", "z_cards_pm")


# S111 (a): the tennis families' members, served from the ATP table UNIONED with the `_wta`
# sibling that domains/tennis/asof_wta_siblings.py builds. Both are already one row per
# event and already as-of by construction, so the bridge rule is `event` on `event_id`.
ATP_WTA = "data/domains/tennis/asof_{0}.parquet,data/domains/tennis/asof_{0}_wta.parquet"
TENNIS_FEATURES = tuple("%s_%s_asof" % (s, m) for s in ("p1", "p2", "diff")
                        for m in ("ace_rate", "1st_in", "1st_win", "2nd_win", "bp_saved"))
TENNIS_RETURN = tuple("%s_%s%s_asof" % (s, m, f) for m in ("return_won", "break_pct")
                      for f in ("", "_hard", "_clay", "_grass")
                      for s in (("p1", "p2", "diff") if not f else ("p1", "p2")))
TENNIS_META = tuple("%s_%s" % (s, m) for m in ("ht", "rank_points", "minutes_prior_asof")
                    for s in ("p1", "p2", "diff")) + ("p1_seed", "p2_seed", "draw_size")

# The remaining inline member tuples and source paths, lifted here beside _PIT / _STYLE /
# _NBA_QUARTER so asof_supply.py holds the 300-line rail after the two S136 entries land.
# PURE DATA -- no entry's member list, source or rule changes; every string is verbatim.
_STYLE_SRC = "data/domains/soccer/style_fingerprints.parquet"
_MATCHES_SRC = "data/domains/soccer/matches.parquet"
_VALUE_SRC = "data/domains/basketball_nba/player_value_features.parquet"
_REFEREE_SRC = "data/domains/soccer/referee_card_foul_profiles.parquet"
_VALUE = ("roster_value_asof", "star_absence_delta", "continuity", "top_heavy")
_ADV = ("usagepercentage_asof", "offensiverating_asof", "defensiverating_asof", "pie_asof",
        "possessions_asof", "n_prior")
_RELIEF = ("battersFaced", "rest_days", "is_b2b", "appearances_last_3d")
_REFEREE = ("total_fouls", "total_yellow", "total_red", "total_cards")
_SERVE = ("serve_strength", "return_strength", "n_matches", "z_serve_strength",
          "z_return_strength")

# S136: the ROUND-GRAIN tennis schedule-density / travel tables. The frozen parquets keyed every
# match of a tourney on the START date, so a trailing count spanned rounds played AFTER the match
# (the 2025 Wimbledon champion served 0,3,4,5,1,6,2 and the served value correlated +0.2616 with
# the outcome). domains/tennis/schedule_density_roundgrain.py re-counts at (tourney start date,
# Sackmann round) grain -- the champion now serves 0,1,2,3,4,5,6, the correlation is +0.0481
# inside a +/-0.0693 two-sigma band at n = 800, and the local re-screen is NULL (0 of 32 screens
# improve on the close). `rest_days` is DELIBERATELY ABSENT from RG_DENSITY: real rest days inside
# a tourney are unrecoverable at this date grain, so the member is CLOSED AT LIMIT rather than
# served as a round-depth proxy wearing a rest name. Its hypotheses stay UNCOVERED.
# See docs/evidence/harness/S136_tennis_roundgrain_builders_2026-09-03.md.
RG_DENSITY_SRC = ("data/domains/tennis/schedule_density_rg.parquet,"
                  "data/domains/tennis/schedule_density_rg_wta.parquet")
RG_TRAVEL_SRC = ("data/domains/tennis/travel_scouting_rg.parquet,"
                 "data/domains/tennis/travel_scouting_rg_wta.parquet")
RG_DENSITY = ("matches_last_7d", "matches_last_14d")
RG_TRAVEL = ("miles_flown_in", "venue_altitude_m")
RG_DENSITY_PREGAME = ("schedule_density_roundgrain: a match at (D, r) counts only rows with "
                      "date < D, or date == D and round < r -- strictly before at (tourney start "
                      "date, Sackmann round) grain, so the row can never see itself, a sibling "
                      "of equal round, or a later round of its own event")
RG_TRAVEL_PREGAME = ("schedule_density_roundgrain: prior_city_travel reads the player's PREVIOUS "
                     "resolved host city under that same (date, round) order -- a first "
                     "appearance is NaN, never 0; venue_altitude_m is a property of the venue, "
                     "published with the draw")
