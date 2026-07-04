"""Per-file tests for verdict_claims_validator (claim_kind=verdict sibling).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_verdict_claims_validator.py -q

Acceptance criteria:
  1. A well-formed verdict claim citing a real verdict JSON on disk with
     correct field_paths -> VERIFIED.
  2. A claimed verdict/primary_number/planted_null_passed that disagrees
     with the cited file -> MISMATCH with first_divergence populated.
  3. verdict_file missing on disk -> UNVERIFIABLE (fail-closed).
  4. field_paths path that does not resolve in the verdict JSON ->
     UNVERIFIABLE (fail-closed), never silently VERIFIED.
  5. edge_claimed != false -> UNVERIFIABLE (hard rail, never validated).
  6. missing required claim field -> UNVERIFIABLE.
  7. this module never imports a gate module (no gate-package import at
     all beyond stdlib/json) -- a structural guard on the intent.
"""
from __future__ import annotations

import json

from scripts.platformkit.intel_validation import verdict_claims_validator as vcv


def _base_verdict_payload() -> dict:
    return {
        "verdict": "REJECT",
        "pooled_delta": 0.00045,
        "planted_null_dies": True,
        "nested": {"deep": {"value": 1.5}},
    }


def _base_claim(verdict_path) -> dict:
    return {
        "claim_id": "fixture_verdict_claim",
        "kind": "verdict",
        "gate_module": "fixture gate",
        "verdict_file": str(verdict_path),
        "verdict": "REJECT",
        "primary_number": 0.00045,
        "corpus_ids": ["fixture_corpus"],
        "planted_null_passed": True,
        "edge_claimed": False,
        "field_paths": {
            "verdict": "verdict",
            "primary_number": "pooled_delta",
            "planted_null_passed": "planted_null_dies",
        },
        "computed_at": "2026-07-04T00:00:00+00:00",
        "caveats": ["fixture caveat"],
    }


def _write_verdict_file(tmp_path, payload) -> str:
    path = tmp_path / "fixture_verdict.json"
    path.write_text(json.dumps(payload), encoding="ascii")
    return str(path)


def test_wellformed_claim_verifies_against_real_file(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "VERIFIED"


def test_mismatched_primary_number_is_mismatch(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["primary_number"] = 0.999  # disagrees with cited file's 0.00045
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "MISMATCH"
    assert result.first_divergence["field"] == "primary_number"


def test_mismatched_verdict_string_is_mismatch(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["verdict"] = "SHIP"  # cited file says REJECT
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "MISMATCH"


def test_mismatched_planted_null_passed_is_mismatch(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["planted_null_passed"] = False  # cited file says True
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "MISMATCH"
    assert result.first_divergence["field"] == "planted_null_passed"


def test_missing_verdict_file_is_unverifiable(tmp_path):
    claim = _base_claim(str(tmp_path / "does_not_exist.json"))
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "UNVERIFIABLE"
    assert "not found" in result.reason


def test_unresolvable_field_path_is_unverifiable(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["field_paths"]["primary_number"] = "does.not.exist"
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "UNVERIFIABLE"
    assert "not resolvable" in result.reason


def test_nested_field_path_resolves(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["field_paths"]["primary_number"] = "nested.deep.value"
    claim["primary_number"] = 1.5
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "VERIFIED"


def test_edge_claimed_true_is_unverifiable(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["edge_claimed"] = True
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "UNVERIFIABLE"
    assert "edge_claimed" in result.reason


def test_missing_required_field_is_unverifiable(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    del claim["corpus_ids"]
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "UNVERIFIABLE"
    assert "missing required field" in result.reason


def test_missing_field_paths_dict_is_unverifiable(tmp_path):
    verdict_path = _write_verdict_file(tmp_path, _base_verdict_payload())
    claim = _base_claim(verdict_path)
    claim["field_paths"] = {}
    result = vcv.validate_verdict_claim(claim)
    assert result.verdict == "UNVERIFIABLE"


def test_module_never_imports_a_gate_package():
    """Structural guard: this validator must re-read artifacts, never
    execute gate code. Its import list should contain no scripts.platformkit
    package other than itself (i.e. no gate/composition/ingame import)."""
    import inspect
    src = inspect.getsource(vcv)
    forbidden_substrings = [
        "scripts.platformkit.composition",
        "scripts.platformkit.ingame",
        "scripts.platformkit.eval_gate",
    ]
    for forbidden in forbidden_substrings:
        assert forbidden not in src


def test_real_three_verdicts_validate_end_to_end():
    """Live proof: every real on-disk verdict file this lane targets is
    VERIFIED via the checked-in proof claims JSONL (wave-26: 3 seed claims;
    wave-33 extended to 6 -- see lane claims-breadth: mlb sp_velo_fatigue,
    nba positional_weight, tennis surface_hold_gate_verdict_domains added)."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    claims_path = repo_root / "data" / "cache" / "intel_claims" / "gate_verdict_claims.jsonl"
    if not claims_path.exists():
        import pytest
        pytest.skip("proof claims artifact not present in this checkout")
    summary = vcv.validate_verdict_claims_file(claims_path)
    assert summary.n_claims == 6
    assert summary.n_verified == 6
    assert summary.n_mismatch == 0
    assert summary.n_unverifiable == 0
