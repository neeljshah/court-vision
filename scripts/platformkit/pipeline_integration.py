"""scripts/platformkit/pipeline_integration.py — Per-sport cohesive read.

Wires existing platformkit layers (sim_framework, sgp_pricer, dist_metrics,
recalibration) into ONE honest dict per game/match.

HONEST framing: edge_claimed is ALWAYS False.  Banner is mandatory.
INVARIANTS: never edit src/, kernel/, api/main.py, scripts/team_system/.
Pure imports only.  <=300 LOC.  No pandas/pyarrow at module top.
"""
from __future__ import annotations
import argparse, json, sys
from typing import Any, Dict, List, Optional
import numpy as np
from scripts.platformkit.sim_framework import JointDistribution
from scripts.platformkit.sgp_pricer import leg_over_total, leg_side_win, price_parlay

_HONEST_BANNER = (
    "HONEST: markets efficient on point markets; "
    "line-shop/devig/CLV/calibration only; NO edge claimed."
)
_SGP_NOTE = (
    "lift = correlation structure books may misprice; "
    "realized SGP edge data-BLOCKED until real multi-leg prices"
)
_PROVENANCE = [
    "scripts.platformkit.sim_framework.JointDistribution",
    "scripts.platformkit.sgp_pricer.price_parlay",
    "scripts.platformkit.sgp_pricer.leg_over_total",
    "scripts.platformkit.sgp_pricer.leg_side_win",
    "calibration supplied by caller dict; not computed here "
    "(see scripts.platformkit.recalibration.measure_recal / dist_metrics upstream)",
]
_H, _A = 0, 1  # column indices: home=0, away=1

# ---------------------------------------------------------------------------
# Per-sport default market ladders
# ---------------------------------------------------------------------------

def build_default_market_specs(sport: str) -> Dict[str, List[float]]:
    """Return sensible per-sport total_lines and spread_lines ladders.

    No edge is implied.  Unknown sports get generic defaults.
    """
    s = sport.lower()
    if s == "nba":
        return {
            "total_lines": [210.5, 215.5, 220.5, 225.5, 230.5, 235.5],
            "spread_lines": [-10.5, -7.5, -4.5, -2.5, -1.5, 1.5, 2.5, 4.5, 7.5, 10.5],
        }
    if s == "soccer":
        return {"total_lines": [1.5, 2.5, 3.5], "spread_lines": [-1.5, -0.5, 0.5, 1.5]}
    if s == "mlb":
        return {"total_lines": [6.5, 7.5, 8.5, 9.5, 10.5], "spread_lines": [-1.5, 1.5]}
    if s == "tennis":
        return {
            "total_lines": [20.5, 21.5, 22.5, 23.5, 24.5],
            "spread_lines": [-3.5, -1.5, 1.5, 3.5],
        }
    return {"total_lines": [200.0, 210.0, 220.0], "spread_lines": [-5.5, -2.5, 2.5, 5.5]}


# ---------------------------------------------------------------------------
# Core: assemble_read
# ---------------------------------------------------------------------------

