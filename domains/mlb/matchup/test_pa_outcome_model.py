"""Per-file tests for pa_outcome_model. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_pa_outcome_model.py -q -m ""

NOTE: the real-corpus ladder test loads both full 2022+2023 statcast files
and fits 4 logistic-regression layers (~1-2 min) -- this is the one
deliberately slow test in this lane; run it explicitly when validating the
model, skip via `-k "not real_corpus"` for a fast per-file loop.

Acceptance criteria:
  1. Every statcast `events` value seen in the corpus buckets to exactly one
     of the 5 PA_BUCKETS or is intentionally dropped (catcher_interf,
     truncated_pa) -- no event silently falls through NaN.
  2. build_features's expected_k_interaction is literally the dot product of
     pitcher pitch-mix usage and batter per-pitch-type k_rate on a tiny
     fixture (hand-computed).
  3. fit_eval_layer's zero-feature path reproduces the plain train-marginal
     log_loss.
  4. Real on-disk corpus: the full ladder runs end-to-end, every layer's
     log_loss is finite, and results are written faithfully (no NaN deltas).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from domains.mlb.matchup import pa_outcome_model as m


def test_bucket_map_covers_every_real_event_or_intentionally_drops_it():
    known_events = {
        "field_out", "strikeout", "single", "walk", "double", "home_run",
        "force_out", "grounded_into_double_play", "hit_by_pitch", "sac_fly",
        "field_error", "triple", "intent_walk", "double_play", "sac_bunt",
        "fielders_choice", "truncated_pa", "fielders_choice_out",
        "strikeout_double_play", "catcher_interf",
    }
    intentionally_dropped = {"truncated_pa", "catcher_interf"}
    for e in known_events - intentionally_dropped:
        assert e in m._BUCKET_MAP, f"{e} not bucketed"
        assert m._BUCKET_MAP[e] in m.BUCKETS
    for e in intentionally_dropped:
        assert e not in m._BUCKET_MAP


def test_expected_k_interaction_is_the_dot_product():
    pa = pd.DataFrame({
        "pitcher": [1], "batter": [10], "bucket": ["K"],
        "stand": ["R"], "p_throws": ["R"], "outs_when_up": [1],
        "bat_score": [0], "home_score": [0], "away_score": [0],
    })
    pitcher_profile = pd.DataFrame({
        "pitcher": [1, 1], "season": [2022, 2022], "pitch_type": ["FF", "SL"],
        "usage_share": [0.6, 0.4], "n_pitches": [60, 40], "n_k": [5, 8],
        "in_zone_rate": [0.5, 0.4],
    })
    batter_profile = pd.DataFrame({
        "batter": [10, 10], "season": [2022, 2022], "pitch_type": ["FF", "SL"],
        "n_pa": [20, 10], "k_rate": [0.2, 0.5], "slug_proxy": [0.4, 0.3],
        "bb_rate": [0.1, 0.05],
    })
    feats = m.build_features(pa, pitcher_profile, batter_profile)
    # expected_k_interaction = 0.6*0.2 (FF) + 0.4*0.5 (SL) = 0.32
    assert abs(feats["expected_k_interaction"].iloc[0] - 0.32) < 1e-9


def test_fit_eval_layer_empty_features_matches_marginal_log_loss():
    train_df = pd.DataFrame({"bucket": ["K", "K", "BB", "IN_PLAY_OUT"]})
    test_df = pd.DataFrame({"bucket": ["K", "IN_PLAY_OUT"]})
    ll = m.fit_eval_layer(train_df, test_df, [])
    rates = train_df["bucket"].value_counts(normalize=True).reindex(m.BUCKETS).fillna(1e-6)
    expected = log_loss(test_df["bucket"], np.tile(rates.to_numpy(), (2, 1)), labels=m.BUCKETS)
    assert abs(ll - expected) < 1e-9


def test_real_corpus_ladder_runs_and_produces_finite_deltas():
    """Slow (~1-2 min): fits all 4 layers on the real 2022/2023 corpus.
    Deliberately not gated behind a marker per repo test-discipline (no
    pytest.ini marker registry checked) -- run explicitly, see module note."""
    report = m.run_ladder()
    assert report["n_train"] > 0 and report["n_test"] > 0
    for name, r in report["layers"].items():
        assert np.isfinite(r["log_loss"]), f"{name} log_loss not finite"
        assert np.isfinite(r["delta_vs_league"]), f"{name} delta not finite"
    assert report["layers"]["league_rate"]["delta_vs_league"] == 0.0
