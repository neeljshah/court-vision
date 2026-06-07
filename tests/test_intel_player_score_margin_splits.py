"""Tests for intel/player_score_margin_splits.py.

Covers:
  1. Leak-safety: a build at an earlier as_of must not include games after that date.
  2. Schema conformance: required sub-fields present, proportions in valid ranges,
     CV slots declared null.
  3. n >= 5 threshold: provenance n reflects actual game count (not season count).
  4. efg_pct bounds: [0, 1.6] per validator eFG ceiling rule.
  5. fg3a_rate bounds: [0, 1].
  6. Per-game rates non-negative.
  7. validate() passes for a well-formed artifact.
  8. build() returns None for an unknown player_id.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_score_margin_splits import (
    PlayerScoreMarginSplits,
    _parse_min,
    _score_state,
    _list_qbox_files,
    _LEADING_THRESH,
    _TRAILING_THRESH,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_artifact(
    section: PlayerScoreMarginSplits,
    leading: Optional[dict] = None,
    tied: Optional[dict] = None,
    trailing: Optional[dict] = None,
    n: int = 20,
    as_of_str: str = "2026-01-01",
) -> AtlasArtifact:
    """Construct a synthetic AtlasArtifact for section self-validation tests."""
    sub_fields: Dict[str, Any] = {
        "leading": leading,
        "tied": tied,
        "trailing": trailing,
        "pace": {"_note": "DEFER"},
        "shot_mix": {"_note": "DEFER"},
        "_thresholds": {
            "leading_min_lead": _LEADING_THRESH,
            "trailing_max_lead": _TRAILING_THRESH,
        },
    }
    confidence = "high" if n >= 20 else "med" if n >= 5 else "low"
    return AtlasArtifact(
        section=section.name,
        entity=section.entity,
        entity_id=999,
        value=None,
        sub_fields=sub_fields,
        provenance={"source": "test", "n": n, "confidence": confidence, "as_of": as_of_str},
        confidence=confidence,
        as_of=as_of_str,
        cv_fields=section.cv_fields(),
    )


def _sample_bucket(
    efg_pct: float = 0.52,
    fg3a_rate: float = 0.35,
    pts_pg: float = 8.5,
) -> dict:
    return {
        "pts_pg": pts_pg,
        "reb_pg": 3.0,
        "ast_pg": 2.0,
        "fg3m_pg": 1.0,
        "fga_pg": 7.0,
        "efg_pct": efg_pct,
        "fg3a_rate": fg3a_rate,
        "min_pg": 10.0,
        "n_quarters": 10,
        "n_games": 5,
    }


# ---------------------------------------------------------------------------
# 1. _parse_min: MM:SS string parsing (Critical Lesson #2)
# ---------------------------------------------------------------------------

class TestParseMin:
    def test_mmss_string(self):
        assert abs(_parse_min("12:00") - 12.0) < 1e-6

    def test_mmss_partial_seconds(self):
        assert abs(_parse_min("6:28") - (6 + 28 / 60)) < 1e-4

    def test_float_passthrough(self):
        assert abs(_parse_min(9.5) - 9.5) < 1e-6

    def test_zero_string(self):
        assert _parse_min("0:00") == 0.0

    def test_none_returns_zero(self):
        assert _parse_min(None) == 0.0

    def test_plain_numeric_string(self):
        assert abs(_parse_min("12.5") - 12.5) < 1e-6

    def test_negative_float_clamps_to_zero(self):
        assert _parse_min(-1.0) == 0.0


# ---------------------------------------------------------------------------
# 2. _score_state: state categorisation
# ---------------------------------------------------------------------------

class TestScoreState:
    def test_leading(self):
        assert _score_state(10.0) == "leading"

    def test_tied_upper_boundary(self):
        assert _score_state(5.0) == "tied"

    def test_tied_lower_boundary(self):
        assert _score_state(-5.0) == "tied"

    def test_trailing(self):
        assert _score_state(-8.0) == "trailing"

    def test_exactly_zero(self):
        assert _score_state(0.0) == "tied"

    def test_just_above_leading_thresh(self):
        assert _score_state(5.1) == "leading"

    def test_just_below_trailing_thresh(self):
        assert _score_state(-5.1) == "trailing"


# ---------------------------------------------------------------------------
# 3. Schema conformance (validate)
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """validate() must pass for well-formed artifacts, fail for malformed ones."""

    def setup_method(self):
        self.sec = PlayerScoreMarginSplits()

    def test_valid_artifact_passes(self):
        art = _make_artifact(
            self.sec,
            leading=_sample_bucket(),
            tied=_sample_bucket(),
            trailing=_sample_bucket(),
        )
        assert self.sec.validate(art) is True

    def test_missing_required_key_fails(self):
        art = _make_artifact(self.sec, leading=_sample_bucket())
        # Remove 'pace' key
        del art.sub_fields["pace"]
        assert self.sec.validate(art) is False

    def test_wrong_section_name_fails(self):
        art = _make_artifact(self.sec, leading=_sample_bucket())
        art.section = "wrong_section"
        assert self.sec.validate(art) is False

    def test_wrong_entity_fails(self):
        art = _make_artifact(self.sec, leading=_sample_bucket())
        art.entity = "team"
        assert self.sec.validate(art) is False

    def test_efg_pct_above_ceiling_fails(self):
        """eFG% above 1.6 is invalid per validator eFG ceiling rule."""
        bucket = _sample_bucket(efg_pct=1.7)
        art = _make_artifact(self.sec, leading=bucket)
        assert self.sec.validate(art) is False

    def test_efg_pct_negative_fails(self):
        bucket = _sample_bucket(efg_pct=-0.1)
        art = _make_artifact(self.sec, leading=bucket)
        assert self.sec.validate(art) is False

    def test_fg3a_rate_above_1_fails(self):
        """fg3a_rate is a proportion ending in _rate -> must be in [0, 1]."""
        bucket = _sample_bucket(fg3a_rate=1.05)
        art = _make_artifact(self.sec, leading=bucket)
        assert self.sec.validate(art) is False

    def test_negative_pts_pg_fails(self):
        bucket = _sample_bucket(pts_pg=-1.0)
        art = _make_artifact(self.sec, leading=bucket)
        assert self.sec.validate(art) is False

    def test_none_bucket_allowed(self):
        """A None state bucket is valid (player may not have leading quarters)."""
        art = _make_artifact(
            self.sec, leading=None, tied=_sample_bucket(), trailing=None
        )
        assert self.sec.validate(art) is True

    def test_cv_slot_with_non_null_value_fails(self):
        art = _make_artifact(self.sec, leading=_sample_bucket())
        # Inject a non-null CV slot value (forbidden until CV branch runs)
        art.cv_fields["cv_usage_leading"] = CVSlot(
            name="cv_usage_leading", dtype="float", value=0.25
        )
        assert self.sec.validate(art) is False


# ---------------------------------------------------------------------------
# 4. CV-slot schema
# ---------------------------------------------------------------------------

class TestCVSlots:
    def setup_method(self):
        self.sec = PlayerScoreMarginSplits()

    def test_cv_slots_declared(self):
        slots = self.sec.cv_fields()
        assert "cv_usage_leading" in slots
        assert "cv_usage_trailing" in slots
        assert "cv_drive_rate_trailing" in slots

    def test_cv_slot_values_null(self):
        """All CV slot values must be None until CV branch fills them."""
        for name, slot in self.sec.cv_fields().items():
            assert slot.value is None, f"CV slot {name} must be None"

    def test_cv_slot_dtypes_valid(self):
        valid_dtypes = {"float", "dist", "list", "categorical", "int"}
        for name, slot in self.sec.cv_fields().items():
            assert slot.dtype in valid_dtypes, f"CV slot {name} has invalid dtype"


# ---------------------------------------------------------------------------
# 5. Leak-safety: build at earlier as_of must not include future games
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that build(pid, as_of) only includes games with game_date <= as_of.

    Patches:
      - mod._load_game_date_map  -> returns a controlled game_id -> date dict
      - mod._load_qbox           -> returns a minimal per-quarter dict
      - mod._list_qbox_files     -> returns a list of synthetic Path objects
    All three are module-level functions and can be patched cleanly on Python 3.9+.
    """

    def setup_method(self):
        self.sec = PlayerScoreMarginSplits()

    def _build_with_mock_data(
        self, as_of: _dt.datetime, game_dates: Dict[str, str], pid: int = 9999
    ) -> int:
        """Inject controlled data and return provenance n (0 if artifact is None)."""
        import intel.player_score_margin_splits as mod

        def fake_load_qbox(game_id: str) -> Dict[int, dict]:
            if game_id not in game_dates:
                return {}
            return {
                1: {
                    "teams": [
                        {"team_abbreviation": "TST", "pts": 28},
                        {"team_abbreviation": "OPP", "pts": 30},
                    ],
                    "players": [{
                        "player_id": pid,
                        "team_abbreviation": "TST",
                        "fgm": 3, "fga": 7, "fg3m": 1, "fg3a": 2,
                        "pts": 7, "reb": 4, "ast": 2, "min": "12:00",
                    }],
                }
            }

        fake_files = [
            Path(f"/fake/{gid}_q1.json") for gid in game_dates
        ]

        original_gd_map = mod._GAME_DATE_MAP
        original_qbox_cache = dict(mod._QBOX_CACHE)

        try:
            mod._QBOX_CACHE.clear()
            with mock.patch.object(mod, "_load_game_date_map", return_value=game_dates):
                with mock.patch.object(mod, "_load_qbox", side_effect=fake_load_qbox):
                    with mock.patch.object(mod, "_list_qbox_files", return_value=fake_files):
                        art = self.sec.build(pid, as_of)
        finally:
            mod._GAME_DATE_MAP = original_gd_map
            mod._QBOX_CACHE.clear()
            mod._QBOX_CACHE.update(original_qbox_cache)

        if art is None:
            return 0
        return int(art.provenance.get("n", 0))

    def test_future_games_excluded(self):
        """Games after as_of must not contribute to n."""
        game_dates = {
            "GAME_PAST": "2025-01-01",
            "GAME_FUTURE": "2025-12-31",
        }
        as_of = _dt.datetime(2025, 6, 1)
        n = self._build_with_mock_data(as_of, game_dates)
        # Only GAME_PAST should count
        assert n == 1, f"Expected n=1 (past game only), got n={n}"

    def test_boundary_date_included(self):
        """Game exactly on as_of date must be included."""
        game_dates = {
            "GAME_ON_DATE": "2025-06-01",
        }
        as_of = _dt.datetime(2025, 6, 1)
        n = self._build_with_mock_data(as_of, game_dates)
        assert n == 1, f"Expected n=1 (boundary date included), got n={n}"

    def test_day_before_as_of_excluded(self):
        """Building at as_of - 1 day must exclude the as_of-day game."""
        game_dates = {
            "GAME_ON_DATE": "2025-06-01",
        }
        as_of = _dt.datetime(2025, 5, 31)  # one day before
        n = self._build_with_mock_data(as_of, game_dates)
        assert n == 0, f"Expected n=0 (game on 06-01 excluded from 05-31 as_of), got n={n}"

    def test_provenance_as_of_matches_input(self):
        """The artifact's as_of must equal the input as_of date."""
        game_dates = {"GAME1": "2025-01-01"}
        as_of = _dt.datetime(2025, 6, 15)
        pid = 9999

        def fake_load_qbox(gid):
            return {1: {
                "teams": [
                    {"team_abbreviation": "TST", "pts": 25},
                    {"team_abbreviation": "OPP", "pts": 20},
                ],
                "players": [{
                    "player_id": pid,
                    "team_abbreviation": "TST",
                    "fgm": 3, "fga": 6, "fg3m": 1, "fg3a": 2,
                    "pts": 7, "reb": 3, "ast": 1, "min": "12:00",
                }],
            }}

        fake_files = [Path("/fake/GAME1_q1.json")]
        import intel.player_score_margin_splits as mod
        original_gd_map = mod._GAME_DATE_MAP
        original_qbox_cache = dict(mod._QBOX_CACHE)
        mod._QBOX_CACHE.clear()
        try:
            with mock.patch.object(mod, "_load_game_date_map", return_value=game_dates):
                with mock.patch.object(mod, "_load_qbox", side_effect=fake_load_qbox):
                    with mock.patch.object(mod, "_list_qbox_files", return_value=fake_files):
                        art = self.sec.build(pid, as_of)
        finally:
            mod._GAME_DATE_MAP = original_gd_map
            mod._QBOX_CACHE.clear()
            mod._QBOX_CACHE.update(original_qbox_cache)

        if art is not None:
            assert art.as_of == "2025-06-15"
            assert art.provenance["as_of"] == "2025-06-15"


