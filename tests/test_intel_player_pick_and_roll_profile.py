"""Tests for intel/player_pick_and_roll_profile.py.

Covers:
  - Leak-safety: rebuilding at an earlier as_of never reads data after that date.
  - Schema conformance: required sub-field keys, proportion ranges, CV slot contract.
  - Coverage (n >= 5): provenance n reflects actual game rows, not seasons.
  - Validate method: returns True on a well-formed artifact, False on violations.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Ensure repo root is on sys.path so src.loop imports resolve
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intel.player_pick_and_roll_profile import (
    PlayerPickAndRollProfile,
    _playtypes_pnr,
    _tracking_pnr,
    _pbp_pnr,
    _SRC_CACHE,
)
from src.loop.atlas import AtlasArtifact, CVSlot, confidence_from_n

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JOKIC_ID = 203999
CURRY_ID = 201939
AS_OF_NOW = _dt.datetime(2026, 5, 31, 0, 0, 0)
AS_OF_EARLY = _dt.datetime(2020, 1, 1, 0, 0, 0)  # before either player had current data

SECTION = PlayerPickAndRollProfile()


def _make_artifact(
    pid: int = JOKIC_ID,
    n: int = 10,
    handler_freq: Optional[float] = 0.15,
    handler_ppp: Optional[float] = 1.10,
    drive_tov_rate: Optional[float] = 0.08,
    drive_fg_pct: Optional[float] = 0.55,
) -> AtlasArtifact:
    """Build a minimal valid artifact for schema-conformance tests."""
    as_of_str = AS_OF_NOW.date().isoformat()
    sub_fields: Dict[str, Any] = {
        "handler": {
            "freq_pct": handler_freq,
            "ppp": handler_ppp,
            "pnr_handler_pg": 1.2,
        },
        "roll_man": {
            "freq_pct": 0.10,
            "ppp": 1.25,
            "pnr_screener_pg": 2.5,
        },
        "passing": {
            "passes_per_drive": 0.35,
            "ast_per_drive": 0.12,
            "drive_tov_rate": drive_tov_rate,
            "drive_fg_pct": drive_fg_pct,
            "drive_count_pg": 4.5,
        },
        "coverage_splits": {
            "_note": "DEFER",
            "drop_ppp": None,
            "switch_ppp": None,
            "blitz_ppp": None,
        },
        "scheme_context": {
            "league_drop_score_mean": -0.05,
            "n_teams_in_scheme_atlas": 30,
            "most_common_defense_tag": "SWITCH HEAVY",
        },
    }
    conf = confidence_from_n(n)
    prov = {"source": "test", "n": n, "confidence": conf, "as_of": as_of_str}
    return AtlasArtifact(
        section=SECTION.name,
        entity=SECTION.entity,
        entity_id=pid,
        value=handler_ppp,
        sub_fields=sub_fields,
        provenance=prov,
        confidence=conf,
        as_of=as_of_str,
        cv_fields=SECTION.cv_fields(),
    )


# ---------------------------------------------------------------------------
# Schema-conformance tests
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Validate that the section name, entity, and CV slots match the spec."""

    def test_section_name(self) -> None:
        assert SECTION.name == "pick_and_roll_profile"

    def test_entity_is_player(self) -> None:
        assert SECTION.entity == "player"

    def test_cv_fields_keys(self) -> None:
        slots = SECTION.cv_fields()
        assert "screen_navigation" in slots
        assert "pocket_pass_window" in slots

    def test_cv_field_values_are_none(self) -> None:
        for slot in SECTION.cv_fields().values():
            assert slot.value is None, f"CV slot {slot.name} must be None before CV fills it"

    def test_cv_field_types_are_float(self) -> None:
        for slot in SECTION.cv_fields().values():
            assert slot.dtype == "float"

    def test_artifact_required_keys(self) -> None:
        art = _make_artifact()
        required = {"handler", "roll_man", "passing", "coverage_splits", "scheme_context"}
        assert required.issubset(art.sub_fields.keys())

    def test_validate_returns_true_for_valid_artifact(self) -> None:
        art = _make_artifact()
        assert SECTION.validate(art) is True

    def test_validate_rejects_wrong_section(self) -> None:
        art = _make_artifact()
        art.section = "wrong_section"
        assert SECTION.validate(art) is False

    def test_validate_rejects_wrong_entity(self) -> None:
        art = _make_artifact()
        art.entity = "team"
        assert SECTION.validate(art) is False

    def test_validate_rejects_missing_required_key(self) -> None:
        art = _make_artifact()
        del art.sub_fields["handler"]
        assert SECTION.validate(art) is False

    def test_validate_rejects_out_of_range_freq_pct(self) -> None:
        """freq_pct > 1.6 must fail face-validity."""
        art = _make_artifact(handler_freq=2.5)  # clearly > 1.6
        assert SECTION.validate(art) is False

    def test_validate_rejects_out_of_range_drive_tov_rate(self) -> None:
        """drive_tov_rate > 1.0 must fail."""
        art = _make_artifact(drive_tov_rate=1.5)
        assert SECTION.validate(art) is False

    def test_validate_rejects_negative_drive_fg_pct(self) -> None:
        """drive_fg_pct < 0 must fail."""
        art = _make_artifact(drive_fg_pct=-0.1)
        assert SECTION.validate(art) is False

    def test_validate_rejects_filled_cv_slot(self) -> None:
        """If a CV slot has a non-None value the artifact is not yet in 'reserved' state."""
        art = _make_artifact()
        art.cv_fields["screen_navigation"].value = 0.72
        assert SECTION.validate(art) is False

    def test_freq_pct_none_is_valid(self) -> None:
        """None freq_pct (player absent from playtypes) is a valid deferred value."""
        art = _make_artifact(handler_freq=None)
        assert SECTION.validate(art) is True

    def test_to_profile_payload_roundtrip(self) -> None:
        """Confirm to_profile_payload embeds _cv_fields."""
        art = _make_artifact()
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data
        assert "screen_navigation" in data["_cv_fields"]
        assert "pocket_pass_window" in data["_cv_fields"]
        assert data["_cv_fields"]["screen_navigation"]["value"] is None
        assert prov["n"] == 10


