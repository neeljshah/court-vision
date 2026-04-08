"""Smoke tests for stat_reconciler."""
import pytest
from pathlib import Path
from src.fusion.source_registry import SourceValue
from src.fusion.stat_reconciler import StatReconciler


def _nba(v): return SourceValue.from_nba_api(v)
def _prior(v): return SourceValue.as_prior(v)
def _cv(v, c=0.90): return SourceValue.from_cv(v, ocr_conf=c)


def test_winner_higher_tier():
    rec = StatReconciler()
    nba = _nba(25.0)
    prior = _prior(22.0)
    winner = rec.reconcile("pts", [prior, nba])
    assert winner.source == "nba_api"
    assert winner.value == 25.0


def test_winner_higher_confidence_same_tier():
    rec = StatReconciler()
    high = SourceValue.from_nba_api(30.0)
    high.confidence = 0.90
    low  = SourceValue.from_nba_api(28.0)
    low.confidence  = 0.60
    winner = rec.reconcile("pts", [low, high])
    assert winner.value == 30.0


def test_empty_returns_none():
    rec = StatReconciler()
    assert rec.reconcile("pts", []) is None


def test_disagreement_logged(tmp_path):
    err_path = tmp_path / "cv_errors.csv"
    rec = StatReconciler(error_path=err_path, diff_thresh=0.05)
    # Two NBA_OFFICIAL sources disagree by >5%
    sv1 = SourceValue.from_nba_api(30.0)
    sv2 = SourceValue.from_nba_api(20.0)   # 33% apart
    rec.reconcile("pts", [sv1, sv2], game_id="G1", player_game_id="G1_P1")
    n = rec.flush_errors()
    assert n == 1
    assert err_path.exists()
    content = err_path.read_text()
    assert "pts" in content and "nba_api" in content


def test_no_disagreement_small_diff(tmp_path):
    err_path = tmp_path / "cv_errors.csv"
    rec = StatReconciler(error_path=err_path, diff_thresh=0.10)
    sv1 = SourceValue.from_nba_api(25.0)
    sv2 = SourceValue.from_nba_api(25.5)   # 2% apart
    rec.reconcile("pts", [sv1, sv2])
    assert rec.flush_errors() == 0


def test_reconcile_many():
    rec = StatReconciler()
    result = rec.reconcile_many({
        "pts":  [_nba(25.0), _prior(20.0)],
        "reb":  [_prior(8.0)],
        "ast":  [],
    })
    assert result["pts"].value == 25.0
    assert result["reb"].value == 8.0
    assert "ast" not in result


def test_cv_beats_prior():
    rec = StatReconciler()
    winner = rec.reconcile("defender_dist", [_prior(4.5), _cv(3.2, c=0.85)])
    assert winner.source in {"cv_high", "cv_low"}
