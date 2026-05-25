"""scripts/train_residual_heads_form_only.py -- R4-D residual heads (form-only).

For each of 7 stats, trains a LightGBM head on the RESIDUAL between the
live_engine baseline projection (endQ3) and the actual full-game total.

Features (~40, NO in-game state):
  l5_<stat>_mean, l5_<stat>_std  (14 features across 7 stats)
  l20_<stat>_mean, l20_<stat>_std (14 features)
  l5_min_mean, l20_min_mean       (2 features)
  b2b, rest_days, is_home         (3 features, from rest_travel.parquet)
  season_<stat>_mean              (7 features, walk-forward shifted expanding mean)
  Total: 40 features

Training set: endQ3 snapshots x 1508 games. Gamelog scan per (pid, game_date).
Gate: WF 4-fold GroupKFold by game_id. Save .lgb only if mean MAE < zero-pred
on >= 3/4 folds.

Usage:
    python scripts/train_residual_heads_form_only.py
    python scripts/train_residual_heads_form_only.py --max-games 200
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta
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
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_form_only")

LGB_PARAMS = {
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "objective": "regression_l1",
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

FEATURE_NAMES = (
    [f"l5_{s}_mean" for s in STATS]
    + [f"l5_{s}_std" for s in STATS]
    + [f"l20_{s}_mean" for s in STATS]
    + [f"l20_{s}_std" for s in STATS]
    + ["l5_min_mean", "l20_min_mean"]
    + ["b2b", "rest_days", "is_home"]
    + [f"season_{s}_mean" for s in STATS]
)


# ---------------------------------------------------------------------------
# Gamelog loading
# ---------------------------------------------------------------------------

def _parse_gamelog_date(s) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def load_player_gamelogs() -> Dict[int, List[Dict]]:
    """Return {pid: [{date_iso, pts, reb, ast, fg3m, stl, blk, tov, min}, ...]}
    chronologically sorted, from all gamelog_<pid>_*.json files.
    """
    out: Dict[int, List[Dict]] = {}
    gamelog_pattern = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")
    for fp in glob.glob(gamelog_pattern):
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
                games = json.load(fh) or []
        except Exception:
            continue
        for row in games:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None:
                continue
            try:
                m = float(row.get("MIN") or 0)
            except (TypeError, ValueError):
                m = 0.0
            if m < 1.0:
                continue
            entry = {
                "date": d,
                "min": m,
            }
            for stat in STATS:
                try:
                    entry[stat] = float(row.get(stat.upper()) or 0)
                except (TypeError, ValueError):
                    entry[stat] = 0.0
            out.setdefault(pid, []).append(entry)
    for pid in out:
        out[pid].sort(key=lambda x: x["date"])
    return out


def _rolling_stats(
    pid: int,
    target_date: str,
    window: int,
    gamelog: Dict[int, List[Dict]],
) -> Optional[Dict[str, float]]:
    """Compute rolling mean+std over last `window` games BEFORE target_date.

    Returns dict with keys: l{window}_<stat>_mean, l{window}_<stat>_std,
    l{window}_min_mean. Returns None if no prior games.
    """
    log = gamelog.get(pid, [])
    prior = [e for e in log if e["date"] < target_date]
    if not prior:
        return None
    window_entries = prior[-window:]

    result: Dict[str, float] = {}
    for stat in STATS:
        vals = [e[stat] for e in window_entries]
        n = len(vals)
        mean = sum(vals) / n
        if n > 1:
            var = sum((v - mean) ** 2 for v in vals) / (n - 1)
            std = var ** 0.5
        else:
            std = 0.0
        result[f"l{window}_{stat}_mean"] = mean
        result[f"l{window}_{stat}_std"] = std

    min_vals = [e["min"] for e in window_entries]
    result[f"l{window}_min_mean"] = sum(min_vals) / len(min_vals)
    return result


def _season_means(
    pid: int,
    target_date: str,
    gamelog: Dict[int, List[Dict]],
) -> Optional[Dict[str, float]]:
    """Walk-forward expanding mean of each stat for the current season (same
    calendar year), using only games strictly BEFORE target_date.
    """
    log = gamelog.get(pid, [])
    year = target_date[:4]
    prior = [e for e in log if e["date"] < target_date and e["date"][:4] == year]
    if not prior:
        return None
    result: Dict[str, float] = {}
    for stat in STATS:
        vals = [e[stat] for e in prior]
        result[f"season_{stat}_mean"] = sum(vals) / len(vals)
    return result


# ---------------------------------------------------------------------------
# Rest/travel loading
# ---------------------------------------------------------------------------

def load_rest_travel() -> Dict[Tuple[str, str], Dict]:
    """Return {(game_id, team_abbr): {b2b, rest_days}} from rest_travel.parquet."""
    import pandas as pd
    path = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
    if not os.path.exists(path):
        print("  WARN: rest_travel.parquet missing — b2b/rest_days will be 0")
        return {}
    df = pd.read_parquet(path)
    out: Dict[Tuple[str, str], Dict] = {}
    for _, r in df.iterrows():
        gid = str(r["game_id"])
        team = str(r["team_abbreviation"])
        # rest_days derived from is_b2b column; approximate via is_b2b flag
        b2b = float(r.get("is_b2b") or 0)
        # rest_days: not directly stored, approximate from is_b2b
        rest_days = 1.0 if b2b else 2.0
        out[(gid, team)] = {"b2b": b2b, "rest_days": rest_days}
    return out


# ---------------------------------------------------------------------------
# Game-date lookup (same pattern as train_minute_trajectory.py)
# ---------------------------------------------------------------------------

def build_game_date_index(
    qstats_df,
    gamelog: Dict[int, List[Dict]],
) -> Dict[str, str]:
    """Map game_id -> ISO date by matching high-MIN player's gamelog."""
    games = sorted(qstats_df["game_id"].unique().tolist())
    out: Dict[str, str] = {}
    for gid in games:
        g = qstats_df[qstats_df["game_id"] == gid]
        if g.empty:
            continue
        totals = g.groupby("player_id")["min"].sum().sort_values(ascending=False)
        found = False
        for pid_raw, min_total in totals.head(5).items():
            pid = int(pid_raw)
            log = gamelog.get(pid, [])
            for entry in log:
                if abs(entry["min"] - float(min_total)) <= 1.0:
                    out[gid] = entry["date"]
                    found = True
                    break
            if found:
                break
    return out


