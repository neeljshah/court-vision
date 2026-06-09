"""Wave 1 builder: per-player in-game rotation & pace profile.

Reads:
  data/cache/quarter_features.parquet      — per-game per-player per-quarter
                                             minutes + pts + usage signals
  data/cache/foul_features.parquet         — rolling foul-trouble rates
  data/cache/atlas_player_pace_fit.parquet — season-agg pace context atlas
  data/cache/atlas_player_quarter_shape_fatigue.parquet — season-agg Q-shape

Emits: data/cache/signals/ingame_rotation.parquet
  One row per player. Entity = player. Consumer = C (in-game reactivity).

Signals computed (all season-aggregate over 2024-25/2025-26 combined):
  q{1..4}_min_avg          — average minutes per quarter
  q{1..4}_pts_pg           — average points per game per quarter
  min_curve_skew           — (q4_min - q1_min) / total_min  (<0 = typical rest, >0 = closer)
  q4_pts_share             — q4 pts / total pts (late-game usage shape)
  q4_fade_abs              — q4 pts - avg(q1..q3) pts  (fatigue flag, from atlas)
  foul_trouble_rate        — fraction of games with 4+ personal fouls in first half
  pf_per36                 — fouls per 36 minutes (rolling-mean across season)
  pace_preference          — "fast" / "slow" / None from atlas (string tag)
  pace_fit_score           — numeric pace-fit score from atlas
  usage_pace_delta         — USG delta fast-vs-slow pace games
  n_games                  — games in sample (for confidence weighting)
  second_half_min_share    — mean second-half minute share (proxy: starter vs bench)
  q3_starter_min_avg       — mean Q3 minutes (proxy for starter load)

Leak rule: season-aggregate across prior completed games in the corpus
  (leaguegamelog_regular_season is the 2024-25 regular season;
  quarter_features includes 2024-25 + 2025-26 through 2026-01-19 — all
  pre-computed and not updated live). Label: leak_rule="season-agg, scouting/ingame".
  Do NOT use for point-model-candidate without shift(1) gamelog variant.

  python scripts/signals/build_ingame_rotation.py
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QF_PATH = os.path.join(ROOT, "data", "cache", "quarter_features.parquet")
FF_PATH = os.path.join(ROOT, "data", "cache", "foul_features.parquet")
ATLAS_QSF_PATH = os.path.join(ROOT, "data", "cache", "atlas_player_quarter_shape_fatigue.parquet")
ATLAS_PACE_PATH = os.path.join(ROOT, "data", "cache", "atlas_player_pace_fit.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "ingame_rotation.parquet")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_quarter_features() -> pd.DataFrame:
    """Load quarter_features; keep game_id as string (zero-padded)."""
    df = pd.read_parquet(QF_PATH)
    # game_id is already object/string — never int() it
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def _build_quarter_agg(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-game quarter data to season-level per-player stats."""
    total_pts_col = df[["q1_pts", "q2_pts", "q3_pts", "q4_pts"]].sum(axis=1)
    total_min_col = df[["q1_minutes", "q4_minutes"]].sum(axis=1)  # proxy; q2/q3 not stored

    agg = df.groupby(["player_id", "player_name"]).agg(
        q1_min_avg=("q1_minutes", "mean"),
        q4_min_avg=("q4_minutes", "mean"),
        q3_starter_min_avg=("q3_starter_minutes", "mean"),
        q1_pts_pg=("q1_pts", "mean"),
        q2_pts_pg=("q2_pts", "mean"),
        q3_pts_pg=("q3_pts", "mean"),
        q4_pts_pg=("q4_pts", "mean"),
        q4_pts_share_mean=("fourth_quarter_share_pts", "mean"),
        second_half_min_share_mean=("second_half_share_min", "mean"),
        n_games=("game_id", "count"),
    ).reset_index()

    # scoring-shape signals
    avg_q13 = (agg["q1_pts_pg"] + agg["q2_pts_pg"] + agg["q3_pts_pg"]) / 3.0
    agg["q4_fade_pts"] = (agg["q4_pts_pg"] - avg_q13).round(3)

    # minute curve skew: positive = plays more in Q4 than Q1 (closer role)
    total_min = agg["q1_min_avg"] + agg["q4_min_avg"]
    agg["min_curve_skew"] = np.where(
        total_min > 0,
        ((agg["q4_min_avg"] - agg["q1_min_avg"]) / total_min).round(4),
        np.nan,
    )
    return agg


