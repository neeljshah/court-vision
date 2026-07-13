"""Tests for scripts.platformkit.omni.native_altitude (P3 contract seam).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_native_altitude.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.omni import native_altitude as na


def _contract(**over):
    c = {
        "signal_name": "star_minutes_load",
        "sport": "nba",
        "native_observable": "minutes_dist",
        "metric": "crps",
        "baseline_model": "elo_v3",
        "market_families": ["props.pts", "mainlines.total"],
        "regime_scope": "clutch",
        "corpus": "discovery_slice_2026_07",
    }
    c.update(over)
    return c


def test_validate_contract_rejects_unknown_observable():
    c = _contract(native_observable="not_a_real_observable")
    with pytest.raises(ValueError):
        na.validate_contract(c)


def test_validate_contract_rejects_missing_field():
    c = _contract()
    del c["baseline_model"]
    with pytest.raises(ValueError):
        na.validate_contract(c)


def test_record_verdicts_writes_family_claims_retrievable(tmp_path):
    contract = _contract()
    verdicts = {
        "props.pts": {"verdict": "ACCEPT", "delta": 0.03, "ci_low": 0.01, "ci_high": 0.05, "n": 400},
        "mainlines.total": {"verdict": "REJECT", "delta": -0.001, "ci_low": -0.01, "ci_high": 0.01, "n": 400},
    }
    claim_ids = na.record_verdicts(contract, verdicts, base_dir=tmp_path)
    assert len(claim_ids) == 2

    summary = na.per_family_summary(contract["signal_name"], sport="nba", base_dir=tmp_path)
    assert summary["props.pts"]["verdict"] == "ACCEPT"
    assert summary["mainlines.total"]["verdict"] == "REJECT"


def test_accept_and_reject_coexist_for_one_signal(tmp_path):
    contract = _contract()
    verdicts = {
        "props.pts": {"verdict": "ACCEPT", "delta": 0.02, "ci_low": 0.0, "ci_high": 0.04, "n": 200},
        "mainlines.total": {"verdict": "REJECT", "delta": 0.0, "ci_low": -0.01, "ci_high": 0.01, "n": 200},
    }
    na.record_verdicts(contract, verdicts, base_dir=tmp_path)
    summary = na.per_family_summary(contract["signal_name"], sport="nba", base_dir=tmp_path)
    assert set(summary) == {"props.pts", "mainlines.total"}
    assert summary["props.pts"]["verdict"] == "ACCEPT"
    assert summary["mainlines.total"]["verdict"] == "REJECT"


def test_record_verdicts_rerun_does_not_duplicate(tmp_path):
    contract = _contract(market_families=["props.pts"])
    verdicts = {"props.pts": {"verdict": "ACCEPT", "delta": 0.03, "ci_low": 0.01, "ci_high": 0.05, "n": 400}}

    ids_1 = na.record_verdicts(contract, verdicts, base_dir=tmp_path)
    ids_2 = na.record_verdicts(contract, verdicts, base_dir=tmp_path)
    assert ids_1 == ids_2

    from scripts.platformkit.omni import claims_ledger as cl
    df = cl.query(sport="nba", base_dir=tmp_path)
    assert len(df) == 1


def test_record_verdicts_rejects_unknown_verdict_string(tmp_path):
    contract = _contract(market_families=["props.pts"])
    verdicts = {"props.pts": {"verdict": "MAYBE", "delta": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 1}}
    with pytest.raises(ValueError):
        na.record_verdicts(contract, verdicts, base_dir=tmp_path)
