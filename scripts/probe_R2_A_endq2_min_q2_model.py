"""probe_R2_A_endq2_min_q2_model.py -- R2_A (loop 5).

Compares baseline (live_engine) vs a DEDICATED endQ2 remaining-minutes model
trained in train_minute_trajectory_q2.py.

R1_A failure: endQ3 model zero-filled Q3 features at endQ2 → OOD, +0.51 PTS.
Fix: new model trained on ONLY endQ2-observable features avoids OOD issue.

Treatment (endQ2 snapshot):
    For each player with min_q1+min_q2 >= 6.0:
        - Build 10-dim feature row (pf_through_q2, min_q1, min_q2, period=2,
          score_margin_abs, is_leading_team, pos_C, pos_F, pos_G, l20_min, l5_min)
        - learned_remaining = model.predict([row])[0], clipped [0, 36]
        - proj_min_total = min_q1 + min_q2 + learned_remaining
        - rate = current_stat / max(min_q1+min_q2, 1e-6)
        - final = rate * proj_min_total
    Players with min_q1+min_q2 < 6.0 → passthrough baseline (tiny sample).

Usage:
    python scripts/probe_R2_A_endq2_min_q2_model.py
    python scripts/probe_R2_A_endq2_min_q2_model.py --max-games 200
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from scripts.improve_loop.scaffold import run_point_probe, BASELINE  # noqa: E402

_MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "minute_trajectory_q2.lgb")

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Minimum Q1+Q2 minutes to apply the learned model.
_MIN_MINUTES_Q2 = 6.0

# Maximum remaining-min prediction (sanity clip: Q3+Q4+OT <= 36).
_MAX_REMAINING = 36.0


def _normalize_position(position_proxy: Optional[str]) -> str:
    if not position_proxy:
        return ""
    s = str(position_proxy).strip().lower()
    if not s:
        return ""
    if "center" in s:
        return "C"
    if "forward" in s:
        return "F"
    if "guard" in s:
        return "G"
    u = s.upper()
    if u == "C":
        return "C"
    if u in {"PF", "SF", "F"}:
        return "F"
    if u in {"PG", "SG", "G"}:
        return "G"
    return ""


def _build_row(p: dict, snap: dict) -> list:
    """Build 10-dim feature row from a player entry + snapshot context."""
    min_q1 = float(p.get("min_q1") or 0.0)
    min_q2 = float(p.get("min_q2") or 0.0)

    # pf_through_q2 = cumulative PF in snapshot (which is endQ2 = Q1+Q2 sum).
    pf_through_q2 = float(p.get("pf") or 0.0)

    # Score margin from snapshot.
    home_score = float(snap.get("home_score") or 0.0)
    away_score = float(snap.get("away_score") or 0.0)
    score_margin_abs = abs(home_score - away_score)

    team = p.get("team", "")
    home_team = snap.get("home_team", "")
    home_score_v = home_score
    away_score_v = away_score
    if team == home_team:
        is_leading = 1 if home_score_v >= away_score_v else 0
    else:
        is_leading = 1 if away_score_v >= home_score_v else 0

    pos = _normalize_position(p.get("position"))
    pos_C = 1.0 if pos == "C" else 0.0
    pos_F = 1.0 if pos == "F" else 0.0
    pos_G = 1.0 if pos == "G" else 0.0

    l20_min = p.get("l20_min")
    l5_min  = p.get("l5_min")
    l20 = float("nan") if l20_min is None else float(l20_min)
    l5  = float("nan") if l5_min  is None else float(l5_min)

    return [
        float(max(0, pf_through_q2)),  # pf_through_q2
        float(max(0.0, min_q1)),        # min_q1
        float(max(0.0, min_q2)),        # min_q2
        2.0,                            # period (endQ2)
        float(score_margin_abs),        # score_margin_abs
        float(is_leading),              # is_leading_team
        pos_C, pos_F, pos_G,           # position one-hot
        l20, l5,                        # rolling form features
    ]


def _load_model():
    """Load the endQ2 LightGBM booster.  Returns None if artifact missing."""
    if not os.path.exists(_MODEL_PATH):
        return None
    try:
        import lightgbm as lgb
        return lgb.Booster(model_file=_MODEL_PATH)
    except Exception as exc:
        print(f"  [R2_A] WARNING: failed to load model: {exc}")
        return None


# Module-level model singleton (loaded once on first treatment call).
_model = None
_model_loaded = False


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """endQ2 treatment: learned remaining-minutes replaces heuristic.

    Falls back to baseline projections for players with < 6.0 min through Q2
    (insufficient signal to extrapolate from).
    """
    global _model, _model_loaded
    if not _model_loaded:
        _model = _load_model()
        _model_loaded = True

    # Passthrough baseline (live_engine) as default.
    base_proj = BASELINE(snap)
    out: Dict[Tuple[int, str], float] = dict(base_proj)

    if _model is None:
        return out

    for p in snap.get("players", []):
        try:
            pid = int(p["player_id"])
        except (KeyError, TypeError, ValueError):
            continue

        min_q1 = float(p.get("min_q1") or 0.0)
        min_q2 = float(p.get("min_q2") or 0.0)
        min_through_q2 = min_q1 + min_q2

        # Passthrough baseline for players with tiny Q1+Q2 usage.
        if min_through_q2 < _MIN_MINUTES_Q2:
            continue

        row = _build_row(p, snap)
        try:
            learned_remaining = float(_model.predict([row])[0])
        except Exception:
            continue
        learned_remaining = max(0.0, min(learned_remaining, _MAX_REMAINING))

        proj_min_total = min_through_q2 + learned_remaining

        for stat in STATS:
            current = float(p.get(stat) or 0.0)
            rate = current / max(min_through_q2, 1e-6)
            out[(pid, stat)] = rate * proj_min_total

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R2_A: endQ2 dedicated min-trajectory probe")
    ap.add_argument("--max-games", type=int, default=None,
                    help="Limit corpus size for quick smoke tests")
    args = ap.parse_args()

    if not os.path.exists(_MODEL_PATH):
        print(f"  ERROR: model not found at {_MODEL_PATH}")
        print("  Run: python scripts/train_minute_trajectory_q2.py")
        return 2

    run_point_probe(
        "endQ2",
        "R2_A_endq2_min_q2_model",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
