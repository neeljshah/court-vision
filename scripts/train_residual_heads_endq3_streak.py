"""scripts/train_residual_heads_endq3_streak.py -- R10_M16 wire (loop 5).

Retrains the endQ3 per-stat residual heads with hot-hand / streak features
added ONLY for the 4 winning stats from probe_R10_M16_streak.py:
  fg3m, stl, blk, tov   -- per-stat ship (4/4 WF folds positive).
  pts, reb, ast         -- legacy 14-feature schema (probe REJECT for streaks).

For each stat we use the same retro_inplay_mae.build_snapshot + BASELINE
projection pipeline as train_residual_heads.py. Streak inputs (computed from
data/nba/gamelog_*.json per player, strict shift(1) on game date) are
appended only for the shipping stats. A per-stat meta JSON
(data/models/residual_heads/<stat>_meta.json) records the feature list
that the live loader (src.prediction.residual_heads) reads back to drive
the inference vector.

Gate: WF 4-fold chronological GroupKFold by game_id. Save .lgb + meta only
when fold_wins >= 3 (matches train_residual_heads.py behaviour).

Usage:
    python -u scripts/train_residual_heads_endq3_streak.py
    python -u scripts/train_residual_heads_endq3_streak.py --max-games 200
"""
from __future__ import annotations

import argparse
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
from src.prediction import streak_features as sf  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SHIP_STREAK_STATS = tuple(sorted(sf.SHIP_STREAK_STATS))  # fg3m, blk, stl, tov

OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")

LGB_PARAMS = {
    "n_estimators":      200,
    "learning_rate":     0.03,
    "num_leaves":        15,
    "min_child_samples": 80,
    "objective":         "regression_l1",
    "random_state":      42,
    "verbosity":         -1,
    "n_jobs":            -1,
}

LEGACY_FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


def feature_names_for_stat(stat: str) -> List[str]:
    """Legacy 14 features (all stats) + streak features (only shipping stats)."""
    names = list(LEGACY_FEATURE_NAMES)
    if stat in sf.SHIP_STREAK_STATS:
        names += sf.STREAK_FEATURE_NAMES_PER_STAT[stat]
    return names


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def _build_game_date_index(
    histories: Dict[int, list],
) -> Dict[Tuple[int, int, int, int], datetime]:
    """Build a (pid, int(min), int(pts), int(reb)) -> game_date lookup.

    A direct reuse of the already-loaded gamelogs avoids the
    per-game glob + read pattern in retro_inplay_mae.find_game_date,
    which dominates wall-time on the full 956-game corpus.
    """
    idx: Dict[Tuple[int, int, int, int], datetime] = {}
    for pid, rows in histories.items():
        for d, r in rows:
            key = (pid, int(round(r.get("min", 0))), int(r.get("pts", 0)), int(r.get("reb", 0)))
            idx[key] = d
    return idx


