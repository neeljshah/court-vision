"""Calibrated, coherent live win probability — margin + seconds-remaining -> P(home win).

Model: P(home win) = Φ( (margin + drift) / sd(t_rem) )
  sd(t_rem) = SD_FINAL * sqrt(t_rem / REG_TOTAL_SEC) + SD_FLOOR

Time-decaying: a lead late in the game produces higher confidence than the same lead
early. The formula collapses to 0.5 at margin=0 for any t_rem.

Honesty class: serve_human (paper scaffold). NOT wired into api/, golive, or any
real-money path. Outputs are diagnostic only.

Calibration note: reliability_check reports n_games AND n_samples separately;
within-game samples are autocorrelated so per-step sample count overstates
effective degrees of freedom. All calibration claims should be treated as
directional, not ground truth.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup (importable as a script from repo root or scripts/)
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from src.sim.live_game_simulator import (  # noqa: E402
    REG_TOTAL_SEC,
    _clock_to_sec,
    _sec_remaining,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_CACHE = str(_REPO / "data" / "cache" / "team_system")

SD_FINAL = 13.5   # empirical ~playoff final-margin SD; calibrate vs data, not asserted as truth
SD_FLOOR = 0.5    # prevents division by zero and keeps P well-defined at buzzer


# ---------------------------------------------------------------------------
# Core probability model
# ---------------------------------------------------------------------------
def live_win_prob(
    margin: float,
    sec_remaining: float,
    *,
    sd_final: float = SD_FINAL,
    sd_floor: float = SD_FLOOR,
    drift: float = 0.0,
) -> float:
    """Calibrated P(home win) from current margin and seconds remaining.

    Parameters
    ----------
    margin:        home_score - away_score (state through the current play only)
    sec_remaining: game seconds left (use _sec_remaining(period, clock_sec))
    drift:         optional home-court term (default 0 = keep honest/simple)

    Returns float in [0, 1]. Tie + no time remaining => 0.5 (overtime model).
    """
    sd = sd_final * math.sqrt(max(sec_remaining, 0.0) / REG_TOTAL_SEC) + sd_floor
    z = (margin + drift) / sd
    # Φ(z) via math.erfc for Py 3.9 compatibility
    return float(0.5 * math.erfc(-z / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Coherence reconciliation
# ---------------------------------------------------------------------------
def reconcile_winprob_with_score(
    home_score: float,
    away_score: float,
    proj_home_final: float,
    proj_away_final: float,
    sec_remaining: float,
    *,
    sd_final: float = SD_FINAL,
    sd_floor: float = SD_FLOOR,
) -> Dict[str, object]:
    """Derive win% from the PROJECTED final margin so win% and projected scores agree.

    Coherence invariant: sign(proj_margin) should match (win_prob > 0.5).
    Returns dict with win_prob, proj_margin, sd_used, coherent (bool).
    """
    proj_margin = float(proj_home_final) - float(proj_away_final)
    sd = sd_final * math.sqrt(max(sec_remaining, 0.0) / REG_TOTAL_SEC) + sd_floor
    z = proj_margin / sd
    win_prob = float(0.5 * math.erfc(-z / math.sqrt(2)))
    coherent = bool(
        (proj_margin > 0 and win_prob > 0.5)
        or (proj_margin < 0 and win_prob < 0.5)
        or (proj_margin == 0 and abs(win_prob - 0.5) < 1e-9)
    )
    return {
        "win_prob": round(win_prob, 4),
        "proj_margin": round(proj_margin, 2),
        "sd_used": round(sd, 3),
        "coherent": coherent,
    }


# ---------------------------------------------------------------------------
# Reliability check (honest small-n calibration)
# ---------------------------------------------------------------------------
def _load_pbp_raw(gid: str, cache: str = DEFAULT_CACHE) -> Optional[List[dict]]:
    """Return sorted actions list or None if file missing."""
    path = os.path.join(cache, "pbp", f"{gid}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    actions = d.get("game", {}).get("actions", [])
    return sorted(actions, key=lambda a: a.get("orderNumber", 0))


def _load_box_raw(gid: str, cache: str = DEFAULT_CACHE) -> Optional[dict]:
    """Return raw box JSON or None if file missing."""
    path = os.path.join(cache, "box", f"{gid}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reliability_check(
    gids: List[str],
    cache: str = DEFAULT_CACHE,
    bins: int = 5,
) -> dict:
    """Walk each game's PBP, compute live_win_prob at scoring actions, compare to outcome.

    Returns a dict with Brier score, per-bin calibration, and an honest caveat.
    Autocorrelation note: samples within a game are autocorrelated -> n_games is the
    correct independent-sample count for headline calibration claims, not n_samples.
    """
    samples: List[tuple[float, int]] = []  # (pred, outcome) outcome=1 if home won
    n_games_processed = 0

    for gid in gids:
        actions = _load_pbp_raw(gid, cache)
        box = _load_box_raw(gid, cache)
        if actions is None or box is None:
            continue

        g = box.get("game", {})
        home_tri = g.get("homeTeam", {}).get("teamTricode", "")
        home_final = int(g.get("homeTeam", {}).get("score", 0))
        away_final = int(g.get("awayTeam", {}).get("score", 0))
        home_won = 1 if home_final > away_final else 0

        for a in actions:
            # Only score at possession-changing events to thin autocorrelated chain
            if a.get("actionType") not in ("2pt", "3pt", "freethrow", "period"):
                continue
            if a.get("actionType") in ("2pt", "3pt") and a.get("shotResult") != "Made":
                continue
            period = int(a.get("period", 1) or 1)
            clock_sec = _clock_to_sec(a.get("clock"))
            sec_rem = _sec_remaining(period, clock_sec)
            try:
                home_score = int(a.get("scoreHome", 0))
                away_score = int(a.get("scoreAway", 0))
            except (TypeError, ValueError):
                continue
            # Identify home from box (box homeTeam is authoritative)
            margin = home_score - away_score
            pred = live_win_prob(margin, sec_rem)
            samples.append((pred, home_won))

        n_games_processed += 1

    if not samples:
        return {
            "n_games": 0,
            "n_samples": 0,
            "brier": None,
            "bins": [],
            "caveat": "no valid game data found",
        }

    preds = [s[0] for s in samples]
    outcomes = [s[1] for s in samples]
    n = len(samples)

    brier = float(sum((p - o) ** 2 for p, o in samples) / n)

    # Calibration bins
    bin_edges = [i / bins for i in range(bins + 1)]
    bin_data = []
    for i in range(bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        in_bin = [(p, o) for p, o in samples if lo <= p < hi]
        if i == bins - 1:  # include right edge in last bin
            in_bin = [(p, o) for p, o in samples if lo <= p <= hi]
        if in_bin:
            mean_pred = sum(p for p, _ in in_bin) / len(in_bin)
            emp_freq = sum(o for _, o in in_bin) / len(in_bin)
            bin_data.append({
                "range": f"[{lo:.1f},{hi:.1f})",
                "mean_pred": round(mean_pred, 3),
                "emp_freq": round(emp_freq, 3),
                "n": len(in_bin),
            })

    caveat = (
        f"n_games={n_games_processed}; n_samples={n} (autocorrelated within game); "
        f"reliability is small-n, treat as directional only"
    )

    return {
        "n_games": n_games_processed,
        "n_samples": n,
        "brier": round(brier, 4),
        "bins": bin_data,
        "caveat": caveat,
    }


# ---------------------------------------------------------------------------
# CLI self-test and reliability report
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Live win% reliability check")
    parser.add_argument(
        "--games",
        nargs="*",
        default=None,
        help="Game IDs to check. Default = all available (pbp + box intersection).",
    )
    parser.add_argument("--cache", default=DEFAULT_CACHE, help="Cache directory")
    parser.add_argument("--bins", type=int, default=5)
    args = parser.parse_args()

    # Self-test: show win% for representative states
    print("=== Self-test: live_win_prob(margin, sec_remaining) ===")
    cases = [
        (+6, 360.0, "+6 with 6:00 left (Q4)"),
        (+6, 30.0,  "+6 with 0:30 left (Q4)"),
        (+6, 1440.0, "+6 with 24:00 left (H2)"),
        (0,  60.0,  " 0 with 1:00 left (tie)"),
        (+20, 120.0, "+20 with 2:00 left (blowout)"),
        (-10, 300.0, "-10 with 5:00 left (Q4, away up 10)"),
    ]
    for margin, sec, label in cases:
        p = live_win_prob(margin, sec)
        print(f"  {label:40s}  P(home win) = {p:.3f}")

    print()

    # Determine game IDs
    if args.games:
        gids = args.games
    else:
        pbp_dir = os.path.join(args.cache, "pbp")
        box_dir = os.path.join(args.cache, "box")
        if os.path.exists(pbp_dir) and os.path.exists(box_dir):
            pbp_ids = {f.replace(".json", "") for f in os.listdir(pbp_dir) if f.endswith(".json")}
            box_ids = {f.replace(".json", "") for f in os.listdir(box_dir) if f.endswith(".json")}
            gids = sorted(pbp_ids & box_ids)
        else:
            gids = []

    if not gids:
        print("No game IDs found — pass --games <gid> [<gid> ...] or populate the cache.")
        return

    print(f"=== Reliability check over {len(gids)} game(s) ===")
    result = reliability_check(gids, cache=args.cache, bins=args.bins)
    print(f"  n_games   : {result['n_games']}")
    print(f"  n_samples : {result['n_samples']}")
    print(f"  Brier     : {result['brier']}")
    print(f"  Caveat    : {result['caveat']}")
    print("  Calibration bins:")
    for b in result["bins"]:
        print(f"    {b['range']:12s}  mean_pred={b['mean_pred']:.3f}  emp_freq={b['emp_freq']:.3f}  n={b['n']}")


if __name__ == "__main__":
    main()
