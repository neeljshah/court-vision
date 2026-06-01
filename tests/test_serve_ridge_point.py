"""Tests for src/ingame/serve_ridge_point.py.

(a) predict_serve_ridge returns a dict with finite home/away on a real snapshot.
(b) Returns None gracefully when the artifact is absent (monkeypatching the path).
(c) Leak-free: prediction uses only snapshot state (no future info accessed).

Run:
    NBA_OFFLINE=1 NBA_FORCE_CPU=1 python -m pytest tests/test_serve_ridge_point.py -q
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LIVE_DIR = os.path.join(ROOT, "data", "live")
# A real mid-game snapshot from game 0042500317 (period 2, clock 12:00, home 25 away 32)
SNAP_FILE = os.path.join(LIVE_DIR, "0042500317_1780188515000.json")


def _load_snap(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# (a) Happy path: real snapshot returns a valid dict
# ---------------------------------------------------------------------------
def test_predict_returns_dict_on_real_snapshot():
    """predict_serve_ridge(snap) -> {"home_final": finite, "away_final": finite}."""
    if not os.path.exists(SNAP_FILE):
        pytest.skip(f"live snapshot not found: {SNAP_FILE}")

    import src.ingame.serve_ridge_point as srp
    # Reset module cache so we use the real artifact (not a prior monkeypatch).
    srp._ARTIFACT = None
    srp._LOAD_FAILED = False
    srp._ARTIFACT_PATH = srp._DEFAULT_ARTIFACT_PATH

    snap = _load_snap(SNAP_FILE)
    result = srp.predict_serve_ridge(snap)

    # The artifact must exist (train_serve_ridge.py must have been run).
    artifact_path = srp._DEFAULT_ARTIFACT_PATH
    if not os.path.exists(artifact_path):
        pytest.skip(f"artifact not present: {artifact_path} — run train_serve_ridge.py first")

    assert result is not None, (
        "Expected a dict but got None — artifact may be missing or snapshot is unusable"
    )
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "home_final" in result and "away_final" in result, (
        f"Keys missing from result: {result.keys()}"
    )
    hf = result["home_final"]
    af = result["away_final"]
    assert np.isfinite(hf), f"home_final is not finite: {hf}"
    assert np.isfinite(af), f"away_final is not finite: {af}"
    # Sane NBA score range
    assert 60 <= hf <= 180, f"home_final={hf} outside sane range [60, 180]"
    assert 60 <= af <= 180, f"away_final={af} outside sane range [60, 180]"
    print(f"[OK] home_final={hf:.1f}  away_final={af:.1f}")


# ---------------------------------------------------------------------------
# (b) Graceful None when artifact is absent
# ---------------------------------------------------------------------------
def test_predict_returns_none_when_artifact_absent(tmp_path, monkeypatch):
    """predict_serve_ridge returns None (safe) when the artifact file is missing."""
    import src.ingame.serve_ridge_point as srp

    # Point artifact path to a non-existent file
    fake_path = str(tmp_path / "nonexistent_ingame_serve_ridge.pkl")
    monkeypatch.setattr(srp, "_ARTIFACT_PATH", fake_path)
    monkeypatch.setattr(srp, "_ARTIFACT", None)
    monkeypatch.setattr(srp, "_LOAD_FAILED", False)

    snap = {
        "game_id": "0042500317",
        "period": 3,
        "clock": "06:00",
        "home_score": 75,
        "away_score": 72,
        "home_team": "OKC",
        "away_team": "SAS",
    }
    result = srp.predict_serve_ridge(snap)
    assert result is None, f"Expected None when artifact absent, got {result}"
    print("[OK] None returned when artifact absent")


# ---------------------------------------------------------------------------
# (c) Leak-free: prediction uses only snapshot state
# ---------------------------------------------------------------------------
def test_predict_is_deterministic_and_uses_only_snapshot_state(monkeypatch):
    """Two calls with identical snapshots produce identical results (no external I/O)."""
    import src.ingame.serve_ridge_point as srp

    srp._ARTIFACT = None
    srp._LOAD_FAILED = False
    srp._ARTIFACT_PATH = srp._DEFAULT_ARTIFACT_PATH

    if not os.path.exists(srp._DEFAULT_ARTIFACT_PATH):
        pytest.skip("artifact not present")

    snap = {
        "game_id": "TEST",
        "period": 3,
        "clock": "06:00",
        "home_score": 75,
        "away_score": 72,
        "home_team": "OKC",
        "away_team": "SAS",
    }

    r1 = srp.predict_serve_ridge(snap)
    r2 = srp.predict_serve_ridge(snap)

    assert r1 == r2, f"Non-deterministic: {r1} vs {r2}"

    # Changing a score field must change the prediction (pure snapshot dependence)
    snap2 = dict(snap, home_score=95, away_score=80)
    r3 = srp.predict_serve_ridge(snap2)
    if r1 is not None and r3 is not None:
        assert r1 != r3, (
            "Expected different predictions for different scores "
            f"but both gave {r1}"
        )
    print(f"[OK] deterministic and score-sensitive: r1={r1} r3={r3}")


# ---------------------------------------------------------------------------
# (d) Period-0 / pre-game returns None (game hasn't started)
# ---------------------------------------------------------------------------
def test_predict_returns_none_for_pregame(monkeypatch):
    """Snapshot with period=0 or period=1 clock 12:00 (game_sec=0) returns None."""
    import src.ingame.serve_ridge_point as srp

    srp._ARTIFACT = None
    srp._LOAD_FAILED = False
    srp._ARTIFACT_PATH = srp._DEFAULT_ARTIFACT_PATH

    if not os.path.exists(srp._DEFAULT_ARTIFACT_PATH):
        pytest.skip("artifact not present")

    snap = {
        "game_id": "0042500317",
        "period": 1,
        "clock": "12:00",   # 0 elapsed -> game_sec = 0
        "home_score": 0,
        "away_score": 0,
    }
    result = srp.predict_serve_ridge(snap)
    # At 0 seconds elapsed there is no eligible bucket, so must be None.
    assert result is None, f"Expected None at tip-off, got {result}"
    print("[OK] None returned at tip-off (game_sec=0)")


# ---------------------------------------------------------------------------
# (e) BUG 5 fix: late-game floor — projected final must be >= current score
# ---------------------------------------------------------------------------
def _make_artifact_with_low_weights(tmp_path):
    """Build a minimal ridge artifact whose weights will predict scores BELOW
    the current score when called with a late-game snapshot (home 124, away 118).
    The weights are deliberately small/negative so the raw ridge output is ~60
    (the [60,180] clip floor) which is below the current score.
    """
    import pickle
    import numpy as np

    n_feats = 12  # len(TEAM_FEATS)
    # bias + n_feats weights — set all to 0 so prediction = 0, clipped to 60
    w_home = np.zeros(n_feats + 1)
    w_away = np.zeros(n_feats + 1)

    artifact = {
        "version": 1,
        "cutoff": "2025-01-01",
        "n_train": 100,
        "feature_spec": [
            "played_share", "home_score", "away_score", "score_margin",
            "pace_poss_per_min", "home_efg", "away_efg", "home_tov_pct",
            "away_tov_pct", "home_ft_rate", "away_ft_rate", "game_remaining_sec",
        ],
        "grid_sec": [360, 720, 1080, 1440, 1800, 2160, 2520],
        "ridge_w": {
            # bucket at 2520s (42 min elapsed) — covers period 4, clock 0:20
            2520: {"home": w_home, "away": w_away},
        },
    }
    path = str(tmp_path / "ingame_serve_ridge.pkl")
    with open(path, "wb") as fh:
        pickle.dump(artifact, fh)
    return path


def test_late_game_floor_prevents_below_current_score(tmp_path, monkeypatch):
    """BUG 5: Late-game ridge raw output (clipped to 60) must be raised to the
    current score.  Period 4, 0:20 left, home 124 away 118 → finals >= 124/118.
    """
    import src.ingame.serve_ridge_point as srp

    artifact_path = _make_artifact_with_low_weights(tmp_path)
    monkeypatch.setattr(srp, "_ARTIFACT_PATH", artifact_path)
    monkeypatch.setattr(srp, "_ARTIFACT", None)
    monkeypatch.setattr(srp, "_LOAD_FAILED", False)

    snap = {
        "game_id": "TEST_BUG5",
        "period": 4,
        "clock": "0:20",
        "home_score": 124,
        "away_score": 118,
    }
    result = srp.predict_serve_ridge(snap)
    assert result is not None, "Expected a dict, got None"
    assert result["home_final"] >= 124, (
        f"home_final {result['home_final']:.1f} is below current score 124 — BUG 5 not fixed"
    )
    assert result["away_final"] >= 118, (
        f"away_final {result['away_final']:.1f} is below current score 118 — BUG 5 not fixed"
    )
    print(
        f"[OK] late-game floor: home_final={result['home_final']:.1f} "
        f"(>= 124), away_final={result['away_final']:.1f} (>= 118)"
    )


def test_early_game_floor_is_noop(tmp_path, monkeypatch):
    """BUG 5: In early-game when current scores are low (e.g. 8/6) and the
    ridge predicts something in the normal range (~100+), the floor has no
    effect — predictions must remain in the ridge output range, not pinned to
    the current score.
    """
    import src.ingame.serve_ridge_point as srp
    import pickle
    import numpy as np

    n_feats = 12
    # Weights that produce ~105/102: bias term set to that, all others 0.
    w_home = np.zeros(n_feats + 1)
    w_home[0] = 105.0   # bias
    w_away = np.zeros(n_feats + 1)
    w_away[0] = 102.0   # bias

    artifact = {
        "version": 1,
        "cutoff": "2025-01-01",
        "n_train": 100,
        "feature_spec": [
            "played_share", "home_score", "away_score", "score_margin",
            "pace_poss_per_min", "home_efg", "away_efg", "home_tov_pct",
            "away_tov_pct", "home_ft_rate", "away_ft_rate", "game_remaining_sec",
        ],
        "grid_sec": [360, 720, 1080, 1440, 1800, 2160, 2520],
        "ridge_w": {
            360: {"home": w_home, "away": w_away},
        },
    }
    path = str(tmp_path / "ingame_serve_ridge_early.pkl")
    with open(path, "wb") as fh:
        pickle.dump(artifact, fh)

    monkeypatch.setattr(srp, "_ARTIFACT_PATH", path)
    monkeypatch.setattr(srp, "_ARTIFACT", None)
    monkeypatch.setattr(srp, "_LOAD_FAILED", False)

    snap = {
        "game_id": "TEST_BUG5_EARLY",
        "period": 1,
        "clock": "6:00",   # 6 min elapsed = 360 s — exactly at first grid bucket
        "home_score": 8,
        "away_score": 6,
    }
    result = srp.predict_serve_ridge(snap)
    assert result is not None, "Expected a dict for early-game snap, got None"
    # Floor (8/6) is a no-op; predictions should be near bias values (clipped to [60,180]).
    assert result["home_final"] >= 8, "home_final dropped below current (shouldn't happen)"
    assert result["away_final"] >= 6, "away_final dropped below current (shouldn't happen)"
    # The ridge output (105/102) is well above the current score — floor must NOT pull it down.
    assert result["home_final"] >= 100, (
        f"home_final {result['home_final']:.1f} unexpectedly low for early-game (floor must be a no-op)"
    )
    assert result["away_final"] >= 100, (
        f"away_final {result['away_final']:.1f} unexpectedly low for early-game (floor must be a no-op)"
    )
    print(
        f"[OK] early-game floor no-op: home_final={result['home_final']:.1f}, "
        f"away_final={result['away_final']:.1f}"
    )
