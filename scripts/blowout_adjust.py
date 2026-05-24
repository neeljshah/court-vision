"""blowout_adjust.py -- live blowout / garbage-time scaling for projections.

Cycle 88f (loop 5) -- live in-game adjustment for blowouts.

See `tests/test_blowout_adjust.py` for the 11-case rule-branch coverage
(each bucket, both monotonicity directions, pre-Q4 + OT + close-game
returns 1.0, and the 12-min -> 6.6-min starter integration check).

Why
---
When a Q4 margin reaches ~20 points, coaches pull starters early. Star prop
projections need to be scaled DOWN against their remaining-minutes baseline,
and bench projections need to be scaled UP because they pick up garbage-time
minutes. Sharp shops account for this; our model does not. This module is the
pure helper + CLI that bolts on top of `scripts/live_game_poll.py` (cycle 88a)
live snapshots and any per-player projection JSON.

Status
------
UNVALIDATED industry heuristic -- the bucket thresholds + scale factors are
hand-picked from public-source descriptions of how garbage time plays out
and are *not* fit on labeled data. Treat output as a directional adjustment,
not a calibrated probability shift. Cycle 88g (planned) will backtest these
factors against L5 closing-line splits to either validate or refit.

Rules (Q4 only -- pre-Q4 always returns 1.00)
---------------------------------------------
    margin_abs < 15                         -> 1.00 / 1.00   (competitive)
    Q4 margin 15-19                         -> 0.85 / 1.05   (mild lean)
    Q4 margin 20-29                         -> 0.55 / 1.30   (likely blowout)
    Q4 margin 30+                           -> 0.25 / 1.50   (garbage time)
    Q4 last 3:00, margin > 25               -> 0.10 / 1.60   (full-on blowout)

CLI
---
    python scripts/blowout_adjust.py \\
        --snapshot data/live/0022400123_1716583200.json \\
        --projection data/projections/0022400123.json

The projection JSON is expected to be a list of
    {"player_id": int, "name": str, "is_starter": bool, "remaining_min": float,
     "proj_pts": float, ...}
records; any numeric "proj_*" field gets scaled by the factor.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# -----------------------------------------------------------------------------
# Pure factor helper
# -----------------------------------------------------------------------------

def blowout_factor(margin_abs: int, period: int, clock_min_remaining: float,
                   is_starter: bool) -> float:
    """Return scale factor for remaining-stat projection given blowout state.

    Parameters
    ----------
    margin_abs : int
        Absolute score margin (always >= 0).
    period : int
        Current period (1-4 regulation, 5+ overtime).
    clock_min_remaining : float
        Minutes remaining in the current period (0.0 - 12.0 in regulation).
    is_starter : bool
        True if the player is a starter (cycle-61 lineups classification).

    Rules (industry heuristic, document as unvalidated):
      Pre-Q4 or margin < 15 -> 1.00 (no adjustment, game is competitive)
      Q4 margin 15-19 -> starters 0.85, bench 1.05  (mild lean)
      Q4 margin 20-29 -> starters 0.55, bench 1.30  (likely blowout)
      Q4 margin 30+   -> starters 0.25, bench 1.50  (garbage time confirmed)
      Margin > 25 in last 3 min Q4 -> starters 0.10, bench 1.60  (full-on)
    """
    # Overtime is by definition a one-possession game -- no garbage time.
    # Pre-Q4 we never adjust; coaches won't pull starters until Q4.
    if period < 4:
        return 1.00
    # In OT, treat like a competitive game.
    if period > 4:
        return 1.00
    if margin_abs < 15:
        return 1.00

    # Q4 confirmed, margin >= 15 -- the bucket cascade begins.
    # Most extreme rule first so it shadows the 30+ rule when both apply.
    if margin_abs > 25 and clock_min_remaining <= 3.0:
        return 0.10 if is_starter else 1.60
    if margin_abs >= 30:
        return 0.25 if is_starter else 1.50
    if margin_abs >= 20:
        return 0.55 if is_starter else 1.30
    # margin_abs in [15, 19]
    return 0.85 if is_starter else 1.05


# -----------------------------------------------------------------------------
# Snapshot-driven projection adjustment
# -----------------------------------------------------------------------------

# Numeric projection fields that get scaled. Conservative allowlist so we
# don't accidentally scale player_id or jersey number.
_SCALABLE_PREFIXES = ("proj_", "remaining_")


def apply_to_projections(snapshot: dict, projections: List[dict]) -> List[dict]:
    """Apply blowout factor to every projection given the live snapshot.

    `snapshot` follows the cycle-88a schema (see scripts/live_game_poll.py).
    `projections` is a list of per-player dicts; the function returns a NEW
    list with scaled values + an added `blowout_factor` audit field.
    """
    margin_abs = abs(int(snapshot.get("home_score", 0)) -
                     int(snapshot.get("away_score", 0)))
    period = int(snapshot.get("period", 0) or 0)
    clock_remaining = _clock_to_minutes(snapshot.get("clock", ""))

    # Build a starter lookup from the snapshot itself so we don't need
    # a second pass against the lineups loader.
    starter_lookup: Dict[int, bool] = {}
    for p in snapshot.get("players", []) or []:
        pid = int(p.get("player_id", 0) or 0)
        if pid:
            starter_lookup[pid] = bool(p.get("is_starter", False))

    out: List[dict] = []
    for proj in projections:
        adjusted = dict(proj)
        pid = int(proj.get("player_id", 0) or 0)
        is_starter = bool(proj.get("is_starter",
                                    starter_lookup.get(pid, False)))
        factor = blowout_factor(margin_abs, period, clock_remaining,
                                is_starter)
        adjusted["blowout_factor"] = factor
        if factor != 1.0:
            for k, v in proj.items():
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                if any(k.startswith(prefix) for prefix in _SCALABLE_PREFIXES):
                    adjusted[k] = round(float(v) * factor, 3)
        out.append(adjusted)
    return out


def _clock_to_minutes(clock: str) -> float:
    """Convert 'MM:SS' clock string to decimal minutes remaining."""
    s = (clock or "").strip()
    if not s:
        return 12.0
    if ":" not in s:
        try:
            return float(s)
        except ValueError:
            return 12.0
    try:
        mm, ss = s.split(":", 1)
        return round(float(mm) + float(ss) / 60.0, 2)
    except (ValueError, TypeError):
        return 12.0


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", required=True,
                    help="path to cycle-88a live snapshot JSON")
    ap.add_argument("--projection", required=True,
                    help="path to per-player projections JSON (list of dicts)")
    ap.add_argument("--out", default=None,
                    help="optional path to write adjusted JSON; "
                         "default prints to stdout")
    args = ap.parse_args()

    with open(args.snapshot, "r", encoding="utf-8") as fh:
        snap = json.load(fh)
    with open(args.projection, "r", encoding="utf-8") as fh:
        projs = json.load(fh)
    if not isinstance(projs, list):
        print("projection file must be a JSON list", file=sys.stderr)
        return 2

    adjusted = apply_to_projections(snap, projs)
    text = json.dumps(adjusted, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {len(adjusted)} adjusted rows -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
