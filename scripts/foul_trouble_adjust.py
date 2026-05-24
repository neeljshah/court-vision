"""foul_trouble_adjust.py — penalty factors for players in foul trouble.

Cycle 88e (loop 5) — companion to live_game_poll (88a) + predict_in_game (88b).

When a player has 4 fouls in Q3 or 5+ at any point, NBA coaches typically bench
them aggressively to avoid foul-out. Their remaining minutes drop ~30-50%
vs their typical pace; our pre-tip prop models do not react to this live
signal. This module wraps a small heuristic table that converts (pf, period,
clock_remaining) into a multiplicative penalty in [0.0, 1.0] which can be
applied to a projection's *remaining-minutes* component.

Factor table (industry intuition — UNVALIDATED until enough live snapshots
accumulate to fit empirically; see TODO at bottom of file):

    5+ fouls (any period)        -> 0.40   deep trouble, pulled aggressively
    4 fouls in Q3                 -> 0.55   classic "rest until Q4" benching
    4 fouls early Q4 (>6 min)     -> 0.65   leash shortened, still plays some
    4 fouls late  Q4 (<=6 min)    -> 0.90   coach lets them play, must win now
    3 fouls in Q2                 -> 0.80   common "save him for the half"
    otherwise                     -> 1.00   no penalty

CLI
---
    python scripts/foul_trouble_adjust.py --snapshot data/live/<gid>_<ts>.json
    python scripts/foul_trouble_adjust.py --snapshot snap.json --projection proj.json

The --projection JSON is the per-player FINAL-stat projection emitted by
`scripts/predict_in_game.py` (cycle 88b). When supplied, each player's
projection is scaled by the foul-trouble factor and printed alongside the
unadjusted baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Per-period regulation length (minutes). Used to estimate remaining clock
# from (period, clock_minutes_remaining) where the caller only knows the
# current quarter clock.
_PERIOD_LENGTH_MIN = 12.0
_REGULATION_PERIODS = 4

# Stats whose projection scales with remaining-minutes. Box-score counts
# (pts/reb/ast/stl/blk/tov/fg3m) are linear in floor time to first order —
# foul trouble cuts the minutes, the counts come down proportionally.
_MINUTE_SCALING_STATS = (
    "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min",
)


# ─────────────────────────────────────────────────────────────────────────────
# Core heuristic
# ─────────────────────────────────────────────────────────────────────────────

# Cycle 89b (loop 5): canonical table moved to src.prediction.live_factors.
# This module's public API (foul_trouble_factor, apply_factor_to_projection,
# adjust_snapshot, clock_str_to_minutes) is preserved — we just re-export the
# unified implementation so all three legacy entry points agree on every input.
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402,F401


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot + projection helpers
# ─────────────────────────────────────────────────────────────────────────────

def clock_str_to_minutes(clock: str) -> float:
    """Convert a 'MM:SS' display clock to decimal minutes. '' or junk -> 12.0.

    Defaults to a full period (12.0 min) when the clock is missing, which is
    the safe assumption pre-tip / between periods.
    """
    if not clock:
        return _PERIOD_LENGTH_MIN
    s = str(clock).strip()
    if ":" not in s:
        try:
            return float(s)
        except (ValueError, TypeError):
            return _PERIOD_LENGTH_MIN
    try:
        mm, ss = s.split(":", 1)
        return round(float(mm) + float(ss) / 60.0, 3)
    except (ValueError, TypeError):
        return _PERIOD_LENGTH_MIN


def apply_factor_to_projection(projection: Dict[str, Any],
                               factor: float) -> Dict[str, Any]:
    """Scale a per-player projection dict by the foul-trouble factor.

    Only minute-linear stats (counts + min) are scaled. Percentage / rate
    stats (e.g. ts_pct, usage) are passed through untouched.
    """
    adjusted = dict(projection)
    for stat in _MINUTE_SCALING_STATS:
        if stat in adjusted:
            try:
                adjusted[stat] = round(float(adjusted[stat]) * factor, 3)
            except (TypeError, ValueError):
                continue
    adjusted["foul_trouble_factor"] = round(float(factor), 3)
    return adjusted


def adjust_snapshot(snapshot: Dict[str, Any],
                    projection_by_pid: Optional[Dict[int, Dict[str, Any]]] = None
                    ) -> List[Dict[str, Any]]:
    """Compute per-player foul-trouble factors + (optionally) adjusted projections.

    Parameters
    ----------
    snapshot : dict
        Live-state JSON written by `scripts/live_game_poll.py`. Must have a
        top-level `period` + `clock` and a `players` list whose rows carry
        `player_id`, `name`, `team`, `pf`.
    projection_by_pid : dict[int, dict] | None
        Optional FINAL-stat projections (from `predict_in_game.py`) keyed by
        player_id. When provided, each row's projection is scaled by the
        factor and included under `adjusted_projection`.

    Returns
    -------
    list[dict]
        One row per player with id/name/team/pf/factor + (optionally) the
        baseline + adjusted projection.
    """
    period = int(snapshot.get("period", 0) or 0)
    clock_min = clock_str_to_minutes(snapshot.get("clock", ""))

    rows: List[Dict[str, Any]] = []
    for p in snapshot.get("players", []) or []:
        pf = int(p.get("pf", 0) or 0)
        factor = foul_trouble_factor(pf, period, clock_min)
        row: Dict[str, Any] = {
            "player_id": int(p.get("player_id", 0) or 0),
            "name":      str(p.get("name", "") or ""),
            "team":      str(p.get("team", "") or ""),
            "pf":        pf,
            "period":    period,
            "clock_min": round(clock_min, 2),
            "factor":    round(factor, 3),
        }
        if projection_by_pid:
            proj = projection_by_pid.get(row["player_id"])
            if proj is not None:
                row["projection"] = proj
                row["adjusted_projection"] = apply_factor_to_projection(
                    proj, factor)
        rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _index_projection(raw: Any) -> Dict[int, Dict[str, Any]]:
    """Accept either {pid: {...}} or [{player_id: pid, ...}, ...]."""
    if isinstance(raw, dict):
        try:
            return {int(k): v for k, v in raw.items()}
        except (ValueError, TypeError):
            pass
    if isinstance(raw, list):
        out: Dict[int, Dict[str, Any]] = {}
        for row in raw:
            pid = row.get("player_id") if isinstance(row, dict) else None
            if pid is not None:
                try:
                    out[int(pid)] = row
                except (ValueError, TypeError):
                    continue
        return out
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Apply foul-trouble penalty factors to live in-game "
                    "projections.")
    ap.add_argument("--snapshot", required=True,
                    help="Path to live-state JSON from live_game_poll.py.")
    ap.add_argument("--projection", default=None,
                    help="Optional projection JSON from predict_in_game.py "
                         "(either {pid: proj} or [{player_id, ...}, ...]).")
    ap.add_argument("--only-trouble", action="store_true",
                    help="Print only players whose factor < 1.0.")
    args = ap.parse_args()

    snapshot = _load_json(args.snapshot)
    proj_idx = (_index_projection(_load_json(args.projection))
                if args.projection else None)

    rows = adjust_snapshot(snapshot, proj_idx)
    if args.only_trouble:
        rows = [r for r in rows if r["factor"] < 1.0]

    period = snapshot.get("period")
    clock = snapshot.get("clock")
    print(f"[foul_trouble_adjust] {snapshot.get('game_id','?')}  "
          f"Q{period} {clock}  ({len(rows)} player(s) shown)")
    for r in rows:
        line = (f"  {r['name']:<24} {r['team']:<4} "
                f"pf={r['pf']}  factor={r['factor']:.2f}")
        if "adjusted_projection" in r:
            base = r["projection"]
            adj = r["adjusted_projection"]
            for stat in ("pts", "reb", "ast"):
                if stat in base:
                    line += f"  {stat}:{base[stat]}->{adj[stat]}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ─────────────────────────────────────────────────────────────────────────────
# TODO — empirical calibration
# ─────────────────────────────────────────────────────────────────────────────
# The factor table above is industry heuristic. Once `data/live/` has
# accumulated enough completed games (~30 with foul-trouble incidents),
# replace each constant with a fitted estimator:
#
#   1. Join each (player, snapshot) where pf >= 3 to the player's actual
#      remaining-minutes-played for the rest of that game (from the FINAL
#      snapshot).
#   2. Group by (pf, period, clock_bucket); compute mean(actual_remaining /
#      expected_remaining_at_normal_pace).
#   3. Replace the constants with the empirical ratios. Add a confidence
#      interval and fall back to the heuristic when the bucket sample is
#      < 10 incidents.
#
# Track in vault/Improvements/Tracker Improvements Log.md once calibrated.
