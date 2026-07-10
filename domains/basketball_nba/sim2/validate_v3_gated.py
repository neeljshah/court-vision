"""domains.basketball_nba.sim2.validate_v3_gated -- bucket-GATED v3 composite
side-by-side deploy candidate. Nothing is deployed, no flag, no default change.

HISTORY (why this candidate, not blanket v3): the blanket v3 composite (all
buckets) FAILED the preregistered replication pooled bar
(nba_sim2_v3_replication.json, ledger row 'sim2_v3_lineup_composite_conditioner_
REPLICATION', verdict NULL) even though 2 named buckets (P3|m3, P2|m1) held
their PIT-improvement DIRECTION in 5/5 MC seeds AND both within-season
temporal halves -- only the ALL-BUCKET pooled statistic exceeded tolerance.
A separate Q4-scoped clutch conditioner (validate_clutch.py) tried to rescue
the 3rd named bucket (P4|m2, which the full v3 composite REGRESSED
0.1292->0.1403) and also NULL'd (pooled improved only 1/2 seeds). That P4|m2
regression gate holds and is not reopened here.

DESIGN (routing-level gate, not a new fitted model): reuses validate_v3.fit_v3
verbatim for the fitted CDFs (pcdf2, pcdf3, composite gcd/thr) -- no
refit, no new conditioner class. Per LIVE SNAPSHOT (period, margin_bucket),
if its reporting bucket key is in GATE_BUCKETS, route to the v3-conditioned
simulate() call (S.simulate(..., comp_home=, comp_thr=)); otherwise route to
the plain v2 simulate() call. This is a QUERY-ROUTING gate ("which live
states get the v3 estimator"), matching how a deploy candidate would actually
be consulted, not a cell-level conditioning restriction (that's what
cond_clutch.ScopedConditionedModel already does for a different hypothesis).
By construction, every non-gated bucket (including P4|m2) is IDENTICAL to
pure v2 -- the v3 simulate() call is never even invoked there, so P4|m2 is
provably untouched, not just numerically close.

Reuses S.simulate/pit_value/crps_ensemble, validate._snapshots,
possession_model.margin_bucket, and validate_v3._uniformity_dev verbatim (the
sim/PIT/CRPS machinery is 100% reused); only the per-snapshot ROUTING decision
is new. validate_v3.py/fit_v3 are READ-ONLY -- not modified.

PREREGISTERED GATE BAR (declared before running): SHIP_CANDIDATE_GATED iff,
in BOTH seed offsets --
  (a) both gate buckets (P3|m3, P2|m1) have pit_dev_gated < pit_dev_v2, AND
  (b) pooled pit_dev_gated <= pooled pit_dev_v2 + POOLED_TOL (0.0005, same
      tolerance replicate_v3 used), AND
  (c) P4|m2 pit_dev_gated == P4|m2 pit_dev_v2 exactly (construction check).
Gate buckets have zero test-set observations in a seed -> UNDERPOWERED.
(c) failing is a construction bug -> REJECT regardless of (a)/(b).

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge
claim. Side-by-side candidate ONLY.
CLI: cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_nba.sim2.validate_v3_gated [--max-fit-games N]
Test: python -m pytest domains/basketball_nba/sim2/test_validate_v3_gated.py -q
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np

from domains.basketball_nba.sim2 import simulator as S
from domains.basketball_nba.sim2.possession_model import margin_bucket
from domains.basketball_nba.sim2.validate import _snapshots
from domains.basketball_nba.sim2.validate_v3 import fit_v3, _uniformity_dev, LEDGER

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "nba_sim2_v3_gated_validation.json"
N_DIST = 2000
GATE_BUCKETS = ["P3|m3", "P2|m1"]
POOLED_TOL = 0.0005
SEEDS = (0, 1000)   # matches cond_clutch's bounded 2-seed robustness convention


def _panel_gated(test_poss, wide, pcdf2, pcdf3, dcdf, gcd, thr, seed_offset: int = 0) -> Dict[str, Any]:
    """v2 baseline is computed for every snapshot; the v3-conditioned simulate()
    call is only invoked for snapshots whose bucket is in GATE_BUCKETS (saves
    compute AND makes non-gated buckets byte-identical to v2 by construction,
    not just numerically close)."""
    pit2: Dict[str, list] = {}; pitg: Dict[str, list] = {}
    crps2: Dict[str, list] = {}; crpsg: Dict[str, list] = {}
    for gid, gdf in test_poss.groupby("game_id"):
        if gid not in wide.index:
            continue
        row = wide.loc[gid]
        ter = S.GameTerciles(int(row.home_off_t), int(row.home_def_t),
                             int(row.away_off_t), int(row.away_def_t), int(row.pace_t))
        ch = gcd.get(str(gid))
        seed = (int(gid[-6:]) if gid[-6:].isdigit() else 7) + seed_offset
        for (per, clk, hs, as_, fm) in _snapshots(gdf):
            key = "P%d|m%d" % (per, margin_bucket(hs - as_))
            s2 = S.simulate(per, clk, hs, as_, ter, pcdf2, dcdf, n=N_DIST, seed=seed)
            p2, c2 = S.pit_value(s2, fm), S.crps_ensemble(s2, fm)
            pit2.setdefault(key, []).append(p2)
            crps2.setdefault(key, []).append(c2)
            if key in GATE_BUCKETS:
                if ch is not None:
                    s3 = S.simulate(per, clk, hs, as_, ter, pcdf3, dcdf, n=N_DIST, seed=seed,
                                    comp_home=ch, comp_thr=thr)
                else:
                    s3 = s2  # no composite for this game -> gated collapses to v2
                pg, cg = S.pit_value(s3, fm), S.crps_ensemble(s3, fm)
            else:
                pg, cg = p2, c2  # not gated -> identical to v2 by construction
            pitg.setdefault(key, []).append(pg)
            crpsg.setdefault(key, []).append(cg)
    buckets = {}
    for k in sorted(pit2):
        buckets[k] = {
            "n": len(pit2[k]),
            "pit_dev_v2": round(_uniformity_dev(pit2[k]), 4),
            "pit_dev_gated": round(_uniformity_dev(pitg[k]), 4),
            "crps_v2": round(float(np.mean(crps2[k])), 4),
            "crps_gated": round(float(np.mean(crpsg[k])), 4),
            "gated_applies_v3": k in GATE_BUCKETS,
        }
    allp2 = [x for v in pit2.values() for x in v]
    allpg = [x for v in pitg.values() for x in v]
    allc2 = [x for v in crps2.values() for x in v]
    allcg = [x for v in crpsg.values() for x in v]
    pooled = {"n": len(allp2),
              "pit_dev_v2": round(_uniformity_dev(allp2), 4),
              "pit_dev_gated": round(_uniformity_dev(allpg), 4),
              "crps_v2": round(float(np.mean(allc2)), 4),
              "crps_gated": round(float(np.mean(allcg)), 4)}
    return {"buckets": buckets, "pooled": pooled}


def gate_verdict(runs: List[Dict[str, Any]]) -> "tuple[str, str, List[Dict[str, Any]]]":
    checks = []
    for r in runs:
        b = r["buckets"]
        gate_present = all(k in b and b[k]["n"] > 0 for k in GATE_BUCKETS)
        gate_ok = gate_present and all(b[k]["pit_dev_gated"] < b[k]["pit_dev_v2"] for k in GATE_BUCKETS)
        pooled_ok = r["pooled"]["pit_dev_gated"] <= r["pooled"]["pit_dev_v2"] + POOLED_TOL
        p4 = b.get("P4|m2")
        p4_untouched = p4 is None or p4["pit_dev_gated"] == p4["pit_dev_v2"]
        checks.append({"seed_offset": r["seed_offset"], "gate_buckets_present": gate_present,
                       "gate_buckets_improved": gate_ok, "pooled_within_tol": pooled_ok,
                       "p4m2_untouched": p4_untouched})
    if not all(c["gate_buckets_present"] for c in checks):
        return "UNDERPOWERED", ("gate buckets P3|m3/P2|m1 have zero test-set observations in "
                                "at least one seed -- cannot evaluate the gate."), checks
    if not all(c["p4m2_untouched"] for c in checks):
        return "REJECT", ("P4|m2 pit_dev_gated != pit_dev_v2 -- construction bug, P4|m2 must be "
                          "byte-identical to v2 since it is never routed to v3."), checks
    if all(c["gate_buckets_improved"] for c in checks) and all(c["pooled_within_tol"] for c in checks):
        return "SHIP_CANDIDATE_GATED", (
            "gated routing (v3 only on P3|m3+P2|m1, v2 everywhere else including P4|m2) improves "
            "both gate buckets in both seeds without exceeding the preregistered pooled PIT "
            "tolerance, and P4|m2 is provably untouched. Side-by-side candidate only -- no flag, "
            "no default change, nothing deployed."), checks
    return "REJECT", (
        "gate buckets did not improve in both seeds, or pooled tolerance exceeded, or a "
        "construction check failed -- gated candidate does not clear the preregistered bar."), checks


def run(max_fit_games: Optional[int] = None) -> Dict[str, Any]:
    art = fit_v3(max_fit_games=max_fit_games)
    runs = [dict(seed_offset=so, **_panel_gated(
                art["test_poss"], art["wide"], art["pcdf2"], art["pcdf3"], art["dcdf"],
                art["gcd"], art["comp_thr"], seed_offset=so))
            for so in SEEDS]
    verdict, lesson, checks = gate_verdict(runs)
    doc = {
        "model": "nba_sim2_v3_composite_GATED_candidate", "edge_claimed": False,
        "gate_buckets": GATE_BUCKETS, "seeds": list(SEEDS), "pooled_tol": POOLED_TOL,
        "prior_history": {
            "blanket_v3_replication_verdict": "NULL (pooled bar failed; bucket direction held "
                "5/5 seeds + both temporal halves) -- nba_sim2_v3_replication.json",
            "p4m2_full_v3_regression": "0.1292 -> 0.1403 (nba_sim2_v3_validation.json); "
                "clutch Q4-scoped rescue also NULL'd -- gate holds, P4|m2 stays v2 here"},
        "runs": runs, "gate_checks": checks,
        "verdict": verdict, "lesson": lesson,
        "leak_audit": ("reuses fit_v3()'s already leak-audited CDFs/composite unchanged; the "
                       "only new logic is a per-live-snapshot routing decision keyed on the "
                       "CURRENT (period, margin_bucket) -- no new leak surface."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "hypothesis": "sim2_v3_composite_GATED_candidate_P3m3_P2m1_only", "sport": "nba",
            "atomic_unit": "possession_state_cell_query_routing", "method": "sim2_v3_gated_v1",
            "season": "walkforward_fit_2023_24+2024_25_test_2025_26", "seeds": list(SEEDS),
            "n": runs[0]["pooled"]["n"],
            "pooled_pit_dev_v2_by_seed": [r["pooled"]["pit_dev_v2"] for r in runs],
            "pooled_pit_dev_gated_by_seed": [r["pooled"]["pit_dev_gated"] for r in runs],
            "gate_buckets_pit_dev_v2": {k: runs[0]["buckets"].get(k, {}).get("pit_dev_v2") for k in GATE_BUCKETS},
            "gate_buckets_pit_dev_gated_by_seed": {
                k: [r["buckets"].get(k, {}).get("pit_dev_gated") for r in runs] for k in GATE_BUCKETS},
            "p4m2_untouched_all_seeds": all(c["p4m2_untouched"] for c in checks),
            "verdict": verdict, "lesson": lesson, "edge_claimed": False,
        }) + "\n")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fit-games", type=int, default=None)
    args = ap.parse_args(argv)
    doc = run(max_fit_games=args.max_fit_games)
    print("gated [%s] gate_buckets=%s seeds=%s" % (doc["verdict"], GATE_BUCKETS, list(SEEDS)))
    for r in doc["runs"]:
        po = r["pooled"]
        print("  seed=%d POOLED n=%d PITdev v2=%.4f gated=%.4f | CRPS v2=%.3f gated=%.3f" % (
            r["seed_offset"], po["n"], po["pit_dev_v2"], po["pit_dev_gated"], po["crps_v2"], po["crps_gated"]))
        for k in GATE_BUCKETS + ["P4|m2"]:
            b = r["buckets"].get(k)
            if b:
                print("    %-6s n=%d PITdev v2=%.4f gated=%.4f applies_v3=%s" % (
                    k, b["n"], b["pit_dev_v2"], b["pit_dev_gated"], b["gated_applies_v3"]))
    print("  lesson:", doc["lesson"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