# ---------------------------------------------------------------------------
# 6. Unknown player returns None
# ---------------------------------------------------------------------------

class TestUnknownPlayer:
    def test_build_unknown_player_returns_none(self):
        sec = PlayerScoreMarginSplits()
        # Use player_id that will not match any quarter_box JSON
        art = sec.build(entity_id=0, as_of=_dt.datetime(2020, 1, 1))
        # Should return None (no data for this player in the past)
        # Allow None or an artifact with n=0 (both are valid graceful failures)
        if art is not None:
            assert art.provenance.get("n", 0) == 0


# ---------------------------------------------------------------------------
# 7. n >= 5 for real players (integration, reads real data files)
# ---------------------------------------------------------------------------

class TestRealPlayerN:
    """Integration test: real quarter_box data must yield n >= 5 for star players."""

    @pytest.mark.skipif(
        not (ROOT / "data" / "cache" / "quarter_box").exists(),
        reason="quarter_box data not present",
    )
    def test_jokic_n_ge_5(self):
        sec = PlayerScoreMarginSplits()
        as_of = _dt.datetime(2026, 5, 31)
        art = sec.build(203999, as_of)
        assert art is not None, "Jokic should have score_margin_splits data"
        n = art.provenance.get("n", 0)
        assert n >= 5, f"Jokic n={n} is below min_n=5 threshold"

    @pytest.mark.skipif(
        not (ROOT / "data" / "cache" / "quarter_box").exists(),
        reason="quarter_box data not present",
    )
    def test_curry_n_ge_5(self):
        sec = PlayerScoreMarginSplits()
        as_of = _dt.datetime(2026, 5, 31)
        art = sec.build(201939, as_of)
        assert art is not None, "Curry should have score_margin_splits data"
        n = art.provenance.get("n", 0)
        assert n >= 5, f"Curry n={n} is below min_n=5 threshold"

    @pytest.mark.skipif(
        not (ROOT / "data" / "cache" / "quarter_box").exists(),
        reason="quarter_box data not present",
    )
    def test_validate_passes_for_real_player(self):
        sec = PlayerScoreMarginSplits()
        as_of = _dt.datetime(2026, 5, 31)
        art = sec.build(203999, as_of)
        if art is not None:
            assert sec.validate(art) is True, "validate() must pass for real Jokic data"

    @pytest.mark.skipif(
        not (ROOT / "data" / "cache" / "quarter_box").exists(),
        reason="quarter_box data not present",
    )
    def test_efg_in_range_real_player(self):
        """eFG% for a real player must be in [0, 1.6] across all state buckets."""
        sec = PlayerScoreMarginSplits()
        as_of = _dt.datetime(2026, 5, 31)
        art = sec.build(203999, as_of)
        if art is None:
            return
        for state in ("leading", "tied", "trailing"):
            bucket = art.sub_fields.get(state)
            if bucket is None:
                continue
            efg = bucket.get("efg_pct")
            if efg is not None:
                assert 0.0 <= efg <= 1.6, f"{state} efg_pct={efg} out of [0,1.6]"

    @pytest.mark.skipif(
        not (ROOT / "data" / "cache" / "quarter_box").exists(),
        reason="quarter_box data not present",
    )
    def test_fg3a_rate_in_range_real_player(self):
        """fg3a_rate must be in [0, 1] for all state buckets."""
        sec = PlayerScoreMarginSplits()
        as_of = _dt.datetime(2026, 5, 31)
        art = sec.build(203999, as_of)
        if art is None:
            return
        for state in ("leading", "tied", "trailing"):
            bucket = art.sub_fields.get(state)
            if bucket is None:
                continue
            rate = bucket.get("fg3a_rate")
            if rate is not None:
                assert 0.0 <= rate <= 1.0, f"{state} fg3a_rate={rate} out of [0,1]"