# ---------------------------------------------------------------------------
# Feature row builder
# ---------------------------------------------------------------------------

def build_form_feature_row(
    pid: int,
    game_date: str,
    game_id: str,
    player_team: str,
    home_team: str,
    gamelog: Dict[int, List[Dict]],
    rest_index: Dict[Tuple[str, str], Dict],
) -> Optional[Tuple[List[float], bool]]:
    """Build a ~40-feature form-only row.

    Returns (feature_list, valid) where valid=False if l5 stats are NaN
    (cold-start — caller should drop the row).
    """
    l5 = _rolling_stats(pid, game_date, 5, gamelog)
    l20 = _rolling_stats(pid, game_date, 20, gamelog)
    season = _season_means(pid, game_date, gamelog)

    # Drop rows where l5 is NaN (cold-start)
    if l5 is None or l5.get("l5_pts_mean") is None:
        return None, False

    row: List[float] = []
    # l5 mean + std for 7 stats
    for stat in STATS:
        row.append(l5.get(f"l5_{stat}_mean", 0.0))
    for stat in STATS:
        row.append(l5.get(f"l5_{stat}_std", 0.0))
    # l20 mean + std for 7 stats
    for stat in STATS:
        row.append(l20.get(f"l20_{stat}_mean", 0.0) if l20 else 0.0)
    for stat in STATS:
        row.append(l20.get(f"l20_{stat}_std", 0.0) if l20 else 0.0)
    # l5_min_mean, l20_min_mean
    row.append(l5.get("l5_min_mean", 0.0))
    row.append(l20.get("l20_min_mean", 0.0) if l20 else 0.0)
    # b2b, rest_days, is_home
    rest = rest_index.get((game_id, player_team), {})
    row.append(rest.get("b2b", 0.0))
    row.append(rest.get("rest_days", 2.0))
    row.append(float(player_team == home_team))
    # season_<stat>_mean
    for stat in STATS:
        row.append(season.get(f"season_{stat}_mean", 0.0) if season else 0.0)

    return row, True


# ---------------------------------------------------------------------------
# Corpus builder
# ---------------------------------------------------------------------------

