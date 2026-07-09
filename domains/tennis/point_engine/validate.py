"""domains.tennis.point_engine.validate -- fit the point engine on FIT_YEARS
(2011-2013), VALIDATE DISTRIBUTIONALLY on held-out TEST_YEAR (2014). Two panels,
edge_claimed:false throughout (calibration, not a betting-edge product).

  (A) POINT-LEVEL log-loss: the score-state-conditioned model vs the naive
      per-server CONSTANT-rate baseline (classic i.i.d.-points tennis model),
      matching mlb.pitch_engine.selection's panel-A design.
  (B) MATCH-LEVEL: MC-simulate held-out matches point-by-point (both models,
      same interface) from the real first server -> PIT of the realized final
      games-margin + CRPS of the margin ensemble vs a season-climatology Normal
      baseline, plus match-winner Brier for both models.

MARKET BASELINE: explicitly SKIPPED. The 1,778 settled Kalshi tennis files on
disk are current ATP/WTA tour markets (2025-2026); joining them to this
2011-2014 Sackmann slam corpus would require cross-corpus player-name+date
matching across a 10+ year gap for zero shared matches -- not a cheap join, so
no market row is reported here (honest omission, not a fabricated number).

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge claim.
Tests: python -m pytest domains/tennis/point_engine/test_validate.py -q
CLI: python -m domains.tennis.point_engine.validate [--n-sims N] [--max-matches N]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian, pit_value
from domains.tennis.point_engine.corpus import (
    FIT_YEARS, TEST_YEAR, build_point_frame, build_match_frame,
    score_bucket, set_bucket,
)
from domains.tennis.point_engine.point_model import PointModel, naive_baseline
from domains.tennis.point_engine.match_sim import simulate_match_ensemble

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "tennis_point_engine_v1.json"
SCORE = _REPO / "data" / "frontend" / "ops" / "tennis_point_engine_v1_scoreboard.json"
_EPS = 1e-12
N_SIMS_DEFAULT = 400
MAX_MATCHES_DEFAULT = 150


def _logloss(p_true: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p_true, _EPS, 1.0))))


def _panel_point_logloss(model: PointModel, base: dict, te: pd.DataFrame) -> dict:
    p_model = np.array([model.prob(sid, sb, tb) for sid, sb, tb in
                        zip(te["server_id"], te["score_bucket"], te["set_bucket"])])
    p_model_true = np.where(te["server_won"] == 1, p_model, 1.0 - p_model)
    base_glob = base["__global__"]
    p_base = te["server_id"].map(base).fillna(base_glob).to_numpy()
    p_base_true = np.where(te["server_won"] == 1, p_base, 1.0 - p_base)
    ll_m, ll_b = _logloss(p_model_true), _logloss(p_base_true)
    return {"n": int(len(te)), "logloss_state_conditioned": round(ll_m, 5),
            "logloss_naive_constant_rate": round(ll_b, 5),
            "model_beats_naive": bool(ll_m < ll_b)}


def _make_prob_fn(kind: str, model: PointModel, base: dict):
    if kind == "model":
        return lambda sid, sb, tb: model.prob(sid, sb, tb)
    glob = base["__global__"]
    return lambda sid, sb, tb: base.get(sid, glob)


def _panel_match(model: PointModel, base: dict, matches: pd.DataFrame,
                 n_sims: int, max_matches: int) -> dict:
    if len(matches) > max_matches:
        matches = matches.sample(max_matches, random_state=0)
    clim_mu = float(matches["total_games"].mean())
    clim_sd = float(matches["total_games"].std() or 1.0)
    rows_model: List[dict] = []
    rows_base: List[dict] = []
    for r in matches.itertuples(index=False):
        p1, p2, bo, fs, wid, tg = (r.player1id, r.player2id, r.best_of,
                                    r.first_server_id, r.winner_id, r.total_games)
        realized_p1_win = int(wid == p1)
        for kind, sink in (("model", rows_model), ("naive", rows_base)):
            prob_fn = _make_prob_fn(kind, model, base)
            margins, totals, p1_win = simulate_match_ensemble(
                p1, p2, bo, fs, prob_fn, n=n_sims, seed=hash(r.match_id) % 100000)
            sink.append({"pit_total": pit_value(totals, tg),
                         "crps_total_sim": crps_ensemble(totals, tg),
                         "p1_win_pred": p1_win, "p1_win_real": realized_p1_win})
    def _summ(rows: List[dict]) -> dict:
        pit = np.array([r["pit_total"] for r in rows])
        dev = max(abs((pit <= q).mean() - q) for q in np.linspace(0.1, 1.0, 10))
        p = np.clip(np.array([r["p1_win_pred"] for r in rows]), _EPS, 1 - _EPS)
        y = np.array([r["p1_win_real"] for r in rows], dtype=float)
        brier = float(np.mean((p - y) ** 2))
        crps_sim = float(np.mean([r["crps_total_sim"] for r in rows]))
        return {"n": len(rows), "pit_total_uniformity_dev": round(float(dev), 4),
                "crps_total_sim": round(crps_sim, 4), "brier_match_winner": round(brier, 5)}
    m_summ, b_summ = _summ(rows_model), _summ(rows_base)
    crps_clim = float(np.mean([crps_gaussian(clim_mu, clim_sd, r.total_games)
                              for r in matches.itertuples(index=False)]))
    return {"model": m_summ, "naive_baseline": b_summ,
            "climatology_normal": {"mu_total_games": round(clim_mu, 3),
                                   "sd_total_games": round(clim_sd, 3),
                                   "crps_total_climatology": round(crps_clim, 4)},
            "model_beats_naive_brier": bool(m_summ["brier_match_winner"] < b_summ["brier_match_winner"]),
            "model_beats_climatology_crps": bool(m_summ["crps_total_sim"] < crps_clim)}


def run(n_sims: int = N_SIMS_DEFAULT, max_matches: int = MAX_MATCHES_DEFAULT) -> Dict[str, Any]:
    fit_pts = build_point_frame(FIT_YEARS)
    test_pts = build_point_frame((TEST_YEAR,))
    model = PointModel.fit(fit_pts)
    base = naive_baseline(fit_pts)
    panel_a = _panel_point_logloss(model, base, test_pts)

    test_matches = build_match_frame((TEST_YEAR,))
    panel_b = _panel_match(model, base, test_matches, n_sims, max_matches)

    doc = {
        "model": "tennis_point_engine_v1", "edge_claimed": False,
        "unit": "point (real point-by-point sequences, Sackmann Grand Slam PBP)",
        "fit_years": list(FIT_YEARS), "test_year": TEST_YEAR,
        "n_points_fit": int(len(fit_pts)), "n_points_test": int(len(test_pts)),
        "n_matches_test_total": int(len(test_matches)),
        "point_model": model.summary(),
        "panel_A_point_logloss": panel_a,
        "panel_B_match_mc": panel_b,
        "market_baseline": "SKIPPED -- no cheap join between 2011-2014 Sackmann "
                           "slam corpus and the current 1,778-file Kalshi tennis "
                           "settled corpus (different eras, no shared match ids).",
        "honest_note": ("Distributional calibration only vs held-out 2014 slams; "
                        "no dollars, no edge. Naive baseline is the classic "
                        "i.i.d.-points tennis model (per-server constant rate)."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    SCORE.write_text(json.dumps({
        "row": "tennis_point_engine_v1", "edge_claimed": False,
        "point_logloss_model": panel_a["logloss_state_conditioned"],
        "point_logloss_naive": panel_a["logloss_naive_constant_rate"],
        "match_brier_model": panel_b["model"]["brier_match_winner"],
        "match_brier_naive": panel_b["naive_baseline"]["brier_match_winner"],
        "pit_dev_model": panel_b["model"]["pit_total_uniformity_dev"],
        "model_beats_naive_point": panel_a["model_beats_naive"],
        "model_beats_naive_match": panel_b["model_beats_naive_brier"],
    }, indent=2), encoding="utf-8")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=N_SIMS_DEFAULT)
    ap.add_argument("--max-matches", type=int, default=MAX_MATCHES_DEFAULT)
    a = ap.parse_args(argv)
    d = run(n_sims=a.n_sims, max_matches=a.max_matches)
    A, B = d["panel_A_point_logloss"], d["panel_B_match_mc"]
    print("point LL model=%.4f naive=%.4f (beats=%s) | match brier model=%.4f naive=%.4f | "
          "PIT dev=%.3f | CRPS sim=%.3f clim=%.3f" % (
              A["logloss_state_conditioned"], A["logloss_naive_constant_rate"],
              A["model_beats_naive"], B["model"]["brier_match_winner"],
              B["naive_baseline"]["brier_match_winner"],
              B["model"]["pit_total_uniformity_dev"], B["model"]["crps_total_sim"],
              B["climatology_normal"]["crps_total_climatology"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
