"""tests.governance.test_pkl_integrity -- pkl_integrity gate tests.

Verifies:
  1. register_model happy path: appends a valid record to the registry.
  2. n_features_in mismatch vs feature_catalog_n BLOCKS registration (IntegrityError).
  3. integrity_check against a matching meta passes (ok=True).
  4. integrity_check against a mismatching meta BLOCKS (ok=False, reason listed).
  5. Unregistered model_id -> ok=False.
  6. Offline pkl (path absent) -> structural_skip=True, ok depends only on meta match.
  7. A real (tmp) pkl with matching n_features_in_ -> ok=True.
  8. A real (tmp) pkl with wrong n_features_in_ -> ok=False (BLOCKED).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/governance/test_pkl_integrity.py -q
"""
from __future__ import annotations

import pathlib
import pickle
import types

import pytest

from governance.pkl_integrity import (
    MODEL_REGISTRY_PATH,
    REGISTRY_VERSION,
    IntegrityError,
    register_model,
    integrity_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reg(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "model_registry.jsonl"


def _make_fake_pkl(path: pathlib.Path, n_features_in: int) -> None:
    """Write a minimal pickle that has an n_features_in_ attribute."""
    obj = types.SimpleNamespace(n_features_in_=n_features_in)
    with path.open("wb") as fh:
        pickle.dump(obj, fh)


# ---------------------------------------------------------------------------
# Test 1: register_model happy path
# ---------------------------------------------------------------------------

def test_register_model_happy_path(tmp_path):
    reg = _reg(tmp_path)
    meta = {
        "model_id": "nba_winprob_v1",
        "kind": "nba_winprob",
        "n_features_in": 17,
    }
    record = register_model(meta, registry_path=reg)
    assert record["model_id"] == "nba_winprob_v1"
    assert record["n_features_in"] == 17
    assert record["registry_version"] == REGISTRY_VERSION
    assert reg.exists()
    # Registry must have one line.
    lines = [l for l in reg.read_text("utf-8").splitlines() if l.strip()]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# Test 2: feature_catalog_n mismatch BLOCKS registration
# ---------------------------------------------------------------------------

def test_register_model_catalog_mismatch_blocked(tmp_path):
    reg = _reg(tmp_path)
    meta = {
        "model_id": "nba_pts_v1",
        "kind": "nba_pts",
        "n_features_in": 20,
        "feature_catalog_n": 19,  # mismatch -> BLOCKED
    }
    with pytest.raises(IntegrityError, match="BLOCKED"):
        register_model(meta, registry_path=reg)
    # Registry file must not have been created / must be empty.
    assert not reg.exists() or reg.stat().st_size == 0


# ---------------------------------------------------------------------------
# Test 3: integrity_check meta match -> ok=True
# ---------------------------------------------------------------------------

def test_integrity_check_meta_match(tmp_path):
    reg = _reg(tmp_path)
    meta = {"model_id": "reb_v2", "kind": "nba_reb", "n_features_in": 12}
    register_model(meta, registry_path=reg)

    result = integrity_check(
        {"model_id": "reb_v2", "n_features_in": 12},
        registry_path=reg,
    )
    assert result["ok"] is True
    assert result["expected_n"] == 12
    assert result["observed_n"] == 12
    assert result["reasons"] == []


# ---------------------------------------------------------------------------
# Test 4: integrity_check meta mismatch -> ok=False + reason listed
# ---------------------------------------------------------------------------

def test_integrity_check_meta_mismatch_blocked(tmp_path):
    reg = _reg(tmp_path)
    meta = {"model_id": "ast_v1", "kind": "nba_ast", "n_features_in": 15}
    register_model(meta, registry_path=reg)

    result = integrity_check(
        {"model_id": "ast_v1", "n_features_in": 9},  # wrong n
        registry_path=reg,
    )
    assert result["ok"] is False
    assert result["expected_n"] == 15
    assert result["observed_n"] == 9
    assert any("MISMATCH" in r or "mismatch" in r.lower() for r in result["reasons"])


# ---------------------------------------------------------------------------
# Test 5: unregistered model_id -> ok=False
# ---------------------------------------------------------------------------

def test_integrity_check_unregistered(tmp_path):
    reg = _reg(tmp_path)
    result = integrity_check(
        {"model_id": "ghost_model", "n_features_in": 5},
        registry_path=reg,
    )
    assert result["ok"] is False
    assert any("not found" in r or "unregistered" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Test 6: offline pkl (path absent) -> structural_skip=True
# ---------------------------------------------------------------------------

def test_integrity_check_offline_pkl(tmp_path):
    reg = _reg(tmp_path)
    meta = {"model_id": "offline_v1", "kind": "nba_blk", "n_features_in": 8}
    register_model(meta, registry_path=reg)

    absent_pkl = tmp_path / "offline_v1.pkl"
    assert not absent_pkl.exists()
    result = integrity_check(absent_pkl, registry_path=reg)
    assert result["structural_skip"] is True
    # No n-mismatch can be proven (pkl absent), but the model_id IS in the
    # registry so no "unregistered" error either.  ok=True (gap logged only).
    assert result["ok"] is True
    assert result["observed_n"] is None


# ---------------------------------------------------------------------------
# Test 7: real pkl with MATCHING n_features_in_ -> ok=True
# ---------------------------------------------------------------------------

def test_integrity_check_real_pkl_match(tmp_path):
    reg = _reg(tmp_path)
    meta = {"model_id": "pts_v3", "kind": "nba_pts", "n_features_in": 22}
    register_model(meta, registry_path=reg)

    pkl_path = tmp_path / "pts_v3.pkl"
    _make_fake_pkl(pkl_path, n_features_in=22)

    result = integrity_check(pkl_path, registry_path=reg)
    assert result["ok"] is True
    assert result["pkl_loaded"] is True
    assert result["observed_n"] == 22
    assert result["expected_n"] == 22
    assert result["structural_skip"] is False
    assert result["reasons"] == []


# ---------------------------------------------------------------------------
# Test 8: real pkl with WRONG n_features_in_ -> ok=False (BLOCKED)
# ---------------------------------------------------------------------------

def test_integrity_check_real_pkl_mismatch_blocked(tmp_path):
    reg = _reg(tmp_path)
    meta = {"model_id": "reb_v3", "kind": "nba_reb", "n_features_in": 18}
    register_model(meta, registry_path=reg)

    pkl_path = tmp_path / "reb_v3.pkl"
    _make_fake_pkl(pkl_path, n_features_in=14)  # wrong

    result = integrity_check(pkl_path, registry_path=reg)
    assert result["ok"] is False
    assert result["pkl_loaded"] is True
    assert result["observed_n"] == 14
    assert result["expected_n"] == 18
    assert any("MISMATCH" in r or "BLOCKED" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Test 9: most-recent-wins convention (retrain increments expected width)
# ---------------------------------------------------------------------------

def test_most_recent_wins(tmp_path):
    reg = _reg(tmp_path)
    # First registration: n=10.
    register_model(
        {"model_id": "pts_v1", "kind": "nba_pts", "n_features_in": 10},
        registry_path=reg,
    )
    # Retrain: n=14 (added features).
    register_model(
        {"model_id": "pts_v1", "kind": "nba_pts", "n_features_in": 14},
        registry_path=reg,
    )
    # Integrity check with n=14 must pass.
    result = integrity_check(
        {"model_id": "pts_v1", "n_features_in": 14},
        registry_path=reg,
    )
    assert result["ok"] is True
    assert result["expected_n"] == 14
    # Integrity check with old n=10 must fail.
    result_old = integrity_check(
        {"model_id": "pts_v1", "n_features_in": 10},
        registry_path=reg,
    )
    assert result_old["ok"] is False


# ---------------------------------------------------------------------------
# Test 10: MODEL_REGISTRY_PATH is the canonical path constant
# ---------------------------------------------------------------------------

def test_registry_path_constant():
    assert isinstance(MODEL_REGISTRY_PATH, pathlib.Path)
    # Must be under data/frontend/governance/ (local-only, gitignored).
    parts = MODEL_REGISTRY_PATH.parts
    assert "data" in parts
    assert "frontend" in parts
    assert "governance" in parts
    assert MODEL_REGISTRY_PATH.name == "model_registry.jsonl"
