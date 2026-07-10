"""domains.soccer.chain_engine.validate_full_power -- GATE LANE F6: rerun the
possession-chain engine's state-conditioning test (mechanisms.md entry #2,
REPLICATED NULL on 2 corpora, dd33ce8a) plus its extra-corpora replication
check (validate_extra_corpora.py, NULL on 2 more) at FULL-CORPUS POWER now
that StatsBomb open-data is 100% pulled locally (4,235/4,235 event files,
match_meta_full.parquet rebuilt to 3,961 matches / 80 competitions).

ADDITIVE ONLY: imports and reuses the SHIPPED panel functions unchanged --
`validate._panel_possession_logloss` (panel A), `validate._panel_match`
(panel B) -- and `validate_extra_corpora._split_fit_test` (per-competition
walk-forward split). Does not edit validate.py, validate_extra_corpora.py,
corpus.py, or shot_model.py.

SCOPE: every competition in match_meta_full.parquet with >= MIN_MATCHES
cached-event matches (20 competitions, 3,126 matches -- "thousands", vs the
4 corpora of ~200-380 matches tested before). Competitions are partitioned
into 3 DISJOINT groups (mens_league, womens_league, international_tournament,
plus an auto "other" bucket for anything uncategorised) so the survivor check
below is genuinely cross-group, not just cross-competition.

POWER: per-competition panel A/B (same walk-forward 70/30 split as before),
then a competition-CLUSTERED bootstrap (resample competitions with
replacement, B=2000) on the possession-count-weighted pooled log-loss
delta (naive - model; positive = model beats naive) -- the competition is
the exchangeable resampling unit, not the match, since within-competition
matches share a single fitted model/baseline.

VERDICT: CLASS_CLOSED_AT_POWER if the pooled delta's 95% CI does not sit
entirely above 0 (i.e. no reliable model-beats-naive signal pooled) AND
fewer than 2 disjoint groups contain an individual model_beats_naive
survivor competition. Otherwise PROVISIONAL_SURVIVOR.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; local only; no $/edge
claim; edge_claimed:false throughout (this is prediction-accuracy calibration,
never ROI).
Tests: python -m pytest domains/soccer/chain_engine/test_validate_full_power.py -q
CLI: python -m domains.soccer.chain_engine.validate_full_power [--min-matches N]
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
from domains.soccer.chain_engine.match_sim import PossessionRate
from domains.soccer.chain_engine.validate import (
    _panel_possession_logloss, _panel_match, N_SIMS_DEFAULT, MAX_MATCHES_DEFAULT,
)
from domains.soccer.chain_engine.validate_extra_corpora import _split_fit_test
from domains.soccer.knowledge._data import LEDGER_PATH
from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic

_REPO = Path(__file__).resolve().parents[3]
MATCH_META_FULL = _REPO / "data" / "cache" / "statsbomb" / "match_meta_full.parquet"
OUT = _REPO / "data" / "frontend" / "ops" / "soccer_chain_engine_v1_full_power.json"
MIN_MATCHES_DEFAULT = 40
N_BOOT_DEFAULT = 2000

# Curated disjoint partition of the competitions this repo already has cached
# metadata+events for (see match_meta_full's `competition` labels). Anything
# eligible (>= min_matches) but not named here auto-falls into "other" below,
# so a fresh StatsBomb pull never silently drops a competition from the gate.
GROUPS: Dict[str, Tuple[str, ...]] = {
    "mens_league": (
        "Premier_League_2015_2016", "La_Liga_2015_2016", "Serie_A_2015_2016",
        "Ligue_1_2015_2016", "Indian_Super_league_2021_2022",
    ),
    "womens_league": (
        "Liga_F_2023_2024", "NWSL_2023", "Frauen_Bundesliga_2023_2024",
        "FA_Women_s_Super_League_2023_2024", "FA_Women_s_Super_League_2020_2021",
        "Serie_A_Women_2023_2024", "FA_Women_s_Super_League_2018_2019",
        "FA_Women_s_Super_League_2019_2020",
    ),
    "international_tournament": (
        "Women_s_World_Cup_2023", "FIFA_World_Cup_2022", "FIFA_World_Cup_2018",
        "African_Cup_of_Nations_2023", "Women_s_World_Cup_2019",
        "UEFA_Euro_2020", "UEFA_Euro_2024",
    ),
}


def assign_group(comp: str) -> str:
    for g, members in GROUPS.items():
        if comp in members:
            return g
    return "other"


def _eligible_competitions(meta_full: pd.DataFrame, min_matches: int) -> List[str]:
    vc = meta_full["competition"].value_counts()
    return sorted(vc[vc >= min_matches].index.tolist())


def _weighted_delta(deltas: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(weights * deltas) / np.sum(weights))


def cluster_bootstrap_ci(deltas: Sequence[float], weights: Sequence[float],
                          n_boot: int = N_BOOT_DEFAULT, seed: int = 0) -> Tuple[float, float]:
    """Resample COMPETITIONS (the exchangeable cluster) with replacement;
    each draw recomputes the possession-weighted pooled delta. Returns the
    (2.5, 97.5) percentile CI on the pooled delta."""
    deltas_a, weights_a = np.asarray(deltas, dtype=float), np.asarray(weights, dtype=float)
    k = len(deltas_a)
    if k == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, k, size=k)
        boots[b] = _weighted_delta(deltas_a[idx], weights_a[idx])
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _run_competition(comp: str, sub: pd.DataFrame, n_sims: int, max_matches: int) -> Dict[str, Any]:
    fit_meta, test_meta = _split_fit_test(sub)
    fit_poss = build_possession_frame(fit_meta)
    test_poss = build_possession_frame(test_meta)
    model = ShotModel.fit(fit_poss)
    base = naive_baseline(fit_poss)
    rate = PossessionRate.fit(fit_poss)
    panel_a = _panel_possession_logloss(model, base, test_poss)
    panel_b = _panel_match(model, base, rate, test_meta, n_sims, max_matches)
    return {
        "group": assign_group(comp), "n_matches_fit": int(len(fit_meta)),
        "n_matches_test": int(len(test_meta)), "panel_A_possession_logloss": panel_a,
        "panel_B_match_mc": panel_b,
        "delta_ll": round(panel_a["logloss_naive_constant_rate"] - panel_a["logloss_state_conditioned"], 6),
        "delta_brier": round(panel_b["naive_baseline"]["brier_home_win"] - panel_b["model"]["brier_home_win"], 6),
    }


def run(min_matches: int = MIN_MATCHES_DEFAULT, n_sims: int = N_SIMS_DEFAULT,
        max_matches: int = MAX_MATCHES_DEFAULT, n_boot: int = N_BOOT_DEFAULT) -> Dict[str, Any]:
    meta_full = pd.read_parquet(MATCH_META_FULL)
    comps = _eligible_competitions(meta_full, min_matches)
    results: Dict[str, Any] = {}
    for comp in comps:
        results[comp] = _run_competition(comp, meta_full[meta_full["competition"] == comp],
                                         n_sims, max_matches)

    deltas_ll = np.array([r["delta_ll"] for r in results.values()])
    weights = np.array([r["panel_A_possession_logloss"]["n"] for r in results.values()], dtype=float)
    deltas_brier = np.array([r["delta_brier"] for r in results.values()])
    weights_b = np.array([r["panel_B_match_mc"]["model"]["n"] for r in results.values()], dtype=float)

    pooled_delta_ll = _weighted_delta(deltas_ll, weights)
    ci_ll = cluster_bootstrap_ci(deltas_ll, weights, n_boot=n_boot)
    pooled_delta_brier = _weighted_delta(deltas_brier, weights_b)
    ci_brier = cluster_bootstrap_ci(deltas_brier, weights_b, n_boot=n_boot)

    survivors_a = [c for c, r in results.items() if r["panel_A_possession_logloss"]["model_beats_naive"]]
    survivors_b = [c for c, r in results.items() if r["panel_B_match_mc"]["model_beats_naive_brier"]]
    groups_with_survivor_a = {assign_group(c) for c in survivors_a}
    groups_with_survivor_b = {assign_group(c) for c in survivors_b}
    n_groups_survivor = len(groups_with_survivor_a | groups_with_survivor_b)

    ll_null_holds = not (ci_ll[0] > 0)   # CI does NOT sit entirely above 0
    brier_null_holds = not (ci_brier[0] > 0)
    class_closed = ll_null_holds and brier_null_holds and n_groups_survivor < 2
    verdict = "CLASS_CLOSED_AT_POWER" if class_closed else "PROVISIONAL_SURVIVOR"

    # original (pre-power) baselines, for the "does calibration tighten" ask
    prior_brier = {"A_epl": {"model": 0.24819, "naive": 0.24239},
                   "B_wsl": {"model": 0.19601, "naive": 0.19552}}
    prior_avg_gap = float(np.mean([prior_brier["A_epl"]["model"] - prior_brier["A_epl"]["naive"],
                                   prior_brier["B_wsl"]["model"] - prior_brier["B_wsl"]["naive"]]))
    calibration_tightens = abs(pooled_delta_brier) < abs(-prior_avg_gap) if pooled_delta_brier <= 0 else False

    doc = {
        "model": "soccer_chain_engine_v1_full_power_gate", "edge_claimed": False,
        "gate": "F6", "unit": "possession (panel A) / match MC-sim (panel B)",
        "n_competitions": len(comps),
        "n_matches_total": int(meta_full["competition"].isin(comps).sum()),
        "min_matches_per_competition": min_matches,
        "groups": {g: [c for c in members if c in comps] for g, members in GROUPS.items()},
        "other_competitions": [c for c in comps if assign_group(c) == "other"],
        "results": results,
        "pooled": {
            "panel_A_delta_ll_naive_minus_model": {
                "point_estimate": round(pooled_delta_ll, 6),
                "ci95_competition_clustered_bootstrap": [round(ci_ll[0], 6), round(ci_ll[1], 6)],
                "interpretation": "positive = model beats naive; CI entirely above 0 = reliable pooled win",
            },
            "panel_B_delta_brier_naive_minus_model": {
                "point_estimate": round(pooled_delta_brier, 6),
                "ci95_competition_clustered_bootstrap": [round(ci_brier[0], 6), round(ci_brier[1], 6)],
            },
            "survivors_panel_A": survivors_a, "survivors_panel_B": survivors_b,
            "groups_with_any_survivor": sorted(groups_with_survivor_a | groups_with_survivor_b),
            "n_disjoint_groups_with_survivor": n_groups_survivor,
        },
        "calibration_tightens_vs_prior_2corpus_run": calibration_tightens,
        "verdict": verdict,
        "prior_verdicts_this_class": {
            "A_B_original": "REJECTED / REPLICATED NULL (commit dd33ce8a9dc16373b04eea3f060ed49e80e88d91)",
            "La_Liga_Serie_A_extra": "NULL (soccer_chain_engine_v1_extra_corpora.json)",
        },
        "honest_note": ("Distributional calibration only (Brier/log-loss/PIT/CRPS vs a naive "
                        "per-team constant-rate baseline and a Poisson climatology); no dollars, "
                        "no ROI, no market-follow claim. edge_claimed=false throughout."),
    }
    write_json_atomic(OUT, doc, indent=2)
    return doc


def append_ledger_row(doc: Dict[str, Any]) -> None:
    pooled = doc["pooled"]["panel_A_delta_ll_naive_minus_model"]
    row = {
        "sport": "soccer", "corpus": "statsbomb_match_meta_full__%d_matches_%d_competitions" % (
            doc["n_matches_total"], doc["n_competitions"]),
        "hypothesis": "state_conditioned_shot_model_vs_naive_full_power",
        "n": doc["n_matches_total"], "effect": pooled["point_estimate"],
        "p": None,
        "verdict": "NULL_REPLICATED_AT_POWER" if doc["verdict"] == "CLASS_CLOSED_AT_POWER"
                   else "PROVISIONAL",
        "edge_claimed": False,
        "note": ("full-corpus-power gate (F6): %d competitions / %d matches, %d disjoint groups "
                 "(mens_league/womens_league/international_tournament/other); pooled panel-A "
                 "delta_ll(naive-model)=%.5f CI95=%s (competition-clustered bootstrap); pooled "
                 "panel-B delta_brier=%.5f CI95=%s; survivors_A=%s; verdict=%s" % (
                     doc["n_competitions"], doc["n_matches_total"],
                     doc["pooled"]["n_disjoint_groups_with_survivor"],
                     pooled["point_estimate"], pooled["ci95_competition_clustered_bootstrap"],
                     doc["pooled"]["panel_B_delta_brier_naive_minus_model"]["point_estimate"],
                     doc["pooled"]["panel_B_delta_brier_naive_minus_model"]["ci95_competition_clustered_bootstrap"],
                     doc["pooled"]["survivors_panel_A"], doc["verdict"])),
    }
    append_jsonl_atomic(LEDGER_PATH, row)


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-matches", type=int, default=MIN_MATCHES_DEFAULT)
    ap.add_argument("--n-sims", type=int, default=N_SIMS_DEFAULT)
    ap.add_argument("--max-matches", type=int, default=MAX_MATCHES_DEFAULT)
    ap.add_argument("--n-boot", type=int, default=N_BOOT_DEFAULT)
    ap.add_argument("--no-ledger", action="store_true")
    a = ap.parse_args(argv)
    doc = run(min_matches=a.min_matches, n_sims=a.n_sims, max_matches=a.max_matches, n_boot=a.n_boot)
    if not a.no_ledger:
        append_ledger_row(doc)
    p = doc["pooled"]
    print("competitions=%d matches=%d groups_with_survivor=%d verdict=%s" % (
        doc["n_competitions"], doc["n_matches_total"],
        p["n_disjoint_groups_with_survivor"], doc["verdict"]))
    print("panel A pooled delta_ll(naive-model)=%.5f CI95=%s" % (
        p["panel_A_delta_ll_naive_minus_model"]["point_estimate"],
        p["panel_A_delta_ll_naive_minus_model"]["ci95_competition_clustered_bootstrap"]))
    print("panel B pooled delta_brier(naive-model)=%.5f CI95=%s" % (
        p["panel_B_delta_brier_naive_minus_model"]["point_estimate"],
        p["panel_B_delta_brier_naive_minus_model"]["ci95_competition_clustered_bootstrap"]))
    return 0


__all__ = ["run", "append_ledger_row", "assign_group", "cluster_bootstrap_ci",
           "GROUPS", "MIN_MATCHES_DEFAULT"]

if __name__ == "__main__":
    raise SystemExit(_main())
