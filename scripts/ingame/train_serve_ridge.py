"""Train and persist the leak-free serve-ridge POINT estimator for team score.

This script fits the SAME per-bucket ridge used in eval_routed_ensemble.py
(see _fit_team_ridge / TEAM_FEATS / _ridge_fit) on a training corpus that is
strictly before a configurable cutoff date.  The fitted model is persisted to
data/models/ingame_serve_ridge.pkl for use by src/ingame/serve_ridge_point.py
at serve time.

LEAK DISCIPLINE
---------------
Only games with game_date < CUTOFF are used for training.  The CUTOFF is the
date of the last game in the corpus minus a configurable hold-back window
(default: 120 days).  At serve time, predict_serve_ridge featurizes only the
CURRENT live snapshot state (home_score, away_score, elapsed time, four-factor
rates so far) — no future info is ever accessed.

FEATURES (TEAM_FEATS from eval_second_by_second.py -- must mirror exactly):
    played_share, home_score, away_score, score_margin,
    pace_poss_per_min, home_efg, away_efg, home_tov_pct, away_tov_pct,
    home_ft_rate, away_ft_rate, game_remaining_sec

GRID BUCKETS (must match eval_second_by_second.GRID_SEC):
    360, 720, 1080, 1440, 1800, 2160, 2520  (6,12,18,24,30,36,42 min elapsed)

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/train_serve_ridge.py [--cutoff YYYY-MM-DD]
Output:
    data/models/ingame_serve_ridge.pkl
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np  # noqa: E402

# Reuse EXACT featurization + ridge helpers from the eval harness so that
# the persisted artifact is byte-identical to the eval's per-bucket ridge.
from scripts.ingame.eval_second_by_second import (  # noqa: E402
    TEAM_FEATS, GamelogStore, load_season_games, build_game_record,
    _parse_iso_date, _ridge_fit,
)
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402

MODEL_PATH = os.path.join(ROOT, "data", "models", "ingame_serve_ridge.pkl")
# Grid buckets (must match eval_second_by_second.GRID_SEC exactly).
GRID_SEC = [360, 720, 1080, 1440, 1800, 2160, 2520]
# Hold-back window: don't train on the last N days so the artifact's cutoff is
# clearly prior to recently-played games that could still be served live.
DEFAULT_HOLDBACK_DAYS = 120


def _fit_ridge(train_recs: List[Dict[str, Any]]) -> Dict[int, Dict[str, np.ndarray]]:
    """Per-bucket ridge: TEAM_FEATS at grid t -> (home_final, away_final).

    Exactly mirrors eval_routed_ensemble._fit_team_ridge.
    """
    by_X: Dict[int, List[List[float]]] = defaultdict(list)
    by_yh: Dict[int, List[float]] = defaultdict(list)
    by_ya: Dict[int, List[float]] = defaultdict(list)
    for r in train_recs:
        for t, gd in r["grids"].items():
            grow = gd["game"]
            by_X[t].append([float(grow.get(k, 0) or 0) for k in TEAM_FEATS])
            by_yh[t].append(float(r["home_final"]))
            by_ya[t].append(float(r["away_final"]))
    out: Dict[int, Dict[str, np.ndarray]] = {}
    for t in sorted(by_X.keys()):
        if len(by_X[t]) < 10:
            continue  # skip buckets with too few training samples
        X = np.array(by_X[t], dtype=np.float64)
        out[t] = {
            "home": _ridge_fit(X, np.array(by_yh[t], dtype=np.float64)),
            "away": _ridge_fit(X, np.array(by_ya[t], dtype=np.float64)),
        }
    return out


def train(cutoff: Optional[str] = None) -> Dict[str, Any]:
    """Build training corpus, fit ridge, persist artifact.

    Args:
        cutoff: ISO date string "YYYY-MM-DD"; games strictly before this date
            are used for training.  If None, auto-computed as
            (latest_game_date - DEFAULT_HOLDBACK_DAYS).
    Returns:
        Summary dict with cutoff, n_train, n_fail, bucket counts.
    """
    season_games = load_season_games()
    store = GamelogStore()
    all_ids = [g for g in discover_game_ids()
               if g in season_games
               and _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])

    if not all_ids:
        raise RuntimeError("No dated PBP games found")

    # Determine cutoff
    if cutoff is not None:
        cutoff_date = _parse_iso_date(cutoff)
        if cutoff_date is None:
            raise ValueError(f"Invalid cutoff date: {cutoff!r}")
    else:
        latest = max(_parse_iso_date(season_games[g]["game_date"]) for g in all_ids)
        cutoff_date = latest - timedelta(days=DEFAULT_HOLDBACK_DAYS)

    train_ids = [g for g in all_ids
                 if _parse_iso_date(season_games[g]["game_date"]) < cutoff_date]
    print(f"[train_serve_ridge] cutoff={cutoff_date}  train_ids={len(train_ids)}"
          f"  (of {len(all_ids)} total dated)")

    if len(train_ids) < 20:
        raise RuntimeError(f"Too few training games ({len(train_ids)}) before {cutoff_date}")

    # Build records
    train_recs: List[Dict[str, Any]] = []
    n_fail = 0
    for i, gid in enumerate(train_ids):
        try:
            rec = build_game_record(gid, season_games[gid], store)
        except Exception as exc:
            rec = None
            n_fail += 1
            if n_fail <= 5:
                print(f"  [warn] {gid}: {exc!r}")
        if rec is not None:
            train_recs.append(rec)
        if (i + 1) % 200 == 0:
            print(f"  ...{i+1}/{len(train_ids)} ({len(train_recs)} usable, {n_fail} fail)")

    print(f"[train_serve_ridge] {len(train_recs)} usable records, {n_fail} failed")
    if len(train_recs) < 20:
        raise RuntimeError("Too few usable training records")

    # Fit per-bucket ridge
    ridge_w = _fit_ridge(train_recs)
    print(f"[train_serve_ridge] fitted {len(ridge_w)} bucket(s): "
          f"{sorted(ridge_w.keys())}")

    # Persist artifact
    artifact = {
        "version": 1,
        "cutoff": str(cutoff_date),
        "n_train": len(train_recs),
        "feature_spec": TEAM_FEATS,
        "grid_sec": GRID_SEC,
        "ridge_w": ridge_w,   # {t: {"home": ndarray, "away": ndarray}}
    }
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(artifact, fh, protocol=4)
    print(f"[train_serve_ridge] persisted -> {MODEL_PATH}")

    # Quick sanity: predict on a synthetic mid-Q3 row
    t_test = 1800  # 30 min
    if t_test in ridge_w:
        test_feat = np.zeros((1, len(TEAM_FEATS)))
        # played_share=0.625, home_score=60, away_score=58, margin=2,
        # pace=2.0, efg=0.50/0.49, tov_pct=0.12/0.12, ft_rate=0.25/0.25, rem=1080
        test_vals = [0.625, 60.0, 58.0, 2.0, 2.0, 0.50, 0.49, 0.12, 0.12,
                     0.25, 0.25, 1080.0]
        test_feat[0] = test_vals
        from scripts.ingame.eval_second_by_second import _ridge_pred
        ph = float(_ridge_pred(ridge_w[t_test]["home"], test_feat)[0])
        pa = float(_ridge_pred(ridge_w[t_test]["away"], test_feat)[0])
        print(f"[train_serve_ridge] sanity @ 30min: home={ph:.1f} away={pa:.1f}")

    return {
        "cutoff": str(cutoff_date),
        "n_train": len(train_recs),
        "n_fail": n_fail,
        "n_buckets": len(ridge_w),
        "buckets": sorted(ridge_w.keys()),
        "artifact_path": MODEL_PATH,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cutoff", default=None,
                    help="ISO date; games strictly before this date are used "
                         "(default: latest_game_date - 120 days)")
    args = ap.parse_args()
    summary = train(args.cutoff)
    import json
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
