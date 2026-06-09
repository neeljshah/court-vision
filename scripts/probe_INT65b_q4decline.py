"""
probe_INT65b_q4decline.py -- INT-65 REBUILT on REAL per-quarter data.

Context
-------
INT-65 (CV fatigue trajectories) was DEFER'd 2026-05-30: the CV
`scoreboard_period` is a frame-percentile fill, NOT real OCR quarters
(36/38 games match the percentile bucket >0.97), so a velocity-decay slope
built on it measures clip-position, not game-quarter, and fails the Q1>Q4
prior. See vault INT-65 + memory feedback_percentile_fill_defeats_quarter_signals.

The correct data source for a fatigue / Q4-decline signal is the NBA-API
per-quarter box: data/player_quarter_stats.parquet (real Q1-Q4 splits).

This probe builds a LEAK-FREE per-player Q4-decline prior and tests it as a
residual-head feature on top of the endQ3 -> final baseline (same harness as
probe_R10_M9_fatigue.py). Physics argument (satisfies the player-level
volume rule): a player's historical tendency to fade in Q4 (lower Q4 minutes
share, lower Q4 per-minute production, negative Q4 plus-minus) is a prior on
late-game output that the endQ3 snapshot's current Q1-3 box cannot contain.

Ship gate: WF 4/4 folds non-positive (MAE down) for the residual head AND
mean pooled delta <= -0.005 on >= 4/7 stats. Else REJECT/DEFER honestly.

Run:
    python -u scripts/probe_INT65b_q4decline.py 2>&1 | tee scripts/_results/improve_INT65b_run.log
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
OUT_JSON = os.path.join(PROJECT_DIR, "data", "cache", "probe_INT65b_q4decline_results.json")
os.makedirs(os.path.join(PROJECT_DIR, "data", "cache"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_DIR, "scripts", "_results"), exist_ok=True)

# Q4-decline feature columns (leak-free priors)
Q4_FEATS = [
    "q4_min_share_l",     # prior mean (Q4 min / total min) — low = benched late
    "q4_permin_ratio_l",  # prior mean (Q4 pts/min) / (Q1-3 pts/min) — efficiency fade
    "q4_pm_l",            # prior mean Q4 plus_minus
    "q4_pts_share_l",     # prior mean (Q4 pts / total pts)
    "n_prior_games",      # support / shrinkage signal
]

# Base endQ3 snapshot features (same spirit as M9 residual head)
BASE_FEATS = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m", "cur_stl", "cur_blk", "cur_tov",
    "cur_pf", "min_through_q3", "score_margin_abs", "is_leading",
]
FEATURE_COLS = BASE_FEATS + Q4_FEATS


def build_game_date_map(rest_travel: pd.DataFrame) -> Dict[str, str]:
    """game_id -> ISO date string, from rest_travel parquet."""
    gd: Dict[str, str] = {}
    gcol = "game_id" if "game_id" in rest_travel.columns else None
    dcol = None
    for c in rest_travel.columns:
        if c.lower() in ("game_date", "date"):
            dcol = c
            break
    if gcol is None or dcol is None:
        return gd
    for _, r in rest_travel[[gcol, dcol]].dropna().iterrows():
        gd[str(r[gcol])] = str(r[dcol])[:10]
    return gd


def build_q4_decline_lookup(
    qs: pd.DataFrame,
    game_date_map: Dict[str, str],
) -> Dict[Tuple[int, str], dict]:
    """Leak-free per-(player_id, game_id) Q4-decline priors.

    For each player, order games by date; for each game use the EXPANDING mean
    of PRIOR games only (shift(1)) over per-game Q4-decline metrics. Players with
    no prior games get the league-mean default.
    """
    qs = qs.copy()
    qs["period"] = pd.to_numeric(qs["period"], errors="coerce")
    qs = qs[qs["period"].notna()]
    qs["period"] = qs["period"].astype(int)

    # Per (game, player): Q4 (period==4) vs early (periods 1-3) aggregates
    early = qs[qs["period"].isin([1, 2, 3])].groupby(["game_id", "player_id"]).agg(
        early_min=("min", "sum"), early_pts=("pts", "sum")
    )
    q4 = qs[qs["period"] == 4].groupby(["game_id", "player_id"]).agg(
        q4_min=("min", "sum"), q4_pts=("pts", "sum"), q4_pm=("plus_minus", "sum")
    )
    pg = early.join(q4, how="outer").reset_index().fillna(0.0)

    pg["total_min"] = pg["early_min"] + pg["q4_min"]
    pg["total_pts"] = pg["early_pts"] + pg["q4_pts"]
    # per-game raw metrics (guard divide-by-zero)
    pg["m_min_share"] = np.where(pg["total_min"] > 0, pg["q4_min"] / pg["total_min"], np.nan)
    pg["m_pts_share"] = np.where(pg["total_pts"] > 0, pg["q4_pts"] / pg["total_pts"], np.nan)
    early_permin = np.where(pg["early_min"] > 0, pg["early_pts"] / pg["early_min"], np.nan)
    q4_permin = np.where(pg["q4_min"] > 0, pg["q4_pts"] / pg["q4_min"], np.nan)
    pg["m_permin_ratio"] = np.where(
        (early_permin > 0) & np.isfinite(q4_permin), q4_permin / early_permin, np.nan
    )
    pg["m_pm"] = pg["q4_pm"]

    pg["game_date"] = pg["game_id"].map(game_date_map)
    pg = pg[pg["game_date"].notna()].copy()
    pg = pg.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)

    # League-mean defaults (computed over all games — only used as a neutral prior
    # for players with no history; not a per-row leak since it's a global constant)
    defaults = {
        "q4_min_share_l": float(np.nanmean(pg["m_min_share"])),
        "q4_permin_ratio_l": float(np.nanmean(pg["m_permin_ratio"])),
        "q4_pm_l": float(np.nanmean(pg["m_pm"])),
        "q4_pts_share_l": float(np.nanmean(pg["m_pts_share"])),
    }

    lookup: Dict[Tuple[int, str], dict] = {}
    for pid, grp in pg.groupby("player_id"):
        grp = grp.sort_values(["game_date", "game_id"])
        # expanding mean of PRIOR games (shift 1 => excludes current game)
        for col, feat in (
            ("m_min_share", "q4_min_share_l"),
            ("m_permin_ratio", "q4_permin_ratio_l"),
            ("m_pm", "q4_pm_l"),
            ("m_pts_share", "q4_pts_share_l"),
        ):
            grp[feat] = grp[col].shift(1).expanding(min_periods=1).mean()
        grp["n_prior_games"] = np.arange(len(grp))  # 0 for first game
        for _, r in grp.iterrows():
            feats = {}
            for feat in ("q4_min_share_l", "q4_permin_ratio_l", "q4_pm_l", "q4_pts_share_l"):
                v = r[feat]
                feats[feat] = float(v) if pd.notna(v) else defaults[feat]
            feats["n_prior_games"] = float(r["n_prior_games"])
            lookup[(int(pid), str(r["game_id"]))] = feats
    return lookup, defaults


def build_all_datasets(
    qs: pd.DataFrame,
    q4_lookup: Dict[Tuple[int, str], dict],
    defaults: dict,
    game_date_map: Dict[str, str],
    baseline_fn,
) -> Dict[str, pd.DataFrame]:
    """Single game-iteration pass building per-stat residual datasets for ALL stats.

    7x faster than calling a per-stat builder (which rebuilds every snapshot 7
    times). Snapshot/actuals/base_projs are computed once per game; each player
    contributes one row per stat that has both an actual and a projection.
    """
    import retro_inplay_mae as v1  # noqa: E402

    games = sorted(qs["game_id"].unique().tolist())
    stat_rows: Dict[str, list] = {s: [] for s in STATS}
    n_proc = 0
    for gid in games:
        gdate = game_date_map.get(gid)
        if gdate is None:
            continue
        snap = v1.build_snapshot(gid, "endQ3", qs)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qs)
        try:
            base_projs = baseline_fn(snap)
        except Exception:
            continue
        n_proc += 1

        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))
        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue
            team = str(player.get("team", ""))
            q4f = q4_lookup.get((pid, gid))
            if q4f is None:
                q4f = dict(defaults); q4f["n_prior_games"] = 0.0
            base_row = {
                "game_id": gid, "player_id": pid, "team": team, "game_date": gdate,
                "cur_pts": float(player.get("pts", 0)), "cur_reb": float(player.get("reb", 0)),
                "cur_ast": float(player.get("ast", 0)), "cur_fg3m": float(player.get("fg3m", 0)),
                "cur_stl": float(player.get("stl", 0)), "cur_blk": float(player.get("blk", 0)),
                "cur_tov": float(player.get("tov", 0)), "cur_pf": float(player.get("pf", 0)),
                "min_through_q3": float(player.get("min", 0)),
                "score_margin_abs": float(margin),
                "is_leading": float(
                    (team == home_team and home_pts > away_pts) or
                    (team == away_team and away_pts > home_pts)
                ),
            }
            base_row.update(q4f)
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = base_projs.get((pid, stat))
                if actual is None or proj is None:
                    continue
                row = dict(base_row)
                row["proj_base"] = float(proj)
                row["residual"] = float(actual - proj)
                stat_rows[stat].append(row)
    print(f"  build_all_datasets: processed {n_proc} games")
    return {s: pd.DataFrame(r) for s, r in stat_rows.items()}


def walk_forward_cv(df: pd.DataFrame, stat: str, n_folds: int = 4):
    """Expanding-window WF; trains LGB residual head on FEATURE_COLS vs residual."""
    import lightgbm as lgb
    df = df.sort_values(["game_date", "game_id", "player_id"]).reset_index(drop=True)
    games_ordered = df["game_id"].unique().tolist()
    n_games = len(games_ordered)
    if n_games < n_folds * 2:
        return [], float("nan"), float("nan")
    game_to_fold = {}
    fold_size = n_games // n_folds
    for fi in range(n_folds):
        lo = fi * fold_size
        hi = n_games if fi == n_folds - 1 else (fi + 1) * fold_size
        for g in games_ordered[lo:hi]:
            game_to_fold[g] = fi
    df["fold"] = df["game_id"].map(game_to_fold)
    all_base, all_treat, folds_out = [], [], []
    for fi in range(n_folds):
        train_df = df[df["fold"] < fi]
        val_df = df[df["fold"] == fi]
        if len(train_df) < 50 or len(val_df) < 10:
            continue
        X_train = train_df[FEATURE_COLS].values
        y_train = train_df["residual"].values
        X_val = val_df[FEATURE_COLS].values
        y_val = val_df["residual"].values
        try:
            model = lgb.LGBMRegressor(
                n_estimators=200, learning_rate=0.05, num_leaves=31,
                subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
                min_child_samples=20, random_state=42, n_jobs=2, verbose=-1,
            )
            model.fit(X_train, y_train)
            preds = model.predict(X_val)
        except Exception as exc:
            print(f"  ERROR [{stat}] fold {fi+1}: {exc}")
            continue
        proj_base = val_df["proj_base"].values
        actual = proj_base + y_val
        base_errs = np.abs(proj_base - actual)
        treat_proj = np.clip(proj_base + preds, 0.0, None)
        treat_errs = np.abs(treat_proj - actual)
        bm, tm = float(np.mean(base_errs)), float(np.mean(treat_errs))
        all_base.extend(base_errs.tolist()); all_treat.extend(treat_errs.tolist())
        folds_out.append({"fold": fi + 1, "n_train": int(len(train_df)), "n_val": int(len(val_df)),
                          "baseline_mae": round(bm, 5), "treat_mae": round(tm, 5),
                          "delta": round(tm - bm, 5)})
        print(f"  [{stat}] fold {fi+1}: train={len(train_df)}, val={len(val_df)}, "
              f"base={bm:.4f}, treat={tm:.4f}, delta={tm-bm:+.4f}")
    if not all_base:
        return folds_out, float("nan"), float("nan")
    return folds_out, float(np.mean(all_base)), float(np.mean(all_treat))


def main():
    t0 = time.time()
    print("=" * 70)
    print("probe_INT65b_q4decline — INT-65 rebuilt on REAL per-quarter data")
    print("=" * 70)

    print("\n[1/5] Loading rest_travel + player_quarter_stats ...")
    rt = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "rest_travel.parquet"))
    qs = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet"))
    print(f"  rest_travel: {rt.shape}, player_quarter_stats: {qs.shape}")

    print("[2/5] Building game_date_map + leak-free Q4-decline lookup ...")
    game_date_map = build_game_date_map(rt)
    q4_lookup, defaults = build_q4_decline_lookup(qs, game_date_map)
    print(f"  game_date_map: {len(game_date_map)} games")
    print(f"  q4_lookup: {len(q4_lookup)} (player, game) entries")
    print(f"  league defaults: {json.dumps({k: round(v,4) for k,v in defaults.items()})}")

    print("[3/5] Loading baseline (live_engine.project_from_snapshot) ...")
    from src.prediction.live_engine import project_from_snapshot

    def baseline_fn(snap):
        out = {}
        for r in project_from_snapshot(snap):
            try:
                pid = int(r.get("player_id"))
            except (TypeError, ValueError):
                continue
            out[(pid, r["stat"])] = float(r["projected_final"])
        return out

    print("[4/5] Building all-stat datasets in one pass ...")
    all_ds = build_all_datasets(qs, q4_lookup, defaults, game_date_map, baseline_fn)

    print("[5/5] Per-stat walk-forward CV ...\n")
    per_stat = {}
    for stat in STATS:
        print(f"--- {stat.upper()} ---")
        df = all_ds[stat]
        print(f"  Dataset: {len(df)} rows, {df['game_id'].nunique() if len(df) else 0} games")
        if len(df) < 100:
            per_stat[stat] = {"skip": True, "overall_delta": None}
            print("  WARN: too few rows, skip\n")
            continue
        folds, ob, ot = walk_forward_cv(df, stat)
        if folds:
            od = ot - ob
            npos = sum(1 for f in folds if f["delta"] <= 0)
            print(f"  [{stat}] WF overall: base={ob:.4f} treat={ot:.4f} delta={od:+.4f} "
                  f"folds_pos={npos}/{len(folds)}\n")
        else:
            od, npos = float("nan"), 0
            print("  no folds\n")
        per_stat[stat] = {
            "n_rows": int(len(df)), "n_games": int(df["game_id"].nunique()),
            "folds": folds, "n_folds_positive": npos,
            "overall_base_mae": round(ob, 5) if not np.isnan(ob) else None,
            "overall_treat_mae": round(ot, 5) if not np.isnan(ot) else None,
            "overall_delta": round(od, 5) if not np.isnan(od) else None,
        }

    print("=" * 70)
    print("SHIP GATE")
    print("=" * 70)
    improving, full_wf, deltas = [], [], []
    for stat in STATS:
        r = per_stat.get(stat, {})
        if r.get("skip") or r.get("overall_delta") is None:
            continue
        deltas.append(r["overall_delta"])
        if r.get("n_folds_positive", 0) == 4:
            full_wf.append(stat)
        if r["overall_delta"] <= -0.005:
            improving.append(stat)
    mean_delta = float(np.mean(deltas)) if deltas else float("nan")
    ship = len(full_wf) >= 4 and mean_delta <= -0.005 and len(improving) >= 4
    print(f"  stats improving (delta<=-0.005): {improving}")
    print(f"  stats WF 4/4 positive: {full_wf}")
    print(f"  mean pooled delta across stats: {mean_delta:+.5f}")
    print(f"  VERDICT: {'SHIP' if ship else 'REJECT/DEFER'}")

    out = {"per_stat": per_stat, "mean_delta": mean_delta,
           "stats_improving": improving, "stats_wf_4_4": full_wf,
           "ship": bool(ship), "elapsed_sec": round(time.time() - t0, 1)}
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {OUT_JSON}  ({out['elapsed_sec']}s)")


if __name__ == "__main__":
    main()
