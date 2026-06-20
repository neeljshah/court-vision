"""scripts.platformkit.ingame.ingame_ladder_mlb -- MLB in-game detail-layer LADDER.

Tests whether structural MLB layers improve on a strong BASE model
(run_diff, frac_elapsed), which achieves Brier-skill ~0.36.

BASE is the sigmoid((a+b*frac_elapsed)*state_diff) model from ingame_gate_generic_models
-- already proven strong for MLB. Layers are gated INDEPENDENTLY vs BASE using the same
cross-corpus A->B / B->A design with DM clustered by game_id.

LAYERS TESTED (each fit on TRAIN only -- leak-free):
  L1  LATE_INNING_SHRINK: inning >= 7 -> late; small leads are safer late; re-price
      best prob as p' = 0.5 + (best-0.5)*shrink(inning_z). 'best' here is BASE.
      Hypothesis: a 1-run lead in the 9th is MUCH safer than in the 5th (non-linear
      lateness effect that a linear frac_elapsed misses).
  L2  LEVERAGE_INTERACTION: late_flag * clipped_abs_lead interaction; a small lead late
      should be priced differently than a large lead late. Logit-shift: p' = sig(lo +
      beta*z_lev). Hypothesis: the product late*small_lead is the key safety signal.
  L3  INNING_HALF_CALIBRATION: mid vs end of inning (top vs bottom half). In MLB the
      home team bats last; a tie going into the home-half (end*) is safer for the home
      team. Logit-shift by is_bottom * clipped_run_diff on TRAIN. A principled
      structural signal -- may REJECT if BASE already prices it via state_diff.

SHIP iff: Brier(BASE+layer) < Brier(BASE) AND DM clustered p<0.05 AND consistent in
BOTH cross-corpus directions. REJECT is the honest, expected outcome for most layers.

NOTE: MLB parquets have no base/out columns. All layers use columns present:
  half_inning_label (e.g. 'mid3', 'end7'), frac_elapsed, state_diff, game_id, outcome.

ASCII-only; <=300 LOC; per-file tests only; no $ claims; never edit src/ or kernel/.
CLI: python scripts/platformkit/ingame/ingame_ladder_mlb.py
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_predict,
    fit_base,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "ingame")


# --------------------------------------------------------------------------- load
def _parse_inning(label: str) -> Tuple[int, bool]:
    """Parse 'mid3'/'end7' -> (inning_number, is_bottom_half)."""
    label = str(label).strip().lower()
    if label.startswith("mid"):
        return int(label[3:]), False   # top half (away bats)
    if label.startswith("end"):
        return int(label[3:]), True    # bottom half complete (home batted)
    return 1, False


def load_mlb_states(path: str) -> List[dict]:
    """Load MLB parquet into dicts; extract inning + half from half_inning_label."""
    df = pd.read_parquet(path)
    states: List[dict] = []
    for r in df.itertuples(index=False):
        inning, is_bottom = _parse_inning(r.half_inning_label)
        fe = float(r.frac_elapsed)
        fe = max(0.0, min(1.0, fe))
        states.append({
            "game_id": r.game_id,
            "state_diff": float(r.state_diff),
            "frac_elapsed": fe,
            "p0": float(r.p0),
            "outcome": int(r.outcome),
            "inning": inning,
            "is_bottom": is_bottom,
        })
    return states


# L1/L2/L3 fit+apply layer helpers live in ingame_ladder_mlb_layers (sibling-split for
# <=300 LOC). Re-exported under their private names so call sites + tests are unchanged.
from scripts.platformkit.ingame.ingame_ladder_mlb_layers import (  # noqa: E402
    apply_inning_half as _apply_inning_half,
    apply_late_shrink as _apply_late_shrink,
    apply_leverage as _apply_leverage,
    fit_inning_half as _fit_inning_half,
    fit_late_shrink as _fit_late_shrink,
    fit_leverage as _fit_leverage,
)


# --------------------------------------------------------------------------- gate
@dataclass
class LayerResult:
    name: str
    verdict: str
    why: str
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"layer": self.name, "verdict": self.verdict, "why": self.why,
                "vs_close": "CALIBRATION only (Brier) -- not a market edge",
                "a_to_b": self.a_to_b, "b_to_a": self.b_to_a}


_LAYERS = [
    ("late_inning_shrink", _fit_late_shrink, _apply_late_shrink,
     "inning lateness adds non-linear info beyond frac_elapsed; late small leads safer.",
     "inning number adds no calibration signal beyond frac_elapsed; BASE already prices it."),
    ("leverage_late_close", _fit_leverage, _apply_leverage,
     "late*close interaction reprices close games in innings 7+ correctly.",
     "late*close interaction adds no signal beyond (run_diff, frac_elapsed) in BASE."),
    ("inning_half_calibration", _fit_inning_half, _apply_inning_half,
     "bottom-half has residual home-team advantage beyond run_diff.",
     "BASE state_diff already prices the home batting advantage; no residual half signal."),
]


def _cross_dir(train: List[dict], test: List[dict],
               fit_fn, apply_fn, eps: float = 0.05) -> Dict:
    ab = fit_base(train)
    base_tr = base_predict(train, ab)
    base_te = base_predict(test, ab)
    y = np.array([s["outcome"] for s in test], float)
    params = fit_fn(train, base_tr)
    layer_te = apply_fn(test, base_te, params)
    bb, bl = float(brier(base_te, y)), float(brier(layer_te, y))
    d = (base_te - y) ** 2 - (layer_te - y) ** 2
    gids = [s["game_id"] for s in test]
    dm = diebold_mariano(d, gids)
    beats = bool((bl < bb) and (dm.p_value < eps))
    return {
        "n_train": len(train), "n_test": len(test), "n_games": dm.n_clusters,
        "brier_base": round(bb, 4), "brier_layer": round(bl, 4),
        "brier_delta": round(bb - bl, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "layer_beats_base": beats,
    }


def gate_layer_cross(states_a: List[dict], states_b: List[dict],
                     fit_fn, apply_fn, name: str,
                     why_ship: str, why_reject: str,
                     eps: float = 0.05) -> LayerResult:
    a_to_b = _cross_dir(states_a, states_b, fit_fn, apply_fn, eps)
    b_to_a = _cross_dir(states_b, states_a, fit_fn, apply_fn, eps)
    both = a_to_b["layer_beats_base"] and b_to_a["layer_beats_base"]
    verdict = "SHIP" if both else "REJECT"
    why = why_ship if both else why_reject
    return LayerResult(name, verdict, why, a_to_b, b_to_a)


# --------------------------------------------------------------------------- driver
def run(path_a: str | None = None, path_b: str | None = None) -> List[LayerResult]:
    if path_a is None:
        path_a = os.path.join(_STATE_DIR, "mlb_states__2023.parquet")
    if path_b is None:
        path_b = os.path.join(_STATE_DIR, "mlb_states__2024.parquet")
    states_a = load_mlb_states(path_a)
    states_b = load_mlb_states(path_b)
    results: List[LayerResult] = []
    for name, fit_fn, apply_fn, why_ship, why_reject in _LAYERS:
        r = gate_layer_cross(states_a, states_b, fit_fn, apply_fn,
                             name, why_ship, why_reject)
        results.append(r)
    return results


def _report(results: List[LayerResult]) -> str:
    lines = ["=" * 70,
             "IN-GAME DETAIL-LAYER LADDER (MLB) -- candidates vs BASE (run_diff,frac)",
             "BASE: sigmoid((a+b*frac_elapsed)*run_diff); a,b fit per corpus",
             "GATE: cross-corpus A->B / B->A; DM clustered by game_id; p<0.05",
             "NOTE: MLB parquets have no base/out columns; layers use inning+half only.",
             "=" * 70]
    for r in results:
        ab, ba = r.a_to_b, r.b_to_a
        lines.append(f"LAYER: {r.name}")
        lines.append(f"  verdict   : {r.verdict}")
        lines.append(f"  A->B  n_test={ab.get('n_test')} games={ab.get('n_games')} "
                     f"BASE {ab.get('brier_base')} -> +layer {ab.get('brier_layer')} "
                     f"(delta {ab.get('brier_delta'):+.5f})  DM p={ab.get('dm_p')}  "
                     f"beats={ab.get('layer_beats_base')}")
        lines.append(f"  B->A  n_test={ba.get('n_test')} games={ba.get('n_games')} "
                     f"BASE {ba.get('brier_base')} -> +layer {ba.get('brier_layer')} "
                     f"(delta {ba.get('brier_delta'):+.5f})  DM p={ba.get('dm_p')}  "
                     f"beats={ba.get('layer_beats_base')}")
        lines.append(f"  why       : {r.why}")
        lines.append("-" * 70)
    lines.append("=" * 70)
    return "\n".join(lines)


def write(results: List[LayerResult], out: str | None = None) -> str:
    if out is None:
        out = os.path.join(_OUT_DIR, "ladder_mlb.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    payload = {
        "current_base": "sigmoid((a+b*frac_elapsed)*run_diff); a,b fit per corpus",
        "note": ("No base/out data in MLB parquets; layers use inning+half from "
                 "half_inning_label. Honest REJECT is the expected outcome for most layers."),
        "vs_close": "CALIBRATION only (held-out Brier) -- not a market edge",
        "ladder": [r.to_dict() for r in results],
    }
    with open(out, "w", encoding="ascii") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return out


def main() -> None:
    results = run()
    p = write(results)
    print(_report(results))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
