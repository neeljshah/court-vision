"""Tests for intel/player_monthly_form.py — leak-safety + schema-conformance.

Covers:
  - Leak-safety: as_of filtering excludes games after the cutoff date.
  - Schema conformance: AtlasArtifact structure, required sub-dicts, provenance n.
  - Slope field naming: _slope suffix present (signed, exempt from [0,1] rule).
  - CV fields: empty dict (no CV enrichment for this section).
  - Self-validation: PlayerMonthlyForm.validate() returns True for valid artifact.
  - No-data path: build() returns None when player has no games before as_of.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np
import pandas as pd
import pytest

from intel.player_monthly_form import (
    PlayerMonthlyForm,
    _build_player_gamelog,
    _compute_last15,
    _compute_monthly,
    _compute_summary,
    _CORE_STATS,
    _MIN_GAMES_FOR_SLOPE,
    _SRC_CACHE,
)
from src.loop.atlas import AtlasArtifact, confidence_from_n


# ---------------------------------------------------------------------------
# Fixtures: synthetic game-log DataFrame
# ---------------------------------------------------------------------------

def _make_games(n: int, base_date: str = "2024-10-01") -> pd.DataFrame:
    """Create a synthetic per-game DataFrame with n rows, starting at base_date."""
    dates = pd.date_range(base_date, periods=n, freq="3D")
    rng = np.random.default_rng(42)
    data = {
        "game_id": [f"002400{i:04d}" for i in range(n)],
        "game_date": dates,
    }
    for stat in _CORE_STATS:
        # Reasonable range per stat
        hi = {"pts": 40, "reb": 15, "ast": 12, "fg3m": 8,
              "stl": 4, "blk": 4, "tov": 6}.get(stat, 5)
        data[stat] = rng.integers(0, hi + 1, size=n).astype(float)
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Leak-safety tests
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that as_of filtering actually excludes future games."""

    def test_leak_filter_excludes_future_rows(self):
        """Games after as_of must NOT appear in _build_player_gamelog results."""
        # Inject a synthetic gamelog into the module cache so no parquet needed
        import intel.player_monthly_form as mod

        pid = 999901
        n_past = 20
        n_future = 5
        # Past games: Oct 2024
        past = _make_games(n_past, "2024-10-01")
        past["player_id"] = pid
        # Future games: Dec 2024
        future = _make_games(n_future, "2024-12-01")
        future["player_id"] = pid

        all_games = pd.concat([past, future], ignore_index=True)

        # Patch the module-level cache: override glog source
        old_cache = dict(mod._SRC_CACHE)
        try:
            # Build a minimal glog DataFrame with the right columns
            mod._SRC_CACHE["glog_reg"] = all_games.rename(columns={
                c: c.upper() for c in ["game_id", "game_date"] + _CORE_STATS
            }).assign(PLAYER_ID=pid).rename(columns={"PLAYER_ID": "PLAYER_ID"})[
                ["PLAYER_ID", "GAME_ID", "GAME_DATE"] + [c.upper() for c in _CORE_STATS]
            ]
            mod._SRC_CACHE["glog_reg"] = (
                all_games
                .assign(**{"PLAYER_ID": all_games["player_id"]})
                .rename(columns={
                    "player_id": "player_id",
                    "game_id": "GAME_ID",
                    "game_date": "GAME_DATE",
                    **{s: s.upper() for s in _CORE_STATS},
                })
                [["PLAYER_ID", "GAME_ID", "GAME_DATE"] + [s.upper() for s in _CORE_STATS]]
            )
            mod._SRC_CACHE["glog_ply"] = None
            mod._SRC_CACHE["pqs"] = None  # disable secondary source
            mod._SRC_CACHE["adv"] = None

            as_of = _dt.datetime(2024, 11, 30)
            result = _build_player_gamelog(pid, as_of)

            assert len(result) <= n_past, (
                f"Got {len(result)} rows; expected <= {n_past} (future rows leaked)"
            )
            if not result.empty:
                assert result["game_date"].max() <= pd.Timestamp(as_of), (
                    "A game after as_of was included (leak!)"
                )
        finally:
            mod._SRC_CACHE.clear()
            mod._SRC_CACHE.update(old_cache)

    def test_as_of_in_past_returns_none_when_no_data(self):
        """build() returns None for a far-past as_of if no games existed yet."""
        import intel.player_monthly_form as mod
        old_cache = dict(mod._SRC_CACHE)
        try:
            # No data available
            mod._SRC_CACHE["glog_reg"] = None
            mod._SRC_CACHE["glog_ply"] = None
            mod._SRC_CACHE["pqs"] = None
            mod._SRC_CACHE["adv"] = None

            section = PlayerMonthlyForm()
            as_of = _dt.datetime(2010, 1, 1)  # before any NBA data in repo
            art = section.build(203999, as_of)
            assert art is None, "Expected None when no data is available for player"
        finally:
            mod._SRC_CACHE.clear()
            mod._SRC_CACHE.update(old_cache)


