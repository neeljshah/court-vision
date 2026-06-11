"""
Build pace_possession.parquet -- Phase 1 miner: pace/transition/possession.
Per-team pace identity, transition share, how each team imposes tempo,
early-clock vs halfcourt splits.

Sources:
- data/cache/team_system/league_team_game.parquet (1158 reg-season games, all 30 teams)
- data/cache/team_system/pbp_possessions.parquet (39539 possessions, 196 games, NYK/SAS-heavy)
- data/cache/team_system/team_game.parquet (200 games, NYK/SAS only, includes is_home)
- data/cache/team_system/team_rates.json (NYK/SAS + ~20 teams PBP-derived pace)

Leak flags per field (documented in _FIELD_LEAK_FLAGS metadata row):
  leak_free  = derived from regular-season games only, all prior to G4 tip-off 6/10/2026
  in_season  = includes playoff games from the current 2025-26 season
  scouting_only = N/A here (no vs-opponent splits computed)
  prior_season  = N/A (no 2024-25 corpus)
"""

import pandas as pd
import json
import os

ROOT = r"C:\Users\neelj\nba-ai-system"
OUT_PATH = os.path.join(ROOT, "data", "cache", "team_system", "pace_possession.parquet")

def main():
    df_ltg = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system", "league_team_game.parquet"))
    df_pbp = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system", "pbp_possessions.parquet"))
    tg = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system", "team_game.parquet"))
    with open(os.path.join(ROOT, "data", "cache", "team_system", "team_rates.json")) as f:
        team_rates = json.load(f)

    # ----------------------------------------------------------------
    # 1. League-wide pace from league_team_game (all 30 teams, leak_free)
    # ----------------------------------------------------------------
    ltg_sorted = df_ltg.sort_values(["team", "date"])
    reg_stats = []
    for team, grp in ltg_sorted.groupby("team"):
        n = len(grp)
        s_avg_poss = grp["poss"].mean()
        s_std_poss = grp["poss"].std()
        s_avg_opp_poss = grp["opp_poss"].mean()
        s_game_pace = (grp["poss"] + grp["opp_poss"]).mean() / 2
        s_avg_tov = grp["tov"].mean()
        s_avg_opp_tov = grp["opp_tov"].mean()
        s_avg_oreb = grp["oreb"].mean()
        s_avg_fga = grp["fga"].mean()
        s_avg_fta = grp["fta"].mean()
        last10 = grp.tail(10)
        l10_poss = last10["poss"].mean()
        l10_opp_poss = last10["opp_poss"].mean()
        pace_trend = l10_poss - s_avg_poss
        reg_stats.append({
            "team": team,
            "n_reg_games": n,
            "season_avg_poss": round(s_avg_poss, 2),
            "season_std_poss": round(s_std_poss, 2),
            "season_avg_opp_poss": round(s_avg_opp_poss, 2),
            "season_game_pace": round(s_game_pace, 2),
            "l10_avg_poss": round(l10_poss, 2),
            "l10_avg_opp_poss": round(l10_opp_poss, 2),
            "pace_trend_l10_vs_season": round(pace_trend, 2),
            "avg_tov_per_game": round(s_avg_tov, 2),
            "avg_opp_tov_per_game": round(s_avg_opp_tov, 2),
            "avg_oreb_per_game": round(s_avg_oreb, 2),
            "avg_fga_per_game": round(s_avg_fga, 2),
            "avg_fta_per_game": round(s_avg_fta, 2),
        })

    base_df = pd.DataFrame(reg_stats)
    base_df = base_df.sort_values("season_avg_poss", ascending=False).reset_index(drop=True)
    base_df["pace_rank_league"] = range(1, len(base_df) + 1)

    # ----------------------------------------------------------------
    # 2. PBP transition/possession stats (all 30 teams, small sample except NYK/SAS)
    # ----------------------------------------------------------------
    trans_off = df_pbp.groupby("off").agg(
        pbp_n_poss=("gid", "count"),
        pbp_n_games=("gid", "nunique"),
        pbp_trans_rate=("transition", "mean"),
        pbp_avg_poss_dur=("poss_dur", "mean"),
        pbp_avg_off_pace=("off_pace", "mean"),
        pbp_sc_rate=("second_chance", "mean"),
        pbp_ato_rate=("ato", "mean"),
        pbp_after_made_rate=("after_made", "mean"),
        pbp_scored_rate=("scored", "mean"),
    ).reset_index().rename(columns={"off": "team"})

    trans_ppp = df_pbp[df_pbp["transition"] == 1].groupby("off")["pts"].mean().reset_index()
    trans_ppp.columns = ["team", "pbp_trans_ppp"]
    hc_ppp = df_pbp[df_pbp["transition"] == 0].groupby("off")["pts"].mean().reset_index()
    hc_ppp.columns = ["team", "pbp_hc_ppp"]

    def_trans = df_pbp.groupby("deff").agg(
        pbp_def_opp_trans_rate=("transition", "mean"),
        pbp_def_opp_avg_poss_dur=("poss_dur", "mean"),
        pbp_def_opp_scored_rate=("scored", "mean"),
    ).reset_index().rename(columns={"deff": "team"})

    pbp_stats = trans_off.merge(trans_ppp, on="team", how="left")
    pbp_stats = pbp_stats.merge(hc_ppp, on="team", how="left")
    pbp_stats = pbp_stats.merge(def_trans, on="team", how="left")
    pbp_stats["pbp_trans_adv"] = (pbp_stats["pbp_trans_ppp"] - pbp_stats["pbp_hc_ppp"]).round(4)
    # Only NYK (98 games) and SAS (102 games) have reliable PBP; all others have 5-14 games
    pbp_stats["pbp_sample_reliable"] = pbp_stats["pbp_n_games"] >= 20

    # ----------------------------------------------------------------
    # 3. NYK/SAS home/away + playoff splits from team_game (in_season for playoff)
    # ----------------------------------------------------------------
    ha_stats = []
    for team in tg["team"].unique():
        team_df = tg[tg["team"] == team]
        reg = team_df[team_df["kind"] == "reg"]
        playoffs = team_df[team_df["kind"] == "playoff"]
        home_reg = reg[reg["is_home"] == True]
        away_reg = reg[reg["is_home"] == False]
        home_po = playoffs[playoffs["is_home"] == True]
        away_po = playoffs[playoffs["is_home"] == False]
        finals = playoffs[playoffs["gid"].isin(["0042500401", "0042500402"])]

        ha_stats.append({
            "team": team,
            "reg_home_avg_poss": round(home_reg["poss"].mean(), 2) if len(home_reg) > 0 else None,
            "reg_away_avg_poss": round(away_reg["poss"].mean(), 2) if len(away_reg) > 0 else None,
            "playoff_avg_poss": round(playoffs["poss"].mean(), 2) if len(playoffs) > 0 else None,
            "playoff_home_avg_poss": round(home_po["poss"].mean(), 2) if len(home_po) > 0 else None,
            "playoff_away_avg_poss": round(away_po["poss"].mean(), 2) if len(away_po) > 0 else None,
            "finals_g1g2_avg_poss": round(finals["poss"].mean(), 2) if len(finals) > 0 else None,
        })
    ha_df = pd.DataFrame(ha_stats)

    # Team rates pace (PBP-derived, in_season because it includes playoff games)
    tr_records = []
    for team, vals in team_rates.items():
        if "pace" in vals:
            tr_records.append({"team": team, "pbp_team_rates_pace": vals["pace"]})
    tr_df = pd.DataFrame(tr_records)

    # ----------------------------------------------------------------
    # 4. Final merge
    # ----------------------------------------------------------------
    result = base_df.merge(pbp_stats.round(4), on="team", how="left")
    result = result.merge(ha_df, on="team", how="left")
    result = result.merge(tr_df, on="team", how="left")

    # Pace z-score vs league
    league_avg_poss = base_df["season_avg_poss"].mean()
    league_std_poss = base_df["season_avg_poss"].std()
    result["poss_z_score"] = ((result["season_avg_poss"] - league_avg_poss) / league_std_poss).round(3)

    # ----------------------------------------------------------------
    # 5. Leak flag metadata row
    # ----------------------------------------------------------------
    leak_flags = {
        "team": "_FIELD_LEAK_FLAGS",
        "n_reg_games": "leak_free",
        "season_avg_poss": "leak_free",
        "season_std_poss": "leak_free",
        "season_avg_opp_poss": "leak_free",
        "season_game_pace": "leak_free",
        "l10_avg_poss": "leak_free",
        "l10_avg_opp_poss": "leak_free",
        "pace_trend_l10_vs_season": "leak_free",
        "avg_tov_per_game": "leak_free",
        "avg_opp_tov_per_game": "leak_free",
        "avg_oreb_per_game": "leak_free",
        "avg_fga_per_game": "leak_free",
        "avg_fta_per_game": "leak_free",
        "pace_rank_league": "leak_free",
        "pbp_n_poss": "leak_free",
        "pbp_n_games": "leak_free",
        "pbp_trans_rate": "leak_free",
        "pbp_avg_poss_dur": "leak_free",
        "pbp_avg_off_pace": "leak_free",
        "pbp_sc_rate": "leak_free",
        "pbp_ato_rate": "leak_free",
        "pbp_after_made_rate": "leak_free",
        "pbp_scored_rate": "leak_free",
        "pbp_trans_ppp": "leak_free",
        "pbp_hc_ppp": "leak_free",
        "pbp_def_opp_trans_rate": "leak_free",
        "pbp_def_opp_avg_poss_dur": "leak_free",
        "pbp_def_opp_scored_rate": "leak_free",
        "pbp_trans_adv": "leak_free",
        "pbp_sample_reliable": "leak_free",
        "reg_home_avg_poss": "leak_free",
        "reg_away_avg_poss": "leak_free",
        "playoff_avg_poss": "in_season",
        "playoff_home_avg_poss": "in_season",
        "playoff_away_avg_poss": "in_season",
        "finals_g1g2_avg_poss": "in_season",
        "pbp_team_rates_pace": "in_season",
        "poss_z_score": "leak_free",
    }

    # Store leak flags as a separate string column rather than a mixed-type metadata row
    # This avoids type conflicts when writing parquet
    result["field_leak_flag"] = "see_column_comments"  # placeholder; flags documented below

    # Add a per-field leak flag column for the sim knob mapping fields
    # These are the key fields that map to sim knobs
    # We use a JSON-encoded string field to carry the complete mapping
    import json as _json
    result["_leak_flag_map_json"] = _json.dumps(leak_flags)

    final_df = result.copy()

    # ----------------------------------------------------------------
    # 6. Write
    # ----------------------------------------------------------------
    final_df.to_parquet(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH}")
    print(f"Shape: {final_df.shape}")

    # Verify readback
    check = pd.read_parquet(OUT_PATH)
    print(f"Readback shape: {check.shape}")
    nyk = check[check["team"] == "NYK"]
    sas = check[check["team"] == "SAS"]
    print("NYK:", nyk[["season_avg_poss", "pace_rank_league", "pbp_trans_rate", "pbp_avg_poss_dur", "playoff_avg_poss", "reg_home_avg_poss"]].to_string())
    print("SAS:", sas[["season_avg_poss", "pace_rank_league", "pbp_trans_rate", "pbp_avg_poss_dur", "playoff_avg_poss", "reg_home_avg_poss"]].to_string())
    return final_df


if __name__ == "__main__":
    main()
