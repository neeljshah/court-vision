"""tests.governance.test_run_governance -- the single governance aggregator.

An all-clean set of artifacts -> ok=True, exit 0. A poisoned artifact (a
retracted number, a $edge key, a leak, or a parity divergence) -> ok=False,
exit 1, with the FAILING gate named in the verdict. The risk register renders and
every mitigation is owned by a gate. Run ONLY this file (a full pytest run freezes
the box):

    python -m pytest tests/governance/test_run_governance.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance import run_governance as RG
from governance import risk_register as RR
from governance import number_provenance as PROV
from governance.policy import Provenance


def _empty_ledger(tmp_path: Path) -> Path:
    """An absent ledger path -> load_rows returns [] (clean concurrency gate)."""
    return tmp_path / "no_such_ledger.jsonl"


def _empty_registry(tmp_path: Path) -> Path:
    return tmp_path / "no_such_registry.jsonl"


def _clean_kwargs(tmp_path: Path) -> dict:
    """Inject only clean, honest artifacts; load_disk off so on-disk state never
    bleeds into the test. Empty ledger/registry => those gates have nothing to
    flag and are clean."""
    return dict(
        load_disk=False,
        envelope={"sport": "nba", "win_prob": 0.55,
                  "note": "calibrated predictor; matches the devigged close"},
        scoreboard={"clv_mean": 0.2, "n_settled": 120},
        ledger_path=_empty_ledger(tmp_path),
        registry_path=_empty_registry(tmp_path),
    )


# --------------------------------------------------------------------------- #
# all-clean -> ok=True, exit 0                                                 #
# --------------------------------------------------------------------------- #
def test_all_clean_passes(tmp_path):
    res = RG.run_all(**_clean_kwargs(tmp_path))
    assert res["ok"] is True
    assert res["exit_code"] == 0
    gr = res["gate_results"]
    for gate in ("honesty_linter", "provenance", "concurrency",
                 "pkl_integrity", "leak_audit", "parity"):
        assert gr[gate]["ok"] is True, (gate, gr[gate])
    # Real-money is REPORTED and default-DENY, but does NOT gate ok-ness.
    assert gr["realmoney_authorized"]["authorized"] is False
    assert gr["realmoney_authorized"]["authorizes_bet"] is False
    assert res["ok"] is True


def test_clean_with_honest_provenance_and_parity(tmp_path):
    kw = _clean_kwargs(tmp_path)
    kw["envelope"] = {
        "model_wp": PROV.tag(0.55, Provenance.REAL_MODEL),
        "close_wp": PROV.tag(0.53, Provenance.CAPTURED_MARKET),
    }
    kw["parity_candidates"] = [({"a": 1.0, "b": 2.0}, {"a": 1.0, "b": 2.0})]
    res = RG.run_all(**kw)
    assert res["ok"] is True
    assert res["exit_code"] == 0


# --------------------------------------------------------------------------- #
# poisoned artifact -> ok=False, exit 1, failing gate named                    #
# --------------------------------------------------------------------------- #
def test_banned_number_blocks(tmp_path):
    kw = _clean_kwargs(tmp_path)
    # A retracted ROI printed as a live result, no retraction framing.
    kw["envelope"] = {"headline": "pregame ROI +18.38% this season"}
    res = RG.run_all(**kw)
    assert res["ok"] is False
    assert res["exit_code"] == 1
    assert res["gate_results"]["honesty_linter"]["ok"] is False
    kinds = {v["kind"]
             for v in res["gate_results"]["honesty_linter"]["violations"]}
    assert "banned_number" in kinds


def test_retracted_number_in_context_passes(tmp_path):
    kw = _clean_kwargs(tmp_path)
    # Same number, but inside explicit retraction framing -> permitted.
    kw["envelope"] = {"note": "RETRACTED artifact: the old +18.38% pregame ROI "
                              "was a market-follow artifact, never claim it."}
    res = RG.run_all(**kw)
    assert res["gate_results"]["honesty_linter"]["ok"] is True
    assert res["ok"] is True


def test_dollar_edge_key_blocks(tmp_path):
    kw = _clean_kwargs(tmp_path)
    kw["scoreboard"] = {"$edge": 12.3, "n": 100}
    res = RG.run_all(**kw)
    assert res["ok"] is False
    assert res["exit_code"] == 1
    kinds = {v["kind"]
             for v in res["gate_results"]["honesty_linter"]["violations"]}
    assert "banned_key" in kinds


def test_filled_presented_as_real_blocks(tmp_path):
    kw = _clean_kwargs(tmp_path)
    # A FILLED number not flagged -> provenance gate BLOCKS.
    kw["envelope"] = {"q4_pace": {"value": 99.4, "provenance": "FILLED"}}
    res = RG.run_all(**kw)
    assert res["ok"] is False
    assert res["exit_code"] == 1
    assert res["gate_results"]["provenance"]["ok"] is False


def test_parity_divergence_blocks(tmp_path):
    kw = _clean_kwargs(tmp_path)
    # rest reads 0.0 at inference -> silent-zero wiring bug -> BLOCKS.
    kw["parity_candidates"] = [({"home_edge": 1.5, "rest": 2.0},
                                {"home_edge": 1.5, "rest": 0.0})]
    res = RG.run_all(**kw)
    assert res["ok"] is False
    assert res["exit_code"] == 1
    assert res["gate_results"]["parity"]["ok"] is False
    assert res["gate_results"]["parity"]["failures"]


def test_leak_blocks(tmp_path):
    kw = _clean_kwargs(tmp_path)
    # A future-dated feature (availability >= state_ts) is a leak.
    kw["build"] = [{
        "game_id": "G1", "state_ts": "2026-01-01T00:00:00",
        "features": {"x": 1.0},
        "feature_avail": {"x": "2026-02-01T00:00:00"},  # AFTER state_ts -> leak
    }]
    # Skip the golden schema validator (needs ~100 states); the vintage guard is
    # what catches this single future-dated feature.
    kw["leak_kwargs"] = {"validate_schema": False}
    res = RG.run_all(**kw)
    assert res["ok"] is False
    assert res["exit_code"] == 1
    assert res["gate_results"]["leak_audit"]["ok"] is False
    kinds = {f["kind"]
             for f in res["gate_results"]["leak_audit"]["findings"]}
    assert "future_dated_feature" in kinds


# --------------------------------------------------------------------------- #
# risk register renders + every mitigation owned by a gate                     #
# --------------------------------------------------------------------------- #
def test_risk_register_renders(tmp_path):
    res = RG.run_all(**_clean_kwargs(tmp_path))
    reg = res["risk_register"]
    assert reg["version"] == RR.RISK_REGISTER_VERSION
    assert reg["n_risks"] == len(RR.RISKS)
    assert reg["n_risks"] >= 7  # drift / proxy-CLV / concurrency / fill / leak ...
    assert isinstance(reg["text"], str) and reg["text"]
    # Every risk's owning_gate is a real governance gate name surfaced in results.
    valid_gates = set(res["gate_results"].keys())
    for risk in RR.RISKS:
        assert risk.owning_gate in valid_gates, risk.owning_gate


def test_render_lists_known_risk_ids():
    reg = RR.render()
    ids = {r["id"] for r in reg["risks"]}
    for expected in ("percentile_fill_defeats_signals", "proxy_clv_inflates_eligibility",
                     "concurrent_ledger_writes", "train_inference_parity_break",
                     "secret_leakage", "leak_or_scale_guard_gap"):
        assert expected in ids


# --------------------------------------------------------------------------- #
# CLI main() exit-code semantics                                               #
# --------------------------------------------------------------------------- #
def test_main_exits_zero_when_disk_clean(monkeypatch, tmp_path, capsys):
    # Force disk artifacts absent so the on-disk preflight is clean.
    monkeypatch.setattr(RG, "_DEFAULT_ENVELOPE", tmp_path / "no_env.json")
    monkeypatch.setattr(RG, "_DEFAULT_SCOREBOARD", tmp_path / "no_score.json")
    rc = RG.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "GOVERNANCE PREFLIGHT" in out
    assert "VERDICT: OK" in out


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