# ---------------------------------------------------------------------------
# Schema-conformance tests (using synthetic data)
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Verify AtlasArtifact structure from PlayerMonthlyForm.build()."""

    def _build_with_synthetic(self, n: int = 30) -> AtlasArtifact:
        """Helper: inject synthetic data and build an artifact."""
        import intel.player_monthly_form as mod

        pid = 999902
        games = _make_games(n, "2024-10-01")
        games["player_id"] = pid

        old_cache = dict(mod._SRC_CACHE)
        try:
            mod._SRC_CACHE["glog_reg"] = (
                games
                .assign(**{"PLAYER_ID": games["player_id"]})
                .rename(columns={
                    "game_id": "GAME_ID",
                    "game_date": "GAME_DATE",
                    **{s: s.upper() for s in _CORE_STATS},
                })
                [["PLAYER_ID", "GAME_ID", "GAME_DATE"] + [s.upper() for s in _CORE_STATS]]
            )
            mod._SRC_CACHE["glog_ply"] = None
            mod._SRC_CACHE["pqs"] = None
            mod._SRC_CACHE["adv"] = None

            section = PlayerMonthlyForm()
            as_of = _dt.datetime(2025, 6, 1)
            art = section.build(pid, as_of)
        finally:
            mod._SRC_CACHE.clear()
            mod._SRC_CACHE.update(old_cache)

        return art

    def test_artifact_not_none_with_sufficient_data(self):
        art = self._build_with_synthetic(30)
        assert art is not None, "build() returned None with 30 synthetic games"

    def test_required_sub_dicts_present(self):
        art = self._build_with_synthetic(30)
        assert "monthly" in art.sub_fields
        assert "last15" in art.sub_fields
        assert "summary" in art.sub_fields

    def test_section_and_entity_labels(self):
        art = self._build_with_synthetic(30)
        assert art.section == "monthly_form"
        assert art.entity == "player"

    def test_provenance_n_is_real_game_count(self):
        """n in provenance must be the actual game count, not a constant."""
        art = self._build_with_synthetic(30)
        n = art.provenance["n"]
        assert n >= _MIN_GAMES_FOR_SLOPE, (
            f"provenance n={n} is below _MIN_GAMES_FOR_SLOPE; "
            "might be n_seasons=1 (Lesson 1 bug)"
        )
        # For 30 games of synthetic data, n should be close to 30
        assert n >= 20, f"Expected n>=20 for 30 synthetic games, got n={n}"

    def test_confidence_scales_with_n(self):
        art = self._build_with_synthetic(30)
        n = art.provenance["n"]
        expected_conf = confidence_from_n(n)
        assert art.confidence == expected_conf

    def test_slope_fields_present_with_slope_suffix(self):
        """last15 must expose *_slope keys for all core stats."""
        art = self._build_with_synthetic(30)
        last15 = art.sub_fields["last15"]
        for stat in _CORE_STATS:
            key = f"{stat}_slope"
            assert key in last15, f"Missing slope field '{key}' in last15"

    def test_slope_fields_are_signed_floats(self):
        """Slopes can be negative — they must NOT be clipped to [0,1]."""
        art = self._build_with_synthetic(30)
        last15 = art.sub_fields["last15"]
        for stat in _CORE_STATS:
            v = last15.get(f"{stat}_slope")
            if v is not None:
                # Slopes CAN be negative; just check they're finite floats
                assert isinstance(v, float), f"{stat}_slope is not a float"
                assert np.isfinite(v), f"{stat}_slope is not finite"

    def test_summary_per_game_rates_non_negative(self):
        """Per-game averages in summary must be >= 0."""
        art = self._build_with_synthetic(30)
        summary = art.sub_fields["summary"]
        for stat in _CORE_STATS:
            v = summary.get(f"{stat}_pg")
            if v is not None:
                assert v >= 0, f"Negative per-game rate {stat}_pg={v}"

    def test_monthly_keys_are_yyyy_mm_strings(self):
        """Monthly dict keys must be 'YYYY-MM' formatted strings."""
        art = self._build_with_synthetic(30)
        monthly = art.sub_fields["monthly"]
        for key in monthly:
            assert len(key) == 7, f"Monthly key '{key}' is not 7 chars (YYYY-MM)"
            assert key[4] == "-", f"Monthly key '{key}' lacks '-' separator"

    def test_cv_fields_is_empty_dict(self):
        """No CV slots for monthly form — cv_fields() must return empty dict."""
        section = PlayerMonthlyForm()
        assert section.cv_fields() == {}, "cv_fields() should return empty dict"

    def test_cv_fields_on_artifact_is_empty(self):
        art = self._build_with_synthetic(30)
        assert art.cv_fields == {}, "Artifact cv_fields must be empty dict"

    def test_as_of_is_iso_date_string(self):
        art = self._build_with_synthetic(30)
        assert art.as_of is not None
        _dt.date.fromisoformat(art.as_of)  # raises ValueError if malformed

    def test_self_validate_returns_true(self):
        """section.validate(artifact) must return True for a valid artifact."""
        section = PlayerMonthlyForm()
        art = self._build_with_synthetic(30)
        assert section.validate(art) is True, "section.validate() returned False"

    def test_insufficient_games_returns_none(self):
        """build() returns None if fewer than _MIN_GAMES_FOR_SLOPE games."""
        import intel.player_monthly_form as mod

        pid = 999903
        # Only 3 games -- below min
        games = _make_games(3, "2025-01-01")
        games["player_id"] = pid
        old_cache = dict(mod._SRC_CACHE)
        try:
            mod._SRC_CACHE["glog_reg"] = (
                games
                .assign(**{"PLAYER_ID": games["player_id"]})
                .rename(columns={
                    "game_id": "GAME_ID",
                    "game_date": "GAME_DATE",
                    **{s: s.upper() for s in _CORE_STATS},
                })
                [["PLAYER_ID", "GAME_ID", "GAME_DATE"] + [s.upper() for s in _CORE_STATS]]
            )
            mod._SRC_CACHE["glog_ply"] = None
            mod._SRC_CACHE["pqs"] = None
            mod._SRC_CACHE["adv"] = None

            section = PlayerMonthlyForm()
            art = section.build(pid, _dt.datetime(2025, 6, 1))
            assert art is None, "Expected None with only 3 games"
        finally:
            mod._SRC_CACHE.clear()
            mod._SRC_CACHE.update(old_cache)


# ---------------------------------------------------------------------------
# Unit tests on helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    """Unit tests for _compute_monthly, _compute_last15, _compute_summary."""

    def test_compute_monthly_groups_by_month(self):
        games = _make_games(20, "2025-01-01")
        monthly = _compute_monthly(games)
        # 20 games at 3-day intervals starting Jan 1 spans ~60 days = Jan+Feb+Mar
        assert len(monthly) >= 1, "Expected at least 1 month"
        for ym, stats in monthly.items():
            assert "n_games" in stats
            assert stats["n_games"] >= 1

    def test_compute_last15_returns_slope_keys(self):
        games = _make_games(20)
        last15 = _compute_last15(games)
        for stat in _CORE_STATS:
            assert f"{stat}_slope" in last15
            assert f"{stat}_mean" in last15

    def test_compute_last15_uses_only_last_15(self):
        """Slope is computed on at most 15 games, not all games."""
        games = _make_games(30)
        last15 = _compute_last15(games)
        assert last15["n_games"] == 15

    def test_compute_last15_with_fewer_than_min(self):
        """Slopes are None when fewer than _MIN_GAMES_FOR_SLOPE games."""
        games = _make_games(3)
        last15 = _compute_last15(games)
        for stat in _CORE_STATS:
            assert last15[f"{stat}_slope"] is None

    def test_compute_summary_averages(self):
        games = _make_games(10)
        # Force known pts values
        games["pts"] = 20.0
        summary = _compute_summary(games)
        assert summary["n_games"] == 10
        assert abs(summary["pts_pg"] - 20.0) < 1e-4

    def test_monthly_n_games_sums_to_total(self):
        games = _make_games(20)
        monthly = _compute_monthly(games)
        total = sum(v["n_games"] for v in monthly.values())
        assert total == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