# ---------------------------------------------------------------------------
# Leak-safety tests (mock pbp_possession_features with game_date column)
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that _pbp_pnr filters to game_date <= as_of."""

    def _make_pbp_df(self) -> pd.DataFrame:
        """Synthetic pbp possession features with games spread across dates."""
        dates = pd.date_range("2023-10-01", periods=20, freq="7D")
        rows = []
        for d in dates:
            rows.append({
                "player_id": JOKIC_ID,
                "game_id": f"g{d.strftime('%Y%m%d')}",
                "game_date": d,
                "pbp_pnr_ball_handler": 1.0,
                "pbp_pnr_screener_proxy": 3.0,
                "pbp_avg_seconds_per_touch": 400.0,
                "pbp_transition_count": 0.5,
            })
        return pd.DataFrame(rows)

    def test_pbp_filters_future_games(self) -> None:
        """Games after as_of must be excluded from n."""
        full_df = self._make_pbp_df()
        cutoff = _dt.datetime(2024, 1, 1, 0, 0, 0)
        expected_n = int((full_df["game_date"] <= pd.Timestamp(cutoff)).sum())

        with patch.dict(_SRC_CACHE, {"pbp_poss": full_df}, clear=False):
            result = _pbp_pnr(JOKIC_ID, cutoff)
        assert result["n_games"] == expected_n

    def test_pbp_full_date_range_returns_all_rows(self) -> None:
        """Using a far-future as_of must return all rows."""
        full_df = self._make_pbp_df()
        future = _dt.datetime(2099, 1, 1, 0, 0, 0)

        with patch.dict(_SRC_CACHE, {"pbp_poss": full_df}, clear=False):
            result = _pbp_pnr(JOKIC_ID, future)
        assert result["n_games"] == len(full_df)

    def test_pbp_early_cutoff_returns_zero_rows(self) -> None:
        """as_of before all game dates must return empty dict (no rows pass filter)."""
        full_df = self._make_pbp_df()
        before_all = _dt.datetime(2020, 1, 1, 0, 0, 0)

        with patch.dict(_SRC_CACHE, {"pbp_poss": full_df}, clear=False):
            result = _pbp_pnr(JOKIC_ID, before_all)
        assert result == {}

    def test_build_provenance_as_of_matches_input(self) -> None:
        """The artifact's as_of must equal the input as_of date string."""
        full_df = self._make_pbp_df()
        cutoff = _dt.datetime(2024, 3, 15, 0, 0, 0)

        with patch.dict(_SRC_CACHE, {"pbp_poss": full_df}, clear=False):
            art = SECTION.build(JOKIC_ID, cutoff)
        if art is not None:
            assert art.as_of == "2024-03-15"
            assert art.provenance["as_of"] == "2024-03-15"


