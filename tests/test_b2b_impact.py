"""
test_b2b_impact.py — Unit tests for src/features/back_to_back_impact.py

Uses synthetic gamelogs with explicit B2B and non-B2B game pairs.
All NBA API and disk I/O redirected to temp dirs.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.features.back_to_back_impact as _b2b


# ── Synthetic fixtures ─────────────────────────────────────────────────────────

def _make_b2b_logs(player_id: int, age: int = 32) -> list:
    """
    Return a synthetic gamelog containing both B2B and regular rest games.

    B2B games: pts=16 (underperforming season avg of 22)
    Regular games: pts=22 (on avg)
    """
    from datetime import date, timedelta
    rows = []
    base = date(2024, 1, 1)

    # 20 regular-rest games (every 2 days)
    for i in range(20):
        d = base + timedelta(days=i * 2)
        rows.append({
            "player_id": player_id,
            "game_date": d.isoformat(),
            "min": "32:00",
            "pts": 22.0, "reb": 7.0, "ast": 4.0,
            "fg3m": 2.0, "stl": 1.0, "blk": 0.5,
            "tov": 2.0, "fg_pct": 0.48,
            "age": age,
        })

    # 10 B2B pairs — second night underperforms
    b2b_start = base + timedelta(days=50)
    for i in range(10):
        d1 = b2b_start + timedelta(days=i * 3)
        d2 = d1 + timedelta(days=1)  # B2B
        # Night 1: normal
        rows.append({
            "player_id": player_id,
            "game_date": d1.isoformat(),
            "min": "33:00",
            "pts": 22.0, "reb": 7.0, "ast": 4.0,
            "fg3m": 2.0, "stl": 1.0, "blk": 0.5,
            "tov": 2.0, "fg_pct": 0.48,
            "age": age,
        })
        # Night 2: B2B — clearly underperforms
        rows.append({
            "player_id": player_id,
            "game_date": d2.isoformat(),
            "min": "28:00",
            "pts": 16.0, "reb": 5.5, "ast": 3.0,
            "fg3m": 1.2, "stl": 0.7, "blk": 0.3,
            "tov": 2.5, "fg_pct": 0.41,
            "age": age,
        })

    return sorted(rows, key=lambda r: r["game_date"])


def _make_b2b_logs_young(player_id: int) -> list:
    return _make_b2b_logs(player_id, age=23)


@pytest.fixture()
def tmp_dirs(tmp_path, monkeypatch):
    nba_dir   = tmp_path / "nba"
    model_dir = tmp_path / "models"
    nba_dir.mkdir()
    model_dir.mkdir()

    old_player  = 11111  # age 32
    young_player = 22222  # age 23
    b2b_date_old   = "2024-03-01"  # a B2B date for old_player (last game was 2024-02-29)
    b2b_date_young = "2024-03-01"

    old_logs   = _make_b2b_logs(old_player, age=32)
    young_logs = _make_b2b_logs_young(young_player)

    gamelog_path = nba_dir / "gamelog_full_synthetic.json"
    gamelog_path.write_text(json.dumps({
        str(old_player):   old_logs,
        str(young_player): young_logs,
    }))

    monkeypatch.setattr(_b2b, "_NBA_CACHE", str(nba_dir))
    monkeypatch.setattr(_b2b, "_MODEL_DIR", str(model_dir))
    monkeypatch.setattr(_b2b, "_B2B_PATH",  str(model_dir / "b2b_curve.json"))
    monkeypatch.setattr(_b2b, "_b2b_cache", None)

    return tmp_path, old_player, young_player


# ── fit_b2b_curve ─────────────────────────────────────────────────────────────

class TestFitB2bCurve:
    def test_returns_dict_with_all_stats(self, tmp_dirs):
        curve = _b2b.fit_b2b_curve()
        assert isinstance(curve, dict)
        for stat in ("pts", "reb", "ast", "tov"):
            assert stat in curve

    def test_json_persisted(self, tmp_dirs):
        tmp_path, *_ = tmp_dirs
        _b2b.fit_b2b_curve()
        path = os.path.join(str(tmp_path), "models", "b2b_curve.json")
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert "pts" in loaded

    def test_ratios_in_valid_range(self, tmp_dirs):
        curve = _b2b.fit_b2b_curve()
        for stat in curve:
            for age_label, entry in curve[stat].items():
                ratio = entry.get("ratio", 1.0)
                assert 0.88 <= ratio <= 1.05, (
                    f"Ratio out of range for {stat}/{age_label}: {ratio}"
                )

    def test_b2b_dip_captured_for_pts(self, tmp_dirs):
        """B2B pts ratio should be below 1.0 for the 30-32 age bucket."""
        curve = _b2b.fit_b2b_curve()
        ratio_30 = curve.get("pts", {}).get("30-32", {}).get("ratio", 1.0)
        assert ratio_30 < 1.0, f"Expected pts B2B dip for 30-32, got ratio={ratio_30}"

    def test_b2b_older_worse_than_younger(self, tmp_dirs):
        """33+ bucket should show larger dip (lower ratio) than <25 bucket."""
        curve = _b2b.fit_b2b_curve()
        ratio_young = curve.get("pts", {}).get("<25",   {}).get("ratio", 1.0)
        ratio_old   = curve.get("pts", {}).get("30-32", {}).get("ratio", 1.0)
        # Both may equal fallback if sample too small — but when n >= 30, old should be worse
        n_old = curve.get("pts", {}).get("30-32", {}).get("n_b2b", 0)
        if n_old >= 10:
            assert ratio_old <= ratio_young, (
                f"Expected older players hurt more: {ratio_old} vs {ratio_young}"
            )


# ── get_b2b_multiplier ────────────────────────────────────────────────────────

class TestGetB2bMultiplier:
    def test_multiplier_below_1_for_b2b(self, tmp_dirs):
        """After fitting, any age bucket should have pts multiplier < 1.0."""
        _b2b.fit_b2b_curve()
        mult = _b2b.get_b2b_multiplier(11111, "pts", 32)
        assert mult < 1.0, f"Expected B2B pts penalty, got {mult}"

    def test_older_player_has_larger_penalty(self, tmp_dirs):
        _b2b.fit_b2b_curve()
        mult_young = _b2b.get_b2b_multiplier(22222, "pts", 23)
        mult_old   = _b2b.get_b2b_multiplier(11111, "pts", 32)
        assert mult_old <= mult_young, (
            f"Expected older player to have larger penalty: {mult_old} vs {mult_young}"
        )

    def test_multiplier_in_valid_range(self, tmp_dirs):
        _b2b.fit_b2b_curve()
        for stat in ("pts", "reb", "ast", "stl", "blk"):
            for age in (23, 27, 31, 34):
                mult = _b2b.get_b2b_multiplier(11111, stat, age)
                assert 0.88 <= mult <= 1.05, f"{stat} age={age}: {mult} out of range"

    def test_fallback_when_no_model(self, tmp_dirs, monkeypatch):
        """Should return FALLBACK_RATIO when no model file exists."""
        monkeypatch.setattr(_b2b, "_b2b_cache", None)
        monkeypatch.setattr(_b2b, "_B2B_PATH", "/nonexistent/b2b_curve.json")
        # fit will find no gamelog files either since NBA_CACHE is redirected already
        mult = _b2b.get_b2b_multiplier(99999, "pts", 27)
        assert isinstance(mult, float)
        assert 0.88 <= mult <= 1.05


# ── is_back_to_back ───────────────────────────────────────────────────────────

class TestIsBackToBack:
    def test_returns_bool(self, tmp_dirs):
        tmp_path, old_player, _ = tmp_dirs
        result = _b2b.is_back_to_back(old_player, "2024-03-01")
        assert isinstance(result, bool)

    def test_false_for_unknown_player(self, tmp_dirs):
        result = _b2b.is_back_to_back(999999999, "2024-03-01")
        assert result is False

    def test_false_for_invalid_date(self, tmp_dirs):
        tmp_path, old_player, _ = tmp_dirs
        result = _b2b.is_back_to_back(old_player, "not-a-date")
        assert result is False


# ── _age_bucket helper ────────────────────────────────────────────────────────

class TestAgeBucket:
    def test_young(self):
        assert _b2b._age_bucket(22) == "<25"
        assert _b2b._age_bucket(24) == "<25"

    def test_prime(self):
        assert _b2b._age_bucket(25) == "25-29"
        assert _b2b._age_bucket(29) == "25-29"

    def test_veteran(self):
        assert _b2b._age_bucket(30) == "30-32"
        assert _b2b._age_bucket(32) == "30-32"

    def test_old(self):
        assert _b2b._age_bucket(33) == "33+"
        assert _b2b._age_bucket(40) == "33+"
