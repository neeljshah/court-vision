"""scripts/train_quantile_heads.py -- R4-G directly-trained quantile heads (q10 + q90).

For each of 7 stats, trains TWO LightGBM models with objective="quantile":
  alpha=0.10 -> predicts the 10th percentile of the final-game stat
  alpha=0.90 -> predicts the 90th percentile of the final-game stat

TARGETS: actual_final_stat (NOT residuals — heads learn the full conditional quantile).

Features (14 — same as R2-F heads):
  cur_pts, cur_reb, cur_ast, cur_fg3m, cur_stl, cur_blk, cur_tov, cur_pf,
  min_through_<point>, score_margin_abs, is_leading, pos_C, pos_F, pos_G

Gate: WF 4-fold GroupKFold by game_id. Save .lgb only if WF mean PINBALL LOSS
< zero-prediction-baseline pinball on >= 3/4 folds.
  pinball(alpha, y, q) = max(alpha*(y-q), (alpha-1)*(y-q))

Output dirs:
  data/models/quantile_heads/endQ2/{stat}_q10.lgb  {stat}_q90.lgb
  data/models/quantile_heads/endQ3/{stat}_q10.lgb  {stat}_q90.lgb

Usage:
    python scripts/train_quantile_heads.py
    python scripts/train_quantile_heads.py --snapshot-point endQ3 --max-games 300
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
ALPHAS = (0.10, 0.90)
OUT_BASE = os.path.join(PROJECT_DIR, "data", "models", "quantile_heads")

LGB_BASE_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

# Minutes feature name differs by snapshot point
_MIN_FEATURE = {
    "endQ2": "min_through_q2",
    "endQ3": "min_through_q3",
}

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_point", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot from NBA position string."""
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def _min_through(player: dict, point: str) -> float:
    """Cumulative minutes through snapshot point."""
    if point == "endQ2":
        return float(player.get("min_q1", 0)) + float(player.get("min_q2", 0))
    # endQ3
    return (float(player.get("min_q1", 0))
            + float(player.get("min_q2", 0))
            + float(player.get("min_q3", 0)))


def build_rows(
    qstats_df,
    point: str,
    max_games: Optional[int],
    positions: Dict[int, str],
) -> Tuple[List[List[float]], Dict[str, List[float]], List[str]]:
    """Build feature matrix X and per-stat actual-total vectors Y.

    Returns:
        X:        List of 14-float feature rows.
        Y:        {stat: [actual_full_game_total, ...]} — same length as X.
        game_ids: game_id per row (for GroupKFold).
    """
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X: List[List[float]] = []
    Y: Dict[str, List[float]] = {s: [] for s in STATS}
    game_ids_out: List[str] = []

    n_games = len(games)
    for gi, gid in enumerate(games):
        if gi % 100 == 0:
            print(f"  [{point}] building rows {gi}/{n_games} ...", flush=True)

        snap = v1.build_snapshot(gid, point, qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)
        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))

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
            min_val = _min_through(player, point)

            feat = [
                float(player.get("pts", 0)),
                float(player.get("reb", 0)),
                float(player.get("ast", 0)),
                float(player.get("fg3m", 0)),
                float(player.get("stl", 0)),
                float(player.get("blk", 0)),
                float(player.get("tov", 0)),
                float(player.get("pf", 0)),
                min_val,
                margin,
                float(raw_margin > 0),
                pos_c,
                pos_f,
                pos_g,
            ]

            # Verify all actuals present before adding row
            all_ok = True
            row_actuals: Dict[str, float] = {}
            for stat in STATS:
                actual = actuals.get((pid, stat))
                if actual is None:
                    all_ok = False
                    break
                row_actuals[stat] = actual

            if not all_ok:
                continue

            X.append(feat)
            for stat in STATS:
                Y[stat].append(row_actuals[stat])
            game_ids_out.append(gid)

    return X, Y, game_ids_out


def _pinball_loss(alpha: float, y, q) -> float:
    """Mean pinball (quantile) loss: mean(max(alpha*(y-q), (alpha-1)*(y-q)))."""
    import numpy as np
    diff = y - q
    loss = np.where(diff >= 0, alpha * diff, (alpha - 1) * diff)
    return float(np.mean(loss))


