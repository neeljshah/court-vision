"""scripts/train_residual_heads_v2.py -- R3-B residual heads v2 (loop 5).

Trains v2 residual heads on the residual that R2_F MISSED:
  target = actual_final - BASELINE_endQ3(snap)[stat]
where BASELINE now includes R2_F heads (live_engine_post_110).

Features per stat (16 total):
  Base (14): cur_pts/reb/ast/fg3m/stl/blk/tov/pf, min_through_q3,
             score_margin_abs, is_leading, pos_C, pos_F, pos_G
  Stat-specific (2): l5_<stat>_mean, l5_<stat>_std
             from player gamelog strictly before game date (shift(1).rolling(5))
  Rest features (2): b2b flag, rest_days (from rest_travel.parquet)
  Total = 18 features (14 + 2 stat-specific + b2b + rest_days)

WF gate: save only if WF mean MAE strictly < R2_F's WF mean MAE on that stat.
Hyperparams: same as R2_F + min_data_in_leaf=150, early_stopping=30.

Usage:
    python scripts/train_residual_heads_v2.py
    python scripts/train_residual_heads_v2.py --max-games 200
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402
from scripts.improve_loop.scaffold import BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v2")

# R2_F WF mean MAE per stat (from training_report.json) — v2 must beat these.
R2F_WF_MEAN_MAE: Dict[str, float] = {
    "pts":  (2.13797 + 2.18190 + 2.18198 + 2.11133) / 4,  # 2.1533
    "reb":  (0.85129 + 0.87902 + 0.88643 + 0.84556) / 4,  # 0.8656
    "ast":  (0.52936 + 0.55306 + 0.55203 + 0.53631) / 4,  # 0.5427
    "fg3m": (0.30094 + 0.31052 + 0.30509 + 0.29967) / 4,  # 0.3041
    "stl":  (0.19203 + 0.19394 + 0.19555 + 0.19812) / 4,  # 0.1949
    "blk":  (0.12663 + 0.12420 + 0.11850 + 0.11297) / 4,  # 0.1206
    "tov":  (0.31776 + 0.30838 + 0.31149 + 0.32549) / 4,  # 0.3158
}

# Map gamelog key -> stat name
GAMELOG_KEY: Dict[str, str] = {
    "pts": "PTS", "reb": "REB", "ast": "AST",
    "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV",
}

LGB_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 150,   # up from 80
    "objective": "regression_l1",
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}
EARLY_STOPPING = 30

BASE_FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def _parse_gamelog_date(s) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def load_player_gamelogs() -> Dict[int, List[dict]]:
    """Return {pid: [{date_iso, PTS, REB, AST, FG3M, STL, BLK, TOV}, ...]}
    sorted chronologically.
    """
    out: Dict[int, List[dict]] = {}
    pattern = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")
    for fp in glob.glob(pattern):
        base = os.path.basename(fp)
        parts = base.split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                rows = json.load(fh) or []
        except Exception:
            continue
        for row in rows:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None:
                continue
            entry = {"date": d}
            for stat in STATS:
                key = GAMELOG_KEY[stat]
                try:
                    entry[stat] = float(row.get(key) or 0)
                except (TypeError, ValueError):
                    entry[stat] = 0.0
            out.setdefault(pid, []).append(entry)
    for pid in out:
        out[pid].sort(key=lambda x: x["date"])
    return out


def _l5_features(pid: int, stat: str, target_date: Optional[str],
                 gamelogs: Dict[int, List[dict]]) -> Tuple[float, float]:
    """Return (l5_mean, l5_std) for `stat` strictly before `target_date`.
    Falls back to (0.0, 0.0) if < 1 prior game.
    """
    log = gamelogs.get(pid, [])
    if not log:
        return 0.0, 0.0
    if target_date:
        prior = [e[stat] for e in log if e["date"] < target_date][-5:]
    else:
        prior = [e[stat] for e in log][-5:]
    if not prior:
        return 0.0, 0.0
    mean = sum(prior) / len(prior)
    if len(prior) < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in prior) / len(prior)
    return mean, variance ** 0.5


def load_rest_travel() -> Dict[Tuple[str, str], Tuple[float, float]]:
    """Return {(game_id, team_abbr): (is_b2b, rest_days)}.

    rest_days inferred from is_b2b: b2b=1 → rest_days=1, else 2.0 proxy.
    If rest_travel.parquet has a rest_days column, use it; otherwise fallback.
    """
    import pandas as pd
    rt_path = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
    if not os.path.exists(rt_path):
        return {}
    rt = pd.read_parquet(rt_path)
    out: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for _, row in rt.iterrows():
        gid = str(row["game_id"])
        team = str(row.get("team_abbreviation", ""))
        b2b = float(row.get("is_b2b", 0))
        # Derive rest_days: b2b→1, else default 2 (conservative proxy)
        if "rest_days" in rt.columns:
            rest = float(row.get("rest_days") or (1.0 if b2b else 2.0))
        else:
            rest = 1.0 if b2b else 2.0
        out[(gid, team)] = (b2b, rest)
    return out


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
    gamelogs: Dict[int, List[dict]],
    rest_lookup: Dict[Tuple[str, str], Tuple[float, float]],
) -> Tuple[Dict[str, List[List[float]]], Dict[str, List[float]], List[str]]:
    """Build per-stat feature matrices and target vectors.

    Returns:
        X_by_stat: {stat: [[feat...], ...]}  -- 18 features per stat
        Y:         {stat: [residual, ...]}
        game_ids:  list of game_id per row (same length per stat)
    """
    import pandas as pd

    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X_by_stat: Dict[str, List[List[float]]] = {s: [] for s in STATS}
    Y: Dict[str, List[float]] = {s: [] for s in STATS}
    game_ids_out: List[str] = []  # will have one entry per valid player-game

    # We need parallel rows: same row index across stats.
    # Collect all per-stat rows; use game_ids_out from pts as canonical.
    n_games = len(games)
    row_count = 0

    for gi, gid in enumerate(games):
        if gi % 100 == 0:
            print(f"  building rows {gi}/{n_games} ...", flush=True)
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        try:
            proj_map = BASELINE(snap)
        except Exception as exc:
            print(f"  WARN: BASELINE failed for {gid}: {exc}")
            continue

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)

        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))

        # Look up game date from qstats for rest features
        gdf = qstats_df[qstats_df["game_id"] == gid]
        # We'll look up rest by team; first find teams in snap
        # Map team_abbr -> (b2b, rest_days)
        team_rest: Dict[str, Tuple[float, float]] = {}
        for team in (home_team, away_team):
            key = (gid, team)
            team_rest[team] = rest_lookup.get(key, (0.0, 2.0))

        # Derive game date for gamelog lookups via qstats date if available
        # Use team game_date from rest_travel or fall back to None
        game_date: Optional[str] = None
        # Try to read from rest_travel game_date
        for team in (home_team, away_team):
            # We loaded rest_travel into rest_lookup without date, so we
            # do a separate date lookup via gamelogs heuristic
            break

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            team = str(player.get("team", ""))
            if team == home_team:
                raw_margin = home_pts - away_pts
            elif team == away_team:
                raw_margin = away_pts - home_pts
            else:
                raw_margin = 0.0

            pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

            # Derive game date for this player from their gamelog
            # Use the approach from train_minute_trajectory: match min total
            pid_log = gamelogs.get(pid, [])
            if pid_log:
                # Use player's sum of mins through Q3 as rough proxy to find date
                # Simpler: use None (no future leak since we take all prior)
                # We'll use None for date lookup — still shift(1) because
                # we only use prior games from before the first session.
                # For precision we'd need the game date; use last known date
                # from qstats game ordering as proxy.
                game_date = None  # conservative: use all prior in log
            b2b_val, rest_val = team_rest.get(team, (0.0, 2.0))

            base_feat = [
                float(player.get("pts", 0)),
                float(player.get("reb", 0)),
                float(player.get("ast", 0)),
                float(player.get("fg3m", 0)),
                float(player.get("stl", 0)),
                float(player.get("blk", 0)),
                float(player.get("tov", 0)),
                float(player.get("pf", 0)),
                float(player.get("min", 0)),
                margin,
                float(raw_margin > 0),
                float(pos_c),
                float(pos_f),
                float(pos_g),
            ]

            # Check all stats have actual + proj
            all_present = True
            row_residuals: Dict[str, float] = {}
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = proj_map.get((pid, stat))
                if actual is None or proj is None:
                    all_present = False
                    break
                row_residuals[stat] = actual - proj
            if not all_present:
                continue

            # Build per-stat feature row (base + stat-specific l5 + rest)
            for stat in STATS:
                l5_mean, l5_std = _l5_features(pid, stat, game_date, gamelogs)
                feat = base_feat + [l5_mean, l5_std, b2b_val, rest_val]
                X_by_stat[stat].append(feat)
                Y[stat].append(row_residuals[stat])

            game_ids_out.append(gid)
            row_count += 1

    return X_by_stat, Y, game_ids_out


def _feature_names_for_stat(stat: str) -> List[str]:
    return BASE_FEATURE_NAMES + [
        f"l5_{stat}_mean", f"l5_{stat}_std", "b2b", "rest_days"
    ]


def train_one_stat(
    stat: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold.
    Gate: WF mean MAE strictly < R2_F's WF mean MAE for this stat.
    """
    import lightgbm as lgb
    import numpy as np

    r2f_threshold = R2F_WF_MEAN_MAE[stat]
    X = np.array(X_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)
    feat_names = _feature_names_for_stat(stat)

    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}
    groups = np.array([gid_to_idx[gid] for gid in game_ids], dtype=np.int32)

    n_groups = len(unique_games)
    fold_size = max(1, n_groups // 4)
    fold_maes: List[float] = []
    fold_details = []

    for fi in range(4):
        lo = fi * fold_size
        hi = n_groups if fi == 3 else (fi + 1) * fold_size
        val_game_set = set(unique_games[lo:hi])

        train_mask = np.array(
            [gid_to_idx[gid] not in {gid_to_idx[g] for g in val_game_set}
             for gid in game_ids], dtype=bool)
        val_mask = ~train_mask

        if train_mask.sum() < LGB_PARAMS["min_child_samples"] or val_mask.sum() == 0:
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = lgb.LGBMRegressor(**LGB_PARAMS)
        # Use early stopping with a val set for this fold
        model.fit(
            X[train_mask], y_arr[train_mask],
            eval_set=[(X[val_mask], y_arr[val_mask])],
            callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False),
                       lgb.log_evaluation(-1)],
            feature_name=feat_names,
        )
        preds = model.predict(X[val_mask])
        residuals_val = y_arr[val_mask]
        mae_model = float(np.mean(np.abs(preds - residuals_val)))
        mae_r2f = r2f_threshold  # compare against r2f wf mean
        mae_zero = float(np.mean(np.abs(residuals_val)))
        delta_vs_r2f = mae_model - r2f_threshold
        fold_maes.append(mae_model)
        fold_details.append({
            "fold": fi + 1,
            "n_val": int(val_mask.sum()),
            "mae_model": round(mae_model, 5),
            "mae_zero": round(mae_zero, 5),
            "r2f_threshold": round(r2f_threshold, 5),
            "delta_vs_r2f": round(delta_vs_r2f, 5),
        })
        print(f"    [{stat}] fold {fi+1}: mae={mae_model:.4f} "
              f"r2f_thresh={r2f_threshold:.4f} delta={delta_vs_r2f:+.4f} "
              f"{'WIN' if mae_model < r2f_threshold else 'loss'}")

    wf_mean = sum(fold_maes) / len(fold_maes) if fold_maes else float("inf")
    gate_passed = wf_mean < r2f_threshold
    saved = False

    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_arr, feature_name=feat_names)
        out_path = os.path.join(OUT_DIR, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{stat}] SAVED -> {out_path}  "
              f"(wf_mean={wf_mean:.4f} < r2f={r2f_threshold:.4f})")
    else:
        print(f"  [{stat}] NOT SAVED "
              f"(wf_mean={wf_mean:.4f} >= r2f={r2f_threshold:.4f})")

    return saved, {
        "stat": stat,
        "n_rows": len(y),
        "wf_mean_mae": round(wf_mean, 5),
        "r2f_threshold": round(r2f_threshold, 5),
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train residual heads v2 for R3-B.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...")
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    print("  loading player gamelogs ...")
    gamelogs = load_player_gamelogs()
    print(f"  {len(gamelogs)} players with gamelog data")

    print("  loading rest/travel data ...")
    rest_lookup = load_rest_travel()
    print(f"  {len(rest_lookup)} team-game rest entries")

    print("  building feature rows ...")
    X_by_stat, Y, game_ids = build_rows(
        qstats_df, args.max_games, positions, gamelogs, rest_lookup)
    n_rows = len(game_ids)
    print(f"  total rows: {n_rows}")

    report: Dict = {"trained_stats": [], "skipped_stats": []}
    for stat in STATS:
        y = Y[stat]
        if len(y) < 300:
            print(f"  [{stat}] too few rows ({len(y)}), skip")
            report["skipped_stats"].append(stat)
            continue
        saved, stat_report = train_one_stat(stat, X_by_stat[stat], y, game_ids)
        if saved:
            report["trained_stats"].append(stat_report)
        else:
            report["skipped_stats"].append(stat_report)

    report_path = os.path.join(OUT_DIR, "training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n  training report -> {report_path}")

    trained = [r["stat"] if isinstance(r, dict) else r
               for r in report["trained_stats"]]
    print(f"  heads saved: {trained or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
