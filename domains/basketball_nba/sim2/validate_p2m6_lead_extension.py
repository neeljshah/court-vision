"""domains.basketball_nba.sim2.validate_p2m6_lead_extension -- P2|m6-scoped
lead-extension conditioning candidate (wave-17 gate target).

HISTORY: mechanisms.md #51 (CONFIRMED REPLICATED, 2 season corpora,
validate_q2_blowout_state.q2_lead_extension_beyond_ar) found Q1 leads >=15
extend ~1.5-2.3 pts FURTHER into Q2 than a naive AR(1) fit on moderate-lead
games predicts. Sim2's own P2|m6 bucket (period 2, home already up >=15,
n=65 eval games) is the #4 worst v2 PIT bucket per
docs/research/sim_heatmap_bucket_sweep_2026-07-10.md with NO prior gate
(unlike P3|m3/P2|m1 -- validate_v3_gated.py -- and P4|m2 -- validate_clutch.py,
whose regression gate holds and is not reopened here).

DESIGN (routing-level additive drift, not a refit): reuses validate.py's plain
v2 fit (PossessionModel/PaceModel on FIT_SEASONS, simulator.simulate
unmodified) -- no composite, no cell refit. Per LIVE SNAPSHOT, if its
reporting key is P2|m6 (home already leading >=15 during Q2), the gated
candidate adds a fixed additive drift (DRIFT_PTS) to every simulated final
margin, nudging the projected margin further toward the CURRENT leader --
the mechanism's own found direction and only that direction (m6 by
definition means home_margin=hs-as_>=15, so the leader is always home here).
All other buckets are byte-identical to v2 by construction: the drift is
applied post-simulate(), gated strictly on the reporting key, never touching
the fitted CDFs, so nothing but P2|m6 can move.

MAGNITUDE (fit NOTHING on eval): DRIFT_PTS is mechanism #51's own AR(1)
signed-residual mean, refit HERE via q2_lead_extension_beyond_ar reused
VERBATIM but restricted to the 2024_25 corpus only (inside sim2's own
FIT_SEASONS=(2023-24,2024-25), excludes TEST_SEASON=2025-26 entirely -- no
eval leakage). This reproduces the already-published fit-half of mechanism
#51 (2024-25: signed_resid_mean=+1.557pts, p=0.0079); no new statistical fit.

PREREGISTERED GATE BAR (declared before running; n=65 is KNOWN THIN going in
-- the UNDERPOWERED floor below is pre-declared, not discovered post-hoc):
  UNDERPOWERED iff P2|m6 has zero snapshots in either seed.
  Otherwise SHIP_CANDIDATE_GATED iff, in BOTH seeds --
    (a) P2|m6 pit_dev_gated < pit_dev_v2 (strictly better), AND
    (b) pooled pit_dev_gated <= pooled pit_dev_v2 + POOLED_TOL, AND
    (c) P3|m3, P2|m1 (validate_v3_gated's gate buckets) and P4|m2 (the
        clutch regression gate) are BYTE-IDENTICAL v2==gated (construction
        check -- the drift never routes there).
  (c) failing anywhere -> REJECT regardless of (a)/(b).
  If (a)+(b)+(c) all hold but n < MIN_POWERED_N (100, a round bar comfortably
  above the known n=65) -> IMPROVES_PROVISIONAL_UNDERPOWERED, not SHIP: this
  candidate is expected to land here and that is reported honestly, not
  upgraded to a ship verdict on a thin bucket.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge
claim. Candidate only -- no flag, no default change, nothing deployed.
CLI: cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_nba.sim2.validate_p2m6_lead_extension [--max-fit-games N]
Test: python -m pytest domains/basketball_nba/sim2/test_validate_p2m6_lead_extension.py -q
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
from domains.basketball_nba.sim2.possession_model import (
    add_state_buckets, margin_bucket, PossessionModel)
from domains.basketball_nba.sim2.pace_model import PaceModel
from domains.basketball_nba.sim2.corpus import (
    load_corpus, build_asof_terciles, attach_terciles, FIT_SEASONS, TEST_SEASON)
from domains.basketball_nba.sim2.validate import _snapshots
from domains.basketball_nba.sim2.validate_v3 import _uniformity_dev
from domains.basketball_nba.knowledge.validate_q2_blowout_state import q2_lead_extension_beyond_ar
from domains.basketball_nba.knowledge.validate_q3_state import load_all_corpora

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "nba_sim2_p2m6_lead_extension_validation.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
N_DIST = 2000
GATE_BUCKET = "P2|m6"
UNTOUCHED_BUCKETS = ["P3|m3", "P2|m1", "P4|m2"]   # prior gate/regression buckets -- must not move
POOLED_TOL = 0.0005
MIN_POWERED_N = 100     # n=65 known going in; pre-declared floor, not post-hoc
SEEDS = (0, 1000)       # matches cond_clutch/validate_v3_gated's bounded 2-seed convention
FIT_CORPUS = "2024_25"  # inside sim2 FIT_SEASONS, excludes TEST_SEASON=2025-26


def fit_drift_pts() -> Dict[str, Any]:
    """DRIFT_PTS: mechanism #51's own AR(1) signed-residual mean, restricted to
    FIT_CORPUS (inside sim2's FIT_SEASONS) -- reuses q2_lead_extension_beyond_ar
    verbatim, fits nothing new, never touches the eval-season corpus."""
    tg = load_all_corpora()
    tg_fit = tg[tg["corpus"] == FIT_CORPUS]
    res = q2_lead_extension_beyond_ar(tg_fit)
    per = res["per_corpus"].get(FIT_CORPUS, {})
    drift = per.get("signed_resid_mean")
    if drift is None:
        raise RuntimeError("%s corpus unavailable/underpowered for lead-extension fit "
                            "-- cannot build candidate" % FIT_CORPUS)
    return {"drift_pts": float(drift), "fit_corpus": FIT_CORPUS, "fit_detail": per}


def _panel_gated(test_poss, wide, pcdf, dcdf, drift_pts: float, seed_offset: int = 0) -> Dict[str, Any]:
    pit2: Dict[str, list] = {}; pitg: Dict[str, list] = {}
    crps2: Dict[str, list] = {}; crpsg: Dict[str, list] = {}
    for gid, gdf in test_poss.groupby("game_id"):
        if gid not in wide.index:
            continue
        row = wide.loc[gid]
        ter = S.GameTerciles(int(row.home_off_t), int(row.home_def_t),
                             int(row.away_off_t), int(row.away_def_t), int(row.pace_t))
        seed = (int(gid[-6:]) if gid[-6:].isdigit() else 7) + seed_offset
        for (per, clk, hs, as_, fm) in _snapshots(gdf):
            key = "P%d|m%d" % (per, margin_bucket(hs - as_))
            s2 = S.simulate(per, clk, hs, as_, ter, pcdf, dcdf, n=N_DIST, seed=seed)
            p2, c2 = S.pit_value(s2, fm), S.crps_ensemble(s2, fm)
            pit2.setdefault(key, []).append(p2)
            crps2.setdefault(key, []).append(c2)
            if key == GATE_BUCKET:
                sg = s2 + drift_pts   # home already leads (m6 == hs-as_>=15) -> extend toward the lead
                pg, cg = S.pit_value(sg, fm), S.crps_ensemble(sg, fm)
            else:
                pg, cg = p2, c2       # not gated -> identical to v2 by construction
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
            "gated_applies_drift": k == GATE_BUCKET,
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
        g = b.get(GATE_BUCKET)
        gate_present = g is not None and g["n"] > 0
        gate_n = g["n"] if g else 0
        gate_ok = gate_present and g["pit_dev_gated"] < g["pit_dev_v2"]
        pooled_ok = r["pooled"]["pit_dev_gated"] <= r["pooled"]["pit_dev_v2"] + POOLED_TOL
        untouched_ok = all(
            (b.get(k) is None) or (b[k]["pit_dev_gated"] == b[k]["pit_dev_v2"])
            for k in UNTOUCHED_BUCKETS)
        checks.append({"seed_offset": r["seed_offset"], "gate_bucket_present": gate_present,
                       "gate_bucket_n": gate_n, "gate_bucket_improved": gate_ok,
                       "pooled_within_tol": pooled_ok, "untouched_buckets_ok": untouched_ok})
    if not all(c["gate_bucket_present"] for c in checks):
        return "UNDERPOWERED", ("P2|m6 has zero test-set observations in at least one seed -- "
                                "cannot evaluate the gate."), checks
    if not all(c["untouched_buckets_ok"] for c in checks):
        return "REJECT", ("P3|m3/P2|m1/P4|m2 pit_dev_gated != pit_dev_v2 -- construction bug, "
                          "these must be byte-identical since the drift never routes there."), checks
    improves = (all(c["gate_bucket_improved"] for c in checks)
                and all(c["pooled_within_tol"] for c in checks))
    thin = any(c["gate_bucket_n"] < MIN_POWERED_N for c in checks)
    if improves and thin:
        return "IMPROVES_PROVISIONAL_UNDERPOWERED", (
            "P2|m6 improves in both seeds without exceeding pooled tolerance and the prior "
            "gate/regression buckets are provably untouched, BUT n=%d per seed is below the "
            "pre-declared powered floor (%d) -- reported honestly as provisional/underpowered, "
            "not shipped." % (checks[0]["gate_bucket_n"], MIN_POWERED_N)), checks
    if improves:
        return "SHIP_CANDIDATE_GATED", (
            "P2|m6 gated additive drift improves PIT in both seeds within the preregistered "
            "pooled tolerance, sufficiently powered, and the prior gate/regression buckets are "
            "provably untouched. Side-by-side candidate only -- no flag, no default change."), checks
    return "REJECT", (
        "P2|m6 did not improve in both seeds, or pooled tolerance exceeded, or a construction "
        "check failed -- gated candidate does not clear the preregistered bar."), checks


def run(max_fit_games: Optional[int] = None) -> Dict[str, Any]:
    drift = fit_drift_pts()
    poss = add_state_buckets(load_corpus(False, max_fit_games))
    wide, _thr = build_asof_terciles(poss)
    fit_poss = attach_terciles(poss[poss["season"].isin(FIT_SEASONS)], wide)
    pmodel = PossessionModel.fit(fit_poss)
    pacemodel = PaceModel.fit(fit_poss)
    pcdf, dcdf = S.build_cdfs(pmodel, pacemodel)
    test_poss = attach_terciles(poss[poss["season"] == TEST_SEASON], wide)
    runs = [dict(seed_offset=so, **_panel_gated(
                test_poss, wide, pcdf, dcdf, drift["drift_pts"], seed_offset=so))
            for so in SEEDS]
    verdict, lesson, checks = gate_verdict(runs)
    doc = {
        "model": "nba_sim2_p2m6_lead_extension_GATED_candidate", "edge_claimed": False,
        "gate_bucket": GATE_BUCKET, "untouched_buckets": UNTOUCHED_BUCKETS,
        "seeds": list(SEEDS), "pooled_tol": POOLED_TOL, "min_powered_n": MIN_POWERED_N,
        "drift_fit": drift,
        "prior_history": {
            "p2m6_prior_gate": "none -- rank-4 worst v2 PIT bucket per "
                "docs/research/sim_heatmap_bucket_sweep_2026-07-10.md, mechanism seeded and "
                "CONFIRMED REPLICATED as mechanisms.md #51 (q2_lead_extension_beyond_ar)",
            "p4m2_regression_gate_untouched": "0.1292 -> 0.1403 full-v3 regression "
                "(nba_sim2_v3_validation.json); clutch Q4-scoped rescue also NULL'd -- gate holds, "
                "P4|m2 stays v2 here (construction check, not reopened)"},
        "runs": runs, "gate_checks": checks,
        "verdict": verdict, "lesson": lesson,
        "leak_audit": ("drift magnitude fit on the %s corpus ONLY (inside sim2's own FIT_SEASONS, "
                       "excludes TEST_SEASON=2025-26 entirely); v2 possession/pace models fit on "
                       "FIT_SEASONS as usual; drift is an additive post-simulate shift gated "
                       "strictly on the CURRENT (period, margin_bucket) reporting key -- no new "
                       "leak surface, no eval-season fitting." % FIT_CORPUS),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "hypothesis": "sim2_p2m6_lead_extension_GATED_candidate", "sport": "nba",
            "atomic_unit": "possession_state_cell_query_routing", "method": "sim2_p2m6_drift_v1",
            "season": "walkforward_fit_2023_24+2024_25_test_2025_26", "seeds": list(SEEDS),
            "n": runs[0]["pooled"]["n"], "gate_bucket_n": checks[0]["gate_bucket_n"],
            "min_powered_n": MIN_POWERED_N, "drift_pts": drift["drift_pts"],
            "pooled_pit_dev_v2_by_seed": [r["pooled"]["pit_dev_v2"] for r in runs],
            "pooled_pit_dev_gated_by_seed": [r["pooled"]["pit_dev_gated"] for r in runs],
            "gate_bucket_pit_dev_v2": runs[0]["buckets"].get(GATE_BUCKET, {}).get("pit_dev_v2"),
            "gate_bucket_pit_dev_gated_by_seed": [
                r["buckets"].get(GATE_BUCKET, {}).get("pit_dev_gated") for r in runs],
            "untouched_buckets_ok_all_seeds": all(c["untouched_buckets_ok"] for c in checks),
            "verdict": verdict, "lesson": lesson, "edge_claimed": False,
        }) + "\n")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-fit-games", type=int, default=None)
    args = ap.parse_args(argv)
    doc = run(max_fit_games=args.max_fit_games)
    print("p2m6 [%s] gate_bucket=%s drift_pts=%.3f seeds=%s" % (
        doc["verdict"], GATE_BUCKET, doc["drift_fit"]["drift_pts"], list(SEEDS)))
    for r in doc["runs"]:
        po = r["pooled"]
        print("  seed=%d POOLED n=%d PITdev v2=%.4f gated=%.4f | CRPS v2=%.3f gated=%.3f" % (
            r["seed_offset"], po["n"], po["pit_dev_v2"], po["pit_dev_gated"],
            po["crps_v2"], po["crps_gated"]))
        b = r["buckets"].get(GATE_BUCKET)
        if b:
            print("    %-6s n=%d PITdev v2=%.4f gated=%.4f" % (
                GATE_BUCKET, b["n"], b["pit_dev_v2"], b["pit_dev_gated"]))
    print("  lesson:", doc["lesson"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
