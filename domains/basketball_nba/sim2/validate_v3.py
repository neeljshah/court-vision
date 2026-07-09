"""domains.basketball_nba.sim2.validate_v3 -- walk-forward v2-vs-v3 distributional
comparison for the lineup-composite conditioner (cond_composite).

Fit possession + pace models on 2023-24 + 2024-25; fit the composite conditioning
on the same fit seasons (thresholds from 2024-25, the only season with a prior
profile window); EVALUATE on held-out 2025-26. Three read-outs, all edge_claimed:false:

  (A) PIT uniformity per (period x margin) bucket, v2 vs v3 -- do the NAMED worst
      v2 buckets (P3|m3, P2|m1, P4|m2) get MORE uniform (lower deviation)?
  (B) CRPS of the simulated final-margin ensemble per bucket, v2 vs v3 (lower=sharper).
  (C) Checkpoint win-prob Brier vs the live market on the read-only mechanism-ladder
      corpus (2025-26 test ticks), v2 vs v3. Market is the honest yardstick.

Leak audit: composite uses STRICT prior-season profiles; test-season comp read from
2024-25 profiles only; comp thresholds fit on 2024-25 possessions and applied
unchanged to 2025-26 (train/inference parity). No game sees its own future. The v3
sim holds the game-representative composite fixed across the replay (no future-
substitution leak). Same snapshots/ticks/seeds for v2 and v3 -> truncation-invariant,
paired comparison.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge claim.
CLI: cd /c/Users/neelj/nba-ai-system && python -m domains.basketball_nba.sim2.validate_v3 [--max-fit-games N]
Test: python -m pytest domains/basketball_nba/sim2/test_validate_v3.py -q
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
import pandas as pd

from domains.basketball_nba.sim2.possession_model import add_state_buckets, margin_bucket, PossessionModel
from domains.basketball_nba.sim2.pace_model import PaceModel
from domains.basketball_nba.sim2 import simulator as S
from domains.basketball_nba.sim2.corpus import (
    load_corpus, build_asof_terciles, attach_terciles, FIT_SEASONS, TEST_SEASON)
from domains.basketball_nba.sim2.validate import _snapshots
from domains.basketball_nba.sim2.cond_composite import (
    all_game_comp_diff, build_comp_thresholds, ConditionedPointModel)

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "nba_sim2_v3_validation.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
N_DIST, N_WP = 2000, 1000
MAX_TICKS_PER_GAME = 12
NAMED = ["P3|m3", "P2|m1", "P4|m2"]


def _uniformity_dev(vals: List[float]) -> float:
    v = np.array(vals)
    return float(max(abs((v <= q).mean() - q) for q in np.linspace(0.1, 1.0, 10)))


def _verdict(named_improved: int, pooled: Dict[str, float]) -> "tuple[str, str]":
    """>=2/3 named worst buckets improved PIT AND pooled PIT-or-CRPS improved ->
    MATTERS_PROVISIONAL (needs replication). Otherwise honest NULL."""
    pit_better = pooled["pit_dev_v3"] < pooled["pit_dev_v2"]
    crps_better = pooled["crps_v3"] < pooled["crps_v2"]
    if named_improved >= 2 and (pit_better or crps_better):
        return "MATTERS_PROVISIONAL", (
            "composite conditioning sharpens the possession distribution on the "
            "named worst buckets; needs independent replication before any weight.")
    return "NULL", (
        "composite is real but its variance contribution is already captured by "
        "the off/def/pace state cells; adds nothing to possession-level PIT/CRPS.")


def _panel_pit_crps(test_poss, wide, pcdf2, pcdf3, dcdf, gcd, thr) -> Dict[str, Any]:
    pit2: Dict[str, list] = {}; pit3: Dict[str, list] = {}
    crps2: Dict[str, list] = {}; crps3: Dict[str, list] = {}
    for gid, gdf in test_poss.groupby("game_id"):
        if gid not in wide.index:
            continue
        row = wide.loc[gid]
        ter = S.GameTerciles(int(row.home_off_t), int(row.home_def_t),
                             int(row.away_off_t), int(row.away_def_t), int(row.pace_t))
        ch = gcd.get(str(gid))
        seed = int(gid[-6:]) if gid[-6:].isdigit() else 7
        for (per, clk, hs, as_, fm) in _snapshots(gdf):
            key = "P%d|m%d" % (per, margin_bucket(hs - as_))
            s2 = S.simulate(per, clk, hs, as_, ter, pcdf2, dcdf, n=N_DIST, seed=seed)
            pit2.setdefault(key, []).append(S.pit_value(s2, fm))
            crps2.setdefault(key, []).append(S.crps_ensemble(s2, fm))
            if ch is not None:
                s3 = S.simulate(per, clk, hs, as_, ter, pcdf3, dcdf, n=N_DIST, seed=seed,
                                comp_home=ch, comp_thr=thr)
            else:
                s3 = s2  # no composite for this game -> v3 collapses to v2
            pit3.setdefault(key, []).append(S.pit_value(s3, fm))
            crps3.setdefault(key, []).append(S.crps_ensemble(s3, fm))
    buckets = {}
    for k in sorted(pit2):
        buckets[k] = {
            "n": len(pit2[k]),
            "pit_dev_v2": round(_uniformity_dev(pit2[k]), 4),
            "pit_dev_v3": round(_uniformity_dev(pit3[k]), 4),
            "crps_v2": round(float(np.mean(crps2[k])), 4),
            "crps_v3": round(float(np.mean(crps3[k])), 4),
        }
    allp2 = [x for v in pit2.values() for x in v]
    allp3 = [x for v in pit3.values() for x in v]
    allc2 = [x for v in crps2.values() for x in v]
    allc3 = [x for v in crps3.values() for x in v]
    pooled = {"n": len(allp2),
              "pit_dev_v2": round(_uniformity_dev(allp2), 4),
              "pit_dev_v3": round(_uniformity_dev(allp3), 4),
              "crps_v2": round(float(np.mean(allc2)), 4),
              "crps_v3": round(float(np.mean(allc3)), 4)}
    return {"buckets": buckets, "pooled": pooled,
            "named": {k: buckets.get(k) for k in NAMED}}


def _panel_checkpoints(wide, pcdf2, pcdf3, dcdf, gcd, thr) -> Dict[str, Any]:
    from scripts.platformkit.ingame.nba_mechanism_ladder import (
        load_corpus as lc, build_crosswalk, TEST_SEASON as CK_TEST)
    from scripts.platformkit.eval_gate.scoring import brier
    df = lc()
    cw = build_crosswalk(df)
    nba_by = dict(zip(cw["game_id"], cw["nba_game_id"]))
    d = df[df["game_id"].isin(nba_by)].copy()
    d["nba_game_id"] = d["game_id"].map(nba_by)
    d = d[d["nba_game_id"].astype(str).isin(wide.index)].copy()
    te = d[d["season"] == CK_TEST].copy()
    if len(te) == 0:
        return {"verdict": "NOT_TESTABLE", "note": "empty test split"}
    te = te.groupby("game_id", group_keys=False)[te.columns.tolist()].apply(
        lambda x: x.iloc[:: max(1, len(x) // MAX_TICKS_PER_GAME)]).reset_index(drop=True)
    p2 = np.empty(len(te)); p3 = np.empty(len(te))
    for i, r in enumerate(te.itertuples(index=False)):
        row = wide.loc[str(r.nba_game_id)]
        ter = S.GameTerciles(int(row.home_off_t), int(row.home_def_t),
                             int(row.away_off_t), int(row.away_def_t), int(row.pace_t))
        st = (int(r.period), float(r.game_clock_s), int(r.score_home), int(r.score_away), ter)
        p2[i] = S.p_home_win(S.simulate(*st, pcdf2, dcdf, n=N_WP, seed=7 + i))
        ch = gcd.get(str(r.nba_game_id))
        if ch is not None:
            p3[i] = S.p_home_win(S.simulate(*st, pcdf3, dcdf, n=N_WP, seed=7 + i,
                                            comp_home=ch, comp_thr=thr))
        else:
            p3[i] = p2[i]
    y = te["outcome_home_win"].astype(float).to_numpy()
    mk = te["market_prob"].to_numpy()
    return {"n_test_ticks": int(len(te)),
            "brier_v2": round(brier(p2.tolist(), y.tolist()), 5),
            "brier_v3": round(brier(p3.tolist(), y.tolist()), 5),
            "brier_market": round(brier(mk.tolist(), y.tolist()), 5),
            "v3_beats_v2": bool(brier(p3.tolist(), y.tolist()) < brier(p2.tolist(), y.tolist())),
            "v3_beats_market": bool(brier(p3.tolist(), y.tolist()) < brier(mk.tolist(), y.tolist())),
            "note": "sim uses ZERO market info; market is the honest yardstick"}


def run(rebuild: bool = False, max_fit_games: Optional[int] = None) -> Dict[str, Any]:
    poss = add_state_buckets(load_corpus(rebuild, max_fit_games))
    wide, _thr = build_asof_terciles(poss)
    fit_poss = attach_terciles(poss[poss["season"].isin(FIT_SEASONS)], wide)
    v2 = PossessionModel.fit(fit_poss)
    pace = PaceModel.fit(fit_poss)
    pcdf2, dcdf = S.build_cdfs(v2, pace)
    # composite conditioning: per-game D for all seasons; thresholds from fit possessions
    gcd = all_game_comp_diff(list(FIT_SEASONS) + [TEST_SEASON])
    comp_thr = build_comp_thresholds(fit_poss, gcd)
    v3 = ConditionedPointModel.fit(fit_poss, v2, gcd, comp_thr)
    pcdf3 = v3.point_cdf_matrix()
    test_poss = attach_terciles(poss[poss["season"] == TEST_SEASON], wide)
    panel_ab = _panel_pit_crps(test_poss, wide, pcdf2, pcdf3, dcdf, gcd, comp_thr)
    try:
        panel_c = _panel_checkpoints(wide, pcdf2, pcdf3, dcdf, gcd, comp_thr)
    except Exception as exc:
        panel_c = {"verdict": "ERROR", "note": str(exc)[:200]}

    named = panel_ab["named"]
    named_improved = sum(1 for k in NAMED if named.get(k)
                         and named[k]["pit_dev_v3"] < named[k]["pit_dev_v2"])
    verdict, lesson = _verdict(named_improved, panel_ab["pooled"])

    n_test_games = len([g for g in gcd if g in set(test_poss["game_id"].astype(str))])
    doc = {
        "model": "nba_sim2_v3_composite_conditioner", "edge_claimed": False,
        "fit_seasons": list(FIT_SEASONS), "test_season": TEST_SEASON,
        "conditioning": v3.summary(),
        "coverage_test_games_with_composite": n_test_games,
        "panel_A_B_pit_crps": panel_ab,
        "panel_C_checkpoint_brier": panel_c,
        "named_buckets_improved_pit": named_improved,
        "verdict": verdict, "lesson": lesson,
        "leak_audit": ("strict prior-season composite; comp thresholds fit on 2024-25 only; "
                       "game-representative D held fixed in the replay; paired seeds -> "
                       "truncation-invariant. 2023-24 has no prior profiles -> neutral bin."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "hypothesis": "sim2_v3_lineup_composite_possession_conditioner", "sport": "nba",
            "atomic_unit": "possession_state_cell", "method": "sim2_cond_composite_v1",
            "season": "walkforward_fit_2023_24+2024_25_test_2025_26",
            "n": pooled["n"], "named_buckets_improved_pit": named_improved,
            "pooled_pit_dev_v2": pooled["pit_dev_v2"], "pooled_pit_dev_v3": pooled["pit_dev_v3"],
            "pooled_crps_v2": pooled["crps_v2"], "pooled_crps_v3": pooled["crps_v3"],
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
    p = doc["panel_A_B_pit_crps"]
    print("v3 [%s] cond_cells full=%d backoff=%d thr=%s" % (
        doc["verdict"], doc["conditioning"]["n_full_conditioned"],
        doc["conditioning"]["n_backoff_v2"], doc["conditioning"]["comp_thresholds"]))
    for k in NAMED:
        b = p["named"].get(k)
        if b:
            print("  %-6s n=%d PITdev v2=%.4f v3=%.4f | CRPS v2=%.3f v3=%.3f" % (
                k, b["n"], b["pit_dev_v2"], b["pit_dev_v3"], b["crps_v2"], b["crps_v3"]))
    po = p["pooled"]
    print("  POOLED n=%d PITdev v2=%.4f v3=%.4f | CRPS v2=%.3f v3=%.3f" % (
        po["n"], po["pit_dev_v2"], po["pit_dev_v3"], po["crps_v2"], po["crps_v3"]))
    c = doc["panel_C_checkpoint_brier"]
    print("  CKPT brier v2=%s v3=%s market=%s" % (
        c.get("brier_v2"), c.get("brier_v3"), c.get("brier_market")))
    print("  lesson:", doc["lesson"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
