"""S85/S111 -- the CLOSED column lists the as-of bridge may serve, and nothing else.

Split out of `asof_supply.py` (which is at its 300-line cap) purely so the registry's
declarations and its rules stay in one readable file. Pure data: no logic, no imports.
A column absent from these tuples is refused by `asof_supply.declared` exactly as before.
"""
from __future__ import annotations

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
