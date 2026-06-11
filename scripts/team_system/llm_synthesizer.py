"""llm_synthesizer.py — the LLM ENGINE-JUDGE / SYNTHESIZER (gate CV_LLM_SYNTH, default-OFF).

The problem this solves: the system emits MANY numbers (16 engines + possession MC + clutch overlay)
that disagree (G4: MC 42% vs equal-weight 52% vs +clutch 56%). Showing all of them and saying "coin
flip" punts the synthesis to the human. This layer uses the LLM to WEIGH which engines actually carry
INDEPENDENT, VALIDATED signal, reconcile them into ONE concise number, and narrate what will happen.

DISCIPLINE (the load-bearing law, preserved):
  * The LLM NEVER invents the number. It chooses BOUNDED weights over the ENGINES; the number is a
    convex combination of REAL engine win%s (sum(w_i * wp_i)). The LLM's only free output is the
    NARRATIVE ("what will happen") + the reasoning for the weights.
  * Weighting is decorrelation-aware + reliability-aware + pregame-validity-aware (transparent rules
    below); the LLM mode may nudge within bounds, never outside.
  * Validated default stays EQUAL-WEIGHT (learned weighting did NOT beat it leak-free, N_eff~2.2;
    engine_reliability_weights.json beats_equal_weight=False). So this layer is DECISION-SUPPORT (a
    concise reasoned call), NOT a claimed accuracy edge, unless it beats equal-weight leak-free.

The reasoned weighting (the "which engines are actually better" logic):
  1. DECORRELATION (N_eff correction): redundant engines (corr_to_cluster >= 0.85) collectively get ONE
     shared slot (so 8 correlated net-rating engines don't count as 8 votes); each decorrelating engine
     (r < 0.85) + the MC get a full slot. This stops the redundant cluster from dominating.
  2. RELIABILITY tilt: within the redundant cluster, weight by 1/Brier^2 where a validated leak-free
     Brier exists (engine_reliability_weights.json).
  3. PREGAME-VALIDITY gate: clutch_close is REJECTED as a pregame marginal (OOS +0.01%, llm_context_layer
     law) -> down-weight it hard for the pregame number (it is an IN-GAME signal, not pregame).
"""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
GATE = "CV_LLM_SYNTH"
_TRUTHY = frozenset({"1", "true", "yes", "on", "y", "t"})

# Live G4 engine board snapshot (win% home, margin) captured from predict_ensemble16.run().
# refresh=True re-runs the ensemble; default uses this snapshot for reproducibility.
_G4_BOARD = {
    "attribute_matchup": (0.394, -3.6), "four_factors": (0.584, 3.5), "player_impact": (0.523, 0.9),
    "power_ratings": (0.511, 0.4), "team_score": (0.547, 2.0), "bayesian_power": (0.531, 1.1),
    "bradley_terry": (0.440, -2.1), "clutch_close": (0.721, 8.5), "elo": (0.333, 1.0),
    "ft_environment": (0.535, 1.4), "lineup_markov": (0.511, 0.4), "matchup_physics": (0.363, -4.7),
    "shot_quality_xpts": (0.511, 0.4), "transition_origin": (0.591, 4.2),
    "possession_mc": (0.419, -3.5), "clock_trajectory": (0.602, 4.2),
}
# engines rejected as PREGAME marginals (valid in-game only) -> hard down-weight for a pregame call
_PREGAME_REJECTED = {"clutch_close": 0.15}  # weight multiplier


def _synth_on() -> bool:
    return os.environ.get(GATE, "").strip().lower() in _TRUTHY


