"""domains.soccer.chain_engine.validate_extra_corpora -- REPLICATION check of the
possession-chain engine's panel A (state-conditioned shot log-loss vs naive
constant-rate baseline) on competitions BEYOND the original A/B (Premier League
2015/16 + FA WSL pooled) corpus, using the metadata-only expansion built by
domains.soccer.build_match_meta_full (data/cache/statsbomb/match_meta_full.parquet).

Read-only reuse of the SHIPPED chain-engine modules (corpus.build_possession_frame,
shot_model.ShotModel/naive_baseline) -- this script does not edit validate.py or
corpus.py, it is an ADDITIVE replication harness only.

SPLIT: same discipline as corpus.split_fit_test -- per-competition date-sorted
70% fit / 30% test (declared v1 simplification, no season-boundary logic needed
since each label here is already a single competition+season).

PRIOR VERDICT (commit dd33ce8a, data/frontend/ops/soccer_chain_engine_v1_scoreboard.json):
NULL in BOTH original corpora -- state-conditioned possession log-loss did NOT
beat the naive per-team constant-rate baseline (A: 0.37568 vs 0.36944; B: 0.35485
vs 0.35038). This script asks: does that NULL replicate, or does state-conditioning
help in a different competition?

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge claim.
CLI: python -m domains.soccer.chain_engine.validate_extra_corpora [--competitions NAME ...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.soccer.chain_engine.corpus import build_possession_frame
from domains.soccer.chain_engine.shot_model import ShotModel, naive_baseline

_REPO = Path(__file__).resolve().parents[3]
MATCH_META_FULL = _REPO / "data" / "cache" / "statsbomb" / "match_meta_full.parquet"
OUT = _REPO / "data" / "frontend" / "ops" / "soccer_chain_engine_v1_extra_corpora.json"
FIT_FRAC = 0.7
_EPS = 1e-12
DEFAULT_COMPETITIONS: Tuple[str, ...] = ("La_Liga_2015_2016", "Serie_A_2015_2016")


def _logloss(p_true: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(p_true, _EPS, 1.0))))


def _split_fit_test(meta: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Per-competition date-sorted 70/30 split (mirrors corpus.split_fit_test,
    but keyed on the `competition` label instead of the A/B `corpus` tag)."""
    sub = meta.sort_values("match_date").reset_index(drop=True)
    cut = int(len(sub) * FIT_FRAC)
    return sub.iloc[:cut], sub.iloc[cut:]


def _panel_a(fit_meta: pd.DataFrame, test_meta: pd.DataFrame) -> Dict[str, Any]:
    fit_poss = build_possession_frame(fit_meta)
    test_poss = build_possession_frame(test_meta)
    model = ShotModel.fit(fit_poss)
    base = naive_baseline(fit_poss)

    p_model = np.array([model.shot_prob(t, tb, sb) for t, tb, sb in
                        zip(test_poss["team"], test_poss["time_bucket"], test_poss["score_bucket"])])
    p_model_true = np.where(test_poss["had_shot"], p_model, 1.0 - p_model)
    base_glob = base["__global__"]
    p_base = test_poss["team"].map(base).fillna(base_glob).to_numpy()
    p_base_true = np.where(test_poss["had_shot"], p_base, 1.0 - p_base)
    ll_m, ll_b = _logloss(p_model_true), _logloss(p_base_true)
    return {
        "n_matches_fit": int(len(fit_meta)), "n_matches_test": int(len(test_meta)),
        "n_possessions_fit": int(len(fit_poss)), "n_possessions_test": int(len(test_poss)),
        "logloss_state_conditioned": round(ll_m, 5),
        "logloss_naive_constant_rate": round(ll_b, 5),
        "model_beats_naive": bool(ll_m < ll_b),
    }


def run(competitions: Sequence[str] = DEFAULT_COMPETITIONS) -> Dict[str, Any]:
    meta_full = pd.read_parquet(MATCH_META_FULL)
    results: Dict[str, Any] = {}
    for comp in competitions:
        sub = meta_full[meta_full["competition"] == comp]
        if sub.empty:
            results[comp] = {"error": "no matches found for this competition label"}
            continue
        fit, test = _split_fit_test(sub)
        results[comp] = _panel_a(fit, test)

    doc = {
        "model": "soccer_chain_engine_v1_replication_check", "edge_claimed": False,
        "unit": "possession (StatsBomb-tagged possession id -> shot)",
        "competitions_tested": list(competitions),
        "prior_verdict_original_corpora": {
            "A_premier_league_2015_16": "NULL (model LL 0.37568 > naive LL 0.36944)",
            "B_fa_wsl_pooled": "NULL (model LL 0.35485 > naive LL 0.35038)",
            "source": "data/frontend/ops/soccer_chain_engine_v1_scoreboard.json (commit dd33ce8a)",
        },
        "results": results,
        "honest_note": ("Panel-A possession-level log-loss only (state-conditioned "
                        "shot model vs naive per-team constant rate), same metric "
                        "as validate.py panel A. Distributional calibration check "
                        "only; no dollars, no edge."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--competitions", nargs="+", default=list(DEFAULT_COMPETITIONS))
    a = ap.parse_args(argv)
    d = run(competitions=a.competitions)
    for comp, r in d["results"].items():
        if "error" in r:
            print(f"{comp}: {r['error']}")
            continue
        print("%s: n_fit=%d n_test=%d poss_LL model=%.5f naive=%.5f (beats_naive=%s)" % (
            comp, r["n_matches_fit"], r["n_matches_test"],
            r["logloss_state_conditioned"], r["logloss_naive_constant_rate"],
            r["model_beats_naive"]))
    return 0


__all__ = ["run", "DEFAULT_COMPETITIONS"]

if __name__ == "__main__":
    raise SystemExit(_main())
