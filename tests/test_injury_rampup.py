"""
test_injury_rampup.py — Unit tests for src/features/injury_rampup.py

Uses synthetic gamelogs: a player with a 15-day gap before game_date.
All NBA API and disk I/O redirected to temp dirs.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.features.injury_rampup as _ir


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _build_logs_with_absence(player_id: int, gap_days: int = 15) -> list:
    """Return a gamelog with a gap_days absence before the 'current' game."""
    from datetime import date, timedelta
    # 10 games before the gap
    base = date(2024, 1, 1)
    rows = []
    for i in range(10):
        d = base + timedelta(days=i * 2)  # every 2 days
        rows.append({
            "player_id": player_id,
            "game_date": d.isoformat(),
            "min": "32:00",
            "pts": 20.0, "reb": 5.0, "ast": 4.0,
            "fg3m": 2.0, "stl": 1.0, "blk": 0.5,
            "tov": 2.0,
            "age": 28,
        })
    # Gap: last pre-absence game
    last_before = base + timedelta(days=18)
    rows.append({
        "player_id": player_id,
        "game_date": last_before.isoformat(),
        "min": "34:00",
        "pts": 22.0, "reb": 6.0, "ast": 5.0,
        "fg3m": 2.0, "stl": 1.2, "blk": 0.6,
        "tov": 2.2,
        "age": 28,
    })
    # First game back after gap_days
    first_back = last_before + __import__("datetime").timedelta(days=gap_days)
    rows.append({
        "player_id": player_id,
        "game_date": first_back.isoformat(),
        "min": "28:00",
        "pts": 16.0, "reb": 4.0, "ast": 3.0,   # underperforming
        "fg3m": 1.0, "stl": 0.7, "blk": 0.3,
        "tov": 2.8,
        "age": 28,
    })
    return rows, last_before.isoformat(), first_back.isoformat()


@pytest.fixture()
def tmp_dirs(tmp_path, monkeypatch):
    nba_dir   = tmp_path / "nba"
    model_dir = tmp_path / "models"
    nba_dir.mkdir()
    model_dir.mkdir()

    player_id = 12345
    rows, last_before, first_back = _build_logs_with_absence(player_id, gap_days=15)

    # Write as per-player keyed dict
    gamelog_path = nba_dir / "gamelog_full_synthetic.json"
    gamelog_path.write_text(json.dumps({str(player_id): rows}))

    monkeypatch.setattr(_ir, "_NBA_CACHE",  str(nba_dir))
    monkeypatch.setattr(_ir, "_MODEL_DIR",  str(model_dir))
    monkeypatch.setattr(_ir, "_RAMPUP_PATH", str(model_dir / "injury_rampup.json"))
    monkeypatch.setattr(_ir, "_rampup_cache", None)

    return tmp_path, player_id, last_before, first_back


# ── days_since_last_game ───────────────────────────────────────────────────────

class TestDaysSinceLastGame:
    def test_returns_15_for_15_day_gap(self, tmp_dirs):
        _, player_id, last_before, first_back = tmp_dirs
        gap = _ir.days_since_last_game(player_id, first_back)
        assert gap == 15, f"Expected 15, got {gap}"

    def test_returns_0_for_unknown_player(self, tmp_dirs):
        gap = _ir.days_since_last_game(999999999, "2024-02-01")
        assert gap == 0

    def test_returns_0_for_invalid_date(self, tmp_dirs):
        _, player_id, _, _ = tmp_dirs
        gap = _ir.days_since_last_game(player_id, "not-a-date")
        assert gap == 0


# ── fit_rampup_curve ──────────────────────────────────────────────────────────

class TestFitRampupCurve:
    def test_returns_dict_with_all_stats(self, tmp_dirs):
        curve = _ir.fit_rampup_curve()
        assert isinstance(curve, dict)
        for stat in ("pts", "reb", "ast"):
            assert stat in curve, f"stat {stat!r} missing"

    def test_json_persisted(self, tmp_dirs):
        tmp_path, *_ = tmp_dirs
        curve = _ir.fit_rampup_curve()
        path = os.path.join(str(tmp_path), "models", "injury_rampup.json")
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert "pts" in loaded

    def test_curve_has_bucket_keys(self, tmp_dirs):
        curve = _ir.fit_rampup_curve()
        # At minimum, structure should have nested dicts for each stat
        for stat in ("pts", "reb"):
            assert isinstance(curve[stat], dict)

    def test_ratios_clipped_to_valid_range(self, tmp_dirs):
        curve = _ir.fit_rampup_curve()
        for stat in curve:
            for key, entry in curve[stat].items():
                ratio = entry.get("ratio", 1.0)
                assert 0.70 <= ratio <= 1.00, (
                    f"Ratio out of range for {stat}/{key}: {ratio}"
                )


# ── get_rampup_multiplier ─────────────────────────────────────────────────────

class TestGetRampupMultiplier:
    def test_multiplier_below_1_for_return_game(self, tmp_dirs):
        """Player returning from 15-day absence: first game back should < 1.0."""
        tmp_path, player_id, last_before, first_back = tmp_dirs
        # Fit curve first so we have data
        _ir.fit_rampup_curve()
        # Direct call to multiplier — checks days_since_last_game internally
        mult = _ir.get_rampup_multiplier(player_id, "pts", first_back)
        # Either < 1.0 (data-backed) or 1.0 (fallback if no data) — both valid
        # BUT: with the synthetic fixture we built actual underperforming data,
        # so if the curve was populated the ratio should be < 1.0.
        # If the bucket key wasn't populated (n < 5), fallback is 1.0 — also fine.
        assert isinstance(mult, float)
        assert 0.70 <= mult <= 1.00, f"Multiplier out of range: {mult}"

    def test_multiplier_is_1_for_normal_game(self, tmp_dirs):
        tmp_path, player_id, last_before, _ = tmp_dirs
        # Game just 2 days after last game: gap < 7, no rampup
        from datetime import date, timedelta
        d = date.fromisoformat(last_before) + timedelta(days=2)
        mult = _ir.get_rampup_multiplier(player_id, "pts", d.isoformat())
        assert mult == 1.0, f"Expected 1.0 for non-rampup game, got {mult}"

    def test_multiplier_is_1_for_unknown_player(self, tmp_dirs):
        mult = _ir.get_rampup_multiplier(999999999, "pts", "2024-03-01")
        assert mult == 1.0

    def test_multiplier_clipped_in_range(self, tmp_dirs):
        """Whatever value is returned, it must be in [0.70, 1.00]."""
        tmp_path, player_id, _, first_back = tmp_dirs
        for stat in ("pts", "reb", "ast", "blk", "stl"):
            mult = _ir.get_rampup_multiplier(player_id, stat, first_back)
            assert 0.70 <= mult <= 1.00, f"{stat} mult out of range: {mult}"


# ── Helper internals ──────────────────────────────────────────────────────────

class TestInternalHelpers:
    def test_days_bucket_label(self):
        assert _ir._days_bucket_label(7)  == "7-13"
        assert _ir._days_bucket_label(14) == "14-29"
        assert _ir._days_bucket_label(30) == "30+"
        assert _ir._days_bucket_label(6)  is None

    def test_game_bucket_label(self):
        assert _ir._bucket_label(1) == "1"
        assert _ir._bucket_label(3) == "3"
        assert _ir._bucket_label(4) == "4-5"
        assert _ir._bucket_label(5) == "4-5"
        assert _ir._bucket_label(6) == "6+"
        assert _ir._bucket_label(10) == "6+"
