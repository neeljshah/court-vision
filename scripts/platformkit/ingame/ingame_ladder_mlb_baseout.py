"""scripts.platformkit.ingame.ingame_ladder_mlb_baseout -- MLB base-out detail layer.

Tests whether BASE-OUT state (runners on base + outs at end of each half-inning)
improves on the strong BASE model (run_diff, frac_elapsed, BSS~0.36) for MLB
in-game win probability.

LAYER: BASE_OUT_RUNEXP
  Run-expectancy adjustment derived from the runners-left-on-base (LOB) state when
  each half-inning ended.  A half-inning that ends with runners stranded (runners > 0)
  is a FAILED threat by the batting team -- the defense over-performed vs. the run-
  expectancy implied by the base-out state.  Conversely, a clean 1-2-3 inning or
  one with no runners left means the defense held the line efficiently.

  Signal construction (from `runners` bitmask + `outs`=-1/3 from ingest):
    lob_count(runners) = popcount(runners bitmask)  -- number of runners stranded
    run_exp_context = LOB count * signed_run_diff_direction
      (a 2-run lead with 2 runners left on base is more "secure" than it appears;
       conversely the trailing team had runners on and failed to convert)
    Logit-shift: p' = sig(logit(BASE) + beta * z_runexp)  where beta fit on TRAIN.

  LEAK-FREE: beta fit on TRAIN only; applied to TEST.
  GATE: cross-corpus A->B / B->A; DM clustered by game_id; p<0.05 both dirs -> SHIP.
  UNKNOWN states (base_out_known=False) get lob_count=0 (neutral, no adjustment).

HONEST PRIOR: base-out MIGHT add a small real lift (genuine baseball structure that
run_diff alone misses), or might REJECT if BASE already captures it indirectly.
Report whatever happens with numbers; do NOT massage.

ASCII-only; <=300 LOC; per-file tests only; no $ claims; never edit src/ or kernel/.
CLI: python scripts/platformkit/ingame/ingame_ladder_mlb_baseout.py
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

# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def _lob_count(runners: int) -> int:
    """Count runners left on base from bitmask (bit2=1B, bit1=2B, bit0=3B)."""
    return bin(int(runners) & 0b111).count("1")


def load_mlb_states_baseout(path: str) -> List[dict]:
    """Load MLB states parquet; extract base-out cols + inning/half from label.

    Tolerates missing base-out cols (older parquets without extension) by
    defaulting to base_out_known=False, runners=0, outs=-1.
    """
    df = pd.read_parquet(path)
    has_bo = "base_out_known" in df.columns
    states: List[dict] = []
    for r in df.itertuples(index=False):
        label = str(r.half_inning_label).strip().lower()
        if label.startswith("mid"):
            inning = int(label[3:])
            is_bottom = False
        elif label.startswith("end"):
            inning = int(label[3:])
            is_bottom = True
        else:
            inning, is_bottom = 1, False
        fe = float(max(0.0, min(1.0, r.frac_elapsed)))
        runners = int(getattr(r, "runners", 0)) if has_bo else 0
        outs = int(getattr(r, "outs", -1)) if has_bo else -1
        known = bool(getattr(r, "base_out_known", False)) if has_bo else False
        lob = _lob_count(runners) if known else 0
        states.append({
            "game_id": r.game_id,
            "state_diff": float(r.state_diff),
            "frac_elapsed": fe,
            "p0": float(r.p0),
            "outcome": int(r.outcome),
            "inning": inning,
            "is_bottom": is_bottom,
            "runners": runners,
            "outs": outs,
            "base_out_known": known,
            "lob_count": lob,
        })
    return states

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(np.clip(p, 1e-6, 1.0 - 1e-6) / (1.0 - np.clip(p, 1e-6, 1.0 - 1e-6)))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))

# ---------------------------------------------------------------------------
# L4: BASE-OUT run-expectancy layer
# ---------------------------------------------------------------------------

def _run_exp_signal(states: List[dict]) -> np.ndarray:
    """Compute run-expectancy context signal per state.

    runexp = lob_count * sign(state_diff) -- positive when leading team had the
    defense hold runners on base (opponent left runners stranded).  Neutral (0)
    when base_out_known=False or game is tied (state_diff=0).
    This directionalizes the LOB count: stranded runners HELP the leading team.
    """
    lob = np.array([s["lob_count"] for s in states], float)
    sd = np.array([s["state_diff"] for s in states], float)
    direction = np.sign(sd)   # +1 home leading, -1 away leading, 0 tied
    return lob * direction    # ~[-3, +3] range


def fit_baseout_layer(train: List[dict], base_tr: np.ndarray) -> Tuple[float, float, float]:
    """Fit L4: logit-shift by z-scored run-expectancy context.

    p' = sig(logit(BASE) + beta * z_runexp)
    z_runexp = (runexp - mu) / sd   standardized on TRAIN.
    Grid search on TRAIN Brier. Returns (beta, mu, sd).
    If all runexp values are 0 (no base-out coverage), returns (0.0, 0.0, 1.0).
    """
    y = np.array([s["outcome"] for s in train], float)
    re = _run_exp_signal(train)
    mu = float(re.mean())
    sd = float(re.std() + 1e-9)
    if sd < 1e-8:
        return 0.0, mu, sd
    re_z = (re - mu) / sd
    lo = _logit(base_tr)
    best_beta, best_b = 0.0, float(np.mean((base_tr - y) ** 2))
    for beta in np.linspace(-0.50, 0.50, 41):
        p = _sigmoid(lo + beta * re_z)
        sc = float(np.mean((p - y) ** 2))
        if sc < best_b:
            best_b, best_beta = sc, float(beta)
    return best_beta, mu, sd


def apply_baseout_layer(
    test: List[dict], base_te: np.ndarray, params: Tuple[float, float, float]
) -> np.ndarray:
    """Apply fitted L4 logit-shift to test states."""
    beta, mu, sd = params
    re = _run_exp_signal(test)
    re_z = (re - mu) / (sd if sd > 1e-8 else 1.0)
    return _sigmoid(_logit(base_te) + beta * re_z)

# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------

@dataclass
class BaseOutResult:
    name: str
    verdict: str
    why: str
    bo_coverage: Dict = field(default_factory=dict)
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "layer": self.name, "verdict": self.verdict, "why": self.why,
            "base_out_coverage": self.bo_coverage,
            "vs_close": "CALIBRATION only (held-out Brier) -- not a market edge",
            "a_to_b": self.a_to_b, "b_to_a": self.b_to_a,
        }


def _cross_dir_bo(train: List[dict], test: List[dict],
                  eps: float = 0.05) -> Dict:
    ab = fit_base(train)
    base_tr = base_predict(train, ab)
    base_te = base_predict(test, ab)
    y = np.array([s["outcome"] for s in test], float)
    params = fit_baseout_layer(train, base_tr)
    layer_te = apply_baseout_layer(test, base_te, params)
    bb, bl = float(brier(base_te, y)), float(brier(layer_te, y))
    d = (base_te - y) ** 2 - (layer_te - y) ** 2
    gids = [s["game_id"] for s in test]
    dm = diebold_mariano(d, gids)
    beats = bool((bl < bb) and (dm.p_value < eps))
    n_known = sum(1 for s in test if s["base_out_known"])
    return {
        "n_train": len(train), "n_test": len(test), "n_games": dm.n_clusters,
        "n_test_bo_known": n_known, "pct_bo_known": round(100.0 * n_known / max(1, len(test)), 1),
        "fitted_beta": round(params[0], 6),
        "brier_base": round(bb, 4), "brier_layer": round(bl, 4),
        "brier_delta": round(bb - bl, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "layer_beats_base": beats,
    }


def gate_baseout(states_a: List[dict], states_b: List[dict],
                 eps: float = 0.05) -> BaseOutResult:
    name = "base_out_runexp"
    n_ko_a = sum(1 for s in states_a if s["base_out_known"])
    n_ko_b = sum(1 for s in states_b if s["base_out_known"])
    cov = {
        "a_states": len(states_a), "a_bo_known": n_ko_a,
        "a_bo_pct": round(100.0 * n_ko_a / max(1, len(states_a)), 1),
        "b_states": len(states_b), "b_bo_known": n_ko_b,
        "b_bo_pct": round(100.0 * n_ko_b / max(1, len(states_b)), 1),
    }
    a_to_b = _cross_dir_bo(states_a, states_b, eps)
    b_to_a = _cross_dir_bo(states_b, states_a, eps)
    both = a_to_b["layer_beats_base"] and b_to_a["layer_beats_base"]
    if both:
        verdict = "SHIP"
        why = ("Base-out LOB signal beats BASE Brier in BOTH cross-corpus directions "
               "with DM p<0.05; runners stranded at inning end add run-expectancy info "
               "beyond (run_diff, frac_elapsed) alone -- MLB's first in-game detail beat.")
    else:
        verdict = "REJECT"
        why = ("Base-out LOB signal does NOT beat BASE Brier in both directions "
               "(or DM p>=0.05); run_diff already captures the outcome-relevant info; "
               "stranded runners are noise conditional on the score.")
    return BaseOutResult(name, verdict, why, cov, a_to_b, b_to_a)

# ---------------------------------------------------------------------------
# driver + CLI
# ---------------------------------------------------------------------------

def run(path_a: str | None = None, path_b: str | None = None) -> BaseOutResult:
    if path_a is None:
        path_a = os.path.join(_STATE_DIR, "mlb_states__2023.parquet")
    if path_b is None:
        path_b = os.path.join(_STATE_DIR, "mlb_states__2024.parquet")
    sa = load_mlb_states_baseout(path_a)
    sb = load_mlb_states_baseout(path_b)
    return gate_baseout(sa, sb)


def _report(r: BaseOutResult) -> str:
    ab, ba, cov = r.a_to_b, r.b_to_a, r.bo_coverage
    lines = [
        "=" * 70,
        "MLB IN-GAME BASE-OUT LAYER (L4: base_out_runexp)",
        "BASE: sigmoid((a+b*frac_elapsed)*run_diff); a,b fit per corpus",
        "LAYER: logit-shift by z-scored LOB-count * sign(run_diff)",
        "GATE: cross-corpus A->B / B->A; DM clustered by game_id; p<0.05",
        "=" * 70,
        f"BASE-OUT COVERAGE: A {cov.get('a_bo_known')}/{cov.get('a_states')} "
        f"({cov.get('a_bo_pct')}%)  B {cov.get('b_bo_known')}/{cov.get('b_states')} "
        f"({cov.get('b_bo_pct')}%)",
        "-" * 70,
        f"VERDICT: {r.verdict}",
        "-" * 70,
        f"A->B  n_test={ab.get('n_test')} games={ab.get('n_games')} "
        f"bo_known={ab.get('pct_bo_known')}% beta={ab.get('fitted_beta')} "
        f"BASE {ab.get('brier_base')} -> +layer {ab.get('brier_layer')} "
        f"(delta {ab.get('brier_delta'):+.5f})  DM p={ab.get('dm_p')}  "
        f"beats={ab.get('layer_beats_base')}",
        f"B->A  n_test={ba.get('n_test')} games={ba.get('n_games')} "
        f"bo_known={ba.get('pct_bo_known')}% beta={ba.get('fitted_beta')} "
        f"BASE {ba.get('brier_base')} -> +layer {ba.get('brier_layer')} "
        f"(delta {ba.get('brier_delta'):+.5f})  DM p={ba.get('dm_p')}  "
        f"beats={ba.get('layer_beats_base')}",
        "-" * 70,
        f"WHY: {r.why}",
        "=" * 70,
    ]
    return "\n".join(lines)


def write(r: BaseOutResult, out: str | None = None) -> str:
    if out is None:
        out = os.path.join(_OUT_DIR, "ladder_mlb_baseout.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(r.to_dict(), f, indent=2, sort_keys=True)
    return out


def main() -> None:
    r = run()
    p = write(r)
    print(_report(r))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
