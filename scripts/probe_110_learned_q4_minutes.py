"""probe_110_learned_q4_minutes.py -- cycle 110 (loop 5).

Re-evaluates the existing learned-Q4-minute substitution (from
probe_minute_trajectory_replacement.py) under the cycle-110 ship gate:

  - 7-stat MAE delta on full corpus
  - 4-fold walk-forward split by game_id (sorted ascending)
  - SHIP iff WF 4/4 PTS folds <= 0 AND mean PTS delta <= -0.005 AND
    single-split PTS strictly down AND >=4/7 stats with single-split
    MAE delta <= -0.005.

Strictly read-only. Writes scripts/_results/learned_q4_minutes_v1.md.
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
        print("  ERROR: minute_trajectory.lgb not found")
        return 2

    qstats_df = v1.load_quarter_stats()
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()
    print(f"  {len(games)} games  {len(positions)} positions")

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

    # Per-game per-stat absolute error accumulators (fold-attributable).
    base_err: Dict[str, Dict[str, List[float]]] = {
        gid: {s: [] for s in STATS} for gid in games
    }
    treat_err: Dict[str, Dict[str, List[float]]] = {
        gid: {s: [] for s in STATS} for gid in games
    }

    for gid in games:
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)
        base_projs = v1.project_snapshot_to_finals(snap)
        treat_projs = project_snapshot_with_learned_minutes(
            snap, model, positions,
            per_game_l20.get(gid, {}), per_game_l5.get(gid, {}),
        )
        for (pid, stat), bval in base_projs.items():
            actual = actuals.get((pid, stat))
            tval = treat_projs.get((pid, stat))
            if actual is None or tval is None:
                continue
            base_err[gid][stat].append(abs(bval - actual))
            treat_err[gid][stat].append(abs(tval - actual))

    # Single-split MAE.
    base_all: Dict[str, List[float]] = {s: [] for s in STATS}
    treat_all: Dict[str, List[float]] = {s: [] for s in STATS}
    for gid in games:
        for s in STATS:
            base_all[s].extend(base_err[gid][s])
            treat_all[s].extend(treat_err[gid][s])

    # 4-fold walk-forward (games sorted ascending).
    n = len(games)
    fold_size = n // 4
    fold_results: List[Dict[str, float]] = []
    for fi in range(4):
        lo = fi * fold_size
        hi = n if fi == 3 else (fi + 1) * fold_size
        fold_games = games[lo:hi]
        b_pts: List[float] = []
        t_pts: List[float] = []
        for gid in fold_games:
            b_pts.extend(base_err[gid]["pts"])
            t_pts.extend(treat_err[gid]["pts"])
        bm, tm = _mae(b_pts), _mae(t_pts)
        fold_results.append({"fold": fi + 1, "n_games": len(fold_games),
                             "n_rows": len(b_pts),
                             "base": bm, "treat": tm, "delta": tm - bm})

    # Compute single-split per-stat deltas + wins.
    per_stat: List[dict] = []
    n_wins = 0
    for s in STATS:
        bm = _mae(base_all[s])
        tm = _mae(treat_all[s])
        d = tm - bm
        per_stat.append({"stat": s, "n": len(base_all[s]),
                         "base": bm, "treat": tm, "delta": d})
        if d <= -0.005:
            n_wins += 1

    pts_d = per_stat[0]["delta"]
    wf_mean_pts = sum(f["delta"] for f in fold_results) / 4.0
    wf_all_nonpos = all(f["delta"] <= 0 for f in fold_results)

    ship = (
        wf_all_nonpos
        and wf_mean_pts <= -0.005
        and pts_d < 0
        and n_wins >= 4
    )

    # Markdown report.
    lines: List[str] = []
    lines.append("# cycle 110 -- learned Q4 minutes (global endQ3 swap)")
    lines.append("")
    lines.append(f"**Games:** {len(games)}  **Stats:** 7")
    lines.append("")
    lines.append("Replaces heuristic `foul_trouble_factor` with "
                 "`learned_remaining_min/12.0` from "
                 "`MinuteTrajectoryModel` for ALL period=4 players (not just "
                 "foul-trouble). Pace + blowout + bench logic unchanged. "
                 "Identical mechanism to "
                 "`probe_minute_trajectory_replacement.py` but evaluated "
                 "under cycle-110 7-stat + walk-forward ship gate.")
    lines.append("")
    lines.append("## Single-split (full corpus) endQ3 MAE")
    lines.append("")
    lines.append("| stat | n | baseline | treat | delta | win? |")
    lines.append("|------|---|----------|-------|-------|------|")
    for r in per_stat:
        win = "Y" if r["delta"] <= -0.005 else "."
        lines.append(f"| {r['stat']} | {r['n']} | {r['base']:.4f} | "
                     f"{r['treat']:.4f} | {r['delta']:+.4f} | {win} |")
    lines.append("")
    lines.append(f"Wins (delta <= -0.005): **{n_wins}/7**")
    lines.append("")
    lines.append("## Walk-forward 4-fold (PTS, game_id sorted)")
    lines.append("")
    lines.append("| fold | games | rows | base PTS | treat PTS | delta |")
    lines.append("|------|-------|------|----------|-----------|-------|")
    for f in fold_results:
        lines.append(f"| {f['fold']} | {f['n_games']} | {f['n_rows']} | "
                     f"{f['base']:.4f} | {f['treat']:.4f} | "
                     f"{f['delta']:+.4f} |")
    lines.append("")
    lines.append(f"WF mean PTS delta: **{wf_mean_pts:+.4f}**  "
                 f"all folds <= 0: **{wf_all_nonpos}**")
    lines.append("")
    lines.append("## Ship gate")
    lines.append("")
    lines.append(f"- WF 4/4 folds non-positive: **{wf_all_nonpos}**")
    lines.append(f"- WF mean PTS delta <= -0.005: "
                 f"**{wf_mean_pts <= -0.005}** ({wf_mean_pts:+.4f})")
    lines.append(f"- Single-split PTS strictly down: **{pts_d < 0}** "
                 f"({pts_d:+.4f})")
    lines.append(f"- >=4/7 stats with delta <= -0.005: **{n_wins >= 4}** "
                 f"({n_wins}/7)")
    lines.append("")
    if ship:
        lines.append("- **SHIP** -- wire learned-Q4-minutes into "
                     "`live_engine` endQ3 path.")
    else:
        lines.append("- **REJECT** -- global learned-minute swap saturated "
                     "at endQ3.")
    lines.append("")
    report = "\n".join(lines) + "\n"

    out_path = output or os.path.join(
        PROJECT_DIR, "scripts", "_results", "learned_q4_minutes_v1.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"  wrote {out_path}")
    print(f"  SHIP={ship}  PTS_d={pts_d:+.4f}  wins={n_wins}/7  "
          f"WF_mean={wf_mean_pts:+.4f}  WF_allneg={wf_all_nonpos}")
    return 0 if ship else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    return run(max_games=args.max_games, output=args.output)


if __name__ == "__main__":
    sys.exit(main())