def train_one_quantile_head(
    stat: str,
    alpha: float,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
    out_dir: str,
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold, WF gate >= 3/4 folds beat zero-pred pinball.

    Zero-pred baseline for quantile: predict the unconditional quantile of y_train
    (not 0), since a constant quantile is the correct naive baseline for pinball loss.

    Returns (saved: bool, report: dict).
    """
    import lightgbm as lgb
    import numpy as np

    X = np.array(X_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)

    # Build sequential group indices
    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}
    groups = np.array([gid_to_idx[gid] for gid in game_ids], dtype=np.int32)

    n_groups = len(unique_games)
    fold_size = max(1, n_groups // 4)
    fold_wins = 0
    fold_details = []

    params = {**LGB_BASE_PARAMS, "objective": "quantile", "alpha": alpha}
    alpha_label = "q10" if alpha < 0.5 else "q90"

    for fi in range(4):
        lo = fi * fold_size
        hi = n_groups if fi == 3 else (fi + 1) * fold_size
        val_game_set = set(unique_games[lo:hi])

        train_mask = np.array(
            [gid_to_idx[gid] not in {gid_to_idx[g] for g in val_game_set}
             for gid in game_ids],
            dtype=bool,
        )
        val_mask = ~train_mask

        if train_mask.sum() < LGB_BASE_PARAMS["min_child_samples"] or val_mask.sum() == 0:
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = lgb.LGBMRegressor(**params)
        model.fit(X[train_mask], y_arr[train_mask], feature_name=FEATURE_NAMES)
        preds = model.predict(X[val_mask])
        y_val = y_arr[val_mask]

        pinball_model = _pinball_loss(alpha, y_val, preds)
        # Baseline: unconditional quantile of training targets
        baseline_q = float(np.quantile(y_arr[train_mask], alpha))
        baseline_preds = np.full_like(y_val, baseline_q)
        pinball_base = _pinball_loss(alpha, y_val, baseline_preds)

        delta = pinball_model - pinball_base
        fold_details.append({
            "fold": fi + 1,
            "n_val": int(val_mask.sum()),
            "pinball_model": round(pinball_model, 5),
            "pinball_base": round(pinball_base, 5),
            "delta": round(delta, 5),
        })
        won = pinball_model < pinball_base
        if won:
            fold_wins += 1
        print(f"    [{stat}/{alpha_label}] fold {fi+1}: "
              f"pinball_model={pinball_model:.4f} "
              f"base={pinball_base:.4f} delta={delta:+.4f} "
              f"{'WIN' if won else 'loss'}")

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**params)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
        fname = f"{stat}_{alpha_label}.lgb"
        out_path = os.path.join(out_dir, fname)
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{stat}/{alpha_label}] SAVED -> {out_path}  ({fold_wins}/4 folds won)")
    else:
        print(f"  [{stat}/{alpha_label}] NOT SAVED (only {fold_wins}/4 folds beat baseline)")

    return saved, {
        "stat": stat,
        "alpha": alpha,
        "alpha_label": alpha_label,
        "n_rows": len(y),
        "fold_wins": fold_wins,
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def train_for_point(
    point: str,
    qstats_df,
    positions: Dict[int, str],
    max_games: Optional[int],
) -> Dict:
    """Train all 14 heads (7 stats x 2 alphas) for one snapshot point."""
    out_dir = os.path.join(OUT_BASE, point)
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n=== Building feature rows for {point} ===")
    X_rows, Y, game_ids = build_rows(qstats_df, point, max_games, positions)
    print(f"  total rows: {len(X_rows)}")

    report: Dict = {"point": point, "saved": [], "not_saved": []}

    for stat in STATS:
        y = Y[stat]
        if len(y) < 200:
            print(f"  [{point}/{stat}] too few rows ({len(y)}), skip")
            report["not_saved"].append({"stat": stat, "reason": "too_few_rows"})
            continue
        for alpha in ALPHAS:
            saved, stat_report = train_one_quantile_head(
                stat, alpha, X_rows, y, game_ids, out_dir
            )
            if saved:
                report["saved"].append(stat_report)
            else:
                report["not_saved"].append(stat_report)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Train quantile heads (q10+q90) for R4-G.")
    ap.add_argument(
        "--snapshot-point",
        choices=["endQ2", "endQ3", "both"],
        default="both",
        help="Which snapshot point(s) to train for (default: both).",
    )
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_BASE, exist_ok=True)

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...")
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    points_to_run = (
        ["endQ2", "endQ3"] if args.snapshot_point == "both"
        else [args.snapshot_point]
    )

    all_reports = []
    for point in points_to_run:
        rpt = train_for_point(point, qstats_df, positions, args.max_games)
        all_reports.append(rpt)

    report_path = os.path.join(OUT_BASE, "training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(all_reports, fh, indent=2)
    print(f"\n  training report -> {report_path}")

    for rpt in all_reports:
        pt = rpt["point"]
        saved_keys = [f"{r['stat']}/{r['alpha_label']}" for r in rpt["saved"]]
        print(f"  [{pt}] saved: {saved_keys or 'none'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
