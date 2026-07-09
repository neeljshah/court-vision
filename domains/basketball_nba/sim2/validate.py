"""domains.basketball_nba.sim2.validate -- fit the v2 possession + pace models on
2023-24 + 2024-25 and VALIDATE DISTRIBUTIONALLY on held-out 2025-26.

Three panels (edge_claimed:false throughout; this is calibration, not $):
  (A) PIT: for each held-out game, snapshot the state at the start of Q2/Q3/Q4 and
      mid-Q4, simulate to the final buzzer, and take the probability-integral
      transform of the REALIZED final margin within the simulated distribution.
      Uniform PIT per (period x margin) bucket == an honest distribution. Worst
      buckets are named -> the v3 improvement queue.
  (B) CRPS of the simulated final-margin ensemble vs the NBARepricer Gaussian
      score-anchor baseline, per bucket. Lower = sharper+calibrated.
  (C) Checkpoint win-prob: sim P(home) at each checkpoint tick vs the mechanism-
      ladder base logistic (refit walk-forward) AND the live market, on the
      READ-ONLY nba_checkpoints_full corpus (2025-26 test ticks only). Pooled +
      per-phase Brier, GAME-CLUSTERED. Sim<ladder => the sim carries structure the
      ladder lacks; note the ladder is MARKET-ANCHORED (uses first-traded p0) while
      the sim uses ZERO market info, so sim<ladder is a high bar. sim<market
      anywhere is flagged for replication only.

Data prep (corpus walk + leak-free as-of terciles) lives in corpus.py. Subsampling
(declared): checkpoint ticks thinned to <=MAX_TICKS_PER_GAME/game; PIT/CRPS use
N_DIST sims, checkpoints use N_WP sims.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; threads<=4; local only; no
$/edge claim. Tests: python -m pytest domains/basketball_nba/sim2/test_validate.py -q
CLI: python -m domains.basketball_nba.sim2.validate [--rebuild] [--max-fit-games N]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.possession_model import (
    add_state_buckets, margin_bucket, PossessionModel)
from domains.basketball_nba.sim2.pace_model import PaceModel
from domains.basketball_nba.sim2 import simulator as S
from domains.basketball_nba.sim2.corpus import (
    load_corpus, build_asof_terciles, attach_terciles, FIT_SEASONS, TEST_SEASON)

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "nba_sim2_validation.json"
SCORE = _REPO / "data" / "frontend" / "ops" / "nba_sim2_scoreboard.json"
N_DIST, N_WP = 2000, 1000
MAX_TICKS_PER_GAME = 12


def _snapshots(gdf: pd.DataFrame):
    """Held-out game -> [(period, clock, hs, as, final_margin)] snapshots at the
    start of Q2/Q3/Q4 and mid-Q4 (clock<=360)."""
    fh = int(gdf[gdf["off_is_home"]]["points"].sum())
    fa = int(gdf[~gdf["off_is_home"]]["points"].sum())
    fm = fh - fa
    out = []
    for per in (2, 3, 4):
        sub = gdf[gdf["period"] == per]
        if sub.empty:
            continue
        r = sub.sort_values("clock_start", ascending=False).iloc[0]
        out.append((per, 720.0, int(r.home_score_start), int(r.away_score_start), fm))
    q4 = gdf[(gdf["period"] == 4) & (gdf["clock_start"] <= 360.0)]
    if not q4.empty:
        r = q4.sort_values("clock_start", ascending=False).iloc[0]
        out.append((4, float(r.clock_start), int(r.home_score_start),
                    int(r.away_score_start), fm))
    return out


def _panel_pit_crps(test_poss, wide, pcdf, dcdf) -> Tuple[dict, dict]:
    from domains.basketball_nba.repricer import NBARepricer, _DEF_MU, _DEF_MARGIN_SIGMA

    class _St:
        pregame_params: dict = {}
    rep = NBARepricer()
    pit_bkt: Dict[str, list] = {}
    crps_s: Dict[str, list] = {}
    crps_g: Dict[str, list] = {}
    for gid, gdf in test_poss.groupby("game_id"):
        if gid not in wide.index:
            continue
        row = wide.loc[gid]
        ter = S.GameTerciles(int(row.home_off_t), int(row.home_def_t),
                             int(row.away_off_t), int(row.away_def_t), int(row.pace_t))
        for (per, clk, hs, as_, fm) in _snapshots(gdf):
            sims = S.simulate(per, clk, hs, as_, ter, pcdf, dcdf, n=N_DIST,
                              seed=int(gid[-6:]) if gid[-6:].isdigit() else 7)
            key = "P%d|m%d" % (per, margin_bucket(hs - as_))
            pit_bkt.setdefault(key, []).append(S.pit_value(sims, fm))
            crps_s.setdefault(key, []).append(S.crps_ensemble(sims, fm))
            st = _St()
            st.home_score, st.away_score = hs, as_
            st.elapsed_minutes = (per - 1) * 12.0 + (12.0 - clk / 60.0)
            st.pregame_params = {"mu_home": _DEF_MU, "mu_away": _DEF_MU,
                                 "margin_sigma": _DEF_MARGIN_SIGMA}
            pr = rep.reprice(st)
            crps_g.setdefault(key, []).append(
                S.crps_gaussian(pr["proj_margin_home"], max(pr["_margin_sd"], 1e-6), fm))
    pit_summary = {}
    for k, vals in sorted(pit_bkt.items()):
        v = np.array(vals)
        dev = max(abs((v <= q).mean() - q) for q in np.linspace(0.1, 1.0, 10))
        pit_summary[k] = {"n": len(v), "mean_pit": round(float(v.mean()), 4),
                          "uniformity_dev": round(float(dev), 4)}
    crps_summary = {}
    for k in sorted(crps_s):
        cs, cg = float(np.mean(crps_s[k])), float(np.mean(crps_g[k]))
        crps_summary[k] = {"n": len(crps_s[k]), "crps_sim": round(cs, 4),
                           "crps_gauss": round(cg, 4), "sim_better": bool(cs < cg)}
    return pit_summary, crps_summary


def _panel_checkpoints(wide, pcdf, dcdf) -> dict:
    from scripts.platformkit.ingame.nba_mechanism_ladder import (
        load_corpus as lc, build_crosswalk, _fit_predict, _BASE_COLS,
        TRAIN_SEASON, TEST_SEASON as CK_TEST, _dm_gameclustered)
    from scripts.platformkit.eval_gate.scoring import brier
    df = lc()
    cw = build_crosswalk(df)
    nba_by = dict(zip(cw["game_id"], cw["nba_game_id"]))
    d = df[df["game_id"].isin(nba_by)].copy()
    d["nba_game_id"] = d["game_id"].map(nba_by)
    d = d[d["nba_game_id"].astype(str).isin(wide.index)].copy()
    tr, te = d[d["season"] == TRAIN_SEASON], d[d["season"] == CK_TEST].copy()
    if len(tr) == 0 or len(te) == 0:
        return {"verdict": "NOT_TESTABLE", "note": "empty split"}
    te["p_ladder"] = _fit_predict(tr, te, _BASE_COLS)
    te = te.groupby("game_id", group_keys=False)[te.columns.tolist()].apply(
        lambda x: x.iloc[:: max(1, len(x) // MAX_TICKS_PER_GAME)]).reset_index(drop=True)
    p_sim = np.empty(len(te))
    for i, r in enumerate(te.itertuples(index=False)):
        row = wide.loc[str(r.nba_game_id)]
        ter = S.GameTerciles(int(row.home_off_t), int(row.home_def_t),
                             int(row.away_off_t), int(row.away_def_t), int(row.pace_t))
        sims = S.simulate(int(r.period), float(r.game_clock_s), int(r.score_home),
                          int(r.score_away), ter, pcdf, dcdf, n=N_WP, seed=7 + i)
        p_sim[i] = S.p_home_win(sims)
    y = te["outcome_home_win"].astype(float).to_numpy()
    pl, mk = te["p_ladder"].to_numpy(), te["market_prob"].to_numpy()
    b_sim, b_lad, b_mkt = (brier(p_sim.tolist(), y.tolist()),
                           brier(pl.tolist(), y.tolist()), brier(mk.tolist(), y.tolist()))
    md_l, dmp_l, g = _dm_gameclustered(te, (y - pl) ** 2, (y - p_sim) ** 2)
    phase = {}
    for ph in ["P1-2", "P3", "P4+OT"]:
        m = (te["phase"] == ph).to_numpy()
        if m.sum():
            phase[ph] = {"n": int(m.sum()),
                         "brier_sim": round(brier(p_sim[m].tolist(), y[m].tolist()), 5),
                         "brier_ladder": round(brier(pl[m].tolist(), y[m].tolist()), 5),
                         "brier_market": round(brier(mk[m].tolist(), y[m].tolist()), 5)}
    return {"n_test_ticks": int(len(te)), "n_test_games": int(g),
            "brier_sim": round(b_sim, 5), "brier_ladder": round(b_lad, 5),
            "brier_market": round(b_mkt, 5), "sim_beats_ladder": bool(b_sim < b_lad),
            "sim_beats_market": bool(b_sim < b_mkt),
            "dm_ladder_minus_sim": round(md_l, 6), "dm_p_gameclustered": round(dmp_l, 5),
            "ladder_note": "ladder base uses first-traded market p0; sim uses no market info",
            "phase": phase, "subsample": "<=%d ticks/game" % MAX_TICKS_PER_GAME}


def run(rebuild: bool = False, max_fit_games: Optional[int] = None) -> Dict[str, Any]:
    poss = add_state_buckets(load_corpus(rebuild, max_fit_games))
    wide, thr = build_asof_terciles(poss)
    fit_poss = attach_terciles(poss[poss["season"].isin(FIT_SEASONS)], wide)
    pmodel = PossessionModel.fit(fit_poss)
    pacemodel = PaceModel.fit(fit_poss)
    pcdf, dcdf = S.build_cdfs(pmodel, pacemodel)
    test_poss = attach_terciles(poss[poss["season"] == TEST_SEASON], wide)
    pit, crps = _panel_pit_crps(test_poss, wide, pcdf, dcdf)
    try:
        ckpt = _panel_checkpoints(wide, pcdf, dcdf)
    except Exception as exc:
        ckpt = {"verdict": "ERROR", "note": str(exc)[:200]}
    worst_pit = sorted(pit.items(), key=lambda kv: -kv[1]["uniformity_dev"])[:3]
    doc = {
        "model": "nba_sim2_possession_mc", "edge_claimed": False,
        "fit_seasons": list(FIT_SEASONS), "test_season": TEST_SEASON,
        "n_possessions_total": int(len(poss)), "n_possessions_fit": int(len(fit_poss)),
        "possession_model": pmodel.summary(), "pace_model": pacemodel.summary(),
        "tercile_thresholds": thr,
        "panel_A_pit": pit, "panel_A_worst_buckets": [k for k, _ in worst_pit],
        "panel_B_crps_vs_gaussian": crps, "panel_C_checkpoint_brier": ckpt,
        "honest_note": ("Distributional calibration only vs held-out 2025-26 and the "
                        "live in-play market; no dollars, no edge. sim<market is flagged "
                        "for replication discipline only."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    SCORE.write_text(json.dumps({
        "row": "nba_sim2", "edge_claimed": False,
        "checkpoint_brier_sim": ckpt.get("brier_sim"),
        "checkpoint_brier_ladder": ckpt.get("brier_ladder"),
        "checkpoint_brier_market": ckpt.get("brier_market"),
        "sim_beats_ladder": ckpt.get("sim_beats_ladder"),
        "worst_pit_buckets": [k for k, _ in worst_pit],
    }, indent=2), encoding="utf-8")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--max-fit-games", type=int, default=None)
    args = ap.parse_args(argv)
    doc = run(rebuild=args.rebuild, max_fit_games=args.max_fit_games)
    c = doc["panel_C_checkpoint_brier"]
    print("sim2: poss=%d fit=%d | ckpt brier sim=%s ladder=%s market=%s | worst PIT=%s" % (
        doc["n_possessions_total"], doc["n_possessions_fit"], c.get("brier_sim"),
        c.get("brier_ladder"), c.get("brier_market"), doc["panel_A_worst_buckets"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
