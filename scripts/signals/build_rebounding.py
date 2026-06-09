"""Rebounding Profile signal builder (entity=player, edge_path=pregame).

Sources  (verified schema before coding):
  hustle_features          -> box_outs_pg, contested_shots_pg (2018-2024-25)
  player_adv_stats         -> oreb/dreb/reb pct per-game (2022-23..2024-25)
  leaguegamelog_{rs,po}    -> OREB/DREB/REB per-game (2025-26 only)
  player_breakdown_features -> pts_2nd_chance_pg (2024-25 only)
  team_reb_context         -> team OREB%/DREB% per game (2022-2025)
  ingame_eval_cache        -> player->team mapping for 2022-25 (used for team context join)

Leak rule: season-agg (scouting, no overfit risk) + shift(1)-prior-games-only for L10.
Note: 2025-26 reb rate uses per-minute proxy stored in *_pm_s columns (not *_pct_s)
      to avoid unit mixing (pct_s = possession-based %; pm_s = reb/min).

  python scripts/signals/build_rebounding.py
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "rebounding.parquet")

HUSTLE = os.path.join(ROOT, "data", "cache", "hustle_features.parquet")
ADV = os.path.join(ROOT, "data", "player_adv_stats.parquet")
GL_RS = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")
GL_PO = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_playoffs.parquet")
BREAKDOWN = os.path.join(ROOT, "data", "cache", "player_breakdown_features.parquet")
TEAM_REB = os.path.join(ROOT, "data", "team_reb_context.parquet")
INGAME_EVAL = os.path.join(ROOT, "data", "cache", "ingame_eval_cache.parquet")

MIN_GAMES_L10 = 5        # min games for L10 to be meaningful
MIN_GAMES_SEASON = 10    # min games for season aggregate to be included


def _season_label(game_date: pd.Series) -> pd.Series:
    """Map game_date to NBA season string (e.g. 2024-25)."""
    d = pd.to_datetime(game_date)
    yr = d.dt.year
    mo = d.dt.month
    season_year = np.where(mo >= 10, yr, yr - 1)
    return pd.Series(
        [f"{y}-{str(y+1)[2:]}" for y in season_year],
        index=game_date.index,
    )


def build_season_adv() -> pd.DataFrame:
    """Season reb rate per player. Leak rule: season-agg — scouting only.

    Unit separation (Bug 2 fix):
      2022-25: possession-based % from adv_stats -> *_pct_s (mean ~0.088)
      2025-26: per-minute proxy from leaguegamelog -> *_pm_s (mean ~0.182)
    *_pct_s is NaN for 2025-26; *_pm_s is NaN for 2022-25. Never mixed.
    Percentile ranks are within-season on whichever rate is available.
    """
    adv = pd.read_parquet(ADV)
    adv["season"] = _season_label(adv["game_date"])
    adv_agg = (
        adv.groupby(["player_id", "season"])
        .agg(n_games=("offensivereboundpercentage", "count"),
             oreb_pct_s=("offensivereboundpercentage", "mean"),
             dreb_pct_s=("defensivereboundpercentage", "mean"),
             reb_pct_s=("reboundpercentage", "mean"))
        .reset_index()
    )
    adv_agg = adv_agg[adv_agg["n_games"] >= MIN_GAMES_SEASON].copy()
    adv_agg[["oreb_pm_s", "dreb_pm_s", "reb_pm_s"]] = np.nan  # different units

    rs = pd.read_parquet(GL_RS)
    po = pd.read_parquet(GL_PO)
    gl26 = pd.concat([rs, po], ignore_index=True)
    gl26 = gl26[gl26["MIN"] > 0].copy()
    gl26["season"] = _season_label(gl26["GAME_DATE"])
    gl26["oreb_pm"] = gl26["OREB"] / gl26["MIN"]
    gl26["dreb_pm"] = gl26["DREB"] / gl26["MIN"]
    gl26["reb_pm"] = gl26["REB"] / gl26["MIN"]
    gl_agg = (
        gl26.groupby(["PLAYER_ID", "season"])
        .agg(n_games=("MIN", "count"),
             oreb_pm_s=("oreb_pm", "mean"),
             dreb_pm_s=("dreb_pm", "mean"),
             reb_pm_s=("reb_pm", "mean"))
        .reset_index()
        .rename(columns={"PLAYER_ID": "player_id"})
    )
    gl_agg = gl_agg[gl_agg["n_games"] >= MIN_GAMES_SEASON].copy()
    gl_agg[["oreb_pct_s", "dreb_pct_s", "reb_pct_s"]] = np.nan  # possession data unavailable

    combined = pd.concat([adv_agg, gl_agg], ignore_index=True)

    # Rank within-season on whichever rate column is populated
    for _tmp, rank_col, c_pct, c_pm in [
        ("_r", "reb_pct_rank_s", "reb_pct_s", "reb_pm_s"),
        ("_o", "oreb_pct_rank_s", "oreb_pct_s", "oreb_pm_s"),
        ("_d", "dreb_pct_rank_s", "dreb_pct_s", "dreb_pm_s"),
    ]:
        combined[_tmp] = combined[c_pct].fillna(combined[c_pm])
        combined[rank_col] = (
            combined.groupby("season")[_tmp].rank(pct=True) * 100
        ).round(1)
        combined.drop(columns=[_tmp], inplace=True)

    for c in ["oreb_pct_s", "dreb_pct_s", "reb_pct_s", "oreb_pm_s", "dreb_pm_s", "reb_pm_s"]:
        combined[c] = combined[c].round(4)
    return combined[["player_id", "season", "n_games",
                      "oreb_pct_s", "dreb_pct_s", "reb_pct_s",
                      "oreb_pm_s", "dreb_pm_s", "reb_pm_s",
                      "oreb_pct_rank_s", "dreb_pct_rank_s", "reb_pct_rank_s"]]


def build_hustle_season() -> pd.DataFrame:
    """Box-outs/game and contested_shots/game per season. Leak rule: season-agg."""
    df = pd.read_parquet(HUSTLE)
    df = df[df["hustle_games_played"].fillna(0) >= MIN_GAMES_SEASON].copy()
    df = df.rename(columns={
        "hustle_box_outs": "box_outs_pg",
        "hustle_contested_shots": "contested_shots_pg",
    })
    return df[["player_id", "season", "box_outs_pg", "contested_shots_pg"]].copy()


def build_l10_rolling() -> pd.DataFrame:
    """L10 rolling rebound snapshot (shift(1) prior-games-only — pregame safe).
    Returns the most recent valid L10 per (player, season)."""
    rs = pd.read_parquet(GL_RS)
    po = pd.read_parquet(GL_PO)
    df = pd.concat([rs, po], ignore_index=True)
    df["game_date"] = pd.to_datetime(df["GAME_DATE"])
    df["season"] = _season_label(df["GAME_DATE"])
    df = df[df["MIN"] > 0].sort_values(["PLAYER_ID", "game_date"]).reset_index(drop=True)

    out_rows = []
    for pid, grp in df.groupby("PLAYER_ID"):
        grp = grp.sort_values("game_date").copy()
        for src, dst in [("OREB", "oreb_l10"), ("DREB", "dreb_l10"),
                         ("REB", "reb_l10"), ("MIN", "min_l10")]:
            grp[dst] = (
                grp[src].shift(1).rolling(10, min_periods=MIN_GAMES_L10).mean()
            )
        # OREB share proxy
        grp["oreb_share"] = np.where(grp["REB"] > 0, grp["OREB"] / grp["REB"], np.nan)
        grp["oreb_share_l10"] = (
            grp["oreb_share"].shift(1).rolling(10, min_periods=MIN_GAMES_L10).mean()
        )

        # Last valid L10 per season
        last_per_season = (
            grp.dropna(subset=["reb_l10"]).groupby("season").last().reset_index()
        )
        for _, row in last_per_season.iterrows():
            out_rows.append({
                "player_id": int(pid),
                "season": row["season"],
                "oreb_l10": round(float(row["oreb_l10"]), 2) if pd.notna(row["oreb_l10"]) else None,
                "dreb_l10": round(float(row["dreb_l10"]), 2) if pd.notna(row["dreb_l10"]) else None,
                "reb_l10": round(float(row["reb_l10"]), 2) if pd.notna(row["reb_l10"]) else None,
                "min_l10": round(float(row["min_l10"]), 1) if pd.notna(row["min_l10"]) else None,
                "oreb_share_l10": round(float(row["oreb_share_l10"]), 3)
                    if pd.notna(row.get("oreb_share_l10")) else None,
            })
    return pd.DataFrame(out_rows)


def build_2nd_chance() -> pd.DataFrame:
    """2nd-chance pts/g from player_breakdown_features (2024-25 only). Leak rule: season-agg."""
    df = pd.read_parquet(BREAKDOWN)
    df = df[["player_id", "season", "misc_pts_2nd_chance"]].rename(
        columns={"misc_pts_2nd_chance": "pts_2nd_chance_pg"}
    )
    return df.copy()


def build_team_reb_context() -> pd.DataFrame:
    """Team OREB%/DREB% for each player's primary team (2022-2025). Leak rule: season-agg.

    Bug 1 fix: the original code built the player->team map from leaguegamelog (2025-26 only)
    while team_reb_context covers 2022-25 only — disjoint seasons -> 100% NaN join.
    Fix: use ingame_eval_cache (spans 2022-25, carries team tricode) for the map instead.
    """
    trc = pd.read_parquet(TEAM_REB)
    trc["season"] = _season_label(trc["game_date"])
    team_season = (
        trc.groupby(["team_tricode", "season"])
        .agg(team_oreb_pct=("oreb_pct", "mean"), team_dreb_pct=("dreb_pct", "mean"))
        .reset_index()
    )
    team_season[["team_oreb_pct", "team_dreb_pct"]] = (
        team_season[["team_oreb_pct", "team_dreb_pct"]].round(4)
    )

    iec = pd.read_parquet(INGAME_EVAL)
    iec["season"] = _season_label(iec["game_date"])
    player_team = (
        iec.groupby(["player_id", "season", "team"])
        .size().reset_index(name="cnt")
        .sort_values("cnt", ascending=False)
        .groupby(["player_id", "season"]).first().reset_index()
        .rename(columns={"team": "team_tricode"})
    )

    merged = player_team.merge(team_season, on=["team_tricode", "season"], how="left")
    assert len(merged) == len(player_team), (
        f"team_reb join blowup: {len(merged)} vs {len(player_team)}"
    )
    # Non-null guard: fires if season ranges become disjoint again.
    assert merged["team_oreb_pct"].notna().any(), (
        "team_oreb_pct is 100% NaN — iec and team_reb_context season ranges are disjoint. "
        f"iec={sorted(player_team['season'].unique())}, "
        f"trc={sorted(team_season['season'].unique())}"
    )
    return merged[["player_id", "season", "team_oreb_pct", "team_dreb_pct"]].copy()


def build() -> pd.DataFrame:
    """Merge all rebounding signal frames on (player_id, season)."""
    print("season adv...")
    adv = build_season_adv()
    print(f"  {len(adv)} rows, {adv['player_id'].nunique()} players, "
          f"seasons={sorted(adv['season'].unique())}")
    print("hustle...")
    hustle = build_hustle_season()
    print(f"  {len(hustle)} rows, seasons={sorted(hustle['season'].unique())}")
    print("L10 rolling...")
    l10 = build_l10_rolling()
    print(f"  {len(l10)} rows, seasons={sorted(l10['season'].unique())}")
    print("2nd-chance...")
    sc2 = build_2nd_chance()
    print(f"  {len(sc2)} rows")
    print("team context...")
    team_ctx = build_team_reb_context()
    print(f"  {len(team_ctx)} rows")

    out = adv.copy()
    out = out.merge(hustle, on=["player_id", "season"], how="left")
    n0 = len(out)
    out = out.merge(l10, on=["player_id", "season"], how="left")
    assert len(out) == n0, f"L10 merge blowup: {len(out)} vs {n0}"
    out = out.merge(sc2, on=["player_id", "season"], how="left")
    assert len(out) == n0, f"sc2 merge blowup"
    out = out.merge(team_ctx, on=["player_id", "season"], how="left")
    assert len(out) == n0, f"team_ctx merge blowup"
    return out.reset_index(drop=True)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)

    n_rows = len(out)
    n_players = out["player_id"].nunique()
    n_seasons = sorted(out["season"].unique())
    print(f"\nDONE: rebounding signals -> {OUT}")
    print(f"  rows={n_rows}  distinct_players={n_players}  seasons={n_seasons}")

    print("\n3 sample rows:")
    print(out.head(3).to_string())

    print("\nSanity: top rebounders 2024-25 by reb_pct_s (>=15g):")
    top_s = (
        out[(out["season"] == "2024-25") & (out["n_games"] >= 15)]
        .nlargest(5, "reb_pct_s")
        [["player_id", "reb_pct_s", "oreb_pct_s", "dreb_pct_s", "box_outs_pg",
          "reb_pct_rank_s", "team_oreb_pct"]]
    )
    print(top_s.to_string(index=False))

    print("\nSanity: top rebounders 2025-26 by reb_pm_s (>=15g):")
    top_26 = (
        out[(out["season"] == "2025-26") & (out["n_games"] >= 15)]
        .dropna(subset=["reb_pm_s"]).nlargest(5, "reb_pm_s")
        [["player_id", "reb_pm_s", "oreb_pm_s", "dreb_pm_s", "reb_pct_rank_s"]]
    )
    print(top_26.to_string(index=False))

    print("\nSanity: top L10 rebounders 2025-26 (reb_l10):")
    top_l10 = (
        out[out["season"] == "2025-26"].dropna(subset=["reb_l10"])
        .nlargest(5, "reb_l10")[["player_id", "reb_l10", "oreb_l10", "dreb_l10", "min_l10"]]
    )
    print(top_l10.to_string(index=False))

    print("\nSignal coverage by season:")
    cov_cols = ["oreb_pct_s", "reb_pm_s", "box_outs_pg", "reb_l10", "pts_2nd_chance_pg", "team_oreb_pct"]
    cov = out[["season"] + cov_cols].copy()
    cov[cov_cols] = cov[cov_cols].notna()
    print(cov.groupby("season")[cov_cols].sum())

    pct_in_26 = out[out["season"] == "2025-26"]["reb_pct_s"].notna().sum()
    pm_in_pre26 = out[out["season"] != "2025-26"]["reb_pm_s"].notna().sum()
    print(f"\nUnit-separation check: reb_pct_s non-null in 2025-26={pct_in_26} (expect 0), "
          f"reb_pm_s non-null in 2022-25={pm_in_pre26} (expect 0)")


if __name__ == "__main__":
    main()
