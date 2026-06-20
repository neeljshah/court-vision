"""GATE the ORPHAN per-AT-BAT RE24 / leverage / base-out grid
(data/cache/ingame/mlb_atbat_states__{2022,2023}.parquet) as an additive in-game
layer ON TOP OF the proven half-inning BASE (run_diff, frac_elapsed). The at-bat
parquet has a materialization but NO in-game-layer verdict -- this is lane B, the
verdict that orphan never had.

Question: do the structurally-NEW within-half-inning as-of columns the half-inning
grid cannot see -- the base-out RUN EXPECTANCY (base_run_value, i.e. RE24) and the
LEVERAGE bucket (low/mid/high) -- improve a strong BASE's held-out Brier in BOTH
cross-corpus directions (2022<->2023)?

BASE   = sigmoid((a + b*frac_elapsed)*state_diff); a,b fit per corpus.
+LAYER = sigmoid(logit(BASE) + beta_r*z_re24 + beta_l*z_lev); beta fit on TRAIN only.
  A noise column fits beta->0 (graceful degrade => REJECT) -- exactly how the
  planted-null control rejects. An isolated RE24-only lever (fit_re24_layer) tests
  the base-out run-expectancy lever on its own.

GATE (identical bar; never weakened): leak-free (beta TRAIN-only; re24/leverage are
the as-of base-out state by ingest construction, not a future aggregate; the realized
win/loss is the LABEL only) + TRUE cross-corpus A->B and B->A (disjoint seasons) + DM
CLUSTERED by game_id both dirs + degenerate-base guard + PLANTED-NULL control (MUST
reject; else the run is UNTRUSTWORTHY). SHIP iff +layer beats BASE on Brier AND DM
p<eps BOTH dirs AND null rejected AND base is skillful. INSUFFICIENT_DATA if <2 real
corpora on disk. REJECT is the expected honest outcome (the at-bat grid already
honest-rejected RE24 for serving; this is the in-game-layer verdict). NO $/ROI/edge:
verdict is CALIBRATION (held-out Brier), not a market edge. PROPOSAL-ONLY (no registry
write, no flag flip). CLI: python -m scripts.platformkit.ingame.ingame_atbat_layer_gate_mlb
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
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_is_degenerate, base_predict, fit_base)
from scripts.platformkit.ingame.ingame_ladder_mlb_layers import logit, sigmoid

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "funnel")
_LEV_ORD = {"low": 0.0, "mid": 1.0, "high": 2.0}


# --------------------------------------------------------------------------- load
def load_atbat_states(path: str) -> List[dict]:
    """Load a per-at-bat-states parquet into gate dicts. Frozen base schema
    (state_diff, frac_elapsed, p0, outcome, game_id) + the orphan additive as-of
    columns the half-inning grid cannot see: base_run_value (RE24 base-out run
    expectancy) and leverage_bucket (low/mid/high -> ordinal). These are the as-of
    base-out STATE at the at-bat, not a future/game-final aggregate; the realized
    win is the LABEL only."""
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
            "re24": float(r.base_run_value),          # base-out run expectancy
            "leverage": _LEV_ORD.get(str(r.leverage_bucket), 0.0),
        })
    return states


# --------------------------------------------------------------------- the new layer
def _col(states: List[dict], key: str) -> np.ndarray:
    return np.array([s[key] for s in states], float)


def _standardize(x: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """NaN-safe z-score; NaN entries map to 0 (mean) -> 0 shift (never fabricated)."""
    finite = x[np.isfinite(x)]
    mu = float(finite.mean()) if finite.size else 0.0
    sd = float(finite.std()) + 1e-9
    z = (np.where(np.isfinite(x), x, mu) - mu) / sd
    return z, mu, sd


def _features(states: List[dict], mu_r=None, sd_r=None, mu_l=None, sd_l=None):
    """Standardized (z_re24, z_leverage). On TRAIN (mu/sd None) fit the moments;
    on TEST reuse the TRAIN moments (no leak)."""
    r = _col(states, "re24")
    l = _col(states, "leverage")
    if mu_r is None:
        z_r, mu_r, sd_r = _standardize(r)
        z_l, mu_l, sd_l = _standardize(l)
    else:
        z_r = (np.where(np.isfinite(r), r, mu_r) - mu_r) / sd_r
        z_l = (np.where(np.isfinite(l), l, mu_l) - mu_l) / sd_l
    return z_r, z_l, (mu_r, sd_r, mu_l, sd_l)


def fit_atbat_layer(train: List[dict], base_tr: np.ndarray):
    """Fit (beta_r, beta_l) on TRAIN by Brier of
    sigmoid(logit(BASE)+beta_r*z_re24+beta_l*z_lev). A noise/no-signal column drives
    beta->0 (graceful degrade) -> +LAYER == BASE."""
    y = np.array([s["outcome"] for s in train], float)
    z_r, z_l, moments = _features(train)
    lo = logit(base_tr)
    best = (0.0, 0.0)
    best_b = float(np.mean((base_tr - y) ** 2))
    grid = np.linspace(-0.50, 0.50, 21)
    for br in grid:
        for bl in grid:
            p = sigmoid(lo + br * z_r + bl * z_l)
            sc = float(np.mean((p - y) ** 2))
            if sc < best_b:
                best_b, best = sc, (float(br), float(bl))
    return (best[0], best[1], moments)


def apply_atbat_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    br, bl, (mu_r, sd_r, mu_l, sd_l) = params
    z_r, z_l, _ = _features(test, mu_r, sd_r, mu_l, sd_l)
    return sigmoid(logit(base_te) + br * z_r + bl * z_l)


# ------------------------------------------ isolated RE24 (base-out run-expectancy) lever
def fit_re24_layer(train: List[dict], base_tr: np.ndarray):
    """ISOLATE the structurally-new lever: fit ONLY beta_r on base_run_value (RE24),
    leverage beta forced to 0, to tell whether base-out run-expectancy carries any
    held-out Brier signal on its own. Same Brier objective / TRAIN-only fit."""
    y = np.array([s["outcome"] for s in train], float)
    z_r, _z_l, moments = _features(train)
    lo = logit(base_tr)
    best, best_b = 0.0, float(np.mean((base_tr - y) ** 2))
    for br in np.linspace(-0.50, 0.50, 21):
        p = sigmoid(lo + br * z_r)
        sc = float(np.mean((p - y) ** 2))
        if sc < best_b:
            best_b, best = sc, float(br)
    return (best, moments)


def apply_re24_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    br, (mu_r, sd_r, mu_l, sd_l) = params
    z_r, _z_l, _ = _features(test, mu_r, sd_r, mu_l, sd_l)
    return sigmoid(logit(base_te) + br * z_r)


# ------------------------------------------------------------------ planted-null layer
def fit_null_layer(train: List[dict], base_tr: np.ndarray):
    """IDENTICAL machinery, but the 'feature' is a pure-noise column seeded ONLY by
    game/index hashing (no outcome). It MUST drive beta->0 and fail to beat BASE,
    which is the proof the gate can FAIL a signal. Same grid, same Brier objective."""
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
    """Deterministic pure-noise column from a hash of (game_id, asof index). Carries
    NO outcome information -> a correct gate finds no held-out Brier gain -> REJECT."""
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
    degen = base_is_degenerate(ab, train, base_te, y)
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
        "base_degenerate": bool(degen["degenerate"]),
        "base_bss": round(float(degen["base_bss_vs_baserate"]), 5),
        "layer_beats_base": bool((bl < bb) and (dm.p_value < eps)
                                 and not degen["degenerate"]),
    }


def gate_layer(states_a, states_b, fit_fn, apply_fn, eps: float = 0.05) -> Dict:
    a_to_b = _cross_dir(states_a, states_b, fit_fn, apply_fn, eps)
    b_to_a = _cross_dir(states_b, states_a, fit_fn, apply_fn, eps)
    replicated = a_to_b["layer_beats_base"] and b_to_a["layer_beats_base"]
    return {"a_to_b": a_to_b, "b_to_a": b_to_a, "replicated": bool(replicated)}


@dataclass
class AtBatGateVerdict:
    verdict: str
    layer_result: Dict = field(default_factory=dict)
    re24_result: Dict = field(default_factory=dict)
    null_result: Dict = field(default_factory=dict)
    null_rejected: bool = False
    base_skillful: bool = False
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "lane": "B -- at-bat RE24/leverage/base-out in-game additive layer",
            "layer": "mlb_atbat_re24_leverage (base_run_value RE24 + leverage bucket)",
            "base_model": "sigmoid((a+b*frac_elapsed)*run_diff); a,b fit per corpus",
            "gate": ("cross-corpus 2022<->2023 + DM clustered by game_id both dirs + "
                     "degenerate-base guard + planted-null control"),
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "no_dollar_field": True, "proposal_only": True,
            "null_rejected": self.null_rejected,
            "base_skillful": self.base_skillful,
            "layer_result": self.layer_result,
            "re24_only_result": self.re24_result,
            "null_result": self.null_result,
            "coverage": self.coverage, "caveats": list(self.caveats),
        }


def run_gate(states_a: List[dict], states_b: List[dict], eps: float = 0.05,
             min_games: int = 8) -> AtBatGateVerdict:
    """Full gate over two materialized at-bat corpora + the planted-null control."""
    cov = {
        "a_states": len(states_a), "a_games": len({s["game_id"] for s in states_a}),
        "b_states": len(states_b), "b_games": len({s["game_id"] for s in states_b}),
    }
    caveats = [
        "Leak-free: beta fit on TRAIN only; re24/leverage are the as-of base-out STATE "
        "at the at-bat (not a future/game-final aggregate); win/loss is the LABEL only.",
        "TRUE cross-corpus: disjoint seasons 2022<->2023; DM clustered by game_id both dirs.",
        "Degenerate-base guard: a vacuous (state,time) base is reported, not silently SHIPped.",
        "Planted-null = pure-noise column through the IDENTICAL gate; it MUST reject.",
        "No in-play odds -> CALIBRATION (held-out Brier) vs (run_diff,frac_elapsed) BASE, "
        "never a market edge. No dollar/ROI field anywhere.",
    ]
    if (cov["a_games"] < min_games or cov["b_games"] < min_games
            or len(states_a) < 200 or len(states_b) < 200):
        return AtBatGateVerdict("INSUFFICIENT_DATA", {}, {}, {}, False, False, cov,
                                caveats + ["corpus too thin / not materialized to gate"])
    # ALWAYS run the planted-null first: if it does NOT reject, the run is untrustworthy.
    null = gate_layer(states_a, states_b, fit_null_layer, apply_null_layer, eps)
    null_rejected = not null["replicated"]
    layer = gate_layer(states_a, states_b, fit_atbat_layer, apply_atbat_layer, eps)
    re24 = gate_layer(states_a, states_b, fit_re24_layer, apply_re24_layer, eps)
    base_ok = not (layer["a_to_b"]["base_degenerate"]
                   or layer["b_to_a"]["base_degenerate"])
    if not null_rejected:
        return AtBatGateVerdict("NOT_TESTABLE", layer, re24, null, False, base_ok, cov,
                                caveats + ["UNTRUSTWORTHY: planted-null did NOT reject -- "
                                           "the gate failed to fail a noise column."])
    if not base_ok:
        return AtBatGateVerdict("INVALID_BASE", layer, re24, null, True, False, cov,
                                caveats + ["BASE is degenerate in a direction -- no in-game "
                                           "result for a prior to improve; not SHIPpable."])
    verdict = "SHIP" if layer["replicated"] else "REJECT"
    return AtBatGateVerdict(verdict, layer, re24, null, True, base_ok, cov, caveats)


# --------------------------------------------------------------------------- driver
def _find_corpora() -> List[str]:
    return sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_atbat_states__*.parquet")))


def run(path_a: Optional[str] = None, path_b: Optional[str] = None,
        eps: float = 0.05) -> AtBatGateVerdict:
    """Find/load >=2 real per-at-bat corpora and gate. INSUFFICIENT_DATA (honest) if
    <2 at-bat corpora on disk."""
    if path_a is None or path_b is None:
        paths = _find_corpora()
        if len(paths) < 2:
            cov = {"corpora_found": len(paths)}
            return AtBatGateVerdict(
                "INSUFFICIENT_DATA", {}, {}, {}, False, False, cov,
                ["need >=2 materialized mlb_atbat_states__*.parquet at "
                 f"{_STATE_DIR}; found {len(paths)} -- reported honestly, not 0-filled."])
        path_a, path_b = paths[0], paths[1]
    return run_gate(load_atbat_states(path_a), load_atbat_states(path_b), eps=eps)


def write(v: AtBatGateVerdict, out: Optional[str] = None) -> str:
    if out is None:
        out = os.path.join(_OUT_DIR, "mlb_atbat_ingame_gate.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    return out


def _report(v: AtBatGateVerdict) -> str:
    lines = ["=" * 72,
             "MLB LANE B: AT-BAT RE24/leverage/base-out additive layer vs BASE",
             "GATE: cross-corpus 2022<->2023 + DM clustered by game_id + null + degen-guard",
             "=" * 72, f"VERDICT       : {v.verdict}",
             f"planted-null REJECTS: {v.null_rejected} (must be True to trust the run)",
             f"base skillful : {v.base_skillful}",
             f"coverage      : A {v.coverage.get('a_games')} games / "
             f"{v.coverage.get('a_states')} states ; B {v.coverage.get('b_games')} games "
             f"/ {v.coverage.get('b_states')} states", "-" * 72]
    for tag, res in (("+LAYER", v.layer_result), ("RE24  ", v.re24_result),
                     ("NULL  ", v.null_result)):
        for name, d in (("A->B", res.get("a_to_b", {})), ("B->A", res.get("b_to_a", {}))):
            if d:
                lines.append(f"  {tag} {name}: BASE {d['brier_base']} -> {d['brier_layer']}"
                             f" (delta {d['brier_delta']:+.5f})  DM p={d['dm_p']}  "
                             f"BSS={d['base_bss']}  beats={d['layer_beats_base']}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
