"""probe_R2_E_possession_pace_q3.py -- R2 slot E.

Treatment: True possession-based pace adjustment via Q3 observed possessions.

Data limitation: player_quarter_stats.parquet has only
[game_id, player_id, period, min, pts, reb, ast, fg3m, stl, blk, tov, pf, plus_minus]
-- no FGA/FTA/OREB. Proxy possessions used instead:
  proxy_poss = pts/2.10 + tov   (synthetic possessions, both teams, Q3 only)

Held-out 25% calibration to verify slope > 0.15 (else REJECT pre-flight).
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import numpy as np  # noqa: E402
import retro_inplay_mae as v1  # noqa: E402
from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

# ---------------------------------------------------------------------------
# Pre-compute per-game Q3 proxy possessions and league median
# ---------------------------------------------------------------------------
_qstats_df = v1.load_quarter_stats()
_games_sorted = sorted(_qstats_df["game_id"].unique().tolist())
_cal_split = int(len(_games_sorted) * 0.25)
_cal_games = set(_games_sorted[:_cal_split])

# Compute per-game total proxy possessions (both teams, Q3 only)
_game_poss: dict = {}
for _gid in _games_sorted:
    _sub = _qstats_df[(_qstats_df["game_id"] == _gid) & (_qstats_df["period"] == 3)]
    if _sub.empty:
        continue
    _game_poss[_gid] = float(_sub["pts"].sum() / 2.10 + _sub["tov"].sum())

# Per-Q3 league median proxy possessions
LEAGUE_MED = float(np.median(list(_game_poss.values())))
print(f"  [R2_E] league_median_proxy_poss={LEAGUE_MED:.2f}  games_with_q3={len(_game_poss)}")

# ---------------------------------------------------------------------------
# Pre-flight calibration: verify slope > 0.15 on held-out 25%
# ---------------------------------------------------------------------------
SLOPE = 0.50
VOLUME_STATS = {"pts", "reb", "ast", "tov"}


def _calibrate_slope() -> float:
    """Fit OLS slope on calibration set: pace_ratio vs pts_residual_sign.

    Simple linear regression: actual_Q4_pts / baseline_Q4_pts ~ intercept + slope*(ratio-1).
    Returns fitted slope; if data missing/degenerate returns 0.0.
    """
    ratios = []
    residuals = []
    for gid in _cal_games:
        poss = _game_poss.get(gid)
        if poss is None:
            continue
        ratio = poss / LEAGUE_MED
        snap = v1.build_snapshot(gid, "endQ3", _qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, _qstats_df)
        base = BASELINE(snap)
        for (pid, stat), bval in base.items():
            if stat != "pts":
                continue
            actual = actuals.get((pid, stat))
            if actual is None or bval <= 0:
                continue
            p = next((x for x in (snap.get("players") or [])
                      if int(x.get("player_id", -1)) == pid), None)
            if p is None:
                continue
            cur = float(p.get("pts", 0) or 0)
            remaining_base = bval - cur
            if remaining_base <= 0:
                continue
            actual_remaining = actual - cur
            # signed relative residual: (actual - base) / base_remaining
            residuals.append((actual_remaining - remaining_base) / (remaining_base + 1e-9))
            ratios.append(ratio - 1.0)

    if len(ratios) < 10:
        return 0.0
    x = np.array(ratios)
    y = np.array(residuals)
    # OLS slope
    denom = float(np.dot(x, x))
    if abs(denom) < 1e-12:
        return 0.0
    return float(np.dot(x, y) / denom)


_cal_slope = _calibrate_slope()
print(f"  [R2_E] calibration_slope={_cal_slope:.4f}  threshold=0.15")
_PREFLIGHT_OK = _cal_slope > 0.15
if not _PREFLIGHT_OK:
    print(f"  [R2_E] PRE-FLIGHT REJECT: slope {_cal_slope:.4f} <= 0.15")


# ---------------------------------------------------------------------------
# Treatment function
# ---------------------------------------------------------------------------
def treatment(snap: dict) -> dict:
    """EndQ3 projection with Q3-possession-based pace adjustment on remaining."""
    base = BASELINE(snap)

    if not _PREFLIGHT_OK:
        # Pre-flight failed: return baseline unmodified (probe will REJECT)
        return base

    gid = snap.get("game_id")
    poss = _game_poss.get(gid)
    if poss is None:
        return base

    ratio = poss / LEAGUE_MED
    factor = max(0.85, min(1.15, 1.0 + SLOPE * (ratio - 1.0)))

    pid_to_player = {int(p["player_id"]): p for p in (snap.get("players") or [])
                     if p.get("player_id") is not None}

    out = {}
    for (pid, stat), proj in base.items():
        if stat not in VOLUME_STATS:
            out[(pid, stat)] = proj
            continue
        p = pid_to_player.get(pid)
        if p is None:
            out[(pid, stat)] = proj
            continue
        cur = float(p.get(stat, 0.0) or 0.0)
        remaining = proj - cur
        if remaining <= 0:
            out[(pid, stat)] = proj
            continue
        out[(pid, stat)] = cur + remaining * factor
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="R2-E: possession-based Q3 pace probe")
    ap.add_argument("--max-games", type=int, default=None,
                    help="Cap number of games for quick smoke-test")
    args = ap.parse_args()
    run_endq3_probe(
        "R2_E_possession_pace_q3",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
