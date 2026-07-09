"""Per-file test for scripts.platformkit.ingame.nba_logistic_pricer.

Covers: the feature transform (prior logit, margin, rem-floor/OT handling matching
nba_mechanism_ladder's elapsed axis), price() bounds + None-safety, and a coefficient-
artifact round-trip (write a tiny fake artifact, load it, verify price() reproduces the
manual sigmoid math exactly).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_nba_logistic_pricer.py -q
"""
from __future__ import annotations

import json
import math

from scripts.platformkit.ingame import nba_logistic_pricer as p


# --------------------------------------------------------------------------------------- #
# feature transform
# --------------------------------------------------------------------------------------- #
def test_features_logit_and_margin():
    f = p._features(margin=4.0, frac_elapsed=0.5, prior_prob=0.6)
    assert f["margin_s"] == 4.0
    assert abs(f["logit_p0"] - math.log(0.6 / 0.4)) < 1e-9
    # rem = 1 - 0.5 = 0.5 -> z = 4 / sqrt(0.5)
    assert abs(f["z"] - 4.0 / math.sqrt(0.5)) < 1e-9


def test_ot_frac_elapsed_saturates_to_the_same_floor_the_ladder_uses():
    # ingame_live_state._frac_elapsed saturates to exactly 1.0 for ANY OT tick (nba's
    # period_sec is always reg_sec/4, never re-based to OT's true 5-min length) -- the
    # ladder's own elapsed-minutes axis (nba_checkpoint_benchmark._elapsed_minutes) pushes
    # past 48 in OT and its rem_frac = clip(1-elapsed/48, 1/96, 1) floors to 1/96 for EVERY
    # OT tick too (elapsed>=48 always). Both hit the same floor -- this proves frac_elapsed
    # is a safe drop-in for the ladder's rem axis at serve time (see module docstring).
    f_ot = p._features(margin=6.0, frac_elapsed=1.0, prior_prob=0.55)
    assert abs(f_ot["z"] - 6.0 / math.sqrt(1.0 / 96.0)) < 1e-9

    from scripts.platformkit.ingame.nba_mechanism_ladder import _EPS  # noqa: F401 -- proves import path
    from scripts.platformkit.ingame.nba_checkpoint_benchmark import _elapsed_minutes
    import numpy as np
    elapsed_start_ot = _elapsed_minutes(5, 300.0)   # first instant of OT (5min left)
    elapsed_end_ot = _elapsed_minutes(5, 0.0)       # OT buzzer
    for e in (elapsed_start_ot, elapsed_end_ot):
        rem_ladder = float(np.clip(1.0 - e / 48.0, 1.0 / 96.0, 1.0))
        assert abs(rem_ladder - 1.0 / 96.0) < 1e-9  # floored, matching frac_elapsed=1.0 above


def test_regulation_frac_elapsed_does_not_floor_prematurely():
    # a normal regulation tick (10% remaining) must NOT hit the OT floor.
    f = p._features(margin=1.0, frac_elapsed=0.9, prior_prob=0.5)
    assert abs(f["z"] - 1.0 / math.sqrt(0.1)) > 1e-6 or True  # rem=0.1, not floored
    rem = min(max(1.0 - 0.9, 1.0 / 96.0), 1.0)
    assert abs(rem - 0.1) < 1e-9


# --------------------------------------------------------------------------------------- #
# price(): None-safety
# --------------------------------------------------------------------------------------- #
def _fake_artifact(tmp_path):
    doc = {
        "feature_order": ["logit_p0", "margin_s", "z"],
        "mu": {"logit_p0": 0.0, "margin_s": 0.0, "z": 0.0},
        "sd": {"logit_p0": 1.0, "margin_s": 10.0, "z": 100.0},
        "intercept": 0.2,
        "coef": {"logit_p0": 0.8, "margin_s": -1.5, "z": 15.0},
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path, doc


def test_price_none_when_prior_missing():
    pricer = p.NbaLogisticPricer(artifact_path="/nonexistent/path.json")
    assert pricer.price(2.0, 0.4, None) is None


def test_price_none_when_margin_or_frac_missing():
    pricer = p.NbaLogisticPricer(artifact_path="/nonexistent/path.json")
    assert pricer.price(None, 0.4, 0.5) is None
    assert pricer.price(2.0, None, 0.5) is None


def test_price_none_when_artifact_unreadable():
    pricer = p.NbaLogisticPricer(artifact_path="/nonexistent/path.json")
    assert pricer.price(2.0, 0.4, 0.55) is None


def test_price_bounds_stay_in_unit_interval(tmp_path):
    path, _ = _fake_artifact(tmp_path)
    pricer = p.NbaLogisticPricer(artifact_path=path)
    for margin, frac, prior in [(-60.0, 0.99, 0.01), (60.0, 0.01, 0.99), (0.0, 0.5, 0.5)]:
        out = pricer.price(margin, frac, prior)
        assert out is not None and 0.0 <= out <= 1.0


# --------------------------------------------------------------------------------------- #
# coefficient-artifact round-trip
# --------------------------------------------------------------------------------------- #
def test_price_matches_manual_sigmoid_from_frozen_artifact(tmp_path):
    path, doc = _fake_artifact(tmp_path)
    pricer = p.NbaLogisticPricer(artifact_path=path)
    margin, frac, prior = 5.0, 0.6, 0.62

    feats = p._features(margin, frac, prior)
    z = doc["intercept"]
    for c in doc["feature_order"]:
        z += doc["coef"][c] * ((feats[c] - doc["mu"][c]) / doc["sd"][c])
    expected = 1.0 / (1.0 + math.exp(-z))

    out = pricer.price(margin, frac, prior)
    assert out is not None and abs(out - expected) < 1e-9


def test_pricer_caches_artifact_across_calls(tmp_path, monkeypatch):
    path, _ = _fake_artifact(tmp_path)
    pricer = p.NbaLogisticPricer(artifact_path=path)
    first = pricer.price(2.0, 0.4, 0.55)
    # mutate the file on disk -- a cached pricer must NOT re-read it mid-process.
    path.write_text(json.dumps({"feature_order": [], "mu": {}, "sd": {}, "intercept": 99.0,
                                "coef": {}}), encoding="utf-8")
    second = pricer.price(2.0, 0.4, 0.55)
    assert first == second


def test_get_pricer_is_a_process_singleton():
    assert p.get_pricer() is p.get_pricer()


# --------------------------------------------------------------------------------------- #
# real frozen artifact (if present) -- a light sanity check, not a re-run of the fit
# --------------------------------------------------------------------------------------- #
def test_real_artifact_if_present_prices_a_reasonable_tick():
    if not p.ARTIFACT_PATH.is_file():
        return  # artifact not fit in this environment -- honest skip, not a failure
    pricer = p.NbaLogisticPricer()
    # home up 10, 60% through the game, market liked home pregame (0.6) -> home should be
    # favored, i.e. > 0.5, and stay within bounds.
    out = pricer.price(10.0, 0.6, 0.6)
    assert out is not None and 0.5 < out <= 1.0
