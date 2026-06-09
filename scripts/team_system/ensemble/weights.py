"""RELIABILITY-WEIGHTED ENSEMBLE -- the correlation/redundancy guard + a default-OFF weight PROPOSAL
(MASTER_SYSTEM_BUILD section 4D).

WHAT IS HONESTLY COMPUTABLE NOW (and is, here):
  - the measured 7-engine correlation matrix + N_eff (engine_decorrelation_full.json), leak-free on real
    league matchups -> a GLS / minimum-variance weight proposal that SPLITS weight among correlated engines
    (the redundancy penalty: 4 net-rating engines that move together must not pose as 4 independent votes).
  - per-engine `engine_corr` (mean off-diagonal correlation) wired into engine_registry.
  - the N_eff-widened honest uncertainty factor sqrt(n / N_eff).

WHAT IS NOT YET COMPUTABLE (so equal-weight STAYS the shipped default -- section 4D forbids manufacturing
in-sample weights):
  - per-engine SKILL/RELIABILITY (per-game error vs realized) scored leak-free CROSS-SEASON. The 7 engines
    read full-season caches (no per-game as-of prediction substrate) and there is no FROZEN second season for
    them. Building that = the section 4C engine as-of refactor. Until it exists, the GLS proposal assumes
    EQUAL per-engine skill -> it is a REDUNDANCY guard, NOT a skill-weighting, and is recorded DEFAULT-OFF.

This module therefore records a PROPOSAL (data/registry/ensemble_weights_proposal.json) and wires engine_corr;
it NEVER flips predict_ensemble off equal-weight (that is a human-approval gate, section 7.6).

  python scripts/team_system/ensemble/weights.py
"""
from __future__ import annotations
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
DECORR = os.path.join(ROOT, "data", "cache", "team_system", "engine_decorrelation_full.json")
PROPOSAL = os.path.join(ROOT, "data", "registry", "ensemble_weights_proposal.json")


def redundancy_weights(corr: np.ndarray) -> np.ndarray:
    """NON-NEGATIVE redundancy-penalty weights: w_i proportional to 1 / sum_j max(corr_ij, 0). An engine in a
    tight correlated cluster (the 4 net-rating engines) gets down-weighted; a decorrelated engine
    (possession_mc, clock) gets up-weighted. Unconstrained GLS (C^-1 1) goes long-short on this near-singular
    matrix -- which is itself proof these are not shippable as skill weights -- so we use the bounded,
    always-positive redundancy penalty instead (section 4D 'redundancy penalty')."""
    n = corr.shape[0]
    cluster = np.array([np.clip(corr[i], 0, None).sum() for i in range(n)])   # ~ effective cluster size
    w = 1.0 / np.maximum(cluster, 1e-6)
    return w / w.sum()


def build_proposal() -> dict:
    if not os.path.exists(DECORR):
        return dict(ok=False, reason="engine_decorrelation_full.json missing -- run engine_decorrelation_full.py")
    d = json.load(open(DECORR))
    engines = d["engines"]
    C = np.asarray(d["corr_matrix"], float)
    n = len(engines)
    w = redundancy_weights(C)
    n_eff = float(d.get("n_eff_full", n))
    widen = float(np.sqrt(n / max(n_eff, 1e-6)))
    mean_corr = {engines[i]: round(float((C[i].sum() - 1) / (n - 1)), 3) for i in range(n)}
    proposal = dict(
        status="PROPOSAL_DEFAULT_OFF", shipped_default="equal_weight",
        method="gls_correlation_guard (equal-skill; redundancy penalty only)",
        engines=engines, equal_weight=round(1.0 / n, 4),
        proposed_weights={engines[i]: round(float(w[i]), 4) for i in range(n)},
        engine_corr=mean_corr, n_eff=round(n_eff, 3), uncertainty_widen_factor=round(widen, 3),
        outstanding_precondition=("per-engine SKILL scored leak-free CROSS-SEASON (section 4C engine as-of "
                                  "refactor) + human approval to flip the shipped default (section 7.6)"),
        note=("This is the redundancy/correlation guard ONLY. It assumes equal per-engine skill, so it must "
              "NOT be shipped as a skill-weighting. Equal-weight remains the shipped default until a leak-free "
              "cross-season per-engine reliability backtest exists."))
    return dict(ok=True, proposal=proposal)


def wire_engine_corr(proposal: dict) -> int:
    """Record each engine's mean correlation (engine_corr) into engine_registry -- real, queryable progress."""
    sys.path.insert(0, HERE)
    from registry.store import Registry
    ereg = Registry("engine_registry")
    alias = {"clock_trajectory": "clock", "clock": "clock_trajectory"}   # decorr json uses 'clock'
    n = 0
    for _, e in ereg.all().iterrows():
        ec = proposal["engine_corr"].get(e["name"]) or proposal["engine_corr"].get(alias.get(e["name"], ""))
        if ec is not None:
            ereg.update_status(e["engine_id"], engine_corr=float(ec))
            n += 1
    return n


def main():
    res = build_proposal()
    if not res["ok"]:
        print("CANNOT build proposal:", res["reason"]); return
    p = res["proposal"]
    tmp = PROPOSAL + ".tmp"
    json.dump(p, open(tmp, "w", encoding="utf-8"), indent=2)
    os.replace(tmp, PROPOSAL)
    nwired = wire_engine_corr(p)
    print("=== RELIABILITY-WEIGHTED ENSEMBLE (section 4D) -- DEFAULT-OFF PROPOSAL ===")
    print(f"shipped default: {p['shipped_default']} (equal {p['equal_weight']} each)")
    print(f"N_eff = {p['n_eff']} effective views (of {len(p['engines'])}); uncertainty widen x{p['uncertainty_widen_factor']}")
    print("proposed GLS (redundancy-penalty, equal-skill) weights:")
    for e in p["engines"]:
        print(f"  {e:20s} corr {p['engine_corr'][e]:+.3f}  ->  w {p['proposed_weights'][e]:.4f}")
    print(f"\nengine_corr wired into engine_registry for {nwired} engines.")
    print(f"OUTSTANDING (B8 stays BLOCKED, equal-weight shipped): {p['outstanding_precondition']}")
    # B8 marker: record the proposal + correlation guard, but method stays 'equal' (shipped) -> B8 check
    # remains FAIL until cross-season skill weights exist + a human flips. We do NOT fake the cross-season pass.
    from build_done_check import write_marker
    write_marker("B8_ensemble_weights", dict(method="equal", proposal_built=True, n_eff=p["n_eff"],
                 shipped_default="equal_weight", proposal_path=os.path.relpath(PROPOSAL, ROOT),
                 outstanding=p["outstanding_precondition"], asof="2026-06-08"))
    print("proposal recorded; B8 marker = equal-weight shipped (BLOCKED on cross-season skill + human flip).")


if __name__ == "__main__":
    main()
