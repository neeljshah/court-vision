"""scripts/probe_R4_H_lgb_xgb_ensemble.py -- R4-H LGB+XGB residual ensemble (loop 5).

For each (pid, stat) at endQ3:
  1. Compute 14 features (same as R2_F).
  2. Load LGB head (residual_heads/{stat}.lgb) -> resid_lgb
  3. Load XGB head (residual_heads_xgb/{stat}.json) -> resid_xgb
  4. resid_ens = 0.5 * resid_lgb + 0.5 * resid_xgb
  5. out = BASELINE - resid_lgb + resid_ens  = BASELINE + 0.5*(resid_xgb - resid_lgb)
     (i.e. we replace R2_F's pure LGB correction with the averaged correction)

Clips and non-negativity guards same as R2_F.
Also logs per-stat Pearson correlation between resid_lgb and resid_xgb.

Usage:
    python scripts/probe_R4_H_lgb_xgb_ensemble.py
    python scripts/probe_R4_H_lgb_xgb_ensemble.py --max-games 100
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

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
LGB_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
XGB_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_xgb")

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]

# Module-level caches
_lgb_heads: Dict[str, object] = {}
_xgb_heads: Dict[str, object] = {}
_positions_cache: Optional[Dict[int, str]] = None

# For correlation logging: {stat: (lgb_preds, xgb_preds)}
_corr_buf: Dict[str, Tuple[List[float], List[float]]] = {s: ([], []) for s in STATS}


def _load_lgb_heads() -> Dict[str, object]:
    import lightgbm as lgb
    heads: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(LGB_HEAD_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            try:
                heads[stat] = lgb.Booster(model_file=path)
            except Exception as exc:
                print(f"  WARN: LGB load failed {path}: {exc}")
    return heads


def _load_xgb_heads() -> Dict[str, object]:
    import xgboost as xgb
    heads: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(XGB_HEAD_DIR, f"{stat}.json")
        if os.path.exists(path):
            try:
                bst = xgb.Booster()
                bst.load_model(path)
                heads[stat] = bst
            except Exception as exc:
                print(f"  WARN: XGB load failed {path}: {exc}")
    return heads


def _load_positions() -> Dict[int, str]:
    from scripts.train_minute_trajectory import load_positions
    return load_positions()


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """LGB+XGB 50/50 ensemble residual correction on top of BASELINE."""
    global _lgb_heads, _xgb_heads, _positions_cache

    if not _lgb_heads:
        _lgb_heads = _load_lgb_heads()
    if not _xgb_heads:
        _xgb_heads = _load_xgb_heads()
    if _positions_cache is None:
        _positions_cache = _load_positions()

    import numpy as np
    import xgboost as xgb

    base = BASELINE(snap)

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))

    out: Dict[Tuple[int, str], float] = dict(base)

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

        pos_c, pos_f, pos_g = _pos_flags(_positions_cache.get(pid, ""))

        feat_vals = [
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
            pos_c,
            pos_f,
            pos_g,
        ]
        feat_np = np.array([feat_vals], dtype=np.float32)
        feat_dmat = xgb.DMatrix(feat_np, feature_names=FEATURE_NAMES)

        for stat in STATS:
            lgb_head = _lgb_heads.get(stat)
            xgb_head = _xgb_heads.get(stat)

            key = (pid, stat)
            projected = base.get(key)
            if projected is None:
                continue

            # Determine which heads are available
            has_lgb = lgb_head is not None
            has_xgb = xgb_head is not None

            if not has_lgb and not has_xgb:
                # No heads at all — keep BASELINE unchanged
                continue

            # Predict residuals where heads exist
            resid_lgb: float = float(lgb_head.predict(feat_np)[0]) if has_lgb else 0.0
            resid_xgb: float = float(xgb_head.predict(feat_dmat)[0]) if has_xgb else 0.0

            # Accumulate for correlation logging
            if has_lgb and has_xgb:
                _corr_buf[stat][0].append(resid_lgb)
                _corr_buf[stat][1].append(resid_xgb)

            if has_lgb and has_xgb:
                resid_ens = 0.5 * resid_lgb + 0.5 * resid_xgb
                # Swap R2_F's pure LGB correction for the ensemble correction:
                # out = BASELINE + resid_ens  (projected is already BASELINE value)
                # Equivalently: BASELINE - resid_lgb + resid_ens
                residual_pred = resid_ens
            elif has_lgb:
                # Only LGB available — identical to R2_F (fallback, shouldn't happen
                # for stats that passed training gate for LGB)
                residual_pred = resid_lgb
            else:
                # Only XGB available — shouldn't happen given skip logic in trainer
                residual_pred = resid_xgb

            cur_stat = float(player.get(stat, 0))
            lo = -cur_stat
            hi = max(0.0, 2.0 * float(projected))
            adjusted = float(projected) + residual_pred
            adjusted = max(float(projected) + lo, min(float(projected) + hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


def _print_correlations() -> None:
    """Print Pearson r between LGB and XGB residual predictions per stat."""
    import math

    print("\n  LGB vs XGB residual correlations:")
    print(f"  {'stat':6s}  {'n':>6s}  {'corr':>7s}  note")
    for stat in STATS:
        lgb_preds, xgb_preds = _corr_buf[stat]
        n = len(lgb_preds)
        if n < 10:
            print(f"  {stat:6s}  {n:>6d}  {'N/A':>7s}  (too few)")
            continue
        # Pearson r
        mean_l = sum(lgb_preds) / n
        mean_x = sum(xgb_preds) / n
        num = sum((l - mean_l) * (x - mean_x) for l, x in zip(lgb_preds, xgb_preds))
        ss_l = sum((l - mean_l) ** 2 for l in lgb_preds)
        ss_x = sum((x - mean_x) ** 2 for x in xgb_preds)
        denom = math.sqrt(ss_l * ss_x)
        r = num / denom if denom > 0 else float("nan")
        note = "DEAD (r>0.95)" if r > 0.95 else ("diverse" if r < 0.7 else "ok")
        print(f"  {stat:6s}  {n:>6d}  {r:>7.4f}  {note}")


def main() -> int:
    ap = argparse.ArgumentParser(description="R4-H LGB+XGB residual ensemble probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_lgb = sum(1 for s in STATS if os.path.exists(os.path.join(LGB_HEAD_DIR, f"{s}.lgb")))
    n_xgb = sum(1 for s in STATS if os.path.exists(os.path.join(XGB_HEAD_DIR, f"{s}.json")))
    print(f"  LGB heads: {n_lgb}/7   XGB heads: {n_xgb}/7")

    if n_lgb == 0:
        print("  No LGB heads. Run train_residual_heads.py first.")
        return 1

    run_endq3_probe(
        "R4_H_lgb_xgb_ensemble",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )

    _print_correlations()
    return 0


if __name__ == "__main__":
    sys.exit(main())
