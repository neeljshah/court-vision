"""domains.tennis.point_engine.validate_2026 -- CALIBRATION DRIFT CHECK: forward
the point engine fit on Sackmann 2011-2013 slams (unchanged, no refit) onto the
2026 MatchChartingProject charted-match population, out to 12+ years past the
fit window. Reuses validate.py's own _panel_point_logloss/_panel_match panel
functions UNCHANGED (corpus_2026.py matches their column contract exactly) --
same two panels as the 2014 held-out check, just a different held-out frame.

POPULATION CAVEAT (repeat on every read of this doc's numbers): the 2026 test
frame is MatchChartingProject's charted sample -- volunteer-selected high-
profile matches, NOT a random draw of the 2026 tour. Any drift/no-drift verdict
here describes THIS non-representative slice, not the tour at large.

Most 2026 servers never appear in the 2011-2013 Sackmann fit (different
generation of players almost entirely) -- PointModel.prob() backs off past the
missing per-server cells straight to the (score_bucket, set_bucket) league
cell, so this exercises the state-CONDITIONING SHAPE (does score pressure
still move serve-hold rate the same way 12 years later), not per-player rates.

MARKET BASELINE: see market_join_2026.py (separate, honest attempt; reported
independently because the temporal population it can even test is disjoint
from this one -- see that module's docstring).

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; no src/kernel imports; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_validate_2026.py -q
CLI: python -m domains.tennis.point_engine.validate_2026 [--n-sims N] [--max-matches N]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from domains.tennis.point_engine.corpus import FIT_YEARS, build_point_frame
from domains.tennis.point_engine.corpus_2026 import (
    POINTS_2026, POPULATION, build_match_frame_2026, build_point_frame_2026,
)
from domains.tennis.point_engine.point_model import PointModel, naive_baseline
from domains.tennis.point_engine.validate import _panel_match, _panel_point_logloss

_REPO = Path(__file__).resolve().parents[3]
OUT = _REPO / "data" / "frontend" / "ops" / "tennis_point_engine_2026_v1.json"
LEDGER = _REPO / "data" / "cache" / "intel_claims" / "prereg_hypothesis_ledger.jsonl"
N_SIMS_DEFAULT = 400
MAX_MATCHES_DEFAULT = 150


def run(n_sims: int = N_SIMS_DEFAULT, max_matches: int = MAX_MATCHES_DEFAULT) -> Dict[str, Any]:
    fit_pts = build_point_frame(FIT_YEARS)
    model = PointModel.fit(fit_pts)
    base = naive_baseline(fit_pts)

    test_pts = build_point_frame_2026()
    panel_a = _panel_point_logloss(model, base, test_pts)

    test_matches = build_match_frame_2026()
    panel_b = _panel_match(model, base, test_matches, n_sims, max_matches)

    n_servers_seen_in_fit = int(test_pts["server_id"].isin(model._server_only.keys()).sum())
    doc = {
        "model": "tennis_point_engine_2026_v1", "edge_claimed": False,
        "population": POPULATION,
        "population_caveat": ("MatchChartingProject charted sample: volunteer-selected "
                               "high-profile matches, NOT a random draw of the 2026 tour. "
                               "Verdicts below describe this slice only."),
        "fit_years": list(FIT_YEARS), "test_population_year": 2026,
        "n_points_fit": int(len(fit_pts)), "n_points_test_2026": int(len(test_pts)),
        "n_points_test_server_seen_in_fit": n_servers_seen_in_fit,
        "n_matches_test_2026": int(len(test_matches)),
        "point_model": model.summary(),
        "panel_A_point_logloss": panel_a,
        "panel_B_match_mc": panel_b,
        "market_baseline": "See market_join_2026.py -- separate module, disjoint "
                           "temporal population from this drift check.",
        "honest_note": ("Same score-state-conditioned point model fit on Sackmann "
                        "2011-2013 slams, forward-applied unchanged 12+ years to a "
                        "2026 charted-match population. Most 2026 servers are unseen "
                        "in the fit and back off to the league (score_bucket,set_bucket) "
                        "cell -- this tests whether the CONDITIONING SHAPE still holds, "
                        "not per-player calibration. No dollars, no edge."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _match_mc_verdict(B: Dict[str, Any]) -> str:
    """Panel-B verdict off the bootstrap CI, not the raw point estimate: a CI that
    straddles zero is UNDERPOWERED regardless of which side the point estimate
    favors; a significant win is still only PROVISIONAL (single MCP-charted
    corpus, no independent second corpus yet -- see module docstring)."""
    if not B["model_beats_climatology_crps_significant"]:
        return "UNDERPOWERED"
    return ("MODEL_BEATS_CLIMATOLOGY_CRPS_PROVISIONAL" if B["model_beats_climatology_crps"]
            else "CLIMATOLOGY_BEATS_MODEL_CRPS")


def _ledger_rows(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    A, B = doc["panel_A_point_logloss"], doc["panel_B_match_mc"]
    return [
        {"hypothesis": "tennis_point_engine_2011_2013fit_2026drift_point_logloss",
         "sport": "tennis", "atomic_unit": "point", "method": "tennis_point_engine_v1",
         "season": "fit_2011_2012_2013_test_2026_mcp_charted",
         "verdict": "MODEL_BEATS_NAIVE" if A["model_beats_naive"] else "NAIVE_HOLDS_OR_TIES",
         "lesson": ("point-level logloss, 2026 MCP charted population (n=%d): "
                    "state-conditioned=%.5f vs naive-constant-rate=%.5f. %d/%d test points' "
                    "server seen in the 2011-2013 fit (rest back off to league cell). "
                    "Population caveat: MCP charted sample is non-representative "
                    "(volunteer-selected high-profile matches)."
                    % (A["n"], A["logloss_state_conditioned"], A["logloss_naive_constant_rate"],
                       doc["n_points_test_server_seen_in_fit"], doc["n_points_test_2026"])),
         "edge_claimed": False, "computed_at": ts},
        {"hypothesis": "tennis_point_engine_2011_2013fit_2026drift_match_mc",
         "sport": "tennis", "atomic_unit": "match_mc_ensemble", "method": "tennis_point_engine_v1",
         "season": "fit_2011_2012_2013_test_2026_mcp_charted",
         "verdict": _match_mc_verdict(B),
         "lesson": ("match-level MC (n=%d): brier model=%.5f naive=%.5f, PIT-uniformity "
                    "dev=%.4f (PIT deviation this large means the ensemble is loosely "
                    "calibrated -- treat any CRPS win here skeptically), CRPS-total "
                    "sim=%.4f vs climatology-normal=%.4f (delta=%.4f, 95%% bootstrap CI "
                    "[%.4f, %.4f] over n_boot=%d resamples, significant=%s). Single "
                    "non-representative MCP-charted corpus (volunteer-selected "
                    "high-profile matches): any beats-claim is PROVISIONAL pending an "
                    "independent second corpus, and UNDERPOWERED whenever the CI "
                    "straddles zero."
                    % (B["model"]["n"], B["model"]["brier_match_winner"],
                       B["naive_baseline"]["brier_match_winner"],
                       B["model"]["pit_total_uniformity_dev"], B["model"]["crps_total_sim"],
                       B["climatology_normal"]["crps_total_climatology"],
                       B["crps_vs_climatology_ci"]["mean_delta"],
                       B["crps_vs_climatology_ci"]["ci_lo"], B["crps_vs_climatology_ci"]["ci_hi"],
                       B["crps_vs_climatology_ci"]["n_boot"], B["crps_vs_climatology_ci"]["significant"])),
         "edge_claimed": False, "computed_at": ts},
    ]


def append_ledger(doc: Dict[str, Any], ledger: Path = LEDGER) -> int:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = _ledger_rows(doc)
    with ledger.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    return len(rows)


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sims", type=int, default=N_SIMS_DEFAULT)
    ap.add_argument("--max-matches", type=int, default=MAX_MATCHES_DEFAULT)
    a = ap.parse_args(argv)
    d = run(n_sims=a.n_sims, max_matches=a.max_matches)
    n_rows = append_ledger(d)
    A, B = d["panel_A_point_logloss"], d["panel_B_match_mc"]
    print("2026 drift check | point LL model=%.4f naive=%.4f (beats=%s) | "
          "match brier model=%.4f naive=%.4f | PIT dev=%.3f | CRPS sim=%.3f clim=%.3f | "
          "%d ledger rows appended" % (
              A["logloss_state_conditioned"], A["logloss_naive_constant_rate"],
              A["model_beats_naive"], B["model"]["brier_match_winner"],
              B["naive_baseline"]["brier_match_winner"],
              B["model"]["pit_total_uniformity_dev"], B["model"]["crps_total_sim"],
              B["climatology_normal"]["crps_total_climatology"], n_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
