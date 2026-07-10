"""domains.basketball_nba.sim2.validate_clutch -- P4|m2-scoped candidate: condition
ONLY the Q4 possession cells (cond_clutch.TIME_SCOPE) on a strictly-PRIOR-GAMES
clutch-lineup-shortening propensity, instead of the full-game 12-attr composite
that regressed P4|m2 in v3 (nba_sim2_v3_validation.json: pit_dev 0.1292->0.1403).

v2/v3 (possession_model, cond_composite, validate, validate_v3, simulator) are
UNCHANGED by this file -- it is a side-by-side candidate that imports and reuses
validate_v3's panel functions verbatim (they are generic over any comp_home/
comp_thr-shaped model, not composite-specific) plus cond_composite's generic
offrel/threshold/backoff plumbing. Only the NEW signal (cond_clutch.py) and its
Q4 scope are new.

VERDICT: scoped to the ONE named bucket this candidate targets (P4|m2) -- v3's
generic >=2-of-3-named-buckets gate does not fit a single-bucket candidate (P3|m3
and P2|m1 are guaranteed byte-identical to v2, out of scope by construction).
MULTI-SEED: panel A/B (PIT/CRPS) is run at 2 seed offsets; P4|m2 must improve on
BOTH to avoid a one-seed fluke (bounded robustness check, not a seed sweep).

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge claim.
CLI: cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_nba.sim2.validate_clutch [--max-fit-games N]
Test: python -m pytest domains/basketball_nba/sim2/test_validate_clutch.py -q
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

from domains.basketball_nba.sim2.possession_model import add_state_buckets, PossessionModel
from domains.basketball_nba.sim2.pace_model import PaceModel
from domains.basketball_nba.sim2 import simulator as S
from domains.basketball_nba.sim2.corpus import (
    load_corpus, build_asof_terciles, attach_terciles, FIT_SEASONS, TEST_SEASON)
from domains.basketball_nba.sim2.cond_composite import build_comp_thresholds
from domains.basketball_nba.sim2.cond_clutch import all_game_shortening_diff, ScopedConditionedModel, TIME_SCOPE
from domains.basketball_nba.sim2.validate_v3 import _panel_pit_crps, _panel_checkpoints

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "nba_sim2_clutch_validation.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
SEEDS = (0, 1000)   # bounded multi-seed robustness check, not a sweep


def _verdict_p4m2(runs: List[Dict[str, Any]]) -> "tuple[str, str]":
    """MATTERS_PROVISIONAL only if P4|m2 PIT-dev improves on EVERY seed AND the
    pooled PIT-or-CRPS is no worse on every seed. Single-fold -> PROVISIONAL
    either way; this just guards against a one-seed fluke."""
    b = [r["named"].get("P4|m2") for r in runs]
    if any(x is None for x in b):
        return "NOT_TESTABLE", "P4|m2 bucket missing from a seed run (thin test coverage)."
    p4_ok = all(x["pit_dev_v3"] < x["pit_dev_v2"] for x in b)
    pooled_ok = all(r["pooled"]["pit_dev_v3"] <= r["pooled"]["pit_dev_v2"] or
                    r["pooled"]["crps_v3"] < r["pooled"]["crps_v2"] for r in runs)
    if p4_ok and pooled_ok:
        return "MATTERS_PROVISIONAL", (
            "prior-games clutch-shortening propensity, scoped to Q4 only, sharpens "
            "P4|m2 across seeds where the full-game composite regressed it; needs "
            "independent replication before any weight.")
    return "NULL", (
        "P4|m2 is a genuinely hard bucket: neither the full-game composite (v3) nor "
        "a Q4-scoped prior-games clutch-shortening signal sharpens it -- the residual "
        "there is more likely small-sample noise (n~288) than a missing conditioning "
        "variable.")


def fit_clutch(rebuild: bool = False, max_fit_games: Optional[int] = None) -> Dict[str, Any]:
    poss = add_state_buckets(load_corpus(rebuild, max_fit_games))
    wide, _thr = build_asof_terciles(poss)
    fit_poss = attach_terciles(poss[poss["season"].isin(FIT_SEASONS)], wide)
    v2 = PossessionModel.fit(fit_poss)
    pace = PaceModel.fit(fit_poss)
    pcdf2, dcdf = S.build_cdfs(v2, pace)
    gcd = all_game_shortening_diff(list(FIT_SEASONS) + [TEST_SEASON])
    comp_thr = build_comp_thresholds(fit_poss, gcd)
    model = ScopedConditionedModel.fit(fit_poss, v2, gcd, comp_thr, time_buckets=TIME_SCOPE)
    pcdf3 = model.point_cdf_matrix()
    test_poss = attach_terciles(poss[poss["season"] == TEST_SEASON], wide)
    return dict(wide=wide, pcdf2=pcdf2, pcdf3=pcdf3, dcdf=dcdf, gcd=gcd,
                comp_thr=comp_thr, model=model, test_poss=test_poss)


def run(rebuild: bool = False, max_fit_games: Optional[int] = None) -> Dict[str, Any]:
    art = fit_clutch(rebuild, max_fit_games)
    wide, pcdf2, pcdf3, dcdf = art["wide"], art["pcdf2"], art["pcdf3"], art["dcdf"]
    gcd, comp_thr, model, test_poss = art["gcd"], art["comp_thr"], art["model"], art["test_poss"]
    runs = [_panel_pit_crps(test_poss, wide, pcdf2, pcdf3, dcdf, gcd, comp_thr, seed_offset=so)
            for so in SEEDS]
    try:
        panel_c = _panel_checkpoints(wide, pcdf2, pcdf3, dcdf, gcd, comp_thr)
    except Exception as exc:
        panel_c = {"verdict": "ERROR", "note": str(exc)[:200]}
    verdict, lesson = _verdict_p4m2(runs)
    n_test_games = len([g for g in gcd if g in set(test_poss["game_id"].astype(str))])
    doc = {
        "model": "nba_sim2_clutch_p4_conditioner", "edge_claimed": False,
        "fit_seasons": list(FIT_SEASONS), "test_season": TEST_SEASON,
        "time_scope": list(TIME_SCOPE), "seeds": list(SEEDS),
        "conditioning": model.summary(),
        "coverage_test_games_with_signal": n_test_games,
        "panel_A_B_pit_crps_by_seed": runs,
        "panel_C_checkpoint_brier": panel_c,
        "verdict": verdict, "lesson": lesson,
        "leak_audit": ("clutch-shortening propensity is a strictly-prior-GAMES as-of "
                       "expanding mean (skips games that never reached the clutch window "
                       "when updating history; never the current game itself); comp "
                       "thresholds fit on FIT seasons only; conditioning applied ONLY to "
                       "Q4 cells (time_b in %s) -- every other cell is byte-identical to "
                       "v2 by construction; paired seeds vs v2 -> truncation-invariant."
                       % (list(TIME_SCOPE),)),
        "baseline_for_comparison": "v3 full-game composite on the SAME P4|m2 bucket "
                                    "regressed it 0.1292->0.1403 (nba_sim2_v3_validation.json)",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    seed0 = runs[0]
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "hypothesis": "sim2_clutch_shortening_possession_conditioner_p4", "sport": "nba",
            "atomic_unit": "possession_state_cell_q4_scope", "method": "sim2_cond_clutch_v1",
            "season": "walkforward_fit_2023_24+2024_25_test_2025_26",
            "n": seed0["pooled"]["n"],
            "p4m2_pit_dev_v2": seed0["named"].get("P4|m2", {}).get("pit_dev_v2"),
            "p4m2_pit_dev_v3_by_seed": [r["named"].get("P4|m2", {}).get("pit_dev_v3") for r in runs],
            "pooled_pit_dev_v2": seed0["pooled"]["pit_dev_v2"],
            "pooled_pit_dev_v3_by_seed": [r["pooled"]["pit_dev_v3"] for r in runs],
            "checkpoint_brier_v3": panel_c.get("brier_v3"),
            "checkpoint_brier_market": panel_c.get("brier_market"),
            "verdict": verdict, "lesson": lesson, "edge_claimed": False,
        }) + "\n")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--max-fit-games", type=int, default=None)
    args = ap.parse_args(argv)
    doc = run(rebuild=args.rebuild, max_fit_games=args.max_fit_games)
    print("clutch-p4 [%s] n_full=%d n_backoff=%d n_out_of_scope=%d thr=%s" % (
        doc["verdict"], doc["conditioning"]["n_full_conditioned"],
        doc["conditioning"]["n_backoff_v2"], doc["conditioning"]["n_out_of_scope_passthrough"],
        doc["conditioning"]["comp_thresholds"]))
    for r in doc["panel_A_B_pit_crps_by_seed"]:
        b = r["named"].get("P4|m2")
        if b:
            print("  seed n=%d P4|m2 PITdev v2=%.4f v3=%.4f | CRPS v2=%.3f v3=%.3f | pooled v2=%.4f v3=%.4f" % (
                b["n"], b["pit_dev_v2"], b["pit_dev_v3"], b["crps_v2"], b["crps_v3"],
                r["pooled"]["pit_dev_v2"], r["pooled"]["pit_dev_v3"]))
    c = doc["panel_C_checkpoint_brier"]
    print("  CKPT brier v2=%s v3=%s market=%s" % (c.get("brier_v2"), c.get("brier_v3"), c.get("brier_market")))
    print("  lesson:", doc["lesson"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