def _build_foul_agg(df: pd.DataFrame) -> pd.DataFrame:
    """Season-level foul signals from the rolling foul_features frame."""
    # foul_features is already per-game rolling — aggregate to player level
    agg = df.groupby("player_id").agg(
        pf_per36=("pf_per_36_l10", "mean"),
        foul_trouble_rate=("foul_trouble_rate_l10", "mean"),
    ).reset_index()
    agg["pf_per36"] = agg["pf_per36"].round(3)
    agg["foul_trouble_rate"] = agg["foul_trouble_rate"].round(4)
    return agg


def _build_pace_atlas(df: pd.DataFrame) -> pd.DataFrame:
    """Extract pace signals from atlas_player_pace_fit."""
    cols = ["player_id", "pace_preference", "pace_fit_score", "usage_pace_delta",
            "median_pace", "min_fast", "min_slow"]
    available = [c for c in cols if c in df.columns]
    sub = df[available].copy()
    if "pace_fit_score" in sub.columns:
        sub["pace_fit_score"] = sub["pace_fit_score"].round(4)
    if "usage_pace_delta" in sub.columns:
        sub["usage_pace_delta"] = sub["usage_pace_delta"].round(4)
    return sub


def _build_atlas_qshape(df: pd.DataFrame) -> pd.DataFrame:
    """Extract per-quarter shape signals from atlas_player_quarter_shape_fatigue."""
    cols = ["player_id", "q1_min", "q2_min", "q3_min", "q4_min",
            "q4_vs_early_ratio", "q4_fade_abs", "min_per_game",
            "b2b_decay_ratio", "n_games"]
    available = [c for c in cols if c in df.columns]
    sub = df[available].copy()
    # rename to avoid collision with quarter_features aggregation
    rename_map = {
        "q1_min": "atlas_q1_min",
        "q2_min": "atlas_q2_min",
        "q3_min": "atlas_q3_min",
        "q4_min": "atlas_q4_min",
        "n_games": "atlas_n_games",
    }
    sub = sub.rename(columns={k: v for k, v in rename_map.items() if k in sub.columns})
    for c in ["atlas_q1_min", "atlas_q2_min", "atlas_q3_min", "atlas_q4_min",
              "q4_vs_early_ratio", "q4_fade_abs", "min_per_game", "b2b_decay_ratio"]:
        if c in sub.columns:
            sub[c] = sub[c].round(3)
    return sub


