"""domains.soccer.chain_engine.validate -- fit the possession-chain engine on the
FIT split (first 70% by date), VALIDATE DISTRIBUTIONALLY on the held-out TEST
split (last 30%), PER CORPUS (A = Premier League 2015/16, B = FA WSL pooled) --
cross-corpus replication discipline, edge_claimed:false throughout.

  (A) POSSESSION-LEVEL log-loss: the (team, time, score)-state-conditioned shot
      model vs the naive per-team CONSTANT shot-rate baseline (classic
      Poisson-attack-rate assumption), mirroring mlb.pitch_engine panel A.
  (B) MATCH-LEVEL: MC-simulate held-out matches possession-by-possession (both
      models, same interface) -> PIT of the realized total-goals + CRPS of the
      goals ensemble vs a per-corpus Poisson-climatology baseline, plus
      home-win Brier for both models.

MARKET BASELINE: explicitly SKIPPED. The existing WC-2026 corpus with a joinable
market Brier (.1614) is a DIFFERENT competition/era (2026 World Cup) with zero
shared match ids against this 2015-2021 club-football corpus -- not a cheap
join, so no market row is reported (honest omission, not a fabricated number).

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge claim.
Tests: python -m pytest domains/soccer/chain_engine/test_validate.py -q
CLI: python -m domains.soccer.chain_engine.validate [--n-sims N] [--max-matches N]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from domains.basketball_nba.sim2.simulator import crps_ensemble, crps_gaussian, pit_value
from domains.soccer.chain_engine.corpus import (
    CORPORA, load_match_meta, split_fit_test, build_possession_frame,
)
from domains.soccer.chain_engine.shot_model import ShotModel, naive_baseline
from domains.soccer.chain_engine.match_sim import PossessionRate, simulate_match_ensemble

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "soccer_chain_engine_v1.json"
SCORE = _REPO / "data" / "frontend" / "ops" / "soccer_chain_engine_v1_scoreboard.json"
_EPS = 1e-12
N_SIMS_DEFAULT = 300
MAX_MATCHES_DEFAULT = 60


def _logloss(p_true: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p_true, _EPS, 1.0))))


def _panel_possession_logloss(model: ShotModel, base: dict, te: pd.DataFrame) -> dict:
    p_model = np.array([model.shot_prob(t, tb, sb) for t, tb, sb in
                        zip(te["team"], te["time_bucket"], te["score_bucket"])])
    p_model_true = np.where(te["had_shot"], p_model, 1.0 - p_model)
    base_glob = base["__global__"]
    p_base = te["team"].map(base).fillna(base_glob).to_numpy()
    p_base_true = np.where(te["had_shot"], p_base, 1.0 - p_base)
    ll_m, ll_b = _logloss(p_model_true), _logloss(p_base_true)
    return {"n": int(len(te)), "logloss_state_conditioned": round(ll_m, 5),
            "logloss_naive_constant_rate": round(ll_b, 5),
            "model_beats_naive": bool(ll_m < ll_b)}


class _NaiveShotModel:
    """Wraps naive_baseline() behind ShotModel's interface (constant rate, real
    xG bootstrap pool reused from the real model) so match_sim can drive both
    on the identical code path."""

    def __init__(self, base: dict, real_model: ShotModel):
        self._base, self._real = base, real_model

    def shot_prob(self, team, time_bucket, score_bucket):
        return self._base.get(team, self._base["__global__"])

    def sample_xg(self, time_bucket, score_bucket, rng):
        return self._real.sample_xg(time_bucket, score_bucket, rng)


def _panel_match(model: ShotModel, base: dict, rate: PossessionRate,
                 test_meta: pd.DataFrame, n_sims: int, max_matches: int) -> dict:
    if len(test_meta) > max_matches:
        test_meta = test_meta.sample(max_matches, random_state=0)
    clim_mu = float((test_meta["home_score"] + test_meta["away_score"]).mean())
    clim_sd = float((test_meta["home_score"] + test_meta["away_score"]).std() or 1.0)
    naive_model = _NaiveShotModel(base, model)
    rows_model: List[dict] = []; rows_base: List[dict] = []
    for r in test_meta.itertuples(index=False):
        realized_total = int(r.home_score + r.away_score)
        real_home_win = int(r.home_score > r.away_score)
        for kind, sink, mdl in (("model", rows_model, model), ("naive", rows_base, naive_model)):
            hg, ag = simulate_match_ensemble(r.home_team, r.away_team, mdl, rate,
                                             n=n_sims, seed=int(r.match_id) % 100000)
            totals = (hg + ag).astype(float)
            sink.append({"pit_total": pit_value(totals, realized_total),
                         "crps_total_sim": crps_ensemble(totals, realized_total),
                         "p_home_win_pred": float(np.mean(hg > ag)),
                         "p_home_win_real": real_home_win})
    def _summ(rows: List[dict]) -> dict:
        pit = np.array([x["pit_total"] for x in rows])
        dev = max(abs((pit <= q).mean() - q) for q in np.linspace(0.1, 1.0, 10))
        p = np.clip(np.array([x["p_home_win_pred"] for x in rows]), _EPS, 1 - _EPS)
        y = np.array([x["p_home_win_real"] for x in rows], dtype=float)
        return {"n": len(rows), "pit_total_uniformity_dev": round(float(dev), 4),
                "crps_total_sim": round(float(np.mean([x["crps_total_sim"] for x in rows])), 4),
                "brier_home_win": round(float(np.mean((p - y) ** 2)), 5)}
    m_summ, b_summ = _summ(rows_model), _summ(rows_base)
    crps_clim = float(np.mean([crps_gaussian(clim_mu, clim_sd, int(r.home_score + r.away_score))
                              for r in test_meta.itertuples(index=False)]))
    return {"model": m_summ, "naive_baseline": b_summ,
            "climatology_poisson_normal_approx": {"mu_total_goals": round(clim_mu, 3),
                                                  "sd_total_goals": round(clim_sd, 3),
                                                  "crps_total_climatology": round(crps_clim, 4)},
            "model_beats_naive_brier": bool(m_summ["brier_home_win"] < b_summ["brier_home_win"]),
            "model_beats_climatology_crps": bool(m_summ["crps_total_sim"] < crps_clim)}


def _run_corpus(tag: str, fit_meta: pd.DataFrame, test_meta: pd.DataFrame,
                n_sims: int, max_matches: int) -> Dict[str, Any]:
    fit_poss = build_possession_frame(fit_meta)
    test_poss = build_possession_frame(test_meta)
    model = ShotModel.fit(fit_poss)
    base = naive_baseline(fit_poss)
    rate = PossessionRate.fit(fit_poss)
    panel_a = _panel_possession_logloss(model, base, test_poss)
    panel_b = _panel_match(model, base, rate, test_meta, n_sims, max_matches)
    return {"corpus": tag, "n_matches_fit": int(len(fit_meta)),
            "n_matches_test": int(len(test_meta)), "n_possessions_fit": int(len(fit_poss)),
            "n_possessions_test": int(len(test_poss)), "shot_model": model.summary(),
            "panel_A_possession_logloss": panel_a, "panel_B_match_mc": panel_b}


def run(n_sims: int = N_SIMS_DEFAULT, max_matches: int = MAX_MATCHES_DEFAULT) -> Dict[str, Any]:
    meta = load_match_meta()
    fit, test = split_fit_test(meta)
    results = {}
    for tag in CORPORA:
        results[tag] = _run_corpus(tag, fit[fit["corpus"] == tag], test[test["corpus"] == tag],
                                   n_sims, max_matches)
    doc = {
        "model": "soccer_chain_engine_v1", "edge_claimed": False,
        "unit": "possession (StatsBomb-tagged possession id -> shot -> goal)",
        "corpora": {"A": "Premier League 2015/16 (men)", "B": "FA WSL pooled (women)"},
        "split": "per-corpus date-sorted 70% fit / 30% test",
        "results": results,
        "market_baseline": "SKIPPED -- no cheap join between this 2015-2021 "
                           "club-football corpus and the WC-2026 market corpus "
                           "(Brier .1614) -- different competitions/eras, no "
                           "shared match ids.",
        "honest_note": ("Distributional calibration only vs held-out test splits; "
                        "no dollars, no edge. Naive baseline is a per-team constant "
                        "shot rate (classic Poisson-attack-rate tennis-style null)."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    SCORE.write_text(json.dumps({
        "row": "soccer_chain_engine_v1", "edge_claimed": False,
        "A": {"poss_logloss_model": results["A"]["panel_A_possession_logloss"]["logloss_state_conditioned"],
              "poss_logloss_naive": results["A"]["panel_A_possession_logloss"]["logloss_naive_constant_rate"],
              "match_brier_model": results["A"]["panel_B_match_mc"]["model"]["brier_home_win"],
              "match_brier_naive": results["A"]["panel_B_match_mc"]["naive_baseline"]["brier_home_win"]},
        "B": {"poss_logloss_model": results["B"]["panel_A_possession_logloss"]["logloss_state_conditioned"],
              "poss_logloss_naive": results["B"]["panel_A_possession_logloss"]["logloss_naive_constant_rate"],
              "match_brier_model": results["B"]["panel_B_match_mc"]["model"]["brier_home_win"],
              "match_brier_naive": results["B"]["panel_B_match_mc"]["naive_baseline"]["brier_home_win"]},
    }, indent=2), encoding="utf-8")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=N_SIMS_DEFAULT)
    ap.add_argument("--max-matches", type=int, default=MAX_MATCHES_DEFAULT)
    a = ap.parse_args(argv)
    d = run(n_sims=a.n_sims, max_matches=a.max_matches)
    for tag in CORPORA:
        r = d["results"][tag]
        A, B = r["panel_A_possession_logloss"], r["panel_B_match_mc"]
        print("corpus %s: poss LL model=%.4f naive=%.4f (beats=%s) | match brier model=%.4f "
              "naive=%.4f | PIT dev=%.3f | CRPS sim=%.3f clim=%.3f" % (
                  tag, A["logloss_state_conditioned"], A["logloss_naive_constant_rate"],
                  A["model_beats_naive"], B["model"]["brier_home_win"],
                  B["naive_baseline"]["brier_home_win"], B["model"]["pit_total_uniformity_dev"],
                  B["model"]["crps_total_sim"],
                  B["climatology_poisson_normal_approx"]["crps_total_climatology"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
