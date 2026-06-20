"""GATE the NEW per-PITCH additive layer (domains/mlb/ingest_pitch_states.py) vs the
proven BASE in-game win-prob model. Question: do the structurally-NEW per-pitch as-of
columns the half-inning/at-bat grids cannot see -- SP within-start fatigue
(velo_decline_vs_early) + the varying pre-pitch count -- improve a strong BASE's held-out
Brier in BOTH cross-corpus directions?

BASE   = sigmoid((a + b*frac_elapsed)*state_diff); a,b fit per corpus.
+LAYER = sigmoid(logit(BASE) + beta_f*z_fatigue + beta_c*z_cnt); beta fit on TRAIN only.
  NaN first-pitch fatigue -> 0 shift (never fabricated). A noise column fits beta->0
  (graceful degrade => REJECT) -- exactly how the planted-null control rejects. An
  isolated fatigue-only lever (fit_fatigue_layer) tests the SP velo-decline lever alone.

GATE (identical bar; never weakened): leak-free (beta TRAIN-only, fatigue prior-N by
ingest) + TRUE cross-corpus A->B and B->A (disjoint seasons) + DM CLUSTERED by game_id
both dirs + PLANTED-NULL control (MUST reject; else run is UNTRUSTWORTHY). SHIP iff
+layer beats BASE on Brier AND DM p<eps BOTH dirs AND null rejected. INSUFFICIENT_DATA
if <2 real corpora on disk. REJECT is the expected honest outcome. NO $/ROI/edge:
verdict is CALIBRATION (held-out Brier), not a market edge. PROPOSAL-ONLY (no registry
write, no flag flip). CLI: python -m scripts.platformkit.ingame.ingame_pitch_layer_gate_mlb
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_gate_generic_models import base_predict, fit_base
from scripts.platformkit.ingame.ingame_ladder_mlb_layers import logit, sigmoid

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "ingame")


# --------------------------------------------------------------------------- load
def load_pitch_states(path: str) -> List[dict]:
    """Load a per-pitch-states parquet into gate dicts. Frozen base schema + the new
    additive as-of columns (velo_decline_vs_early, count_balls/strikes). NaN fatigue
    (first pitch of a side) is carried as NaN -> mapped to a 0 shift downstream (the
    ingest never fabricates a baseline, and the gate never invents one)."""
    import pandas as pd
    df = pd.read_parquet(path)
    states: List[dict] = []
    for r in df.itertuples(index=False):
        fe = max(0.0, min(1.0, float(r.frac_elapsed)))
        states.append({
            "game_id": r.game_id,
            "state_diff": float(r.state_diff),
            "frac_elapsed": fe,
            "p0": float(r.p0),
            "outcome": int(r.outcome),
            "velo_decline": float(r.velo_decline_vs_early),  # may be NaN (first pitch)
            "count_balls": float(r.count_balls),
            "count_strikes": float(r.count_strikes),
        })
    return states


# --------------------------------------------------------------------- the new layer
def _col(states: List[dict], key: str) -> np.ndarray:
    return np.array([s[key] for s in states], float)


def _standardize(x: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """NaN-safe z-score; NaN entries (no prior baseline) map to 0 (mean) -> 0 shift."""
    finite = x[np.isfinite(x)]
    mu = float(finite.mean()) if finite.size else 0.0
    sd = float(finite.std()) + 1e-9
    z = (np.where(np.isfinite(x), x, mu) - mu) / sd
    return z, mu, sd


def _features(states: List[dict], mu_f=None, sd_f=None, mu_c=None, sd_c=None):
    """Standardized (z_fatigue, z_count) features. On TRAIN (mu/sd None) fit the moments;
    on TEST reuse the TRAIN moments (no leak). count proxy = strikes - balls (count
    pressure on the batter), the genuinely-varying pre-pitch count the at-bat grid 0'd."""
    f = _col(states, "velo_decline")
    c = _col(states, "count_strikes") - _col(states, "count_balls")
    if mu_f is None:
        z_f, mu_f, sd_f = _standardize(f)
        z_c, mu_c, sd_c = _standardize(c)
    else:
        z_f = (np.where(np.isfinite(f), f, mu_f) - mu_f) / sd_f
        z_c = (c - mu_c) / sd_c
    return z_f, z_c, (mu_f, sd_f, mu_c, sd_c)


def fit_pitch_layer(train: List[dict], base_tr: np.ndarray):
    """Fit (beta_f, beta_c) on TRAIN by Brier of sigmoid(logit(BASE)+beta_f*z_f+beta_c*z_c).
    A noise/no-signal column drives beta->0 (graceful degrade) -> +LAYER == BASE."""
    y = np.array([s["outcome"] for s in train], float)
    z_f, z_c, moments = _features(train)
    lo = logit(base_tr)
    best = (0.0, 0.0)
    best_b = float(np.mean((base_tr - y) ** 2))
    grid = np.linspace(-0.50, 0.50, 21)
    for bf in grid:
        for bc in grid:
            p = sigmoid(lo + bf * z_f + bc * z_c)
            sc = float(np.mean((p - y) ** 2))
            if sc < best_b:
                best_b, best = sc, (float(bf), float(bc))
    return (best[0], best[1], moments)


