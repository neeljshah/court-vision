"""probe_R2_C_position_residual_shrinkage.py -- R2-C probe (loop 5).

Per-(position, stat) multiplicative residual shrinkage on the learned-Q4
baseline. Factors are fit on the first half of games (chronologically)
to avoid leakage; applied to all games. Scaffold runs WF 4-fold.
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

from collections import defaultdict  # noqa: E402

import retro_inplay_mae as v1  # noqa: E402
import train_minute_trajectory as tmt  # noqa: E402
from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _bucket_pos(pos_str):
    if not pos_str:
        return None
    h = str(pos_str).upper().split("/")[0].split("-")[0]
    if h in {"PG", "SG", "G"}:
        return "G"
    if h in {"SF", "PF", "F"}:
        return "F"
    if h == "C":
        return "C"
    return None


# module load
_positions = tmt.load_positions()
_qstats_df = v1.load_quarter_stats()
_games_sorted = sorted(_qstats_df["game_id"].unique().tolist())
_fit_games = set(_games_sorted[: len(_games_sorted) // 2])

# fit residual factors
_sums = defaultdict(lambda: {"num": 0.0, "den": 0.0, "n": 0})
for gid in _fit_games:
    snap = v1.build_snapshot(gid, "endQ3", _qstats_df)
    if snap is None:
        continue
    actuals = v1.actuals_for_game(gid, _qstats_df)
    b = BASELINE(snap)
    for p in snap.get("players") or []:
        pid = int(p["player_id"])
        pos = _bucket_pos(_positions.get(pid))
        if pos is None:
            continue
        for s in STATS:
            cur = float(p.get(s, 0.0) or 0.0)
            proj = b.get((pid, s))
            act = actuals.get((pid, s))
            if proj is None or act is None:
                continue
            remaining = proj - cur
            if remaining <= 0.05:
                continue
            actual_remaining = act - cur
            d = _sums[(pos, s)]
            d["num"] += actual_remaining
            d["den"] += remaining
            d["n"] += 1

K = 200
_factor = {}
for k, d in _sums.items():
    if d["n"] < 50:
        _factor[k] = 1.0
        continue
    raw = d["num"] / max(d["den"], 1e-6)
    f = (d["n"] * raw + K * 1.0) / (d["n"] + K)
    _factor[k] = max(0.85, min(1.15, f))


def treatment(snap):
    b = BASELINE(snap)
    out = {}
    pid_to_player = {int(p["player_id"]): p for p in (snap.get("players") or [])}
    for (pid, stat), proj in b.items():
        p = pid_to_player.get(pid)
        if p is None:
            out[(pid, stat)] = proj
            continue
        pos = _bucket_pos(_positions.get(pid))
        cur = float(p.get(stat, 0.0) or 0.0)
        remaining = proj - cur
        f = _factor.get((pos, stat), 1.0) if pos else 1.0
        out[(pid, stat)] = cur + max(0.0, remaining) * f
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()
    run_endq3_probe(
        "R2_C_position_residual_shrinkage",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
