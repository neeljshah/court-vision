"""Per-sport source builders extracted from :mod:`corpus_cache`."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.ratings import walk_forward_elo as nba_walk_forward_elo
from domains.mlb.asof_sp_form import build_sp_form_features
from domains.mlb.ratings import walk_forward_elo as mlb_walk_forward_elo
from domains.soccer.ratings import walk_forward_goals
from domains.tennis.elo_walkforward import walk_forward_elo as tennis_walk_forward_elo

_NBA_PAIR_DIFFS: Dict[str, Tuple[str, str]] = {
    "pace_diff_asof": ("home_pace_asof", "away_pace_asof"),
    "oreb_pg_diff_asof": ("home_oreb_pg_asof", "away_oreb_pg_asof"),
    "tov_pg_diff_asof": ("home_tov_pg_asof", "away_tov_pg_asof"),
}
SOCCER_LEAKY_COLUMNS = frozenset({
    "home_shots", "away_shots", "home_sot", "away_sot", "home_corners", "away_corners",
    "home_fouls", "away_fouls", "home_yellow", "away_yellow", "home_red", "away_red",
    "total_shots", "total_sot", "home_sot_ratio", "away_sot_ratio",
    "hthg", "htag", "htr", "fthg", "ftag", "ftr", "total_goals", "target_over25",
    "total_fouls", "total_yellow", "total_red", "total_cards",
    "shot_share", "sot_ratio", "fouls_committed_pm", "fouls_drawn_pm", "corners_pm",
    "cards_pm", "ppg", "finishing_residual_home", "finishing_residual_away", "sot_diff",
})
_SOCCER_ASOF_EXISTING: Tuple[str, ...] = (
    "home_sot_for_l10", "away_sot_for_l10", "diff_sot_for_asof", "diff_sot_against_asof",
    "diff_shots_for_asof", "diff_shots_against_asof", "home_sot_ratio_for_asof",
    "away_sot_ratio_for_asof", "home_n_prior", "away_n_prior")
_SOCCER_ASOF_ADDED: Tuple[str, ...] = (
    "home_sot_for_asof", "home_sot_against_asof", "home_shots_for_asof",
    "home_shots_against_asof", "away_sot_for_asof", "away_sot_against_asof",
    "away_shots_for_asof", "away_shots_against_asof")
_CORPUS_SPINE = frozenset({"event_id", "corpus_unit", "event_date", "y"})


def column_coverage(df: pd.DataFrame) -> Dict[str, object]:
    """Return feature non-null counts globally and for each corpus unit."""
    coverage: Dict[str, object] = {}
    zero_coverage = []
    for column in (name for name in df.columns if name not in _CORPUS_SPINE):
        series = df[column].notna()
        by_unit: Dict[str, Dict[str, object]] = {}
        for unit, group in df.groupby("corpus_unit", dropna=False):
            present = group[column].notna()
            n_non_null = int(present.sum())
            unit_name = str(unit)
            by_unit[unit_name] = {"n_rows": int(len(group)), "n_non_null": n_non_null,
                                  "rate": float(present.mean())}
            if n_non_null == 0:
                zero_coverage.append({"column": column, "corpus_unit": unit_name})
        coverage[column] = {"n_rows": int(len(df)), "n_non_null": int(series.sum()),
                            "rate": float(series.mean()), "corpus_unit": by_unit}
    return {"coverage": coverage, "zero_coverage": zero_coverage}


def _build_mlb() -> Tuple[pd.DataFrame, List[Path]]:
    games_a = _cache._REPO / "data/domains/mlb/games.parquet"
    games_b = _cache._REPO / "data/domains/mlb/games_current.parquet"
    park = _cache._REPO / "data/domains/mlb/asof_park.parquet"
    asof = _cache._REPO / "data/domains/mlb/asof_features.parquet"
    sources = [games_a, games_b, park, asof]
    sp = build_sp_form_features()[["event_id", "sp_first6_diff_ew"]]
    park_df = pd.read_parquet(park)[["event_id", "park_factor"]]
    ra_df = pd.read_parquet(asof)[["event_id", "sp_ra_diff_asof"]]
    frames = []
    for path, unit in ((games_a, "era_2010_2021"), (games_b, "era_2022_2026")):
        games = pd.read_parquet(path)
        games = games[games["target_home_win"].notna()].reset_index(drop=True)
        elo = mlb_walk_forward_elo(games)[["event_id", "date", "p_home_elo"]]
        out = games[["event_id", "target_home_win"]].merge(elo, on="event_id", how="left")
        out = out.merge(sp, on="event_id", how="left").merge(park_df, on="event_id", how="left")
        out = out.merge(ra_df, on="event_id", how="left").sort_values("date").reset_index(drop=True)
        out["corpus_unit"], out["y"], out["p_base"] = unit, out["target_home_win"].astype(float), np.nan
        frames.append(out)
    df = pd.concat(frames, ignore_index=True)
    df["p_base"] = df["p_home_elo"].astype(float)
    df[_cache.DATE_COL] = df["date"]
    return df[["event_id", "corpus_unit", _cache.DATE_COL, "y", "p_base", "p_home_elo",
               "sp_first6_diff_ew", "park_factor", "sp_ra_diff_asof"]], sources


def _build_nba() -> Tuple[pd.DataFrame, List[Path]]:
    games_path = _cache._REPO / "data/domains/basketball_nba/games.parquet"
    asof = _cache._REPO / "data/domains/basketball_nba/asof_features_ext.parquet"
    box_extra = _cache._REPO / "data/domains/basketball_nba/asof_box_extra_ext.parquet"
    sources = [games_path, asof, box_extra]
    games = pd.read_parquet(games_path)
    games = games[games["home_win"].notna()].reset_index(drop=True)
    games["season_label"] = games["season"].astype(str)
    games["season"] = games["season_label"].str.split("-").str[0].astype(int)
    wf = nba_walk_forward_elo(games)
    elo_col = next((c for c in ("p_home_elo", "win_prob_home", "p_elo") if c in wf.columns), None)
    elo_sel = wf[["game_id", elo_col]].rename(columns={elo_col: "p_elo"}) if elo_col else wf[["game_id"]].assign(p_elo=np.nan)
    af = pd.read_parquet(asof)
    for out_col, (home, away) in _NBA_PAIR_DIFFS.items():
        af[out_col] = af[home].astype(float) - af[away].astype(float) if home in af and away in af else np.nan
    box = pd.read_parquet(box_extra)
    box_keep = [c for c in ("dreb_diff_asof", "fg3m_diff_asof", "stl_diff_asof", "blk_diff_asof") if c in box.columns]
    out = af[["game_id"] + list(_NBA_PAIR_DIFFS)].merge(box[["game_id"] + box_keep], on="game_id", how="left")
    out = out.merge(games[["game_id", "date", "season_label", "home_win"]], on="game_id", how="left")
    out = out.merge(elo_sel, on="game_id", how="left").sort_values("date").reset_index(drop=True)
    out["event_id"], out["corpus_unit"] = out["game_id"].astype(str), out["season_label"]
    out["y"], out["p_base"] = out["home_win"].astype(float), out["p_elo"].astype(float)
    out["dreb_x_pace_asof"] = out["dreb_diff_asof"] * out["pace_diff_asof"]
    out["stl_x_fg3m_asof"] = out["stl_diff_asof"] * out["fg3m_diff_asof"]
    out[_cache.DATE_COL] = out["date"]
    cols = (["event_id", "corpus_unit", _cache.DATE_COL, "y", "p_base", "p_elo"] + box_keep
            + list(_NBA_PAIR_DIFFS) + ["dreb_x_pace_asof", "stl_x_fg3m_asof"])
    return out[cols], sources


def _asof_only(columns: List[str]) -> List[str]:
    leaky = sorted(set(columns) & SOCCER_LEAKY_COLUMNS)
    if leaky:
        raise ValueError("same-match (leaky) column(s) refused for the soccer gate spine: " + ", ".join(leaky))
    return list(columns)


def _build_soccer() -> Tuple[pd.DataFrame, List[Path], Dict[str, Dict[str, object]]]:
    matches = _cache._REPO / "data/domains/soccer/matches.parquet"
    asof = _cache._REPO / "data/domains/soccer/asof_features.parquet"
    xg = _cache._REPO / "data/domains/soccer/asof_xg_proxy.parquet"
    sources = [matches, asof, xg]
    mdf = pd.read_parquet(matches)
    mdf["event_id"] = mdf["event_id"].astype(str)
    total_goals = pd.to_numeric(mdf["fthg"], errors="coerce") + pd.to_numeric(mdf["ftag"], errors="coerce")
    mdf["target_over25"] = (total_goals >= 3).astype(float)
    wf = walk_forward_goals(mdf[total_goals.notna()].copy())
    wf["event_id"], wf["p_over25"] = wf["event_id"].astype(str), np.clip(wf["p_over25"].astype(float), 1e-6, 1 - 1e-6)
    adf = pd.read_parquet(asof)
    adf["event_id"] = adf["event_id"].astype(str)
    adf = adf.drop_duplicates("event_id", keep="first")
    ing_cols = _asof_only([c for c in _SOCCER_ASOF_EXISTING if c in adf.columns])
    added_cols = _asof_only([c for c in _SOCCER_ASOF_ADDED if c in adf.columns])
    out = wf.merge(adf[["event_id"] + ing_cols + added_cols], on="event_id", how="left")
    xdf = pd.read_parquet(xg)
    xdf["event_id"] = xdf["event_id"].astype(str)
    xdf = xdf.drop_duplicates("event_id", keep="first")
    xg_cols = _asof_only([c for c in xdf.columns if c != "event_id" and c not in ing_cols + added_cols])
    out = out.merge(xdf[["event_id"] + xg_cols], on="event_id", how="left")
    out["corpus_unit"] = out["div"].astype(str) if "div" in out.columns else "unknown_league"
    out["y"], out["p_base"], out[_cache.DATE_COL] = out["target_over25"].astype(float), out["p_over25"].astype(float), out["date"]
    provenance = {col: {"source": str(src.relative_to(_cache._REPO)).replace("\\", "/"), "join_key": "event_id", "n_rows": int(len(out)), "n_joined": int(out[col].notna().sum()), "join_rate": round(float(out[col].notna().mean()), 6)} for cols, src in ((added_cols, asof), (xg_cols, xg)) for col in cols}
    return out[["event_id", "corpus_unit", _cache.DATE_COL, "y", "p_base", "p_over25"] + ing_cols + added_cols + xg_cols], sources, provenance


def _build_tennis() -> Tuple[pd.DataFrame, List[Path]]:
    atp_m = _cache._REPO / "data/domains/tennis/matches.parquet"
    atp_h = _cache._REPO / "data/domains/tennis/asof_hold.parquet"
    wta_m = _cache._REPO / "data/domains/tennis/wta_matches.parquet"
    wta_h = _cache._REPO / "data/domains/tennis/asof_hold_wta.parquet"
    ret = _cache._REPO / "data/domains/tennis/asof_return.parquet"
    sources, frames = [atp_m, atp_h, wta_m, wta_h, ret], []
    for m_path, h_path, unit in ((atp_m, atp_h, "ATP"), (wta_m, wta_h, "WTA")):
        mm = pd.read_parquet(m_path)
        wf = tennis_walk_forward_elo(mm[mm["winner"].notna()].reset_index(drop=True))
        elo_col = next((c for c in ("win_prob_p1", "p_elo") if c in wf.columns), None)
        out = wf[["event_id", "date", "winner"] + ([elo_col] if elo_col else [])].rename(columns={elo_col: "p_elo"} if elo_col else {})
        if "p_elo" not in out:
            out["p_elo"] = np.nan
        out["target_p1_win"] = (out["winner"].astype(float) == 1.0).astype(float)
        hold = pd.read_parquet(h_path)
        hold_cols = [c for c in ("event_id", "surface", "p1_n_prior", "p2_n_prior", "p1_hold_pct_asof", "p2_hold_pct_asof") if c in hold.columns]
        out = out.merge(hold[hold_cols].drop_duplicates("event_id", keep="first"), on="event_id", how="left")
        ret_df = pd.read_parquet(ret)
        ret_cols = [c for c in ("event_id", "diff_return_won_asof", "diff_break_pct_asof") if c in ret_df.columns]
        out = out.merge(ret_df[ret_cols].drop_duplicates("event_id", keep="first"), on="event_id", how="left")
        out["corpus_unit"], out["y"], out["p_base"] = unit, out["target_p1_win"], out["p_elo"].astype(float)
        frames.append(out)
    df = pd.concat(frames, ignore_index=True)
    df[_cache.DATE_COL] = df["date"]
    keep = ["event_id", "corpus_unit", _cache.DATE_COL, "y", "p_base", "p_elo", "surface", "p1_hold_pct_asof", "p2_hold_pct_asof", "diff_return_won_asof", "diff_break_pct_asof"]
    return df[[c for c in keep if c in df.columns]], sources


_BUILDERS = {"mlb": _build_mlb, "nba": _build_nba, "soccer": _build_soccer, "tennis": _build_tennis}


# Bound at the BOTTOM of this file: corpus_cache imports these builders, so a top-of-file
# back-import crashes whenever this module is the one imported first.
from scripts.platformkit.combo import corpus_cache as _cache
