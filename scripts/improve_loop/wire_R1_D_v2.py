"""wire_R1_D_v2.py -- wiring helper for R1_D_v2 SHIP (loop 5).

Computes pop_mean_stds from the gamelog corpus (same logic as the probe)
and writes data/models/per_player_quantile_calibration.json with:

  {
    "per_stat_rescale": { ... },  # from probe results
    "pop_mean_std": { ... },       # computed here
    "version": "R1_D_v2",
    "ratio_clip": [0.6, 1.8]
  }

Run once after the probe ships:
    python scripts/improve_loop/wire_R1_D_v2.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_GAMELOG_GLOB = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "models", "per_player_quantile_calibration.json")
_L20 = 20

# Per-stat rescales from probe result (probe_R1_D_v2_per_player_quantile_variance.py)
_PER_STAT_RESCALE = {
    "pts":  0.986221,
    "reb":  0.965784,
    "ast":  1.009738,
    "fg3m": 0.872568,
    "stl":  0.970447,
    "blk":  0.992380,
    "tov":  0.928001,
}


def _iso(s) -> Optional[str]:
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except Exception:
        return None


def load_gamelogs() -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """Return {pid: [(date_iso, {stat: value}), ...]} sorted chronologically."""
    out: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
    files = glob.glob(_GAMELOG_GLOB)
    print(f"  [wire_R1_D_v2] found {len(files)} gamelog files", flush=True)
    for fp in files:
        parts = os.path.basename(fp).split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            rows = json.load(open(fp, encoding="utf-8")) or []
        except Exception:
            continue
        for row in rows:
            d = _iso(row.get("GAME_DATE"))
            if d is None:
                continue
            sv = {s: float(row.get(s.upper(), 0) or 0) for s in STATS}
            out.setdefault(pid, []).append((d, sv))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def std_l20(pid: int, date: Optional[str], stat: str,
            idx: Dict[int, List[Tuple[str, Dict[str, float]]]]) -> Optional[float]:
    """Std of last 20 stat values STRICTLY BEFORE date (walk-forward safe)."""
    log = idx.get(pid, [])
    if not log:
        return None
    prior = [r[stat] for (d, r) in log if date is None or d < date][-_L20:]
    return float(np.std(prior, ddof=1)) if len(prior) >= 3 else None


def pop_mean_stds(idx: Dict[int, List[Tuple[str, Dict[str, float]]]]) -> Dict[str, float]:
    """Mean per-player std_l20 across the corpus (normaliser for modulation).
    Mirrors probe logic exactly (stride=5, starting at index 20).
    """
    acc: Dict[str, List[float]] = defaultdict(list)
    for pid, log in idx.items():
        for i in range(_L20, len(log), 5):
            d = log[i][0]
            for s in STATS:
                v = std_l20(pid, d, s, idx)
                if v is not None:
                    acc[s].append(v)
    return {s: float(np.mean(acc[s])) if acc[s] else 1.0 for s in STATS}


def main():
    print("[wire_R1_D_v2] loading gamelogs...", flush=True)
    idx = load_gamelogs()
    print(f"[wire_R1_D_v2] {len(idx)} players found", flush=True)
    print("[wire_R1_D_v2] computing pop_mean_stds...", flush=True)
    pmstds = pop_mean_stds(idx)
    print("  pop_mean_std: " + "  ".join(f"{s}={pmstds[s]:.4f}" for s in STATS), flush=True)

    artifact = {
        "per_stat_rescale": _PER_STAT_RESCALE,
        "pop_mean_std": {s: round(pmstds[s], 6) for s in STATS},
        "version": "R1_D_v2",
        "ratio_clip": [0.6, 1.8],
    }
    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=2)
    print(f"[wire_R1_D_v2] wrote {_OUT_PATH}", flush=True)
    return artifact


if __name__ == "__main__":
    main()