def assemble_read(
    sport: str,
    jd: JointDistribution,
    *,
    total_lines: Optional[List[float]] = None,
    spread_lines: Optional[List[float]] = None,
    sgp_legs: Optional[List[Any]] = None,
    calibration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble a cohesive per-sport honest market read from a JointDistribution.

    Parameters
    ----------
    sport       : sport identifier (e.g. 'nba', 'soccer', 'mlb', 'tennis').
    jd          : JointDistribution; samples shape (n_sims, 2) = [home, away].
    total_lines : over/under lines; falls back to build_default_market_specs.
    spread_lines: home handicap lines; falls back to build_default_market_specs.
    sgp_legs    : predicate callables for correlated parlay; None -> empty list.
    calibration : pre-computed dict from recalibration.measure_recal, or None.

    Returns dict with keys: sport, banner, surface, sgp_lifts, calibration,
    provenance, edge_claimed (always False).
    """
    defs = build_default_market_specs(sport)
    t_lines = total_lines if total_lines is not None else defs["total_lines"]
    s_lines = spread_lines if spread_lines is not None else defs["spread_lines"]

    # Moneyline
    p_home, p_away, p_tie = jd.prob_side_win(_H, _A)
    ml: Dict[str, float] = {"home": p_home, "away": p_away}
    if p_tie > 0.0:
        ml["tie"] = p_tie

    # Totals
    totals = [
        {"line": ln, "over": (ov := jd.prob_over(_H, _A, ln)), "under": round(1.0 - ov, 8)}
        for ln in t_lines
    ]

    # Spreads
    spreads = [{"line": ln, "cover_home": jd.prob_spread(_H, _A, ln)} for ln in s_lines]

    # Score means / 80% intervals
    h_lo, h_hi = jd.interval(_H, alpha=0.80)
    a_lo, a_hi = jd.interval(_A, alpha=0.80)
    surface: Dict[str, Any] = {
        "moneyline": ml,
        "totals": totals,
        "spreads": spreads,
        "score_means": {"home": jd.mean(_H), "away": jd.mean(_A)},
        "intervals": {"home": [h_lo, h_hi], "away": [a_lo, a_hi]},
    }

    # SGP lifts
    sgp_lifts: List[Dict[str, Any]] = []
    if sgp_legs:
        try:
            r = price_parlay(jd, sgp_legs)
            sgp_lifts.append({
                "legs": [repr(leg) for leg in sgp_legs],
                "joint": r["joint"],
                "independent": r["independent"],
                "lift": r["lift"],
                "correlation_sign": r["correlation_sign"],
                "note": _SGP_NOTE,
            })
        except ValueError as exc:
            sgp_lifts.append({"legs": [repr(leg) for leg in sgp_legs],
                               "error": str(exc), "note": _SGP_NOTE})

    # Calibration
    if calibration is None:
        cal_block: Dict[str, Any] = {
            "status": "pending",
            "note": (
                "No labels array supplied; calibration pending. "
                "Supply (raw_probs, outcomes) to recalibration.measure_recal."
            ),
        }
    else:
        cal_block = dict(calibration)
        cal_block.setdefault("status", "measured")

    # Optional brain context (lazy, guarded — degrades gracefully if absent).
    # Wires Track-C reads to the Track-B retrieval seam: understanding, never a number.
    brain_context: Optional[Dict[str, Any]] = None
    try:
        from dataclasses import asdict
        from scripts.platformkit.brain_query import brain_query  # type: ignore[import]
        hits = brain_query(f"{sport} team archetype scheme", sport=sport, top_k=5)
        if hits:
            brain_context = {"hits": [asdict(h) for h in hits],
                             "source": "scripts.platformkit.brain_query"}
    except Exception:  # noqa: BLE001
        pass

    out: Dict[str, Any] = {
        "sport": sport,
        "banner": _HONEST_BANNER,
        "surface": surface,
        "sgp_lifts": sgp_lifts,
        "calibration": cal_block,
        "provenance": _PROVENANCE,
        "edge_claimed": False,
    }
    if brain_context is not None:
        out["brain_context"] = brain_context
    return out


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

_DEMO_PARAMS: Dict[str, Dict[str, float]] = {
    "nba":    {"home_mu": 112.0, "away_mu": 109.0, "sigma": 12.0},
    "soccer": {"home_mu": 1.4,   "away_mu": 1.1,   "sigma": 1.2},
    "mlb":    {"home_mu": 4.5,   "away_mu": 4.2,   "sigma": 3.0},
    "tennis": {"home_mu": 22.5,  "away_mu": 20.5,  "sigma": 4.0},
}


def _build_demo_jd(sport: str, n: int = 5000, seed: int = 42) -> JointDistribution:
    # MLB: use the VALIDATED over-dispersed NegBinom run engine (domains/mlb/negbinom_sim.py)
    # instead of a Gaussian — runs are non-negative integer counts with var/mean ~2.1.
    # This routes the W101 O/U-Brier calibration win (-0.014..-0.021) into the read surface.
    if sport.lower() == "mlb":
        try:
            from domains.mlb.negbinom_sim import build_mlb_jd  # noqa: PLC0415
            p = _DEMO_PARAMS["mlb"]
            return build_mlb_jd(p["home_mu"], p["away_mu"], 4.2, 3.4,
                                n_sims=n, seed=seed, dispersion="negbinom")
        except Exception:  # noqa: BLE001 — degrade gracefully to the Gaussian fallback
            pass
    rng = np.random.default_rng(seed)
    p = _DEMO_PARAMS.get(sport.lower(), {"home_mu": 100.0, "away_mu": 97.0, "sigma": 12.0})
    home = np.clip(rng.normal(p["home_mu"], p["sigma"], n), 0, None)
    away = np.clip(rng.normal(p["away_mu"], p["sigma"], n), 0, None)
    # home/away drawn from INDEPENDENT Gaussians here -> no joint structure.
    # Label it 'independent' so the kernel honestly refuses SGP correlation pricing
    # (labelling this 'simulated' would falsely claim joint-capability).
    return JointDistribution(np.stack([home, away], axis=1), joint_quality="independent")


def _build_demo_legs(sport: str) -> List[Any]:
    over_line = 220.5 if sport.lower() == "nba" else 2.5
    return [leg_side_win(_H, _A, "a"), leg_over_total(_H, _A, over_line)]


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline_integration",
                                     description="Cohesive per-sport honest market read (demo).")
    parser.add_argument("--sport", default="nba")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    sport = args.sport.lower()
    jd = _build_demo_jd(sport)
    specs = build_default_market_specs(sport)
    read = assemble_read(sport, jd, total_lines=specs["total_lines"],
                         spread_lines=specs["spread_lines"],
                         sgp_legs=_build_demo_legs(sport), calibration=None)
    if args.json:
        print(json.dumps(read, indent=2))
        return 0
    print(f"\n{'=' * 68}")
    print(f"PIPELINE INTEGRATION READ — sport={sport.upper()}")
    print(f"{'=' * 68}")
    print(f"BANNER : {read['banner']}")
    print(f"edge_claimed : {read['edge_claimed']}")
    surf = read["surface"]
    ml = surf["moneyline"]
    tie_str = f"  tie={ml['tie']:.4f}" if "tie" in ml else ""
    print(f"\nMoneyline  home={ml['home']:.4f}  away={ml['away']:.4f}{tie_str}")
    m = surf["score_means"]
    print(f"Score means  home={m['home']:.1f}  away={m['away']:.1f}")
    iv = surf["intervals"]
    print(f"80% intervals  home=[{iv['home'][0]:.1f},{iv['home'][1]:.1f}]"
          f"  away=[{iv['away'][0]:.1f},{iv['away'][1]:.1f}]")
    print("\nTotals (first 3):")
    for t in surf["totals"][:3]:
        print(f"  {t['line']:g}: over={t['over']:.4f}  under={t['under']:.4f}")
    print("Spreads (first 3):")
    for sp in surf["spreads"][:3]:
        print(f"  {sp['line']:+g}: cover_home={sp['cover_home']:.4f}")
    if read["sgp_lifts"]:
        e = read["sgp_lifts"][0]
        if "error" in e:  # SGP honestly refused (e.g. independent marginals)
            print(f"\nSGP lift: refused — {e['error']}")
        else:
            print(f"\nSGP lift: joint={e['joint']:.4f}"
                  f"  indep={e['independent']:.4f}"
                  f"  lift={e['lift']:.4f}  ({e.get('correlation_sign','')})")
        print(f"  NOTE: {e['note']}")
    print(f"\nCalibration: status={read['calibration']['status']}")
    print("\nProvenance:")
    for pv in read["provenance"]:
        print(f"  - {pv}")
    print(f"{'=' * 68}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