# ---------------------------------------------------------------------------
# Coverage tests (n must come from real game rows)
# ---------------------------------------------------------------------------

class TestCoverage:
    """Verify that provenance n reflects actual game-row count, not seasons."""

    def _make_pbp_for(self, pid: int, n_games: int) -> pd.DataFrame:
        dates = pd.date_range("2024-01-01", periods=n_games, freq="3D")
        return pd.DataFrame({
            "player_id": [pid] * n_games,
            "game_id": [f"g{i}" for i in range(n_games)],
            "game_date": dates,
            "pbp_pnr_ball_handler": [1.0] * n_games,
            "pbp_pnr_screener_proxy": [2.0] * n_games,
            "pbp_avg_seconds_per_touch": [400.0] * n_games,
            "pbp_transition_count": [0.5] * n_games,
        })

    def test_n_equals_game_row_count(self) -> None:
        """n in provenance must equal the number of pbp game rows filtered <= as_of."""
        pid = 999001
        n_games = 30
        pbp_df = self._make_pbp_for(pid, n_games)
        future = _dt.datetime(2099, 1, 1)

        # Also inject a minimal playtypes row so build() doesn't return None
        pt_df = pd.DataFrame([{
            "player_id": pid, "season": "2024-25",
            "play_type": "PRBallHandler", "freq_pct": 0.12, "ppp": 1.05,
        }])

        with patch.dict(_SRC_CACHE, {"pbp_poss": pbp_df, "pt26": pt_df}, clear=False):
            art = SECTION.build(pid, future)

        assert art is not None
        assert art.provenance["n"] == n_games

    def test_n_at_least_5_yields_med_or_high(self) -> None:
        """5 game rows must yield at least 'med' confidence."""
        pid = 999002
        n_games = 7
        pbp_df = self._make_pbp_for(pid, n_games)
        pt_df = pd.DataFrame([{
            "player_id": pid, "season": "2024-25",
            "play_type": "PRBallHandler", "freq_pct": 0.10, "ppp": 0.95,
        }])
        future = _dt.datetime(2099, 1, 1)

        with patch.dict(_SRC_CACHE, {"pbp_poss": pbp_df, "pt26": pt_df}, clear=False):
            art = SECTION.build(pid, future)

        assert art is not None
        assert art.confidence in ("med", "high")
        assert art.provenance["n"] >= 5

    def test_n_from_seasonal_only_is_not_inflated(self) -> None:
        """If pbp is absent, n comes from the fallback path and will be 1 (low)."""
        pid = 999003
        pt_df = pd.DataFrame([{
            "player_id": pid, "season": "2024-25",
            "play_type": "PRBallHandler", "freq_pct": 0.10, "ppp": 0.95,
        }])
        empty_pbp = pd.DataFrame(columns=[
            "player_id", "game_id", "game_date",
            "pbp_pnr_ball_handler", "pbp_pnr_screener_proxy",
            "pbp_avg_seconds_per_touch", "pbp_transition_count",
        ])
        future = _dt.datetime(2099, 1, 1)

        with patch.dict(_SRC_CACHE, {"pbp_poss": empty_pbp, "pt26": pt_df}, clear=False):
            art = SECTION.build(pid, future)

        # When only playtypes data is available, n falls back to 1 -> confidence='low'
        assert art is not None
        assert art.provenance["n"] == 1
        assert art.confidence == "low"


# ---------------------------------------------------------------------------
# Proportion-range tests
# ---------------------------------------------------------------------------

