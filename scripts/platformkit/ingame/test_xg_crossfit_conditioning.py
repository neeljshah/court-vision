"""Per-file tests for xg_crossfit_conditioning (LANE 3 item 2: cross-fitted
xG conditioning, single-coefficient logit-additive family).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_xg_crossfit_conditioning.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import xg_crossfit_conditioning as X


def _row(gid, y, mp, xg_diff):
    return {"game_id": gid, "y": y, "model_prob": mp, "xg_home": xg_diff if xg_diff >= 0 else 0.0,
            "xg_away": 0.0 if xg_diff >= 0 else -xg_diff}


def test_conditioned_prob_zero_beta_is_identity():
    p = X.conditioned_prob(0.4, 1.5, 0.0)
    assert abs(p - 0.4) < 1e-9


def test_conditioned_prob_positive_beta_positive_xgdiff_raises_prob():
    p0 = X.conditioned_prob(0.5, 1.0, 0.0)
    p1 = X.conditioned_prob(0.5, 1.0, 0.5)
    assert p1 > p0


def test_fit_beta_recovers_known_generative_beta_deterministically():
    """Rows whose LABEL FREQUENCY (not a hard threshold) matches a KNOWN
    beta's conditioned probability -- fit_beta should recover it closely,
    and be exactly deterministic across repeated calls (no RNG in the
    search itself). A hard 0/1-by-sign label set is avoided deliberately:
    with perfectly separable labels the Brier-minimizing beta diverges to
    the search boundary (more separation = lower Brier), which is a
    property of Brier-min fitting, not a bug in fit_beta."""
    true_beta = 0.8
    rows = []
    for g in range(21):
        xg_diff = -1.0 + 0.1 * g
        mp = 0.5
        p = X.conditioned_prob(mp, xg_diff, true_beta)
        # Deterministic pseudo-frequency label: replicate each xg_diff level
        # proportionally to p so the POOLED empirical rate matches p (no RNG).
        n_pos = round(p * 10)
        for k in range(10):
            y = 1.0 if k < n_pos else 0.0
            rows.append({"game_id": "g%d_%d" % (g, k), "model_prob": mp,
                        "y": y, "xg_diff": xg_diff})
    b1 = X.fit_beta(rows)
    b2 = X.fit_beta(rows)
    assert b1 == b2  # exact determinism, no RNG
    assert abs(b1 - true_beta) < 0.15


def test_fit_beta_empty_rows_returns_zero():
    assert X.fit_beta([]) == 0.0


def test_half_report_crossfit_never_scores_beta_on_its_own_training_rows():
    """The core no-leak guarantee: train on one set, eval on a DISJOINT set;
    verify by using training rows that would make beta look great on
    themselves but the eval set is unaffected by that same beta unless it
    generalizes."""
    train_rows = [{"game_id": "t%d" % i, "model_prob": 0.5, "y": 1.0, "xg_diff": 2.0}
                 for i in range(10)]
    # Eval rows: xg_diff has OPPOSITE sign relationship to y -- a beta fit to
    # help train_rows should NOT help (should hurt or be neutral) on eval_rows.
    eval_rows = [{"game_id": "e%d" % i, "model_prob": 0.5, "y": 0.0, "xg_diff": 2.0}
                for i in range(10)]
    report = X._half_report(train_rows, eval_rows)
    # beta fit on train_rows pushes prob UP (since y=1 there); scored on
    # eval_rows (y=0) that same push should make Brier WORSE, not better.
    assert report["brier_delta"] is not None
    assert report["brier_delta"] > 0  # worse on held-out, proving no leak-driven improvement


def test_run_crossfit_deterministic_across_calls():
    def rows_fn():
        rows = []
        for g in range(30):
            xg_diff = -1.0 + (g % 10) * 0.2
            mp = 0.5
            gid = "game%d" % g
            y = 1.0 if xg_diff > 0 else 0.0
            rows.append({"game_id": gid, "model_prob": mp, "y": y,
                        "xg_home": max(xg_diff, 0.0), "xg_away": max(-xg_diff, 0.0)})
        return rows

    doc1 = X.run_crossfit(rows_fn=rows_fn)
    doc2 = X.run_crossfit(rows_fn=rows_fn)
    assert doc1["fit_on_half0_eval_on_half1"] == doc2["fit_on_half0_eval_on_half1"]
    assert doc1["fit_on_half1_eval_on_half0"] == doc2["fit_on_half1_eval_on_half0"]
    assert doc1["overall_verdict"] == doc2["overall_verdict"]


def test_run_crossfit_honesty_fields_present():
    doc = X.run_crossfit(rows_fn=lambda: [])
    assert doc["edge_claimed"] is False
    assert "cross-fit" in doc["honest_note"].lower() or "cross-fitted" in doc["hypothesis"].lower()
    assert doc["provenance"] == "backfill_validation"


def test_run_crossfit_producer_exception_is_honest_insufficient():
    def boom():
        raise RuntimeError("producer broke")

    doc = X.run_crossfit(rows_fn=boom)
    assert doc["n_games_total"] == 0
    assert doc["overall_verdict"] in ("MATCH", "INSUFFICIENT")
    assert "error" in doc


def test_run_crossfit_never_raises_with_real_default_rows_fn():
    """Exercises the real default wiring (enrichment_rows_soccer.rows_fn_backfill)
    against whatever real data currently exists on disk -- must never raise."""
    doc = X.run_crossfit()
    assert isinstance(doc, dict)
    assert "overall_verdict" in doc


def test_prep_rows_skips_missing_fields_never_imputes():
    raw = [
        {"game_id": "a", "model_prob": 0.5, "y": 1.0, "xg_home": 1.0, "xg_away": 0.0},
        {"game_id": "b", "model_prob": 0.5, "y": 1.0, "xg_home": None, "xg_away": 0.0},
        {"game_id": "c", "model_prob": None, "y": 1.0, "xg_home": 1.0, "xg_away": 0.0},
        {"game_id": "d", "model_prob": 0.5, "y": None, "xg_home": 1.0, "xg_away": 0.0},
    ]
    out = X._prep_rows(raw)
    assert len(out) == 1
    assert out[0]["game_id"] == "a"
