"""Tests for champion_challenger.py — champion/challenger state management."""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest

import src.prediction.champion_challenger as cc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_cc_path(tmp_path: str):
    """Return a context manager that redirects _CC_PATH to a temp file."""
    tmp_json = os.path.join(tmp_path, "champion_challenger.json")
    return mock.patch.object(cc, "_CC_PATH", tmp_json)


def _patch_models_dir(tmp_path: str):
    """Also redirect _MODELS_DIR so makedirs works inside the patched context."""
    return mock.patch.object(cc, "_MODELS_DIR", tmp_path)


# ---------------------------------------------------------------------------
# Test 1: record_evaluation increments bets_evaluated
# ---------------------------------------------------------------------------

def test_record_evaluation_increments_bets(tmp_path):
    tmp = str(tmp_path)
    with _patch_cc_path(tmp), _patch_models_dir(tmp):
        cc.record_evaluation("pts", champion_pred=25.0, challenger_pred=None, actual=24.0)
        state = cc._load_state()
        assert state["stats"]["pts"]["bets_evaluated"] == 1


# ---------------------------------------------------------------------------
# Test 2: _compute_r2 returns 1.0 for perfect predictions
# ---------------------------------------------------------------------------

def test_compute_r2_correct():
    result = cc._compute_r2([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert result == 1.0


# ---------------------------------------------------------------------------
# Test 3: check_and_promote returns False with insufficient data
# ---------------------------------------------------------------------------

def test_check_and_promote_insufficient_data(tmp_path):
    tmp = str(tmp_path)
    with _patch_cc_path(tmp), _patch_models_dir(tmp):
        # Record only 5 evaluations — well below _MIN_BETS_PROMOTE (100)
        for i in range(5):
            cc.record_evaluation("reb", champion_pred=float(i), challenger_pred=float(i) - 0.1, actual=float(i))
        result = cc.check_and_promote("reb")
        assert result is False


# ---------------------------------------------------------------------------
# Test 4: check_and_promote returns False when challenger R² < champion R²
# ---------------------------------------------------------------------------

def test_check_and_promote_challenger_worse(tmp_path):
    tmp = str(tmp_path)
    with _patch_cc_path(tmp), _patch_models_dir(tmp):
        # Build state directly: champion is perfect, challenger is noisy
        actuals = [float(i) for i in range(110)]
        champ_preds = actuals[:]                          # perfect
        chall_preds = [a + 5.0 for a in actuals]          # bad

        state = cc._load_state()
        s = state["stats"].setdefault("ast", {
            "champion_r2": None, "challenger_r2": None,
            "challenger_model_path": None, "bets_evaluated": 0,
            "champion_predictions": [], "challenger_predictions": [],
            "actuals": [], "last_promotion": None,
        })
        s["champion_predictions"] = champ_preds
        s["challenger_predictions"] = chall_preds
        s["actuals"] = actuals
        s["bets_evaluated"] = 110
        s["champion_r2"] = cc._compute_r2(champ_preds, actuals)  # 1.0
        s["challenger_r2"] = cc._compute_r2(chall_preds, actuals)  # < 1.0
        cc._save_state(state)

        result = cc.check_and_promote("ast")
        assert result is False


# ---------------------------------------------------------------------------
# Test 5: check_and_promote returns True when challenger is perfect (100+ bets)
# ---------------------------------------------------------------------------

def test_check_and_promote_challenger_better(tmp_path):
    tmp = str(tmp_path)
    with _patch_cc_path(tmp), _patch_models_dir(tmp):
        # Champion is noisy; challenger is perfect
        actuals = [float(i) for i in range(110)]
        champ_preds = [a + 3.0 for a in actuals]  # noisy champion
        chall_preds = actuals[:]                    # perfect challenger

        state = cc._load_state()
        s = state["stats"].setdefault("stl", {
            "champion_r2": None, "challenger_r2": None,
            "challenger_model_path": None, "bets_evaluated": 0,
            "champion_predictions": [], "challenger_predictions": [],
            "actuals": [], "last_promotion": None,
        })
        s["champion_predictions"] = champ_preds
        s["challenger_predictions"] = chall_preds
        s["actuals"] = actuals
        s["bets_evaluated"] = 110
        s["champion_r2"] = cc._compute_r2(champ_preds, actuals)
        s["challenger_r2"] = cc._compute_r2(chall_preds, actuals)  # 1.0
        cc._save_state(state)

        result = cc.check_and_promote("stl")
        assert result is True

        # Verify state was updated correctly
        new_state = cc._load_state()
        ns = new_state["stats"]["stl"]
        assert ns["challenger_predictions"] == []
        assert ns["challenger_r2"] is None
        assert ns["last_promotion"] is not None
