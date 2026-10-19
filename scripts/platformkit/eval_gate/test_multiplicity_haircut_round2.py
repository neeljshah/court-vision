"""S675 round-two regression constructs."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.platformkit.eval_gate import multiplicity_haircut as mh


def test_uneven_clusters_constant_input_never_better_and_stays_in_k():
    arm = {"name": "flat", "diffs": [0.1] * 6,
           "game_ids": ["a", "b", "b", "c", "c", "c"]}
    report = mh.haircut([arm], n_bootstrap=99, seed=4)
    assert report["family"]["k_evaluable"] == 1
    assert report["arms"][0]["n_games"] == 3
    assert report["arms"][0]["raw_p"] == 1.0
    assert report["arms"][0]["holm_p"] == 1.0
    assert report["arms"][0]["label"] == mh.NOT_SEPARATED


@pytest.mark.parametrize("field", ["ratio", "sd_trials", "skew", "kurtosis"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "0.2"],
                         ids=["nan", "inf", "negative-inf", "boolean", "string"])
def test_deflate_refuses_nonfinite_or_nonnumeric_parameters(field, value):
    args = dict(ratio=0.2, n_obs=101, k=10, sd_trials=0.05)
    args[field] = value
    result = mh.deflate("sharpe_like", **args)
    assert result["status"] == mh.NOT_EVALUABLE
    assert "deflated_p" not in result


@pytest.mark.parametrize("field", ["n_obs", "k"])
@pytest.mark.parametrize("value", [True, False, 101.5], ids=["true", "false", "fractional"])
def test_deflate_refuses_noninteger_or_boolean_counts(field, value):
    args = dict(ratio=0.2, n_obs=101, k=10, sd_trials=0.05)
    args[field] = value
    assert mh.deflate("sharpe_like", **args)["status"] == mh.NOT_EVALUABLE


@pytest.mark.parametrize("field,value", [("k", 0), ("k", -1), ("n_obs", 1),
                                        ("sd_trials", -0.05)])
def test_deflate_refuses_out_of_range_parameters(field, value):
    args = dict(ratio=0.2, n_obs=101, k=10, sd_trials=0.05)
    args[field] = value
    assert mh.deflate("sharpe_like", **args)["status"] == mh.NOT_EVALUABLE


def test_deflate_accepts_minimum_counts_and_zero_trial_sd():
    result = mh.deflate("sharpe_like", ratio=0.2, n_obs=2, k=1, sd_trials=0.0)
    assert result["status"] == "DEFLATED" and result["k"] == 1
    assert result["benchmark_ratio"] == 0.0
    assert 0.0 < result["deflated_p"] < 1.0


@pytest.mark.parametrize("rw_p,spa_p,label", [(0.10, 0.01, mh.NOT_SEPARATED),
                                            (0.01, 0.10, mh.NOT_SEPARATED),
                                            (0.01, 0.01, mh.BETTER)],
                         ids=["rw-refuses", "spa-refuses", "both-pass"])
def test_label_requires_each_family_component(monkeypatch, rw_p, spa_p, label):
    arm = {"name": "positive", "diffs": [0.8, 0.9, 1.0, 1.1, 1.2],
           "game_ids": ["a", "b", "c", "d", "e"]}
    monkeypatch.setattr(mh, "romano_wolf_stepdown",
                        lambda *args, **kwargs: SimpleNamespace(adjusted_p=[rw_p]))
    monkeypatch.setattr(mh, "hansen_spa",
                        lambda *args, **kwargs: SimpleNamespace(family_p=spa_p))
    report = mh.haircut([arm], n_bootstrap=99, seed=4)
    row = report["arms"][0]
    assert row["holm_p"] < report["family"]["alpha"]
    assert row["romano_wolf_p"] == rw_p
    assert report["family"]["spa_family_p"] == spa_p
    assert row["label"] == label


def test_s675_spec_uses_required_q6_wording():
    spec = Path(__file__).resolve().parents[3] / "docs/evidence/harness/S675_spec_2026-09-30.md"
    assert "Q6-compliant wording." in spec.read_text(encoding="ascii")