def build_rows(
    qstats_df,
    gamelog: Dict[int, List[Dict]],
    rest_index: Dict[Tuple[str, str], Dict],
    game_date_index: Dict[str, str],
    max_games: Optional[int],
) -> Tuple[List[List[float]], Dict[str, List[float]], List[str]]:
    """Walk endQ3 snapshots and build form-only feature rows + residuals."""
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X: List[List[float]] = []
    Y: Dict[str, List[float]] = {s: [] for s in STATS}
    game_ids_out: List[str] = []

    n_games = len(games)
    n_skip_date = 0
    n_skip_feat = 0
    n_skip_baseline = 0

    for gi, gid in enumerate(games):
        if gi % 100 == 0:
            print(f"  building rows {gi}/{n_games} ...", flush=True)

        game_date = game_date_index.get(gid)
        if game_date is None:
            n_skip_date += 1
            continue

        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        try:
            proj_map = BASELINE(snap)
        except Exception as exc:
            print(f"  WARN: BASELINE failed for {gid}: {exc}")
            n_skip_baseline += 1
            continue

        home_team = str(snap.get("home_team", ""))

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            player_team = str(player.get("team", ""))

            feat, valid = build_form_feature_row(
                pid=pid,
                game_date=game_date,
                game_id=gid,
                player_team=player_team,
                home_team=home_team,
                gamelog=gamelog,
                rest_index=rest_index,
            )
            if not valid:
                n_skip_feat += 1
                continue

            # Collect residuals
            all_stats_present = True
            row_residuals: Dict[str, float] = {}
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = proj_map.get((pid, stat))
                if actual is None or proj is None:
                    all_stats_present = False
                    break
                row_residuals[stat] = actual - proj

            if not all_stats_present:
                continue

            X.append(feat)
            for stat in STATS:
                Y[stat].append(row_residuals[stat])
            game_ids_out.append(gid)

    print(f"  skipped: date_missing={n_skip_date} cold_start={n_skip_feat} "
          f"baseline_fail={n_skip_baseline}")
    return X, Y, game_ids_out


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_one_stat(
    stat: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold, WF gate >= 3/4 folds beat zero-pred."""
    import lightgbm as lgb
    import numpy as np

    X = np.array(X_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)

    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}
    groups = np.array([gid_to_idx[gid] for gid in game_ids], dtype=np.int32)

    n_groups = len(unique_games)
    fold_size = max(1, n_groups // 4)
    fold_wins = 0
    fold_details = []

    for fi in range(4):
        lo = fi * fold_size
        hi = n_groups if fi == 3 else (fi + 1) * fold_size
        val_game_set = set(unique_games[lo:hi])

        train_mask = np.array(
            [gid not in val_game_set for gid in game_ids], dtype=bool
        )
        val_mask = ~train_mask

        if train_mask.sum() < LGB_PARAMS["min_child_samples"] or val_mask.sum() == 0:
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(X[train_mask], y_arr[train_mask], feature_name=FEATURE_NAMES)
        preds = model.predict(X[val_mask])
        residuals_val = y_arr[val_mask]

        mae_model = float(np.mean(np.abs(preds - residuals_val)))
        mae_zero = float(np.mean(np.abs(residuals_val)))
        delta = mae_model - mae_zero
        fold_details.append({
            "fold": fi + 1,
            "n_val": int(val_mask.sum()),
            "mae_model": round(mae_model, 5),
            "mae_zero": round(mae_zero, 5),
            "delta": round(delta, 5),
        })
        if mae_model < mae_zero:
            fold_wins += 1
        print(f"    [{stat}] fold {fi+1}: mae_model={mae_model:.4f} "
              f"zero={mae_zero:.4f} delta={delta:+.4f} "
              f"{'WIN' if mae_model < mae_zero else 'loss'}")

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
        out_path = os.path.join(OUT_DIR, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{stat}] SAVED -> {out_path}  ({fold_wins}/4 folds won)")
    else:
        print(f"  [{stat}] NOT SAVED (only {fold_wins}/4 folds beat zero-pred)")

    return saved, {
        "stat": stat,
        "n_rows": len(y),
        "fold_wins": fold_wins,
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Train form-only residual heads for R4-D angle (endQ3)."
    )
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading player gamelogs ...")
    gamelog = load_player_gamelogs()
    print(f"  {len(gamelog)} players with gamelog entries")

    print("  loading rest/travel data ...")
    rest_index = load_rest_travel()
    print(f"  {len(rest_index)} (game_id, team) rest entries")

    print("  building game-date index ...")
    game_date_index = build_game_date_index(qstats_df, gamelog)
    print(f"  {len(game_date_index)} game dates resolved")

    print("  building feature rows (gamelog scan per player, ~5-15 min) ...")
    X_rows, Y, game_ids = build_rows(
        qstats_df, gamelog, rest_index, game_date_index, args.max_games
    )
    print(f"  total rows: {len(X_rows)}")

    report = {"trained_stats": [], "skipped_stats": []}
    for stat in STATS:
        y = Y[stat]
        if len(y) < 200:
            print(f"  [{stat}] too few rows ({len(y)}), skip")
            report["skipped_stats"].append(stat)
            continue
        saved, stat_report = train_one_stat(stat, X_rows, y, game_ids)
        if saved:
            report["trained_stats"].append(stat_report)
        else:
            report["skipped_stats"].append(stat_report)

    report_path = os.path.join(OUT_DIR, "training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n  training report -> {report_path}")

    trained = [r["stat"] if isinstance(r, dict) else r for r in report["trained_stats"]]
    print(f"  heads saved: {trained or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