def apply_pitch_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    bf, bc, (mu_f, sd_f, mu_c, sd_c) = params
    z_f, z_c, _ = _features(test, mu_f, sd_f, mu_c, sd_c)
    return sigmoid(logit(base_te) + bf * z_f + bc * z_c)


# ------------------------------------------ isolated SP velo-decline (fatigue-only) lever
def fit_fatigue_layer(train: List[dict], base_tr: np.ndarray):
    """ISOLATE the structurally-new lever: fit ONLY beta_f on velo_decline_vs_early
    (count beta forced to 0), so we can tell whether within-start SP velocity-decline
    carries any held-out Brier signal on its own. Same Brier objective / TRAIN-only fit."""
    y = np.array([s["outcome"] for s in train], float)
    z_f, _z_c, moments = _features(train)
    lo = logit(base_tr)
    best, best_b = 0.0, float(np.mean((base_tr - y) ** 2))
    for bf in np.linspace(-0.50, 0.50, 21):
        p = sigmoid(lo + bf * z_f)
        sc = float(np.mean((p - y) ** 2))
        if sc < best_b:
            best_b, best = sc, float(bf)
    return (best, moments)


def apply_fatigue_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    bf, (mu_f, sd_f, mu_c, sd_c) = params
    z_f, _z_c, _ = _features(test, mu_f, sd_f, mu_c, sd_c)
    return sigmoid(logit(base_te) + bf * z_f)


# ------------------------------------------------------------------ planted-null layer
def fit_null_layer(train: List[dict], base_tr: np.ndarray):
    """IDENTICAL machinery, but the 'feature' is a pure-noise column seeded ONLY by
    game/index hashing (no outcome). It MUST drive beta->0 and fail to beat BASE, which
    is the proof the gate can FAIL a signal. Same grid, same Brier objective."""
    y = np.array([s["outcome"] for s in train], float)
    z = _noise_col(train)
    lo = logit(base_tr)
    best_b, best = float(np.mean((base_tr - y) ** 2)), 0.0
    for bn in np.linspace(-0.50, 0.50, 21):
        p = sigmoid(lo + bn * z)
        sc = float(np.mean((p - y) ** 2))
        if sc < best_b:
            best_b, best = sc, float(bn)
    return (best,)


def apply_null_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    (bn,) = params
    return sigmoid(logit(base_te) + bn * _noise_col(test))


def _noise_col(states: List[dict]) -> np.ndarray:
    """Deterministic pure-noise column from a hash of (game_id, asof index). Carries NO
    outcome information -> a correct gate finds no held-out Brier improvement -> REJECT."""
    vals = []
    for i, s in enumerate(states):
        h = (hash((str(s["game_id"]), i)) & 0x7FFFFFFF) / 0x7FFFFFFF
        vals.append(h)
    z, _, _ = _standardize(np.array(vals, float))
    return z


# --------------------------------------------------------------------------- gate
def _cross_dir(train, test, fit_fn, apply_fn, eps: float) -> Dict:
    ab = fit_base(train)
    base_tr, base_te = base_predict(train, ab), base_predict(test, ab)
    y = np.array([s["outcome"] for s in test], float)
    params = fit_fn(train, base_tr)
    layer_te = apply_fn(test, base_te, params)
    bb, bl = float(brier(base_te, y)), float(brier(layer_te, y))
    d = (base_te - y) ** 2 - (layer_te - y) ** 2  # +ve => layer beats base
    dm = diebold_mariano(d, [s["game_id"] for s in test])
    return {
        "n_train": len(train), "n_test": len(test), "n_games": dm.n_clusters,
        "brier_base": round(bb, 4), "brier_layer": round(bl, 4),
        "brier_delta": round(bb - bl, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "layer_beats_base": bool((bl < bb) and (dm.p_value < eps)),
    }


def gate_layer(states_a, states_b, fit_fn, apply_fn, eps: float = 0.05) -> Dict:
    a_to_b = _cross_dir(states_a, states_b, fit_fn, apply_fn, eps)
    b_to_a = _cross_dir(states_b, states_a, fit_fn, apply_fn, eps)
    replicated = a_to_b["layer_beats_base"] and b_to_a["layer_beats_base"]
    return {"a_to_b": a_to_b, "b_to_a": b_to_a, "replicated": bool(replicated)}


@dataclass
class PitchGateVerdict:
    verdict: str
    layer_result: Dict = field(default_factory=dict)
    null_result: Dict = field(default_factory=dict)
    null_rejected: bool = False
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "layer": "mlb_pitch_fatigue_count (velo_decline_vs_early + pre-pitch count)",
            "base_model": "sigmoid((a+b*frac_elapsed)*run_diff); a,b fit per corpus",
            "gate": "cross-corpus A<->B + DM clustered by game_id + planted-null control",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "no_dollar_field": True, "proposal_only": True,
            "null_rejected": self.null_rejected,
            "layer_result": self.layer_result, "null_result": self.null_result,
            "coverage": self.coverage, "caveats": list(self.caveats),
        }


