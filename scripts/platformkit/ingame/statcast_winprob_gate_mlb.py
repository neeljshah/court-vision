"""scripts.platformkit.ingame.statcast_winprob_gate_mlb -- GATE the genuinely-NEW
Statcast per-pitch fields (release_spin_rate, estimated_woba_using_speedangle,
release_speed), aggregated LEAK-FREE as as-of pre-state means, as ADDITIVE features on
the proven in-game win-prob BASE -- the DEEPEST untested new-data question for MLB in-game.

BASE   = sigmoid((a + b*frac_elapsed)*state_diff); a,b fit per corpus (run-diff win-prob).
+FEAT  = sigmoid(logit(BASE) + sum_k beta_k * z_k); z_k = standardized as-of mean of
         {spin, woba, speed} (NaN where no prior half-inning -> 0 shift, never fabricated);
         beta fit on TRAIN only by Brier grid (a no-signal column -> beta->0, degrade==BASE).

GATE (identical sacred bar; never weakened): leak-free (beta TRAIN-only; features are
as-of by statcast_winprob_join, the current half-inning's pitches excluded) + TRUE
cross-corpus A->B and B->A (disjoint seasons 2022<->2023) + DM CLUSTERED by game_id BOTH
dirs + a PLANTED-NULL control that MUST reject through the IDENTICAL gate + a base-skill
check (BASE must beat a degenerate constant-base-rate). SHIP iff +FEAT beats BASE on
held-out Brier AND DM p<eps BOTH dirs AND null rejects AND base is skillful. REJECT is
the expected honest meta-finding. TIER3_BLOCKED if the overlap corpus is missing.

CALIBRATION only (held-out Brier); NO $/ROI/edge; vs-close UNPROVEN. PROPOSAL-ONLY: no
registry write, no flag flip, nothing wired unless it cleanly SHIPS. ASCII; <=300 LOC.
CLI: python -m scripts.platformkit.ingame.statcast_winprob_gate_mlb
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_gate_generic_models import base_predict, fit_base
from scripts.platformkit.ingame.ingame_ladder_mlb_layers import logit, sigmoid
from scripts.platformkit.ingame.ingame_pitch_layer_gate_mlb import (
    apply_null_layer, fit_null_layer)
from scripts.platformkit.ingame.statcast_winprob_join import build_joined_states

_OUT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "data", "frontend", "funnel", "mlb_statcast_winprob_gate.json"))
_FEATS = ("sc_spin", "sc_woba", "sc_speed")
_SEASONS = (2022, 2023)


def _standardize(x: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """NaN-safe z-score; NaN (no prior pitch) maps to 0 (mean) -> 0 shift, never faked."""
    finite = x[np.isfinite(x)]
    mu = float(finite.mean()) if finite.size else 0.0
    sd = float(finite.std()) + 1e-9
    z = (np.where(np.isfinite(x), x, mu) - mu) / sd
    return z, mu, sd


def _zmat(states: List[dict], moments=None):
    """Standardized feature matrix (n x 3). On TRAIN fit moments; on TEST reuse them."""
    raw = {k: np.array([s[k] for s in states], float) for k in _FEATS}
    if moments is None:
        cols, moments = [], {}
        for k in _FEATS:
            z, mu, sd = _standardize(raw[k])
            cols.append(z)
            moments[k] = (mu, sd)
    else:
        cols = []
        for k in _FEATS:
            mu, sd = moments[k]
            x = raw[k]
            cols.append((np.where(np.isfinite(x), x, mu) - mu) / sd)
    return np.vstack(cols).T, moments


def fit_feat_layer(train: List[dict], base_tr: np.ndarray):
    """Coordinate-descent Brier fit of (beta_spin, beta_woba, beta_speed) on TRAIN only.
    A no-signal feature is driven to beta~0 (graceful degrade -> +FEAT==BASE)."""
    y = np.array([s["outcome"] for s in train], float)
    Z, moments = _zmat(train)
    lo = logit(base_tr)
    beta = np.zeros(Z.shape[1])
    grid = np.linspace(-0.50, 0.50, 21)
    for _ in range(3):  # a few sweeps for convergence
        for j in range(Z.shape[1]):
            best_b = float(np.mean((sigmoid(lo + Z @ beta) - y) ** 2))
            best_v = beta[j]
            for v in grid:
                b2 = beta.copy()
                b2[j] = v
                sc = float(np.mean((sigmoid(lo + Z @ b2) - y) ** 2))
                if sc < best_b:
                    best_b, best_v = sc, float(v)
            beta[j] = best_v
    return (beta, moments)


def apply_feat_layer(test: List[dict], base_te: np.ndarray, params) -> np.ndarray:
    beta, moments = params
    Z, _ = _zmat(test, moments)
    return sigmoid(logit(base_te) + Z @ beta)


def _cross_dir(train, test, fit_fn, apply_fn, eps: float) -> Dict:
    ab = fit_base(train)
    base_tr, base_te = base_predict(train, ab), base_predict(test, ab)
    y = np.array([s["outcome"] for s in test], float)
    params = fit_fn(train, base_tr)
    layer_te = apply_fn(test, base_te, params)
    bb, bl = float(brier(base_te, y)), float(brier(layer_te, y))
    d = (base_te - y) ** 2 - (layer_te - y) ** 2  # +ve => layer beats base
    dm = diebold_mariano(d, [s["game_id"] for s in test])
    return {"n_train": len(train), "n_test": len(test), "n_games": dm.n_clusters,
            "brier_base": round(bb, 5), "brier_layer": round(bl, 5),
            "brier_delta": round(bb - bl, 6),
            "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
            "layer_beats_base": bool((bl < bb) and (dm.p_value < eps))}


def _gate(a, b, fit_fn, apply_fn, eps: float) -> Dict:
    ab = _cross_dir(a, b, fit_fn, apply_fn, eps)
    ba = _cross_dir(b, a, fit_fn, apply_fn, eps)
    return {"a_to_b": ab, "b_to_a": ba,
            "replicated": bool(ab["layer_beats_base"] and ba["layer_beats_base"])}


def _base_skillful(a, b) -> Dict:
    """BASE must beat a degenerate constant predictor (the train base-rate). Guards a
    trivial/degenerate base from passing a feature through on a non-skillful comparison."""
    out = {}
    for tag, tr, te in (("a", a, b), ("b", b, a)):
        ab = fit_base(tr)
        p = base_predict(te, ab)
        y = np.array([s["outcome"] for s in te], float)
        rate = float(np.mean([s["outcome"] for s in tr]))
        out[tag] = {"brier_base": round(float(brier(p, y)), 5),
                    "brier_const": round(float(brier(np.full(len(y), rate), y)), 5)}
    skillful = all(out[t]["brier_base"] < out[t]["brier_const"] for t in ("a", "b"))
    out["base_skillful"] = bool(skillful)
    return out


def run(eps: float = 0.05, min_games: int = 8) -> Dict[str, object]:
    builds = {s: build_joined_states(s) for s in _SEASONS}
    a, ia = builds[_SEASONS[0]]
    b, ib = builds[_SEASONS[1]]
    cov = {"a": {k: ia.get(k) for k in ("overlap_games", "espn_states", "matched_asof_rows")},
           "b": {k: ib.get(k) for k in ("overlap_games", "espn_states", "matched_asof_rows")},
           "total_overlap_games": int(ia.get("overlap_games", 0) or 0)
           + int(ib.get("overlap_games", 0) or 0)}
    caveats = [
        "Leak-free: beta fit on TRAIN only; Statcast features are as-of (current "
        "half-inning's pitches excluded by statcast_winprob_join); NaN->0 shift, not faked.",
        "TRUE cross-corpus 2022<->2023 (disjoint seasons); DM clustered by game_id both dirs.",
        "Planted-null = pure-noise column through the IDENTICAL gate; it MUST reject.",
        "CALIBRATION (held-out Brier) vs the (state_diff,frac_elapsed) BASE; never a market "
        "edge; vs-close UNPROVEN; NO $ anywhere.",
    ]
    if ia.get("reasons") or ib.get("reasons") or not a or not b:
        return _verdict("TIER3_BLOCKED", {}, {}, False, {}, cov,
                        caveats + [f"overlap missing: a={ia.get('reasons')} b={ib.get('reasons')}"])
    if (cov["a"]["overlap_games"] < min_games or cov["b"]["overlap_games"] < min_games
            or len(a) < 200 or len(b) < 200):
        return _verdict("INSUFFICIENT_DATA", {}, {}, False, {}, cov,
                        caveats + ["corpus too thin to gate"])
    skill = _base_skillful(a, b)
    null = _gate(a, b, fit_null_layer, apply_null_layer, eps)
    null_rejected = not null["replicated"]
    layer = _gate(a, b, fit_feat_layer, apply_feat_layer, eps)
    if not null_rejected:
        return _verdict("NOT_TESTABLE", layer, null, False, skill, cov,
                        caveats + ["UNTRUSTWORTHY: planted-null did NOT reject."])
    if not skill["base_skillful"]:
        return _verdict("NOT_TESTABLE", layer, null, null_rejected, skill, cov,
                        caveats + ["UNTRUSTWORTHY: BASE not skillful vs constant base-rate."])
    verdict = "SHIP" if layer["replicated"] else "REJECT"
    return _verdict(verdict, layer, null, null_rejected, skill, cov, caveats)


def _verdict(v, layer, null, null_rej, skill, cov, caveats) -> Dict[str, object]:
    return {
        "verdict": v,
        "layer": "mlb_statcast_winprob (as-of spin + estimated_woba + release_speed)",
        "base_model": "sigmoid((a+b*frac_elapsed)*state_diff); a,b fit per corpus",
        "gate": "cross-corpus 2022<->2023 + DM clustered by game_id + planted-null + base-skill",
        "richer_fields": list(_FEATS),
        "null_rejected": bool(null_rej),
        "base_skill": skill,
        "layer_result": layer, "null_result": null, "coverage": cov,
        "caveats": list(caveats),
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "no_dollar_field": True, "proposal_only": True,
    }


def write(res: Dict[str, object], out: Optional[str] = None) -> str:
    out = out or _OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(res, f, indent=2, sort_keys=True)
    return out


def _report(r: Dict[str, object]) -> str:
    L = ["=" * 76,
         "MLB STATCAST RICHER PER-PITCH -> IN-GAME WIN-PROB ADDITIVE GATE",
         "GATE: cross-corpus 2022<->2023 + DM clustered by game_id + planted-null + base-skill",
         "=" * 76, f"VERDICT            : {r['verdict']}",
         f"richer fields      : {', '.join(r['richer_fields'])}",
         f"planted-null rejects: {r.get('null_rejected')}",
         f"base skillful      : {r.get('base_skill', {}).get('base_skillful')}",
         f"overlap games      : {r.get('coverage', {}).get('total_overlap_games')}", "-" * 76]
    for tag, res in (("+FEAT", r.get("layer_result", {})), ("NULL ", r.get("null_result", {}))):
        for nm, d in (("A->B", res.get("a_to_b", {})), ("B->A", res.get("b_to_a", {}))):
            if d:
                L.append(f"  {tag} {nm}: BASE {d['brier_base']} -> {d['brier_layer']} "
                         f"(delta {d['brier_delta']:+.6f})  DM p={d['dm_p']}  "
                         f"beats={d['layer_beats_base']}")
    L += ["=" * 76,
          "CALIBRATION only; NO $/ROI/edge; vs-close UNPROVEN. REJECT = honest meta-finding.",
          "=" * 76]
    return "\n".join(L)


def main() -> int:
    r = run()
    p = write(r)
    print(_report(r))
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run", "write", "fit_feat_layer", "apply_feat_layer", "_zmat", "_standardize"]
