"""scripts/probe_R4_G_learned_quantile_heads.py -- R4-G calibration probe.

Evaluates whether directly-trained LightGBM q10/q90 heads (train_quantile_heads.py)
produce better-calibrated 80% prediction intervals than the existing Gaussian-around-
q50 bands from live_quantile_bands.

For each (stat, snapshot_point) computes:
  cov_lower   = mean(actual < q10_learned)   [target: 0.10]
  cov_upper   = mean(actual > q90_learned)   [target: 0.10]
  overall_cov = mean(q10 <= actual <= q90)   [target: 0.80]
  mean_width  = mean(q90 - q10)

Ship gate (all stats at both points):
  - cov_lower  in [0.08, 0.12]
  - cov_upper  in [0.08, 0.12]
  - overall_cov in [0.78, 0.82]
  - >= 4/7 stats have mean_width_learned <= mean_width_baseline

Usage:
    python scripts/probe_R4_G_learned_quantile_heads.py
    python scripts/probe_R4_G_learned_quantile_heads.py --max-games 300
    python -c "import scripts.probe_R4_G_learned_quantile_heads"  # smoke test
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
# Stats that are non-negative (floor q10 at 0)
NON_NEG_STATS = set(STATS)

HEAD_BASE = os.path.join(PROJECT_DIR, "data", "models", "quantile_heads")

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_point", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]

# Calibration gate bounds
COV_LO_TARGET = 0.10
COV_HI_TARGET = 0.10
COV_LO_BAND = (0.08, 0.12)
COV_HI_BAND = (0.08, 0.12)
OVERALL_COV_BAND = (0.78, 0.82)
WIDTH_WINS_NEEDED = 4  # of 7 stats


# ── module-level caches ────────────────────────────────────────────────────────
_heads_cache: Dict[str, Dict[str, object]] = {}   # point -> {stat_alpha: Booster}
_positions_cache: Optional[Dict[int, str]] = None


def _load_heads(point: str) -> Dict[str, object]:
    """Load all q10/q90 heads for a snapshot point. Returns {} if dir missing."""
    if point in _heads_cache:
        return _heads_cache[point]
    import lightgbm as lgb
    out: Dict[str, object] = {}
    head_dir = os.path.join(HEAD_BASE, point)
    if not os.path.isdir(head_dir):
        _heads_cache[point] = out
        return out
    for stat in STATS:
        for alpha_label in ("q10", "q90"):
            path = os.path.join(head_dir, f"{stat}_{alpha_label}.lgb")
            if os.path.exists(path):
                try:
                    out[f"{stat}_{alpha_label}"] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN: cannot load {path}: {exc}")
    _heads_cache[point] = out
    return out


def _load_positions() -> Dict[int, str]:
    global _positions_cache
    if _positions_cache is None:
        from scripts.train_minute_trajectory import load_positions
        _positions_cache = load_positions()
    return _positions_cache


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def _min_through(player: dict, point: str) -> float:
    if point == "endQ2":
        return float(player.get("min_q1", 0)) + float(player.get("min_q2", 0))
    return (float(player.get("min_q1", 0))
            + float(player.get("min_q2", 0))
            + float(player.get("min_q3", 0)))


def _build_feat(player: dict, snap: dict, point: str, pos: Dict[int, str]):
    """Return a (1, 14) float32 ndarray for this player/snap/point."""
    import numpy as np

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))
    team = str(player.get("team", ""))
    if team == home_team:
        raw_margin = home_pts - away_pts
    elif team == away_team:
        raw_margin = away_pts - home_pts
    else:
        raw_margin = 0.0

    pid = int(player["player_id"])
    pos_c, pos_f, pos_g = _pos_flags(pos.get(pid, ""))

    return np.array([[
        float(player.get("pts", 0)),
        float(player.get("reb", 0)),
        float(player.get("ast", 0)),
        float(player.get("fg3m", 0)),
        float(player.get("stl", 0)),
        float(player.get("blk", 0)),
        float(player.get("tov", 0)),
        float(player.get("pf", 0)),
        _min_through(player, point),
        margin,
        float(raw_margin > 0),
        pos_c,
        pos_f,
        pos_g,
    ]], dtype="float32")


def probe_point(
    point: str,
    qstats_df,
    max_games: Optional[int],
) -> Dict:
    """Run calibration probe for one snapshot point.

    Returns dict with per-stat calibration metrics and overall ship verdict.
    """
    import numpy as np
    import retro_inplay_mae as v1
    from scripts.improve_loop.scaffold import BASELINE

    heads = _load_heads(point)
    positions = _load_positions()

    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    # Collect per-stat arrays
    data: Dict[str, Dict[str, List[float]]] = {
        s: {
            "actual": [],
            "q50": [],          # BASELINE point pred
            "q10_learned": [],
            "q90_learned": [],
            "q10_baseline": [],  # existing live_engine q10 band (if available)
            "q90_baseline": [],
        }
        for s in STATS
    }

    n_games = len(games)
    for gi, gid in enumerate(games):
        if gi % 200 == 0:
            print(f"  [{point}] probing {gi}/{n_games} ...", flush=True)

        snap = v1.build_snapshot(gid, point, qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        # BASELINE projections (includes live_engine q10/q90 bands if wired)
        try:
            from src.prediction.live_engine import project_from_snapshot
            rows_live = project_from_snapshot(snap)
        except Exception:
            rows_live = []

        live_map: Dict[Tuple[int, str], dict] = {}
        for r in rows_live:
            try:
                pid = int(r.get("player_id"))
            except (TypeError, ValueError):
                continue
            live_map[(pid, str(r["stat"]))] = r

        # BASELINE via scaffold (projected_final only)
        try:
            base_proj = BASELINE(snap)
        except Exception:
            continue

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            feat = _build_feat(player, snap, point, positions)

            for stat in STATS:
                actual = actuals.get((pid, stat))
                if actual is None:
                    continue
                q50 = base_proj.get((pid, stat))
                if q50 is None:
                    continue

                # Learned quantile heads
                head_q10 = heads.get(f"{stat}_q10")
                head_q90 = heads.get(f"{stat}_q90")
                if head_q10 is None or head_q90 is None:
                    continue

                q10_raw = float(head_q10.predict(feat)[0])
                q90_raw = float(head_q90.predict(feat)[0])

                # Enforce monotonicity: q10 <= q50 <= q90
                q10 = min(q10_raw, float(q50))
                q90 = max(q90_raw, float(q50))

                # Floor q10 at 0 for non-negative stats
                if stat in NON_NEG_STATS:
                    q10 = max(0.0, q10)

                # Baseline bands from live_engine (may not exist)
                live_row = live_map.get((pid, stat), {})
                q10_base = live_row.get("q10")
                q90_base = live_row.get("q90")

                data[stat]["actual"].append(float(actual))
                data[stat]["q50"].append(float(q50))
                data[stat]["q10_learned"].append(q10)
                data[stat]["q90_learned"].append(q90)
                if q10_base is not None and q90_base is not None:
                    data[stat]["q10_baseline"].append(float(q10_base))
                    data[stat]["q90_baseline"].append(float(q90_base))

    # ── per-stat calibration metrics ──────────────────────────────────────────
    results = []
    width_wins = 0
    all_gate_pass = True

    print(f"\n=== Calibration results for {point} ===")
    print(f"{'stat':6s} {'n':>6s} {'cov_lo':>8s} {'cov_hi':>8s} "
          f"{'ovrl_cov':>10s} {'width_lrn':>10s} {'width_base':>11s} {'gate':>6s}")
    print("-" * 70)

    for stat in STATS:
        y = np.array(data[stat]["actual"])
        q10 = np.array(data[stat]["q10_learned"])
        q90 = np.array(data[stat]["q90_learned"])
        n = len(y)

        if n < 10:
            print(f"  [{point}/{stat}] too few rows ({n}), skipping")
            continue

        cov_lower = float(np.mean(y < q10))
        cov_upper = float(np.mean(y > q90))
        overall_cov = float(np.mean((y >= q10) & (y <= q90)))
        mean_width_learned = float(np.mean(q90 - q10))

        # Baseline width (if available)
        q10b_arr = np.array(data[stat]["q10_baseline"])
        q90b_arr = np.array(data[stat]["q90_baseline"])
        if len(q10b_arr) >= 10:
            mean_width_baseline = float(np.mean(q90b_arr - q10b_arr))
        else:
            mean_width_baseline = float("nan")

        # Gate check
        lo_ok = COV_LO_BAND[0] <= cov_lower <= COV_LO_BAND[1]
        hi_ok = COV_HI_BAND[0] <= cov_upper <= COV_HI_BAND[1]
        cov_ok = OVERALL_COV_BAND[0] <= overall_cov <= OVERALL_COV_BAND[1]
        stat_gate = lo_ok and hi_ok and cov_ok
        if not stat_gate:
            all_gate_pass = False

        # Width comparison
        if not (mean_width_baseline != mean_width_baseline):  # not NaN
            if mean_width_learned <= mean_width_baseline:
                width_wins += 1

        width_base_str = f"{mean_width_baseline:.3f}" if not (mean_width_baseline != mean_width_baseline) else "  n/a"
        gate_str = "PASS" if stat_gate else "FAIL"
        print(f"{stat:6s} {n:>6d} {cov_lower:>8.4f} {cov_upper:>8.4f} "
              f"{overall_cov:>10.4f} {mean_width_learned:>10.3f} {width_base_str:>11s} {gate_str:>6s}")

        results.append({
            "stat": stat,
            "n": n,
            "cov_lower": round(cov_lower, 5),
            "cov_upper": round(cov_upper, 5),
            "overall_cov": round(overall_cov, 5),
            "mean_width_learned": round(mean_width_learned, 4),
            "mean_width_baseline": round(mean_width_baseline, 4) if not (mean_width_baseline != mean_width_baseline) else None,
            "gate_pass": stat_gate,
        })

    width_gate = width_wins >= WIDTH_WINS_NEEDED
    if not width_gate:
        all_gate_pass = False

    print(f"\n  Width wins: {width_wins}/7 (need >= {WIDTH_WINS_NEEDED})"
          f"  -> {'PASS' if width_gate else 'FAIL'}")
    print(f"  All-stat gate: {'PASS' if all_gate_pass else 'FAIL'}")

    return {
        "point": point,
        "n_games_attempted": n_games,
        "per_stat": results,
        "width_wins": width_wins,
        "width_gate": width_gate,
        "all_gate_pass": all_gate_pass,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="R4-G learned quantile heads calibration probe.")
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument(
        "--snapshot-point",
        choices=["endQ2", "endQ3", "both"],
        default="both",
    )
    args = ap.parse_args()

    import retro_inplay_mae as v1

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    print(f"  {qstats_df['game_id'].nunique()} games in parquet")

    points = (
        ["endQ2", "endQ3"] if args.snapshot_point == "both"
        else [args.snapshot_point]
    )

    all_results = []
    for point in points:
        heads = _load_heads(point)
        n_heads = len(heads)
        if n_heads == 0:
            print(f"  [{point}] No heads found at {os.path.join(HEAD_BASE, point)}. "
                  "Run train_quantile_heads.py first.")
            continue
        print(f"  [{point}] {n_heads} heads loaded. Running probe ...")
        rpt = probe_point(point, qstats_df, args.max_games)
        all_results.append(rpt)

    # ── overall ship verdict ───────────────────────────────────────────────────
    print("\n=== Overall Ship Verdict ===")
    if len(all_results) < len(points):
        print("  REJECT: some points missing heads (run training first)")
        return 1

    both_pass = all(r["all_gate_pass"] for r in all_results)
    print(f"  {'SHIP' if both_pass else 'REJECT'}: "
          + (
              "all stats at all points within calibration bands."
              if both_pass
              else "one or more stats/points failed calibration gate."
          ))
    return 0 if both_pass else 2


if __name__ == "__main__":
    sys.exit(main())