class TestProportionRanges:
    """All _pct/_rate fields must stay within their declared bounds."""

    def _make_playtypes(self, pid: int, freq: float) -> pd.DataFrame:
        return pd.DataFrame([{
            "player_id": pid, "season": "2024-25",
            "play_type": "PRBallHandler", "freq_pct": freq, "ppp": 1.0,
        }])

    def test_freq_pct_out_of_range_is_nulled(self) -> None:
        """freq_pct > 1.6 is impossible from playtypes API; _pct_guard should null it."""
        from intel.player_pick_and_roll_profile import _pct_guard
        assert _pct_guard(1.7, ceil=1.6) is None
        assert _pct_guard(0.15, ceil=1.6) == 0.15

    def test_drive_tov_rate_in_range(self) -> None:
        """drive_tov_rate must be None or in [0, 1]."""
        trk_df = pd.DataFrame([{
            "player_id": 999004, "season": "2024-25",
            "trk_drv_count": 5.0, "trk_drv_pts": 10.0,
            "trk_drv_fg_pct": 0.55, "trk_drv_passes": 1.5,
            "trk_drv_ast": 0.6, "trk_drv_tov_pct": 0.08,
        }])
        with patch.dict(_SRC_CACHE, {"trk26": trk_df}, clear=False):
            result = _tracking_pnr(999004, AS_OF_NOW)
        rate = result.get("drive_tov_rate")
        assert rate is None or 0.0 <= rate <= 1.0

    def test_drive_fg_pct_in_range(self) -> None:
        """drive_fg_pct must be None or in [0, 1]."""
        trk_df = pd.DataFrame([{
            "player_id": 999005, "season": "2024-25",
            "trk_drv_count": 4.0, "trk_drv_pts": 8.0,
            "trk_drv_fg_pct": 0.62, "trk_drv_passes": 1.0,
            "trk_drv_ast": 0.4, "trk_drv_tov_pct": 0.05,
        }])
        with patch.dict(_SRC_CACHE, {"trk26": trk_df}, clear=False):
            result = _tracking_pnr(999005, AS_OF_NOW)
        pct = result.get("drive_fg_pct")
        assert pct is None or 0.0 <= pct <= 1.0


# ---------------------------------------------------------------------------
# Live integration smoke tests (real parquets on disk)
# ---------------------------------------------------------------------------

class TestLiveIntegration:
    """Quick end-to-end build for Jokic and Curry using real on-disk data.

    These tests are skipped when the parquets are absent (CI without data).
    """

    @pytest.fixture(autouse=True)
    def clear_cache(self) -> None:
        """Clear the module-level source cache between live tests."""
        _SRC_CACHE.clear()

    def _parquets_available(self) -> bool:
        return (ROOT / "data" / "playtypes_2025-26.parquet").exists()

    def test_jokic_builds_artifact(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(JOKIC_ID, AS_OF_NOW)
        assert art is not None, "Jokic build returned None"
        assert art.section == "pick_and_roll_profile"
        assert art.entity == "player"
        assert art.entity_id == JOKIC_ID

    def test_jokic_n_gte_5(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(JOKIC_ID, AS_OF_NOW)
        assert art is not None
        assert art.provenance["n"] >= 5, (
            f"Jokic n={art.provenance['n']} < 5; "
            "n must come from game rows, not season count"
        )

    def test_curry_builds_artifact(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(CURRY_ID, AS_OF_NOW)
        assert art is not None, "Curry build returned None"
        assert art.provenance["n"] >= 5, (
            f"Curry n={art.provenance['n']} < 5"
        )

    def test_jokic_validate_passes(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(JOKIC_ID, AS_OF_NOW)
        assert art is not None
        assert SECTION.validate(art), "Jokic artifact failed validate()"

    def test_curry_validate_passes(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(CURRY_ID, AS_OF_NOW)
        assert art is not None
        assert SECTION.validate(art), "Curry artifact failed validate()"

    def test_jokic_handler_freq_in_range(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(JOKIC_ID, AS_OF_NOW)
        assert art is not None
        freq = art.sub_fields["handler"].get("freq_pct")
        if freq is not None:
            assert 0.0 <= freq <= 1.6, f"handler.freq_pct={freq} out of range"

    def test_curry_handler_freq_in_range(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(CURRY_ID, AS_OF_NOW)
        assert art is not None
        freq = art.sub_fields["handler"].get("freq_pct")
        if freq is not None:
            assert 0.0 <= freq <= 1.6, f"handler.freq_pct={freq} out of range"

    def test_cv_fields_reserved_null(self) -> None:
        if not self._parquets_available():
            pytest.skip("data parquets not available")
        art = SECTION.build(JOKIC_ID, AS_OF_NOW)
        assert art is not None
        for name, slot in art.cv_fields.items():
            assert slot.value is None, f"CV slot {name} must be None"
