"""scripts/probe_R2_G_starter_burnout.py -- per-stat fatigue decay for high-min starters.

ANGLE: Players with min_through_q3 >= 28 may deliver less per-min in Q4 due to
fatigue.  Calibrate alpha[stat][bucket] from first-half games, apply to all.
"""
from __future__ import annotations

import os
import sys

# --- sys.path setup (mirror probe_110 pattern) ---
_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_FILE_DIR)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)
if _FILE_DIR not in sys.path:
    sys.path.insert(0, _FILE_DIR)
# --------------------------------------------------

import retro_inplay_mae as v1  # noqa: E402
from collections import defaultdict
from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

_qstats_df = v1.load_quarter_stats()
_games_sorted = sorted(_qstats_df["game_id"].unique().tolist())
_fit_games = set(_games_sorted[: len(_games_sorted) // 2])


# Per (bucket, stat): track sum(actual_remaining) / sum(projected_remaining)
def _bucket(min_through_q3):
    if min_through_q3 >= 32:
        return "high"
    if min_through_q3 >= 28:
        return "mid"
    return None


_sums = defaultdict(lambda: {"num": 0.0, "den": 0.0, "n": 0})
for _gid in _fit_games:
    _snap = v1.build_snapshot(_gid, "endQ3", _qstats_df)
    if _snap is None:
        continue
    _actuals = v1.actuals_for_game(_gid, _qstats_df)
    _base = BASELINE(_snap)
    for _p in _snap.get("players") or []:
        _pid = int(_p["player_id"])
        _mt = float(_p.get("min", 0.0) or 0.0)
        _bucket_val = _bucket(_mt)
        if _bucket_val is None:
            continue
        for _s in STATS:
            _cur = float(_p.get(_s, 0.0) or 0.0)
            _proj = _base.get((_pid, _s))
            _act = _actuals.get((_pid, _s))
            if _proj is None or _act is None:
                continue
            _remaining = _proj - _cur
            if _remaining <= 0.05:
                continue
            _d = _sums[(_bucket_val, _s)]
            _d["num"] += (_act - _cur)
            _d["den"] += _remaining
            _d["n"] += 1

# Bayesian shrunk alpha toward 1.0; clip [0.85, 1.10]
K = 100
_alpha = {}
for _k, _d in _sums.items():
    if _d["n"] < 30:
        _alpha[_k] = 1.0
        continue
    _raw = _d["num"] / max(_d["den"], 1e-6)
    _f = (_d["n"] * _raw + K * 1.0) / (_d["n"] + K)
    _alpha[_k] = max(0.85, min(1.10, _f))

print(f"  burnout alpha: {dict(_alpha)}")


def treatment(snap):
    base = BASELINE(snap)
    out = {}
    pid_to_player = {int(p["player_id"]): p for p in (snap.get("players") or [])}
    for (pid, stat), proj in base.items():
        p = pid_to_player.get(pid)
        if p is None:
            out[(pid, stat)] = proj
            continue
        mt = float(p.get("min", 0.0) or 0.0)
        bucket = _bucket(mt)
        if bucket is None:
            out[(pid, stat)] = proj
            continue
        cur = float(p.get(stat, 0.0) or 0.0)
        remaining = proj - cur
        alpha = _alpha.get((bucket, stat), 1.0)
        out[(pid, stat)] = cur + max(0.0, remaining) * alpha
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()
    run_endq3_probe(
        "R2_G_starter_burnout",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
