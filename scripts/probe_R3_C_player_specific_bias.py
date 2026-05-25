"""probe_R3_C_player_specific_bias.py -- R3 cycle C.

Angle: Player-specific Q4 bias correction.
For top-100 players by min played, compute their mean residual against the
post-R2_F BASELINE on the FIRST HALF of games. Apply as a shrunk-mean
per-player-per-stat bias correction (shrinkage weight K=20, capped at
0.5 * pop_std per stat).

Strictly read-only. Writes scripts/_results/improve_R3_C_player_specific_bias.md
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

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402
import retro_inplay_mae as v1  # noqa: E402
from collections import defaultdict  # noqa: E402
import numpy as np  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# ---------------------------------------------------------------------------
# Module-level setup: build bias table once on import.
# ---------------------------------------------------------------------------
_qstats_df = v1.load_quarter_stats()
_games_sorted = sorted(_qstats_df["game_id"].unique().tolist())
_fit_games = set(_games_sorted[: len(_games_sorted) // 2])

# Pass 1: build per-player minutes index
player_min: dict = defaultdict(float)
for _gid in _games_sorted:
    _sub = _qstats_df[_qstats_df["game_id"] == _gid]
    for _, _r in _sub.iterrows():
        player_min[int(_r["player_id"])] += float(_r["min"])
top100 = set(sorted(player_min, key=player_min.get, reverse=True)[:100])

# Pass 2: compute biases on first half ONLY (no leakage)
sums: dict = defaultdict(lambda: {"sum": 0.0, "n": 0})
for _gid in _fit_games:
    _snap = v1.build_snapshot(_gid, "endQ3", _qstats_df)
    if _snap is None:
        continue
    _actuals = v1.actuals_for_game(_gid, _qstats_df)
    _b = BASELINE(_snap)  # post-R2_F baseline
    for (pid, stat), proj in _b.items():
        if pid not in top100:
            continue
        act = _actuals.get((pid, stat))
        if act is None:
            continue
        sums[(pid, stat)]["sum"] += proj - act  # positive = over-projection
        sums[(pid, stat)]["n"] += 1

# Compute pop_std per stat from fit set (for clipping)
_all_acts: dict = defaultdict(list)
for _gid in _fit_games:
    _actuals = v1.actuals_for_game(_gid, _qstats_df)
    for (pid, stat), act in _actuals.items():
        _all_acts[stat].append(act)

pop_std: dict = {}
for s in STATS:
    if _all_acts[s]:
        pop_std[s] = float(np.std(_all_acts[s]))
    else:
        pop_std[s] = 1.0

K = 20
bias: dict = {}
for (pid, stat), d in sums.items():
    if d["n"] < 5:
        continue
    raw_mean = d["sum"] / d["n"]
    b_val = (d["n"] * raw_mean) / (d["n"] + K)
    cap = 0.5 * pop_std.get(stat, 1.0)
    bias[(pid, stat)] = max(-cap, min(cap, b_val))


def treatment(snap: dict) -> dict:
    b = BASELINE(snap)
    out = {}
    for (pid, stat), proj in b.items():
        out[(pid, stat)] = proj - bias.get((pid, stat), 0.0)  # subtract over-projection
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()
    run_endq3_probe(
        "R3_C_player_specific_bias",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
