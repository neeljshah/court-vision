"""scripts.platformkit.ingame.ingame_serve_persist -- persist + provenance helpers
split out of ingame_serve.py to keep each file <=300 LOC (mirrors the wave's
ingame_layer_gate_nba_io.py sibling-split pattern).

Self-contained, NON-GATED helpers:
  * persist / load_artifact : atomic (tmp + os.replace) JSON artifact IO, model_dir
                              passed in so the serve module owns the path (and tests
                              can monkeypatch it there).
  * prior_status            : verdict -> 'proven' / 'experimental' / 'none' label.
  * time_bucket / base_p    : the served BASE sigmoid + its time bucket.
  * result                  : the $-free served-result dict (CALIBRATION, not edge).

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

import numpy as np

# Verdicts under which the +PRIOR layer is honestly servable, and how it is labelled.
PROVEN = {"REPLICATED"}
EXPERIMENTAL = {"PARTIAL"}


def prior_status(verdict: str) -> str:
    if verdict in PROVEN:
        return "proven"
    if verdict in EXPERIMENTAL:
        return "experimental"
    return "none"


def persist(model_dir: str, sport: str, art: Dict) -> str:
    """Atomic write of a served artifact to <model_dir>/<sport>_ingame.json."""
    os.makedirs(model_dir, exist_ok=True)
    out = os.path.join(model_dir, f"{sport}_ingame.json")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(art, f, indent=2, sort_keys=True)
    os.replace(tmp, out)
    return out


def load_artifact(model_dir: str, sport: str) -> Optional[Dict]:
    path = os.path.join(model_dir, f"{sport}_ingame.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="ascii") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def time_bucket(frac: float, n: int = 4) -> int:
    return min(n - 1, max(0, int(float(frac) * n)))


def base_p(state_diff: float, frac_elapsed: float, ab) -> float:
    a, b = float(ab[0]), float(ab[1])
    return float(1.0 / (1.0 + np.exp(-(a + b * float(frac_elapsed)) * float(state_diff))))


def result(p_win: float, model: str, sport: str, verdict: str, prov: List[str]) -> Dict:
    return {
        "sport": sport, "p_win": round(float(p_win), 6), "model": model,
        "verdict": verdict,
        "provenance": prov,
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
    }


__all__ = ["PROVEN", "EXPERIMENTAL", "prior_status", "persist", "load_artifact",
           "time_bucket", "base_p", "result"]