def build() -> pd.DataFrame:
    # --- load sources -------------------------------------------------------
    qf = _load_quarter_features()
    ff = pd.read_parquet(FF_PATH) if os.path.exists(FF_PATH) else pd.DataFrame()
    atlas_qs = pd.read_parquet(ATLAS_QSF_PATH) if os.path.exists(ATLAS_QSF_PATH) else pd.DataFrame()
    atlas_pace = pd.read_parquet(ATLAS_PACE_PATH) if os.path.exists(ATLAS_PACE_PATH) else pd.DataFrame()

    # --- aggregate quarter-features -----------------------------------------
    base = _build_quarter_agg(qf)
    assert len(base) <= qf.player_id.nunique(), \
        f"Row explosion in quarter agg: {len(base)} vs {qf.player_id.nunique()} players"

    # --- foul features -------------------------------------------------------
    if not ff.empty:
        foul_agg = _build_foul_agg(ff)
        base = base.merge(foul_agg, on="player_id", how="left")
    else:
        base["pf_per36"] = np.nan
        base["foul_trouble_rate"] = np.nan

    # --- atlas quarter-shape (season-agg, broader sample) -------------------
    if not atlas_qs.empty:
        qs_agg = _build_atlas_qshape(atlas_qs)
        base = base.merge(qs_agg, on="player_id", how="left")
        assert len(base) <= qf.player_id.nunique(), \
            f"Row explosion after atlas_qs merge: {len(base)}"
    else:
        for c in ["atlas_q1_min", "atlas_q2_min", "atlas_q3_min", "atlas_q4_min",
                  "q4_vs_early_ratio", "q4_fade_abs", "min_per_game", "b2b_decay_ratio",
                  "atlas_n_games"]:
            base[c] = np.nan

    # --- atlas pace (very sparse, outer-left) --------------------------------
    if not atlas_pace.empty:
        pace_agg = _build_pace_atlas(atlas_pace)
        base = base.merge(pace_agg, on="player_id", how="left")
        assert len(base) <= qf.player_id.nunique(), \
            f"Row explosion after atlas_pace merge: {len(base)}"
    else:
        for c in ["pace_preference", "pace_fit_score", "usage_pace_delta", "median_pace"]:
            base[c] = np.nan

    # --- round and finalise -------------------------------------------------
    for col in ["q1_min_avg", "q4_min_avg", "q3_starter_min_avg",
                "q1_pts_pg", "q2_pts_pg", "q3_pts_pg", "q4_pts_pg",
                "q4_pts_share_mean", "second_half_min_share_mean"]:
        if col in base.columns:
            base[col] = base[col].round(3)

    base = base.rename(columns={
        "q4_pts_share_mean": "q4_pts_share",
        "second_half_min_share_mean": "second_half_min_share",
    })

    base["leak_rule"] = "season-agg"
    base["signal_domain"] = "ingame_rotation"
    base = base.sort_values("n_games", ascending=False).reset_index(drop=True)
    return base


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)

    n_players = out.player_id.nunique()
    print(f"DONE: ingame_rotation signals -> {OUT}")
    print(f"  rows={len(out)}  distinct players={n_players}")
    print()
    print("Sample rows (3):")
    print(out.head(3)[[
        "player_id", "player_name", "n_games",
        "q1_min_avg", "q4_min_avg", "min_curve_skew",
        "q4_pts_share", "q4_fade_pts",
        "foul_trouble_rate", "pf_per36",
        "pace_preference", "pace_fit_score",
    ]].to_string(index=False))

    print()
    print("Sanity — top 10 closers by min_curve_skew (most Q4-heavy, q1>=3min):")
    closers = (
        out.dropna(subset=["min_curve_skew"])
        .loc[out["q1_min_avg"] >= 3.0]
        .nlargest(10, "min_curve_skew")[
            ["player_name", "n_games", "q1_min_avg", "q4_min_avg", "min_curve_skew"]
        ]
    )
    for r in closers.itertuples(index=False):
        print(f"  {r.player_name:<26s} skew={r.min_curve_skew:+.3f}  "
              f"q1={r.q1_min_avg:.1f}  q4={r.q4_min_avg:.1f}  n={r.n_games}")

    print()
    print("Sanity — top 10 foul-trouble players (highest rate):")
    foul_heavy = (
        out.dropna(subset=["foul_trouble_rate"])
        .nlargest(10, "foul_trouble_rate")[
            ["player_name", "n_games", "foul_trouble_rate", "pf_per36"]
        ]
    )
    for r in foul_heavy.itertuples(index=False):
        print(f"  {r.player_name:<26s} trouble_rate={r.foul_trouble_rate:.3f}  "
              f"pf/36={r.pf_per36:.2f}  n={r.n_games}")


if __name__ == "__main__":
    main()
