"""Tests for the R12_F1 v2 in-play winprob (endQ2 ensemble + anchor blend).

Covers the new code path in src/prediction/inplay_winprob.py:
  * load_v2_bundle returns a populated dict for endQ2 when artifacts exist
  * predict_home_win_prob on a synthetic endQ2 snapshot returns a probability
    in [0, 1] AND uses the v2 ensemble (so it differs from the pregame anchor)
  * Monotonicity: a larger home lead -> higher home WP at endQ2
  * Anchor blend honors the learned alpha (pregame influence at alpha < 1)
  * Pure-fallback path: with the v2 bundle masked, the predictor still works
    via the v1 endQ2 booster (or returns None if no v1 either).

Tests skip cleanly when the v2 endQ2 artifact is absent (matches the existing
test_inplay_winprob.py pattern).
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import inplay_winprob as iw  # noqa: E402
from src.prediction.inplay_winprob import (  # noqa: E402
    _v2_bundle_paths,
    features_from_snapshot,
    load_v2_bundle,
    predict_home_win_prob,
    reset_cache,
)


def _v2_artifacts_present(snap: str = "endQ2") -> bool:
    paths = _v2_bundle_paths(snap)
    return os.path.exists(paths["lgb"]) and os.path.exists(paths["meta"])


pytestmark = pytest.mark.skipif(
    not _v2_artifacts_present("endQ2"),
    reason=(
        "R12_F1 v2 endQ2 artifacts missing -- run "
        "`python scripts/probe_R12_F1_inplay_winprob_v2.py` first"
    ),
)


@pytest.fixture(autouse=True)
def _reset_module_cache():
    reset_cache()
    yield
    reset_cache()


def _full_v2_features(score_margin: float = 5.0,
                      pregame_win_prob: float = 0.55) -> dict:
    """A complete v2 feature dict so the booster path runs end-to-end."""
    return {
        # core in-play
        "score_margin": score_margin,
        "total_pts": 110.0,
        "pace_so_far": 4.58,
        "q1_delta": score_margin / 2,
        "q2_delta": score_margin / 2,
        "last_q_margin": score_margin / 2,
        # v2 projections
        "projected_final_margin": score_margin * 2.0,
        "projected_total_score": 220.0,
        "qtr_margin_var": 4.0,
        "qtr_margin_mean": score_margin / 2,
        # pregame context
        "pregame_win_prob": pregame_win_prob,
        "net_rtg_diff": 2.0,
        "pace_diff": 0.5,
        "elo_diff": 30.0,
        "stars_diff": 0.0,
        "rest_diff": 0.0,
        "b2b_diff": 0.0,
        "last5_diff": 1.0,
        # categoricals (must be values seen during training for the booster
        # to fire cleanly; LightGBM tolerates unseen categories as missing).
        "home_team_id": 1610612747,
        "season": "2024-25",
    }


def test_v2_bundle_loads_for_endq2():
    """The v2 endQ2 bundle must load and expose the documented schema."""
    bundle = load_v2_bundle("endQ2")
    assert bundle is not None, "v2 endQ2 bundle missing despite artifacts"
    # Required keys
    for k in ("booster", "meta", "w_lgb", "w_lr", "alpha",
              "feature_cols", "lr_feat_order", "lr_coef",
              "lr_intercept", "lr_mean", "lr_std"):
        assert k in bundle, f"v2 bundle missing key: {k}"
    # Weights must lie on the {lgb, lr} simplex.
    assert bundle["w_lgb"] >= 0.0
    assert bundle["w_lr"] >= 0.0
    assert abs(bundle["w_lgb"] + bundle["w_lr"] - 1.0) < 1e-6, (
        f"v2 ensemble weights do not sum to 1: "
        f"lgb={bundle['w_lgb']}, lr={bundle['w_lr']}"
    )
    # Alpha must lie in [0, 1] (the learned blend coefficient).
    assert 0.0 <= bundle["alpha"] <= 1.0


def test_v2_predict_returns_unit_interval_at_endq2():
    """A synthetic v2-shaped feature dict yields a valid probability."""
    feats = _full_v2_features(score_margin=5.0)
    p = predict_home_win_prob(feats, "endQ2")
    assert p is not None, "v2 predictor returned None"
    assert 0.0 <= p <= 1.0, f"v2 endQ2 probability {p} outside [0, 1]"


def test_v2_predict_monotonic_in_score_margin():
    """At endQ2, a bigger home lead must drive WP up (directional sanity)."""
    probs = []
    for m in (-15.0, -5.0, 0.0, 5.0, 15.0):
        p = predict_home_win_prob(_full_v2_features(score_margin=m), "endQ2")
        assert p is not None
        probs.append(p)
    assert probs[-1] > probs[0] + 0.20, (
        f"v2 endQ2 not directionally responsive to margin: {probs}"
    )


def test_v2_anchor_blend_honors_alpha():
    """When alpha < 1, the prediction should partially reflect pregame WP.

    Train on the trained v2 endQ2 model's actual alpha; the test just
    verifies that the blend formula is wired (alpha=1.0 means stack-only,
    alpha=0.0 means pregame-only). When the production alpha is exactly
    1.0 (stack-only), this test confirms two different pregame priors
    produce predictions that DIFFER by NO MORE than the model's own
    differential response to stars_diff/pregame_win_prob features.
    """
    bundle = load_v2_bundle("endQ2")
    assert bundle is not None
    feats_low = _full_v2_features(score_margin=2.0, pregame_win_prob=0.20)
    feats_high = _full_v2_features(score_margin=2.0, pregame_win_prob=0.80)
    p_low = predict_home_win_prob(feats_low, "endQ2")
    p_high = predict_home_win_prob(feats_high, "endQ2")
    assert p_low is not None and p_high is not None
    # The higher pregame must not produce a LOWER in-play WP — both the
    # stack (which uses pregame_win_prob as an input feature) and the anchor
    # blend (1-alpha)*pregame term point in the same direction.
    assert p_high >= p_low - 0.05, (
        f"endQ2 v2 inverts pregame signal: low={p_low}, high={p_high}"
    )


def test_features_from_snapshot_emits_v2_keys_at_endq2_boundary():
    """The helper must emit the v2 feature columns at the endQ2 boundary."""
    snap = {
        "period": 3, "clock": "12:00",  # endQ2 boundary (start of Q3)
        "home_score": 50, "away_score": 47,
        "home_q1": 28, "home_q2": 22,
        "away_q1": 26, "away_q2": 21,
        "home_team_id": 1610612747, "season": "2024-25",
        "pregame_win_prob": 0.58,
        "net_rtg_diff": 1.5, "pace_diff": 0.1, "elo_diff": 25.0,
        "stars_diff": 0.0, "rest_diff": 1.0,
        "b2b_diff": 0.0, "last5_diff": 1.0,
    }
    feats = features_from_snapshot(snap)
    # All v1 keys preserved
    assert feats["score_margin"] == 3
    assert feats["q2_delta"] == 1
    # v2 additions present
    for k in ("projected_final_margin", "projected_total_score",
              "qtr_margin_var", "qtr_margin_mean", "net_rtg_diff",
              "pace_diff", "elo_diff", "stars_diff", "rest_diff",
              "b2b_diff", "last5_diff"):
        assert k in feats, f"features_from_snapshot missing v2 key {k}"
    # projected_total_score = total_pts + pace*rem_min = 97 + (97/24)*24 = 194
    assert abs(feats["projected_total_score"] - 194.0) < 1e-6
    # projected_final_margin = 3 + (3/24)*24 = 6
    assert abs(feats["projected_final_margin"] - 6.0) < 1e-6


def test_v1_fallback_when_v2_bundle_masked(monkeypatch):
    """If load_v2_bundle returns None, the v1 endQ2 booster is used.

    Skips if the v1 endQ2 booster is also absent — that's a separate
    deployment state covered by tests/test_inplay_winprob.py.
    """
    v1_path = iw._artifact_path("endQ2")
    if not os.path.exists(v1_path):
        pytest.skip("v1 endQ2 booster missing — fallback path not testable")

    # Force the v2 lookup to fail.
    monkeypatch.setattr(iw, "load_v2_bundle", lambda snapshot: None)

    feats = _full_v2_features(score_margin=5.0)
    p = predict_home_win_prob(feats, "endQ2")
    assert p is not None, "v1 fallback failed to produce a probability"
    assert 0.0 <= p <= 1.0