def run_gate(states_a: List[dict], states_b: List[dict], eps: float = 0.05,
             min_games: int = 8) -> PitchGateVerdict:
    """Full gate over two materialized pitch corpora + the planted-null control."""
    cov = {
        "a_states": len(states_a), "a_games": len({s["game_id"] for s in states_a}),
        "b_states": len(states_b), "b_games": len({s["game_id"] for s in states_b}),
    }
    caveats = [
        "Leak-free: beta fit on TRAIN only; velo_decline_vs_early is prior-N by ingest "
        "construction (first pitch of a side -> NaN -> 0 shift, never fabricated).",
        "TRUE cross-corpus: disjoint seasons; DM clustered by game_id both directions.",
        "Planted-null = pure-noise column through the IDENTICAL gate; it MUST reject.",
        "No in-play odds -> CALIBRATION (held-out Brier) vs (run_diff,frac_elapsed) BASE, "
        "never a market edge. No $ anywhere.",
    ]
    if (cov["a_games"] < min_games or cov["b_games"] < min_games
            or len(states_a) < 200 or len(states_b) < 200):
        return PitchGateVerdict("INSUFFICIENT_DATA", {}, {}, False, cov,
                                caveats + ["corpus too thin / not materialized to gate"])
    # ALWAYS run the planted-null first: if it does NOT reject, the run is untrustworthy.
    null = gate_layer(states_a, states_b, fit_null_layer, apply_null_layer, eps)
    null_rejected = not null["replicated"]
    layer = gate_layer(states_a, states_b, fit_pitch_layer, apply_pitch_layer, eps)
    if not null_rejected:
        return PitchGateVerdict("NOT_TESTABLE", layer, null, False, cov,
                                caveats + ["UNTRUSTWORTHY: planted-null did NOT reject -- "
                                           "the gate failed to fail a noise column."])
    verdict = "SHIP" if layer["replicated"] else "REJECT"
    return PitchGateVerdict(verdict, layer, null, True, cov, caveats)


# --------------------------------------------------------------------------- driver
def _find_corpora() -> List[str]:
    return sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_pitch_states__*.parquet")))


def run(path_a: Optional[str] = None, path_b: Optional[str] = None,
        eps: float = 0.05) -> PitchGateVerdict:
    """Find/load >=2 real per-pitch corpora and gate. INSUFFICIENT_DATA (honest) if the
    pitch layer has not been network-materialized for >=2 seasons on disk."""
    if path_a is None or path_b is None:
        paths = _find_corpora()
        if len(paths) < 2:
            cov = {"corpora_found": len(paths)}
            return PitchGateVerdict(
                "INSUFFICIENT_DATA", {}, {}, False, cov,
                ["need >=2 materialized mlb_pitch_states__*.parquet at "
                 f"{_STATE_DIR}; found {len(paths)}. The per-pitch layer is "
                 "network-ingested (rides the ESPN summary plays[]); no pitch corpus is "
                 "on disk yet -- reported honestly, not 0-filled into a result."])
        path_a, path_b = paths[0], paths[1]
    return run_gate(load_pitch_states(path_a), load_pitch_states(path_b), eps=eps)


def write(v: PitchGateVerdict, out: Optional[str] = None) -> str:
    if out is None:
        out = os.path.join(_OUT_DIR, "pitch_layer_gate_mlb.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    return out


def _report(v: PitchGateVerdict) -> str:
    lines = ["=" * 72,
             "MLB PER-PITCH ADDITIVE-LAYER GATE: fatigue+count vs BASE (run_diff,frac)",
             "GATE: cross-corpus A<->B + DM clustered by game_id + planted-null control",
             "=" * 72, f"VERDICT       : {v.verdict}",
             f"planted-null REJECTS: {v.null_rejected} (must be True to trust the run)",
             f"coverage      : A {v.coverage.get('a_games')} games / "
             f"{v.coverage.get('a_states')} states ; B {v.coverage.get('b_games')} games "
             f"/ {v.coverage.get('b_states')} states", "-" * 72]
    for tag, res in (("+LAYER", v.layer_result), ("NULL  ", v.null_result)):
        for name, d in (("A->B", res.get("a_to_b", {})), ("B->A", res.get("b_to_a", {}))):
            if d:
                lines.append(f"  {tag} {name}: BASE {d['brier_base']} -> {d['brier_layer']}"
                             f" (delta {d['brier_delta']:+.5f})  DM p={d['dm_p']}  "
                             f"beats={d['layer_beats_base']}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
