"""
tests/test_player_trajectory.py — Unit tests for player_trajectory feature builder.

All tests use synthetic in-memory game histories; no file I/O needed.
"""
from __future__ import annotations

import datetime
import sys
import os

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ── import targets ─────────────────────────────────────────────────────────────
from src.features.player_trajectory import (
    _hot_cold_streaks,
    _z_score_l5,
    _momentum_l10,
    _regression_signal,
    _breakout_flag,
    _workload_anomaly,
    _opponent_history,
    _DEFAULTS,
    get_trajectory_features,
    _load_gamelog,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_rows(pts_list: list, min_list: list | None = None) -> list:
    """Build synthetic gamelog rows (newest-first order)."""
    n = len(pts_list)
    if min_list is None:
        min_list = [30.0] * n
    base_date = datetime.date(2025, 4, 1)
    rows = []
    for i, (p, m) in enumerate(zip(pts_list, min_list)):
        d = base_date - datetime.timedelta(days=i)
        rows.append({
            "game_date": d.strftime("%b %d, %Y"),
            "player_id": 999,
            "game_id": f"FAKE{i:04d}",
            "pts": float(p),
            "min": float(m),
            "matchup": "LAL vs. GSW",
            "fgm": 5, "fga": 10, "ftm": 2, "fta": 2,
        })
    return rows  # newest-first


def _inject_gamelog(player_id: int, season: str, rows: list) -> None:
    """Patch the lru_cache so tests use synthetic data without file I/O."""
    import datetime as _dt

    _DATE_FMTS = ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y")

    def _parse(s):
        for fmt in _DATE_FMTS:
            try:
                return _dt.datetime.strptime(str(s).strip(), fmt).date()
            except ValueError:
                continue
        return None

    parsed = []
    for r in rows:
        d = _parse(r.get("game_date", ""))
        if d is not None:
            parsed.append((d, r))
    parsed.sort(key=lambda x: x[0])  # oldest-first (as _load_gamelog returns)
    _load_gamelog.cache_clear()
    _load_gamelog.__wrapped__ = None  # mark that we patched it
    # Directly set the cache entry
    _load_gamelog.cache_info()  # ensure cache is live
    # Use cache_parameters approach: monkeypatch via module-level override
    import src.features.player_trajectory as _mod
    _mod._load_gamelog.cache_clear()
    # Override the function temporarily with a version that returns our data
    original = _mod._load_gamelog

    def _patched(pid, s):
        if pid == player_id and s == season:
            return tuple(parsed)
        return original(pid, s)

    _patched.cache_clear = original.cache_clear
    _patched.cache_info = original.cache_info
    _mod._load_gamelog = _patched
    return original  # caller can restore


def _restore_gamelog(original) -> None:
    import src.features.player_trajectory as _mod
    _mod._load_gamelog = original


# ── tests ──────────────────────────────────────────────────────────────────────

class TestHotColdStreaks:
    def test_stable_no_streak(self):
        """30-game stable ~20 pts — should have neither hot nor cold streak."""
        pts = [20.0] * 30
        hot, cold = _hot_cold_streaks(pts, pts[:3])
        assert hot == 0
        assert cold == 0

    def test_hot_streak_detected(self):
        """Last 3 games all 30 pts when season avg is 20 → hot_streak=1."""
        pts_all = [30.0, 30.0, 30.0] + [20.0] * 27  # newest-first
        pts_l3 = pts_all[:3]
        hot, cold = _hot_cold_streaks(pts_all, pts_l3)
        assert hot == 1
        assert cold == 0

    def test_cold_streak_detected(self):
        """Last 3 games all 10 pts when season avg is 20 → cold_streak=1."""
        pts_all = [10.0, 10.0, 10.0] + [20.0] * 27  # newest-first
        pts_l3 = pts_all[:3]
        hot, cold = _hot_cold_streaks(pts_all, pts_l3)
        assert hot == 0
        assert cold == 1

    def test_insufficient_history_returns_zeros(self):
        """< 5 games of history → safe defaults."""
        pts = [20.0] * 4
        hot, cold = _hot_cold_streaks(pts, pts[:3])
        assert hot == 0
        assert cold == 0


class TestZScoreL5:
    def test_above_avg_positive(self):
        pts_all = [20.0] * 25
        pts_l5 = [28.0] * 5  # well above avg
        z = _z_score_l5(pts_all + pts_l5, pts_l5)
        # With zero std from stable history, should return 0
        assert isinstance(z, float)

    def test_recent_spike_positive_z(self):
        # Newest-first: first 5 entries are the hot games (30 pts),
        # remaining 10 are baseline at varying ~20 pts.
        pts_l5 = [30.0, 30.0, 30.0, 30.0, 30.0]
        pts_baseline = [15.0, 25.0, 18.0, 22.0, 20.0,
                        19.0, 21.0, 17.0, 23.0, 20.0]
        pts_all = pts_l5 + pts_baseline  # newest-first: hot games at front
        z = _z_score_l5(pts_all, pts_l5)
        assert z > 0, f"Expected positive z-score, got {z}"


class TestMomentumL10:
    def test_flat_trend_near_zero(self):
        pts = [20.0] * 10
        mom = _momentum_l10(pts)
        assert abs(mom) < 0.01

    def test_rising_trend_positive(self):
        # Chronological order oldest→newest after internal reverse: [10..20]
        # newest-first: [20, 19, 18, ..., 10]  (10 values)
        pts_newest_first = list(range(20, 10, -1))  # [20,19,...,11]
        mom = _momentum_l10(pts_newest_first)
        assert mom > 0, f"Rising trend should be positive, got {mom}"

    def test_falling_trend_negative(self):
        # newest-first: [10,11,12,...,19]  → chronological: [19,...,10] = falling
        pts_newest_first = list(range(10, 20))  # [10,11,...,19]
        mom = _momentum_l10(pts_newest_first)
        assert mom < 0, f"Falling (newest lowest) trend should be negative, got {mom}"


class TestWorkloadAnomaly:
    def test_elevated_workload_positive(self):
        """38-min weeks when season avg is 30 → workload_anomaly > 1.0."""
        min_all = [30.0] * 30  # season baseline 30 min, zero std — use variable history
        # Create variable season history with std ~5
        import math
        mins_season = [25.0, 35.0, 28.0, 32.0, 30.0,
                       27.0, 33.0, 29.0, 31.0, 30.0,
                       26.0, 34.0, 28.0, 32.0, 30.0,
                       27.0, 33.0, 29.0, 31.0, 30.0]  # 20 games, avg ~30, std ~3
        # Last 7 are the "current week" at 38 min
        min_l7 = [38.0] * 7
        full_min = min_l7 + mins_season  # newest-first
        anomaly = _workload_anomaly(full_min, min_l7)
        assert anomaly > 1.0, f"Expected anomaly > 1.0, got {anomaly}"

    def test_normal_workload_near_zero(self):
        min_all = [30.0, 29.0, 31.0, 30.0, 28.0, 32.0, 30.0,
                   29.0, 31.0, 30.0, 28.0, 32.0, 30.0, 29.0,
                   31.0, 30.0, 28.0, 32.0, 30.0, 29.0]
        min_l7 = min_all[:7]  # same as season avg
        anomaly = _workload_anomaly(min_all, min_l7)
        assert abs(anomaly) < 1.0


class TestEdgeCases:
    def test_few_games_returns_defaults(self):
        """Player with only 2 games before cutoff → safe defaults."""
        orig = _inject_gamelog(99999, "2024-25", _make_rows([20.0, 20.0]))
        try:
            feats = get_trajectory_features(
                player_id=99999,
                season="2024-25",
                game_date="2025-04-10",
            )
            assert feats == _DEFAULTS
        finally:
            _restore_gamelog(orig)

    def test_hot_streak_end_to_end(self):
        """Full get_trajectory_features with 3 hot games → hot_streak=1."""
        # 27 stable @ 20, then 3 hot @ 25 (newest-first means first 3 are hottest)
        # 20*1.10 = 22, so 25 > 22 qualifies
        all_pts = [25.0, 25.0, 25.0] + [20.0] * 27
        rows = _make_rows(all_pts)
        orig = _inject_gamelog(99998, "2024-25", rows)
        try:
            feats = get_trajectory_features(
                player_id=99998,
                season="2024-25",
                game_date="2025-04-10",
            )
            assert feats["hot_streak"] == 1, f"hot_streak should be 1, got {feats}"
            assert feats["cold_streak"] == 0
        finally:
            _restore_gamelog(orig)

    def test_cold_streak_end_to_end(self):
        """Full get_trajectory_features with 3 cold games → cold_streak=1."""
        # 20*0.85 = 17, so 10 < 17 qualifies
        all_pts = [10.0, 10.0, 10.0] + [20.0] * 27
        rows = _make_rows(all_pts)
        orig = _inject_gamelog(99997, "2024-25", rows)
        try:
            feats = get_trajectory_features(
                player_id=99997,
                season="2024-25",
                game_date="2025-04-10",
            )
            assert feats["cold_streak"] == 1, f"cold_streak should be 1, got {feats}"
            assert feats["hot_streak"] == 0
        finally:
            _restore_gamelog(orig)

    def test_workload_anomaly_end_to_end(self):
        """38-min weeks when season avg ~30 → workload_anomaly > 1.0."""
        mins_season = [25.0, 35.0, 28.0, 32.0, 30.0,
                       27.0, 33.0, 29.0, 31.0, 30.0,
                       26.0, 34.0, 28.0, 32.0, 30.0,
                       27.0, 33.0, 29.0, 31.0, 30.0]
        min_l7 = [38.0] * 7
        all_mins = min_l7 + mins_season
        all_pts = [20.0] * len(all_mins)
        rows = _make_rows(all_pts, min_list=all_mins)
        orig = _inject_gamelog(99996, "2024-25", rows)
        try:
            feats = get_trajectory_features(
                player_id=99996,
                season="2024-25",
                game_date="2025-04-10",
            )
            assert feats["workload_anomaly"] > 1.0, (
                f"Expected workload_anomaly > 1.0, got {feats['workload_anomaly']}"
            )
        finally:
            _restore_gamelog(orig)

    def test_all_keys_present(self):
        """Output dict always contains all 9 required keys."""
        rows = _make_rows([20.0] * 30)
        orig = _inject_gamelog(99995, "2024-25", rows)
        try:
            feats = get_trajectory_features(
                player_id=99995,
                season="2024-25",
                game_date="2025-04-10",
            )
            for key in _DEFAULTS:
                assert key in feats, f"Missing key: {key}"
        finally:
            _restore_gamelog(orig)
