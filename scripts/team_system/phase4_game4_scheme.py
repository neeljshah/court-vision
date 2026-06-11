"""PHASE 4 — Game 4 (NYK home vs SAS): baseline sim (the NUMBER) vs LLM-contextualized sim (scouting).

Phase-3 gate REJECTED the scheme layer for the bettable number (leak-free signal redundant; leak-free
possession WF infeasible). Therefore: the BASELINE sim is the prediction; the LLM scheme read is a clearly
labeled SCOUTING NARRATIVE that does NOT move the number. We still run both sims and attribute each delta
to a named, leak-flagged adjustment, for the scouting brief.

The scout adjustments below are authored by the Opus scheme reasoner from the Phase-1 leak-free + scouting
artifacts (Wemby rim wall, NYK pressure + pace control, SAS guard TO risk). Every adjustment is bounded,
named, justified, confidence-weighted, and leak-flagged. NONE move the number (gate failed).
"""
from __future__ import annotations
import json, os, sys
import numpy as np

ROOT = r"C:\Users\neelj\nba-ai-system"
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
from sim.basketball_sim import TeamModel, simulate_game  # noqa: E402
from sim.scheme_prior import apply_scheme_priors, validate_adjustment  # noqa: E402

NSIMS, SEED = 20000, 2026

# --- the Opus scheme-scout's G4 read (bounded, named, justified, leak-flagged) ---
# leak_safe=True  -> derived from leak-free season/expanding identity (number-eligible IF the gate had passed)
# leak_safe=False -> in-season series/coverage read -> SCOUTING ONLY, never a betting number
G4_ADJ = {
    "NYK": [
        dict(entity="TEAM", param="pace", mult=0.97, confidence=0.6, horizon="g4", leak_safe=True,
             why="NYK is a slow-tempo team (season poss_z -1.24); Finals grind compresses possessions further."),
        dict(entity="TEAM", param="tov_force", mult=1.06, confidence=0.5, horizon="g4", leak_safe=False,
             why="SCOUTING: NYK ball pressure has forced SAS's young guards (Castle/Champagnie) into live-ball TOs across the series."),
        dict(entity="TEAM", param="perim_d", mult=1.03, confidence=0.4, horizon="g4", leak_safe=True,
             why="NYK expanding (leak-free) PPP-allowed below league -> perimeter containment edge at the Garden."),
    ],
    "SAS": [
        dict(entity="TEAM", param="int_d", mult=1.07, confidence=0.6, horizon="g4", leak_safe=False,
             why="SCOUTING: Wembanyama's rim protection (int_d ~93, 3.2 blk) is a paint wall vs NYK's rim-pressure offense (drop coverage concedes mid, denies rim)."),
        dict(entity="TEAM", param="ft_force", mult=0.96, confidence=0.45, horizon="g4", leak_safe=True,
             why="SAS expanding (leak-free) FT-allowed below league (wf_ft_allowed_z<0) -> fewer NYK trips to the line."),
        dict(entity="TEAM", param="pace", mult=0.99, confidence=0.4, horizon="g4", leak_safe=True,
             why="SAS near-league-average tempo (poss_z ~0); slight slowdown on the road in a grind series."),
    ],
}


def _summ(r):
    h, a = r.home_total, r.away_total
    return dict(home=float(h.mean()), away=float(a.mean()),
                spread=float((h - a).mean()), total=float((h + a).mean()),
                home_wp=float(np.mean(h > a)))


def run_sim(adj_by_team=None, betting_mode=False):
    os.environ.pop("CV_LLM_SCHEME", None)  # we apply explicitly, not via the from_cache hook
    nyk = TeamModel.from_cache("NYK"); sas = TeamModel.from_cache("SAS")
    reports = {}
    if adj_by_team:
        for tri, model in (("NYK", nyk), ("SAS", sas)):
            adjs = [validate_adjustment(d) for d in adj_by_team.get(tri, [])]
            reports[tri] = apply_scheme_priors(model, adjs, betting_mode=betting_mode)
    return simulate_game(nyk, sas, n_sims=NSIMS, seed=SEED), reports


def main():
    print("=" * 78)
    print("GAME 4 — NYK (home) vs SAS  |  0042500404  |  series NYK 2-1")
    print("=" * 78)
    base, _ = run_sim(None)
    b = _summ(base)
    print(f"\nBASELINE possession-sim (CV_LLM_SCHEME OFF) -- THIS IS THE PREDICTION (gate rejected the layer):")
    print(f"  NYK {b['home']:.1f} - SAS {b['away']:.1f} | spread NYK {b['spread']:+.1f} | total {b['total']:.1f} | NYK win% {b['home_wp']:.1%}")

    ctx, reports = run_sim(G4_ADJ, betting_mode=False)  # research/scouting: applies the FULL read incl leak_safe=False
    c = _summ(ctx)
    print(f"\nLLM-CONTEXTUALIZED sim (full scout read; SCOUTING ONLY -- does NOT move the number):")
    print(f"  NYK {c['home']:.1f} - SAS {c['away']:.1f} | spread NYK {c['spread']:+.1f} | total {c['total']:.1f} | NYK win% {c['home_wp']:.1%}")
    print(f"\nDELTA (contextualized - baseline), attributed to the scheme read:")
    print(f"  Δ NYK win% {c['home_wp'] - b['home_wp']:+.1%} | Δ spread {c['spread'] - b['spread']:+.1f} | Δ total {c['total'] - b['total']:+.1f}")
    print("  attribution:")
    for tri in ("NYK", "SAS"):
        for d in G4_ADJ[tri]:
            tag = "leak-free" if d["leak_safe"] else "SCOUTING-only"
            print(f"    {tri} {d['param']:<10} x{d['mult']:.2f} (conf {d['confidence']:.2f}, {tag}): {d['why'][:90]}")
    n_betting = sum(1 for tri in G4_ADJ for d in G4_ADJ[tri] if d["leak_safe"])
    print(f"\n  number-eligible (leak_safe) adjustments: {n_betting} — but GATE REJECTED -> none move the bettable number.")

    out = dict(game="0042500404", baseline=b, contextualized=c,
               delta=dict(home_wp=c['home_wp'] - b['home_wp'], spread=c['spread'] - b['spread'], total=c['total'] - b['total']),
               gate="REJECT (Phase 3) -> LLM read is scouting narrative; number = baseline",
               adjustments=G4_ADJ, apply_reports=reports)
    json.dump(out, open(os.path.join(ROOT, ".planning", "scheme", "GAME4_SCHEME_PREDICTION.json"), "w"),
              indent=2, default=str)
    print("\n  wrote .planning/scheme/GAME4_SCHEME_PREDICTION.json")


if __name__ == "__main__":
    main()
