"""probe_111_l20_l5_ablation.py -- cycle 111 (loop 5).

Measures the L20/L5 share of the cycle-110 gain. Three arms over the same
1508-game endQ3 corpus:
  A. baseline (heuristic foul_factor) -- pre-cycle-110 production
  B. learned-Q4-minutes WITH full date-aware L20/L5 lookups -- probe 110
  C. learned-Q4-minutes WITH empty L20/L5 dicts -- the actual live wiring

Reports per-stat MAE for A/B/C, deltas (C-A, C-B), and walk-forward folds.
Writes scripts/_results/l20_l5_ablation_v1.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402
import train_minute_trajectory as tmt  # noqa: E402
from probe_minute_trajectory_replacement import (  # noqa: E402
    project_snapshot_with_learned_minutes,
)
from src.prediction.minute_trajectory import MinuteTrajectoryModel  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _mae(xs: List[float]) -> float:
    return (sum(xs) / len(xs)) if xs else float("nan")


def run(max_games: Optional[int] = None, output: Optional[str] = None) -> int:
    model = MinuteTrajectoryModel.load()
    if model is None:
        print("  ERROR: minute_trajectory.lgb missing")
        return 2
    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()
    print(f"  {len(games)} games")

    per_game_l20: Dict[str, Dict[int, float]] = {}
    per_game_l5: Dict[str, Dict[int, float]] = {}
    for gid in games:
        target_date = tmt.find_game_date_for_game(gid, qstats_df, pid_log_index)
        gpids = set(int(pid) for pid in
                    qstats_df[qstats_df["game_id"] == gid]["player_id"].unique())
        l20m: Dict[int, float] = {}
        l5m: Dict[int, float] = {}
        for pid in gpids:
            l20 = tmt.rolling_mean_min(pid, target_date, 20, pid_log_index)
            l5 = tmt.rolling_mean_min(pid, target_date, 5, pid_log_index)
            if l20 is not None:
                l20m[pid] = l20
            if l5 is not None:
                l5m[pid] = l5
        per_game_l20[gid] = l20m
        per_game_l5[gid] = l5m

    err = {arm: {gid: {s: [] for s in STATS} for gid in games}
           for arm in ("A", "B", "C")}

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        a_projs = v1.project_snapshot_to_finals(snap)
        b_projs = project_snapshot_with_learned_minutes(
            snap, model, positions,
            per_game_l20.get(gid, {}), per_game_l5.get(gid, {}),
        )
        c_projs = project_snapshot_with_learned_minutes(
            snap, model, positions, {}, {},
        )
        for (pid, stat), aval in a_projs.items():
            actual = actuals.get((pid, stat))
            bval = b_projs.get((pid, stat))
            cval = c_projs.get((pid, stat))
            if actual is None or bval is None or cval is None:
                continue
            err["A"][gid][stat].append(abs(aval - actual))
            err["B"][gid][stat].append(abs(bval - actual))
            err["C"][gid][stat].append(abs(cval - actual))

    # Aggregate per-stat MAE.
    agg: Dict[str, Dict[str, List[float]]] = {arm: {s: [] for s in STATS}
                                              for arm in ("A", "B", "C")}
    for gid in games:
        for arm in ("A", "B", "C"):
            for s in STATS:
                agg[arm][s].extend(err[arm][gid][s])

    per_stat = []
    for s in STATS:
        a = _mae(agg["A"][s])
        b = _mae(agg["B"][s])
        c = _mae(agg["C"][s])
        per_stat.append({
            "stat": s, "n": len(agg["A"][s]),
            "A": a, "B": b, "C": c,
            "C_minus_A": c - a, "C_minus_B": c - b,
        })

    # Walk-forward 4-fold on PTS for arm C vs A.
    n = len(games)
    fold_size = n // 4
    fold_results = []
    for fi in range(4):
        lo = fi * fold_size
        hi = n if fi == 3 else (fi + 1) * fold_size
        fold_games = games[lo:hi]
        a_pts: List[float] = []
        c_pts: List[float] = []
        for gid in fold_games:
            a_pts.extend(err["A"][gid]["pts"])
            c_pts.extend(err["C"][gid]["pts"])
        fold_results.append({
            "fold": fi + 1, "n_games": len(fold_games),
            "A": _mae(a_pts), "C": _mae(c_pts),
            "delta": _mae(c_pts) - _mae(a_pts),
        })

    # Decision.
    max_gap = max(abs(r["C_minus_B"]) for r in per_stat)
    any_big_gap = any(r["C_minus_B"] >= 0.05 for r in per_stat)
    safe_to_close = max_gap <= 0.02
    wf_all_neg = all(f["delta"] <= 0 for f in fold_results)

    # Report.
    lines = []
    lines.append("# cycle 111 -- L20/L5 ablation (live-wiring regression check)")
    lines.append("")
    lines.append(f"Games: {len(games)}")
    lines.append("")
    lines.append("## endQ3 MAE per stat -- three arms")
    lines.append("")
    lines.append("| stat | n | A heuristic | B learned+L20/L5 | C learned+empty | C-A | C-B |")
    lines.append("|------|---|-------------|------------------|-----------------|-----|-----|")
    for r in per_stat:
        lines.append(
            f"| {r['stat']} | {r['n']} | {r['A']:.4f} | "
            f"{r['B']:.4f} | {r['C']:.4f} | {r['C_minus_A']:+.4f} | "
            f"{r['C_minus_B']:+.4f} |"
        )
    lines.append("")
    lines.append("## Walk-forward PTS (arm C vs A)")
    lines.append("")
    lines.append("| fold | games | A | C | delta |")
    lines.append("|------|-------|---|---|-------|")
    for f in fold_results:
        lines.append(f"| {f['fold']} | {f['n_games']} | {f['A']:.4f} | "
                     f"{f['C']:.4f} | {f['delta']:+.4f} |")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(f"- max |C-B| across stats: **{max_gap:.4f}**")
    lines.append(f"- any stat C-B >= 0.05: **{any_big_gap}**")
    lines.append(f"- WF 4/4 PTS (C vs A) all <= 0: **{wf_all_neg}**")
    lines.append("")
    if safe_to_close:
        lines.append("- **NO-OP** -- empty-dict wiring is acceptable; "
                     "L20/L5 contributes <=0.02 MAE per stat. Close question, "
                     "advance to next frontier.")
    elif any_big_gap:
        lines.append("- **CYCLE 112 ACTION** -- thread date-aware L20/L5 "
                     "lookups into `_apply_learned_q4_minutes`. Live regresses "
                     ">=0.05 MAE on at least one stat vs the probe number.")
    else:
        lines.append("- **MIXED** -- some stats >0.02 but <0.05 gap. "
                     "Consider date-aware lookups; not urgent.")
    lines.append("")

    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "l20_l5_ablation_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  wrote {out_path}")
    print(f"  max |C-B|={max_gap:.4f}  any_big_gap={any_big_gap}  "
          f"WF_allneg={wf_all_neg}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