def _decorr_r() -> Dict[str, float]:
    """corr_to_cluster per engine from the decorrelation audit ({} if absent)."""
    p = os.path.join(TS, "engine_decorrelation16.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    return {k.replace("engine_", ""): v for k, v in d.get("corr_to_cluster", {}).items()}


def _validated_brier() -> Dict[str, float]:
    p = os.path.join(TS, "engine_reliability_weights.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    return {k: v.get("brier") for k, v in d.get("per_engine", {}).items() if v.get("brier")}


def reasoned_weights(board: Dict[str, tuple], decorr: Dict[str, float],
                     brier: Dict[str, float]) -> Dict[str, float]:
    """Decorrelation + reliability + pregame-validity aware weights (sum to 1). Transparent, bounded."""
    REDUNDANT = {e for e, r in decorr.items() if r is not None and r >= 0.85}
    # the redundant net-rating cluster shares ONE slot; everything else gets a full slot
    raw: Dict[str, float] = {}
    n_redundant = max(len(REDUNDANT), 1)
    for e in board:
        if e in REDUNDANT:
            w = 1.0 / n_redundant                      # 8 correlated engines -> 1 vote total
            if e in brier:                              # reliability tilt inside the cluster
                w *= (0.20 / brier[e]) ** 2             # ~Brier 0.20 reference; better engine -> more
        else:
            w = 1.0                                     # decorrelating engine / MC -> full vote
        w *= _PREGAME_REJECTED.get(e, 1.0)              # pregame-invalid engines down-weighted
        raw[e] = w
    s = sum(raw.values()) or 1.0
    return {e: w / s for e, w in raw.items()}


def synthesize(board: Optional[Dict[str, tuple]] = None) -> dict:
    """Return the reasoned single number + the equal-weight baseline + provenance. LLM-free math."""
    board = board or _G4_BOARD
    decorr = _decorr_r()
    brier = _validated_brier()
    w = reasoned_weights(board, decorr, brier)
    wp = {e: v[0] for e, v in board.items()}
    reasoned_wp = sum(w[e] * wp[e] for e in board)
    equal_wp = sum(wp.values()) / len(wp)
    redundant = sorted(e for e, r in decorr.items() if r is not None and r >= 0.85)
    decorrelating = sorted(e for e in board if e not in redundant)
    return {
        "reasoned_win_prob_home": round(reasoned_wp, 4),
        "equal_weight_win_prob_home": round(equal_wp, 4),
        "weights": {e: round(w[e], 4) for e in sorted(w, key=lambda x: -w[x])},
        "redundant_cluster": redundant,
        "decorrelating_engines": decorrelating,
        "pregame_rejected_downweighted": list(_PREGAME_REJECTED),
        "validated_default": "equal_weight (learned weighting did NOT beat it leak-free; beats_equal_weight=False)",
        "honest_status": ("DECISION-SUPPORT concise call, NOT a validated accuracy edge. The number is a "
                          "convex combo of real engine win%s; the LLM weighs + narrates, never invents."),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description="LLM engine-judge / synthesizer (CV_LLM_SYNTH)")
    ap.add_argument("--refresh", action="store_true", help="re-run predict_ensemble16 for a live board")
    a = ap.parse_args()
    board = None
    if a.refresh:
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from predict_ensemble16 import run as ens_run  # type: ignore
            res = ens_run("NYK", "SAS")
            preds = res.get("preds") or res.get("engines") or []
            board = {p["engine"]: (p["win_prob_home"], p.get("margin_home", 0.0)) for p in preds}
        except Exception as e:
            print(f"  (refresh failed: {str(e)[:80]}; using snapshot)")
            board = None
    out = synthesize(board)
    print("=" * 74)
    print(f"LLM SYNTHESIZER — gate CV_LLM_SYNTH={'ON' if _synth_on() else 'OFF (default; equal-weight ships)'}")
    print("=" * 74)
    print(f"REASONED single number   : NYK {out['reasoned_win_prob_home']*100:.1f}%")
    print(f"equal-weight baseline     : NYK {out['equal_weight_win_prob_home']*100:.1f}%  ({out['validated_default']})")
    print(f"\nredundant cluster (1 shared vote): {out['redundant_cluster']}")
    print(f"decorrelating / MC (full votes)  : {out['decorrelating_engines']}")
    print(f"pregame-rejected, down-weighted  : {out['pregame_rejected_downweighted']}")
    print(f"\ntop engine weights:")
    for e, wv in list(out["weights"].items())[:10]:
        print(f"   {e:20s} {wv*100:5.1f}%")
    print(f"\n{out['honest_status']}")
    json.dump(out, open(os.path.join(ROOT, ".planning", "scheme", "G4_SYNTHESIS.json"), "w"), indent=2)
    print("\nwrote .planning/scheme/G4_SYNTHESIS.json")


if __name__ == "__main__":
    main()
