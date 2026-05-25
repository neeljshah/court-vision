"""scripts/probe_R3_E_endq2_minute_in_head.py -- R3-E (loop 5).

ANGLE: Use minute_trajectory_q2.lgb as a SMALL BOUNDED scaling factor on top
of BASELINE projections at endQ2 -- NOT as a rate-extrapolation replacement.

R2_A regressed because rate * proj_total replaced the calibrated live_engine
projection entirely.  Here we only nudge the baseline by at most ±15% of the
remaining portion (factor clipped to [0.85, 1.15] before a 0.40 blend weight
shrinks the actual adjustment to ±6%).

Algorithm:
    HEAD_IMPLICIT_FACTOR calibrated once at module init:
        median(model_predict / actual_remaining_min) on first half of games.

    For each player at endQ2 with min_through_q2 >= 6.0:
        learned_remaining = clip(model.predict(row), 0, 36)
        expected_remaining = HEAD_IMPLICIT_FACTOR * 24.0
        m_ratio = clip(learned_remaining / max(expected_remaining, 1e-3), 0.85, 1.15)
        factor  = 1.0 + 0.40 * (m_ratio - 1.0)
        out[(pid, stat)] = cur + (proj - cur) * factor

    Players with min_through_q2 < 6.0 → passthrough BASELINE.

Usage:
    from scripts.probe_R3_E_endq2_minute_in_head import treatment
    from scripts.improve_loop.scaffold import run_point_probe, BASELINE
    run_point_probe("endQ2", "R3_E_endq2_minute_in_head", treatment)

CLI:
    python scripts/probe_R3_E_endq2_minute_in_head.py
    python scripts/probe_R3_E_endq2_minute_in_head.py --max-games 200
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

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

_MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "minute_trajectory_q2.lgb")

_MIN_MINUTES_Q2 = 6.0   # minimum Q1+Q2 minutes to apply the model
_MAX_REMAINING  = 36.0  # sanity clip for model output

# Blend weight: how much of the ±ratio signal to transfer to the factor.
# 0.40 => max adjustment is ±0.40 * 0.15 = ±6 % of remaining projection.
_BLEND = 0.40

# Ratio clip: prevents the model's outlier predictions from dominating.
_RATIO_LO = 0.85
_RATIO_HI = 1.15

# ── module-level singletons (loaded + calibrated once) ───────────────────────

_model = None
_model_loaded: bool = False

# Calibrated at first treatment() call.
HEAD_IMPLICIT_FACTOR: Optional[float] = None
_calibrated: bool = False


# ── helpers (mirror probe_R2_A / train_minute_trajectory_q2) ─────────────────

def _normalize_position(position_proxy: Optional[str]) -> str:
    if not position_proxy:
        return ""
    s = str(position_proxy).strip().lower()
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
    """Build 11-dim feature row matching minute_trajectory_q2_meta.json order."""
    min_q1 = float(p.get("min_q1") or 0.0)
    min_q2 = float(p.get("min_q2") or 0.0)
    pf_through_q2 = float(p.get("pf") or 0.0)

    home_score = float(snap.get("home_score") or 0.0)
    away_score = float(snap.get("away_score") or 0.0)
    score_margin_abs = abs(home_score - away_score)

    team = p.get("team", "")
    home_team = snap.get("home_team", "")
    if team == home_team:
        is_leading = 1 if home_score >= away_score else 0
    else:
        is_leading = 1 if away_score >= home_score else 0

    pos = _normalize_position(p.get("position"))
    pos_C = 1.0 if pos == "C" else 0.0
    pos_F = 1.0 if pos == "F" else 0.0
    pos_G = 1.0 if pos == "G" else 0.0

    l20_min = p.get("l20_min")
    l5_min  = p.get("l5_min")
    l20 = float("nan") if l20_min is None else float(l20_min)
    l5  = float("nan") if l5_min  is None else float(l5_min)

    # Order matches FEATURE_NAMES_Q2 / minute_trajectory_q2_meta.json (11 features):
    # pf_through_q2, min_q1, min_q2, period, score_margin_abs, is_leading_team,
    # pos_C, pos_F, pos_G, l20_min, l5_min
    return [
        float(max(0, pf_through_q2)),
        float(max(0.0, min_q1)),
        float(max(0.0, min_q2)),
        2.0,
        float(score_margin_abs),
        float(is_leading),
        pos_C, pos_F, pos_G,
        l20, l5,
    ]


def _load_model():
    if not os.path.exists(_MODEL_PATH):
        return None
    try:
        import lightgbm as lgb
        return lgb.Booster(model_file=_MODEL_PATH)
    except Exception as exc:
        print(f"  [R3_E] WARNING: failed to load model: {exc}")
        return None


def _calibrate(model) -> float:
    """Compute HEAD_IMPLICIT_FACTOR on the first-half of the retro corpus.

    HEAD_IMPLICIT_FACTOR = median(model_predict / actual_remaining_min)
    over all (game, player) rows in the FIRST HALF of games (chronological).
    Falls back to 1.0 if calibration fails.
    """
    try:
        import numpy as np
        import retro_inplay_mae as v1

        qstats_df = v1.load_quarter_stats()
        games = sorted(qstats_df["game_id"].unique().tolist())
        cutoff = max(1, len(games) // 2)
        fit_games = games[:cutoff]

        # Import helpers from train_minute_trajectory_q2 for rolling features.
        from scripts.train_minute_trajectory_q2 import (
            find_game_date_for_game,
            load_positions,
            load_player_gamelog_minutes,
            rolling_mean_min,
        )
        positions      = load_positions()
        pid_log_index  = load_player_gamelog_minutes()

        ratios = []
        for gid in fit_games:
            snap = v1.build_snapshot(gid, "endQ2", qstats_df)
            if snap is None:
                continue

            # Actual remaining minutes (Q3+Q4) from qstats_df.
            gdf = qstats_df[qstats_df["game_id"] == gid]
            target_date = find_game_date_for_game(gid, qstats_df, pid_log_index)

            for player in snap.get("players", []):
                try:
                    pid = int(player["player_id"])
                except (TypeError, ValueError):
                    continue

                min_q1 = float(player.get("min_q1") or 0.0)
                min_q2 = float(player.get("min_q2") or 0.0)
                if min_q1 + min_q2 < _MIN_MINUTES_Q2:
                    continue

                # Actual remaining min from parquet.
                pdf = gdf[gdf["player_id"] == pid]
                actual_rem = 0.0
                for _, r in pdf.iterrows():
                    if int(r["period"]) >= 3:
                        actual_rem += float(r["min"])
                if actual_rem < 0.5:
                    continue

                # Build row with rolling features from gamelog index.
                pos_str = positions.get(pid)
                l20 = rolling_mean_min(pid, target_date, 20, pid_log_index)
                l5  = rolling_mean_min(pid, target_date, 5,  pid_log_index)

                # Patch l20_min / l5_min into player dict for _build_row.
                player_aug = dict(player)
                if "l20_min" not in player_aug:
                    player_aug["l20_min"] = l20
                if "l5_min" not in player_aug:
                    player_aug["l5_min"] = l5
                if "position" not in player_aug and pos_str:
                    player_aug["position"] = pos_str

                row = _build_row(player_aug, snap)
                try:
                    pred = float(model.predict([row])[0])
                except Exception:
                    continue
                pred = max(0.0, min(pred, _MAX_REMAINING))
                if actual_rem > 0.1:
                    ratios.append(pred / actual_rem)

        if not ratios:
            return 1.0
        factor = float(np.median(ratios))
        print(f"  [R3_E] calibrated HEAD_IMPLICIT_FACTOR={factor:.4f} "
              f"(n={len(ratios)} rows, {cutoff} games)")
        return factor

    except Exception as exc:
        print(f"  [R3_E] calibration failed ({exc}), using HEAD_IMPLICIT_FACTOR=1.0")
        return 1.0


def _ensure_init() -> None:
    """Lazy-load model + run calibration exactly once."""
    global _model, _model_loaded, HEAD_IMPLICIT_FACTOR, _calibrated
    if not _model_loaded:
        _model = _load_model()
        _model_loaded = True
    if not _calibrated:
        if _model is not None:
            HEAD_IMPLICIT_FACTOR = _calibrate(_model)
        else:
            HEAD_IMPLICIT_FACTOR = 1.0
        _calibrated = True


# ── treatment ─────────────────────────────────────────────────────────────────

def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """Bounded minute-trajectory scaling applied on top of BASELINE at endQ2.

    For each player with min_through_q2 >= 6.0:
        1. Predict remaining minutes with the Q2 model.
        2. Compute m_ratio = learned_remaining / (HEAD_IMPLICIT_FACTOR * 24.0),
           clipped to [0.85, 1.15].
        3. factor = 1.0 + 0.40 * (m_ratio - 1.0)
        4. out[(pid, stat)] = cur + (proj - cur) * factor
    """
    _ensure_init()

    base = BASELINE(snap)
    out: Dict[Tuple[int, str], float] = dict(base)

    if _model is None or HEAD_IMPLICIT_FACTOR is None:
        return out

    expected_remaining = HEAD_IMPLICIT_FACTOR * 24.0  # calibrated anchor

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        min_q1 = float(player.get("min_q1") or 0.0)
        min_q2 = float(player.get("min_q2") or 0.0)
        min_through_q2 = min_q1 + min_q2

        if min_through_q2 < _MIN_MINUTES_Q2:
            continue

        row = _build_row(player, snap)
        try:
            learned_remaining = float(_model.predict([row])[0])
        except Exception:
            continue
        learned_remaining = max(0.0, min(learned_remaining, _MAX_REMAINING))

        m_ratio = learned_remaining / max(expected_remaining, 1e-3)
        m_ratio = max(_RATIO_LO, min(_RATIO_HI, m_ratio))
        factor  = 1.0 + _BLEND * (m_ratio - 1.0)

        for stat in STATS:
            key = (pid, stat)
            proj = base.get(key)
            if proj is None:
                continue
            cur = float(player.get(stat) or 0.0)
            out[key] = cur + (proj - cur) * factor

    return out


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="R3-E: bounded minute-trajectory scaling at endQ2")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    if not os.path.exists(_MODEL_PATH):
        print(f"  ERROR: model not found at {_MODEL_PATH}")
        print("  Run: python scripts/train_minute_trajectory_q2.py")
        return 2

    run_point_probe(
        "endQ2",
        "R3_E_endq2_minute_in_head",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
