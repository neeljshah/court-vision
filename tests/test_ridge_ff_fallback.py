"""Test CV_RIDGE_FF_FALLBACK gated fix in serve_ridge_point.predict_serve_ridge.

Bug (sweep INGAME_SIM, HIGH/LIVE under CV_INGAME_SBS=1): the ridge was trained on real in-game
four-factors but the live snapshot never emits them, so they zero-fill → team total biased ~-23.5 pts
low. The snapshot lacks fgm/fga/fta/oreb/dreb so four-factors can't be reconstructed live; the fix is to
ABSTAIN (return None) → score_ensemble falls back to the unbiased sim mean. Default OFF = byte-identical.
"""
import pytest
from src.ingame import serve_ridge_point as srp

# period 3, 6:00 left -> game_sec 1800 -> reaches a ridge bucket (per the audit probe)
_SNAP = {"period": 3, "clock": "6:00", "home_score": 60, "away_score": 58,
         "home_team": "OKC", "away_team": "SAS", "game_status": "in_progress"}

_FF = {"pace_poss_per_min": 4.3, "home_efg": 0.55, "away_efg": 0.54,
       "home_tov_pct": 0.12, "away_tov_pct": 0.13, "home_ft_rate": 0.25, "away_ft_rate": 0.24}

_ARTIFACT = srp._load_artifact() is not None
_skip = pytest.mark.skipif(not _ARTIFACT, reason="ingame_serve_ridge.pkl artifact not present")


@_skip
def test_off_default_serves_zero_filled_ridge(monkeypatch):
    monkeypatch.delenv("CV_RIDGE_FF_FALLBACK", raising=False)
    out = srp.predict_serve_ridge(dict(_SNAP))
    assert out is not None and "home_final" in out and "away_final" in out  # legacy behavior preserved


@_skip
def test_on_abstains_when_four_factors_absent(monkeypatch):
    monkeypatch.setenv("CV_RIDGE_FF_FALLBACK", "1")
    out = srp.predict_serve_ridge(dict(_SNAP))
    assert out is None  # abstains -> score_ensemble uses unbiased sim mean


@_skip
def test_on_serves_when_four_factors_present(monkeypatch):
    monkeypatch.setenv("CV_RIDGE_FF_FALLBACK", "1")
    snap = dict(_SNAP); snap.update(_FF)
    on_ff = srp.predict_serve_ridge(snap)
    assert on_ff is not None  # FF present -> gate bypassed, ridge serves
    # and equals the OFF output on the same (FF-bearing) snap (gate is a no-op when FF present)
    monkeypatch.delenv("CV_RIDGE_FF_FALLBACK", raising=False)
    off_ff = srp.predict_serve_ridge(dict(snap))
    assert on_ff == off_ff


def test_no_artifact_returns_none(monkeypatch):
    """Always-on safety: if the artifact is missing, both modes return None (no crash)."""
    monkeypatch.setattr(srp, "_load_artifact", lambda: None)
    monkeypatch.setenv("CV_RIDGE_FF_FALLBACK", "1")
    assert srp.predict_serve_ridge(dict(_SNAP)) is None