def _resolve_game_date(
    game_id: str,
    qstats_df,
    date_index: Dict[Tuple[int, int, int, int], datetime],
) -> Optional[datetime]:
    """Resolve game_date by matching full-game (pid, min, pts, reb) against the index.

    Uses qstats_df totals (Q1..Q4 summed per player) which equal the values
    stored in the player's gamelog. Tries up to 5 highest-minutes players.
    +/- 1 min tolerance on the MIN key (gamelogs round to int minutes,
    quarter sums are decimals).
    """
    g = qstats_df[qstats_df["game_id"] == game_id]
    if g.empty:
        return None
    totals = g.groupby("player_id").agg(
        {"min": "sum", "pts": "sum", "reb": "sum"}
    ).reset_index()
    totals = totals.sort_values("min", ascending=False).head(5)
    for _, row in totals.iterrows():
        try:
            pid = int(row["player_id"])
            m = float(row["min"])
            pts = int(float(row["pts"]))
            reb = int(float(row["reb"]))
        except (TypeError, ValueError):
            continue
        for dm in (0, 1, -1):
            key = (pid, int(round(m)) + dm, pts, reb)
            d = date_index.get(key)
            if d is not None:
                return d
    return None


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
    date_index: Optional[Dict[Tuple[int, int, int, int], datetime]] = None,
) -> Tuple[List[List[float]], Dict[str, List[float]], List[str], List[Optional[datetime]]]:
    """Build a 14-float base feature matrix + per-stat residual vectors.

    Streak features are NOT added to the base matrix; they're appended
    per-stat in train_one_stat() because streak names are stat-specific
    and shipping stats want 4 extra inputs.

    Returns:
        X_base:    14-float legacy feature rows.
        Y:         {stat -> [residual, ...]} parallel to X_base.
        game_ids:  game_id per row (for GroupKFold).
        target_dates: per-row datetime (game date) for streak lookup.
    """
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X_base: List[List[float]] = []
    Y: Dict[str, List[float]] = {s: [] for s in STATS}
    game_ids_out: List[str] = []
    target_dates: List[Optional[datetime]] = []
    player_ids: List[int] = []

    n_games = len(games)
    n_baseline_fail = 0
    n_snap_fail = 0
    for gi, gid in enumerate(games):
        if gi % 100 == 0:
            print(f"  building rows {gi}/{n_games} ...", flush=True)
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            n_snap_fail += 1
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        try:
            proj_map = BASELINE(snap)
        except Exception as exc:
            n_baseline_fail += 1
            if n_baseline_fail <= 3:
                print(f"  WARN: BASELINE failed for {gid}: {exc}")
            continue

        # Look up the game date once per game. Prefer the prebuilt
        # date_index (in-memory hashmap, microsecond lookups) over the
        # legacy v1.find_game_date which globs + reads gamelogs per call
        # (dominant wall-time on the full 956-game corpus).
        target_date: Optional[datetime] = None
        if date_index is not None:
            target_date = _resolve_game_date(gid, qstats_df, date_index)
        if target_date is None:
            iso = v1.find_game_date(gid, qstats_df)
            if iso:
                try:
                    target_date = datetime.strptime(iso[:10], "%Y-%m-%d")
                except ValueError:
                    target_date = None

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            team = str(player.get("team", ""))
            home_team = str(snap.get("home_team", ""))
            away_team = str(snap.get("away_team", ""))
            if team == home_team:
                raw_margin = home_pts - away_pts
            elif team == away_team:
                raw_margin = away_pts - home_pts
            else:
                raw_margin = 0.0

            pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

            feat = [
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

            X_base.append(feat)
            for stat in STATS:
                Y[stat].append(row_residuals[stat])
            game_ids_out.append(gid)
            target_dates.append(target_date)
            player_ids.append(pid)

    print(f"  build summary: snap_fail={n_snap_fail} baseline_fail={n_baseline_fail} "
          f"kept_rows={len(X_base)}", flush=True)
    return X_base, Y, game_ids_out, target_dates, player_ids


def _streak_columns_for_stat(
    stat: str,
    target_dates: List[Optional[datetime]],
    player_ids: List[int],
    histories: Dict[int, list],
) -> List[List[float]]:
    """Compute the streak feature columns for the given stat (length = N_rows).

    Returns an empty per-row list when stat doesn't ship streak features.
    """
    if stat not in sf.SHIP_STREAK_STATS:
        return [[] for _ in target_dates]
    out: List[List[float]] = []
    n_zero_history = 0
    for pid, td in zip(player_ids, target_dates):
        if td is None:
            out.append([0.0, 0.0, 0.0, 0.0])
            n_zero_history += 1
            continue
        history = histories.get(pid) or []
        if not history:
            out.append([0.0, 0.0, 0.0, 0.0])
            n_zero_history += 1
            continue
        feats = sf.compute_streak_features_for_stat(history, td, stat)
        out.append([feats[name] for name in sf.STREAK_FEATURE_NAMES_PER_STAT[stat]])
    if n_zero_history:
        print(f"    [{stat}] streak zero-fill on {n_zero_history}/{len(target_dates)} rows "
              f"(missing game_date or gamelog)", flush=True)
    return out


def train_one_stat(
    stat: str,
    X_base_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
    streak_cols: List[List[float]],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold. Save if >= 3/4 folds beat zero-pred."""
    import lightgbm as lgb
    import numpy as np

    if streak_cols and streak_cols[0]:
        X_arr = np.array(
            [base + extra for base, extra in zip(X_base_rows, streak_cols)],
            dtype=np.float32,
        )
    else:
        X_arr = np.array(X_base_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)
    feature_names = feature_names_for_stat(stat)
    assert X_arr.shape[1] == len(feature_names), (
        f"shape mismatch for {stat}: {X_arr.shape[1]} vs {len(feature_names)}"
    )

    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}
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
        model.fit(X_arr[train_mask], y_arr[train_mask], feature_name=feature_names)
        preds = model.predict(X_arr[val_mask])
        residuals_val = y_arr[val_mask]

        mae_model = float(np.mean(np.abs(preds - residuals_val)))
        mae_zero = float(np.mean(np.abs(residuals_val)))
        delta = mae_model - mae_zero
        fold_details.append({
            "fold":      fi + 1,
            "n_val":     int(val_mask.sum()),
            "mae_model": round(mae_model, 5),
            "mae_zero":  round(mae_zero, 5),
            "delta":     round(delta, 5),
        })
        if mae_model < mae_zero:
            fold_wins += 1
        marker = "WIN" if mae_model < mae_zero else "loss"
        print(f"    [{stat}] fold {fi+1}: mae_model={mae_model:.4f} "
              f"zero={mae_zero:.4f} delta={delta:+.4f} {marker}", flush=True)

    gate_passed = fold_wins >= 3
    saved = False
    mean_mae_model = float(
        np.mean([d["mae_model"] for d in fold_details if "mae_model" in d])
    ) if fold_details else 0.0
    mean_mae_zero = float(
        np.mean([d["mae_zero"] for d in fold_details if "mae_zero" in d])
    ) if fold_details else 0.0
    mean_delta = mean_mae_model - mean_mae_zero

    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X_arr, y_arr, feature_name=feature_names)
        out_path = os.path.join(OUT_DIR, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        # Per-stat meta so live_engine knows which features to assemble.
        meta = {
            "stat":         stat,
            "features":     feature_names,
            "has_streak":   stat in sf.SHIP_STREAK_STATS,
            "fold_wins":    fold_wins,
            "mean_delta":   round(mean_delta, 5),
            "folds":        fold_details,
            "lgb_params":   LGB_PARAMS,
            "trained_at":   datetime.utcnow().isoformat(),
            "n_rows":       int(len(y)),
        }
        meta_path = os.path.join(OUT_DIR, f"{stat}_meta.json")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        saved = True
        print(f"  [{stat}] SAVED -> {out_path}  ({fold_wins}/4 folds won, "
              f"mean delta {mean_delta:+.5f}, {len(feature_names)} features)",
              flush=True)
    else:
        print(f"  [{stat}] NOT SAVED (only {fold_wins}/4 folds beat zero-pred)",
              flush=True)

    return saved, {
        "stat":        stat,
        "n_rows":      len(y),
        "n_features":  len(feature_names),
        "fold_wins":   fold_wins,
        "gate_passed": gate_passed,
        "saved":       saved,
        "mean_delta":  round(mean_delta, 5),
        "folds":       fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train endQ3 residual heads with R10_M16 streaks.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("  loading quarter stats ...", flush=True)
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet", flush=True)

    print("  loading positions ...", flush=True)
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded", flush=True)

    print("  loading player gamelogs (streak histories) ...", flush=True)
    histories = sf.load_player_histories()
    print(f"  {len(histories)} player histories loaded", flush=True)

    print("  building game_date index from histories ...", flush=True)
    date_index = _build_game_date_index(histories)
    print(f"  {len(date_index)} (pid, min, pts, reb) keys indexed", flush=True)

    print("  building feature rows ...", flush=True)
    X_base, Y, game_ids, target_dates, player_ids = build_rows(
        qstats_df, args.max_games, positions, date_index=date_index,
    )
    print(f"  total rows: {len(X_base)}", flush=True)
    if not X_base:
        print("  no rows built -- aborting.", flush=True)
        return 2

    # Pre-compute streak columns per stat (avoid recomputing for each fold).
    streak_cols_by_stat: Dict[str, List[List[float]]] = {}
    for stat in STATS:
        if stat in sf.SHIP_STREAK_STATS:
            print(f"  computing streak columns for {stat} ...", flush=True)
            streak_cols_by_stat[stat] = _streak_columns_for_stat(
                stat, target_dates, player_ids, histories,
            )
        else:
            streak_cols_by_stat[stat] = [[] for _ in target_dates]

    report = {"trained_stats": [], "skipped_stats": []}
    for stat in STATS:
        y = Y[stat]
        if len(y) < 200:
            print(f"  [{stat}] too few rows ({len(y)}), skip", flush=True)
            report["skipped_stats"].append(stat)
            continue
        print(f"\n  ---- training {stat} ----", flush=True)
        saved, stat_report = train_one_stat(
            stat, X_base, y, game_ids, streak_cols_by_stat[stat],
        )
        if saved:
            report["trained_stats"].append(stat_report)
        else:
            report["skipped_stats"].append(stat_report)

    report_path = os.path.join(OUT_DIR, "training_report_R10_M16.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n  training report -> {report_path}", flush=True)

    trained = [r["stat"] if isinstance(r, dict) else r for r in report["trained_stats"]]
    print(f"  heads saved: {trained or 'none'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
