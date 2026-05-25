"""scripts/improve_loop/state.py -- compounding loop state.

JSON-backed registry of probes the loop has tried, what shipped, what was
rejected, and what's saturated. Planning agents read this BEFORE proposing
a new probe so they don't re-attempt rejected angles.

Schema:
{
  "rounds_completed": 0,
  "ships": [
    {"name": "110_learned_q4_minutes", "round": 0, "delta_pts": -0.2312,
     "stats_won": 7, "commit": "fe27de4a", "date": "2026-05-25"}
  ],
  "rejects": [
    {"name": "109a_endq3_period_head", "reason": "1/7 wins", "round": 0,
     "saturated_angle": "endq3 LightGBM head replacement"}
  ],
  "saturated_angles": [
    "endq3 period head", "multitask MLP live", "AST opp_def_l5",
    "center-BLK opp shrinkage", "Q4 foul forecast heuristic",
    "foul-rate shrinkage heuristic", "garbage-time v1", "b2b veteran",
    "top-decile pull", "high-min bidirectional", "Q1 pace residual",
    "heat-check shrinkage heuristic", "per-position stratified PTS",
    "all cycle 99-101 retrain attempts"
  ],
  "current_baseline_mae": {"pts": 2.2140, "reb": 0.8987, "ast": 0.5755,
                          "fg3m": 0.3528, "stl": 0.2506, "blk": 0.1543,
                          "tov": 0.3663}
}
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_PATH = os.path.join(PROJECT_DIR, "scripts", "improve_loop", "state.json")


_DEFAULT_STATE = {
    "rounds_completed": 0,
    "ships": [
        {"name": "110_learned_q4_minutes", "round": 0, "delta_pts": -0.2312,
         "stats_won": 7, "commit": "fe27de4a", "date": "2026-05-25",
         "summary": "Replaced heuristic foul_trouble_factor with learned "
                    "Q4 minutes from MinuteTrajectoryModel for all period=4 "
                    "players. 7/7 win, WF 4/4."},
        {"name": "112_quantile_recal", "round": 0, "delta_pts": 0.0,
         "stats_won": 14, "commit": "post-110-cal",
         "date": "2026-05-25",
         "summary": "Recalibrated quantile bands against new tighter endQ3 "
                    "projections; 7/7 stats at endQ2 AND endQ3 hit 0.80 "
                    "coverage target."},
    ],
    "rejects": [
        {"name": "109a_endq3_period_head", "reason": "1/7 wins",
         "saturated_angle": "endq3 LightGBM head replacement"},
        {"name": "106d_center_blk_opp_shrinkage", "reason": "WF 0/4",
         "saturated_angle": "center-BLK opp shrinkage"},
        {"name": "104e_pts_stratified_position", "reason": "Guard regresses",
         "saturated_angle": "per-position stratified PTS"},
        {"name": "111_l20_l5_ablation", "reason": "no-op (live wiring safe)",
         "saturated_angle": "L20/L5 rolling features in learned-Q4 live"},
    ],
    "saturated_angles": [
        "endq3 LightGBM period head replacement",
        "multitask MLP live",
        "AST opp_def_l5 (0.045 = noise)",
        "center-BLK opp shrinkage",
        "Q4 foul forecast heuristic v1/v2/v3",
        "foul-rate shrinkage heuristic v1/v2/v3",
        "star_pulled bias (trap)",
        "all cycle 99-101 retrain attempts",
        "garbage-time v1",
        "b2b veteran selection bias",
        "top-decile pull",
        "high-min bidirectional",
        "Q1 pace residual",
        "heat-check shrinkage heuristic",
        "per-position stratified PTS",
        "blowout_residual on top of learned-Q4 (composes poorly)",
        "foul_residual on top of learned-Q4 (trained against replaced heuristic)",
    ],
    "current_baseline_mae": {
        "pts": 2.2140, "reb": 0.8987, "ast": 0.5755, "fg3m": 0.3528,
        "stl": 0.2506, "blk": 0.1543, "tov": 0.3663,
    },
    "open_frontier": [
        "Apply learned-minute mechanism at endQ1/endQ2 (replace period_specific_heads)",
        "Train Q3-remaining-minutes head and wire at endQ2",
        "Re-test opp_def_BLK_l5 on tighter post-110 baseline",
        "Re-test opp_def_REB_l5 on tighter post-110 baseline",
        "Position-aware Q4 minute shrinkage on learned baseline",
        "Lineup pace adjustment via recent 5-on-5 net pace",
        "Score margin shrinkage on learned baseline (different than blowout_residual)",
        "Per-player Q4 pace volatility (variance estimate -> wider quantiles)",
    ],
}


def load() -> dict:
    if not os.path.exists(STATE_PATH):
        save(_DEFAULT_STATE)
        return dict(_DEFAULT_STATE)
    with open(STATE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE_PATH)


def record_ship(name: str, delta_pts: float, stats_won: int,
                commit: str, summary: str) -> None:
    s = load()
    from datetime import date
    s["ships"].append({
        "name": name, "round": s.get("rounds_completed", 0),
        "delta_pts": delta_pts, "stats_won": stats_won,
        "commit": commit, "date": date.today().isoformat(),
        "summary": summary,
    })
    save(s)


def record_reject(name: str, reason: str, saturated_angle: str) -> None:
    s = load()
    s["rejects"].append({
        "name": name, "reason": reason,
        "saturated_angle": saturated_angle,
        "round": s.get("rounds_completed", 0),
    })
    if saturated_angle and saturated_angle not in s["saturated_angles"]:
        s["saturated_angles"].append(saturated_angle)
    save(s)


def bump_round() -> int:
    s = load()
    s["rounds_completed"] = int(s.get("rounds_completed", 0)) + 1
    save(s)
    return s["rounds_completed"]


def update_baseline(per_stat_mae: Dict[str, float]) -> None:
    s = load()
    s["current_baseline_mae"].update(per_stat_mae)
    save(s)


def saturated_summary() -> str:
    """One-line list — feed into planning agents to prevent re-attempts."""
    s = load()
    return "; ".join(s["saturated_angles"])


def frontier_summary() -> List[str]:
    return list(load().get("open_frontier", []))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        save(_DEFAULT_STATE)
        print(f"  wrote {STATE_PATH}")
    else:
        s = load()
        print(f"  rounds:      {s.get('rounds_completed', 0)}")
        print(f"  ships:       {len(s.get('ships', []))}")
        print(f"  rejects:     {len(s.get('rejects', []))}")
        print(f"  saturated:   {len(s.get('saturated_angles', []))}")
        print(f"  frontier:    {len(s.get('open_frontier', []))}")
        print(f"  baseline:    {s.get('current_baseline_mae', {})}")
