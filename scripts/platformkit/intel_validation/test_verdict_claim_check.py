"""Per-file tests for verdict_claim_check -- the gate_verdict/verdict-kind
claim cross-checker. Synthetic verdict files via tmp_path + monkeypatched
repo root; one real-store dispatch test at the end (skips without data)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.intel_validation import verdict_claim_check as vcc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(vcc, "_REPO_ROOT", tmp_path)
    return tmp_path


def _write(repo: Path, rel: str, doc: dict) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc), encoding="ascii")
    return rel


def _claim(**over):
    base = {
        "claim_id": "test_gate", "kind": "gate_verdict",
        "verdict_file": "data/x/verdict.json",
        "verdict": "REJECT", "mean_rho": 0.268, "sign_holds_folds": "0/3",
    }
    base.update(over)
    return base


def test_verified_generic_shared_keys(repo):
    _write(repo, "data/x/verdict.json",
           {"verdict": "REJECT", "mean_rho": 0.267972226, "sign_holds_folds": 0,
            "n_folds": 3, "honest_note": "x"})
    v = vcc.validate_verdict_claim(_claim())
    assert v.verdict == "VERIFIED", v.reason
    # display-rounded 0.268 vs 0.267972 must pass; "0/3" expands to (0, 3)
    assert "fields match" in v.reason


def test_mismatch_on_diverged_verdict(repo):
    _write(repo, "data/x/verdict.json",
           {"verdict": "SHIP", "mean_rho": 0.268, "sign_holds_folds": 0, "n_folds": 3})
    v = vcc.validate_verdict_claim(_claim())
    assert v.verdict == "MISMATCH"
    assert v.first_divergence["field"] == "verdict"


def test_mismatch_on_float_beyond_tolerance(repo):
    _write(repo, "data/x/verdict.json",
           {"verdict": "REJECT", "mean_rho": 0.31, "sign_holds_folds": 0, "n_folds": 3})
    v = vcc.validate_verdict_claim(_claim())
    assert v.verdict == "MISMATCH"


def test_ratio_denominator_checked_against_n_folds(repo):
    _write(repo, "data/x/verdict.json",
           {"verdict": "REJECT", "mean_rho": 0.268, "sign_holds_folds": 0, "n_folds": 4})
    v = vcc.validate_verdict_claim(_claim())  # claim says "0/3", file says 4 folds
    assert v.verdict == "MISMATCH"


def test_verdict_kind_delegates_to_strict_validator(repo, monkeypatch):
    from scripts.platformkit.intel_validation import verdict_claims_validator as vcv
    monkeypatch.setattr(vcv, "REPO_ROOT", repo)
    _write(repo, "data/x/verdict.json",
           {"verdict": "REJECT", "atp": {"real": {"delta": 0.000121}}, "planted_null_dies": True})
    claim = {
        "claim_id": "t", "kind": "verdict", "question": "q", "gate_module": "fixture",
        "verdict_file": "data/x/verdict.json", "verdict": "REJECT",
        "primary_number": 0.000121, "corpus_ids": ["c1"], "planted_null_passed": True,
        "edge_claimed": False,
        "field_paths": {"verdict": "verdict", "primary_number": "atp.real.delta",
                        "planted_null_passed": "planted_null_dies"},
    }
    assert vcc.validate_verdict_claim(claim).verdict == "VERIFIED"
    claim["planted_null_passed"] = False
    assert vcc.validate_verdict_claim(claim).verdict == "MISMATCH"
    # strict contract enforced via delegation: dropping a required field fails closed
    del claim["gate_module"]
    assert vcc.validate_verdict_claim(claim).verdict == "UNVERIFIABLE"


def test_nested_dict_subkeys_compared(repo):
    _write(repo, "data/x/verdict.json",
           {"verdict": "REJECT", "mean_rho": 0.268, "sign_holds_folds": 0, "n_folds": 3,
            "ci": {"lo": -0.2198, "hi": -0.0566}})
    v = vcc.validate_verdict_claim(_claim(ci={"lo": -0.2198, "hi": -0.0566}))
    assert v.verdict == "VERIFIED"
    v = vcc.validate_verdict_claim(_claim(ci={"lo": -0.9, "hi": -0.0566}))
    assert v.verdict == "MISMATCH"


def test_unverifiable_paths(repo):
    assert vcc.validate_verdict_claim(_claim(verdict_file=None)).verdict == "UNVERIFIABLE"
    assert vcc.validate_verdict_claim(_claim()).verdict == "UNVERIFIABLE"  # file absent
    _write(repo, "data/x/verdict.json", {"unrelated": 1})
    assert "no comparable fields" in vcc.validate_verdict_claim(
        {"claim_id": "t", "kind": "gate_verdict", "verdict_file": "data/x/verdict.json"}
    ).reason


def test_validate_claim_dispatches_verdict_kinds(repo, monkeypatch):
    _write(repo, "data/x/verdict.json",
           {"verdict": "REJECT", "mean_rho": 0.268, "sign_holds_folds": 0, "n_folds": 3})
    v = validate_claim(_claim())
    assert v.verdict == "VERIFIED"  # would be UNVERIFIABLE (no formula) without dispatch


def test_real_nba_quality_gate_claim():
    store = Path(__file__).resolve().parents[3] / "data/cache/intel_claims/nba_quality_claims.jsonl"
    if not store.exists():
        pytest.skip("nba_quality_claims store absent on this clone")
    rows = [json.loads(l) for l in store.open(encoding="utf-8")]
    gate = [c for c in rows if c.get("kind") == "gate_verdict"]
    assert gate, "expected the gate-3a claim in the store"
    v = validate_claim(gate[0])
    assert v.verdict == "VERIFIED", f"{v.verdict}: {v.reason}"
