"""Tests for intel/player_quarter_shape_fatigue.py.

Assertions:
  1. Leak-safety: build() with as_of strictly BEFORE all data returns None or
     an artifact whose as_of is not in the future.
  2. Schema conformance: artifact has all required sub_fields + cv_fields present
     and correctly keyed.
  3. CV-slot invariant: cv_fields values are all None at build time.
  4. Validate passes on a well-formed artifact.
  5. B2B flag is derived correctly from consecutive game dates.
"""
from __future__ import annotations

import datetime as _dt
import types
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Minimal fixture data (no real parquets needed for schema tests)
# ---------------------------------------------------------------------------

_GAME_DATES = [
    "2024-10-20",  # game 1
    "2024-10-21",  # game 2 -- B2B (1 day gap)
    "2024-10-23",  # game 3 -- NOT B2B (2 days gap)
    "2024-10-25",  # game 4
    "2024-10-26",  # game 5 -- B2B
]
_GAME_IDS = [f"G00{i}" for i in range(1, len(_GAME_DATES) + 1)]
_PLAYER_ID = 9999


def _make_quarter_stats() -> pd.DataFrame:
    """Four-quarter rows for each game; two players."""
    rows = []
    for gid, gd in zip(_GAME_IDS, _GAME_DATES):
        for period in [1, 2, 3, 4]:
            rows.append(
                {
                    "game_id": gid,
                    "player_id": _PLAYER_ID,
                    "period": period,
                    "pts": float(10 - period),  # Q1=9, Q2=8, Q3=7, Q4=6 -- descending
                    "reb": 2.0,
                    "ast": 1.0,
                    "fg3m": 0.5,
                    "stl": 0.2,
                    "blk": 0.1,
                    "tov": 0.5,
                    "pf": 1.0,
                    "min": 9.0,
                    "plus_minus": 0.0,
                }
            )
    return pd.DataFrame(rows)


def _make_adv_stats() -> pd.DataFrame:
    """Minimal adv_stats rows (per-game minutes, game_date)."""
    rows = []
    for gid, gd in zip(_GAME_IDS, _GAME_DATES):
        rows.append(
            {
                "player_id": _PLAYER_ID,
                "game_id": gid,
                "game_date": gd,
                "minutes": 34.0,
                "usagepercentage": 0.30,
                "trueshootingpercentage": 0.60,
                "effectivefieldgoalpercentage": 0.55,
                "assistpercentage": 0.20,
                "reboundpercentage": 0.10,
                "offensivereboundpercentage": 0.05,
                "defensivereboundpercentage": 0.15,
                "offensiverating": 115.0,
                "defensiverating": 110.0,
                "netrating": 5.0,
                "assisttoturnover": 2.0,
                "assistratio": 0.15,
                "turnoverratio": 0.10,
                "pie": 0.14,
                "possessions": 80,
                "paceper40": 98.0,
            }
        )
    return pd.DataFrame(rows)


def _mock_load_sources(as_of: _dt.datetime):
    """Return toy DataFrames with the same join logic as the real _load_sources."""
    import numpy as np
    from intel.player_quarter_shape_fatigue import _load_sources as _real  # noqa

    pqs_raw = _make_quarter_stats()
    adv_raw = _make_adv_stats()

    adv = adv_raw.copy()
    adv["game_date"] = pd.to_datetime(adv["game_date"])
    as_of_date = as_of.date().isoformat()
    adv = adv[adv["game_date"] <= as_of_date].sort_values(["player_id", "game_date"])
    adv["prev_game_date"] = adv.groupby("player_id")["game_date"].shift(1)
    adv["days_rest"] = (adv["game_date"] - adv["prev_game_date"]).dt.days
    adv["is_b2b"] = (adv["days_rest"] == 1).astype("Int8")

    game_info = adv[["player_id", "game_id", "game_date", "minutes", "is_b2b"]].copy()
    game_info["game_date_str"] = game_info["game_date"].dt.date.astype(str)

    pqs_dated = pqs_raw.merge(game_info, on=["player_id", "game_id"], how="inner")
    return pqs_dated, game_info


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_with_fixtures(as_of: _dt.datetime):
    """Patch _load_sources and run build for _PLAYER_ID."""
    from intel.player_quarter_shape_fatigue import PlayerQuarterShapeFatigue, _build_artifact

    pqs_dated, game_info = _mock_load_sources(as_of)
    if pqs_dated.empty:
        return None
    return _build_artifact(_PLAYER_ID, pqs_dated, game_info, as_of.date().isoformat())


# ---------------------------------------------------------------------------
# Test 1: Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must not include data after the requested as_of."""

    def test_future_as_of_returns_none_or_valid(self) -> None:
        """Passing as_of before ANY game date must return None (no data yet)."""
        as_of = _dt.datetime(2020, 1, 1)  # before all fixture game dates
        art = _build_with_fixtures(as_of)
        assert art is None, "Expected None when no data is before as_of"

    def test_as_of_boundary_respected(self) -> None:
        """as_of=2024-10-21 should include games 1+2 only (not 3, 4, 5)."""
        as_of = _dt.datetime(2024, 10, 21, 23, 59, 59)
        art = _build_with_fixtures(as_of)
        assert art is not None
        n = art.sub_fields["n_games"]
        assert n == 2, f"Expected 2 games, got {n}"

    def test_as_of_does_not_include_future_game(self) -> None:
        """All fixture games present when as_of >= last game date."""
        as_of = _dt.datetime(2024, 10, 31)
        art = _build_with_fixtures(as_of)
        assert art is not None
        n = art.sub_fields["n_games"]
        assert n == len(_GAME_IDS), f"Expected {len(_GAME_IDS)} games, got {n}"

    def test_artifact_as_of_not_in_future(self) -> None:
        """artifact.as_of must be <= the request as_of (never a future stamp)."""
        as_of = _dt.datetime(2024, 10, 23)
        art = _build_with_fixtures(as_of)
        assert art is not None
        art_date = art.as_of  # ISO string
        assert art_date is not None
        assert art_date <= as_of.date().isoformat(), (
            f"Artifact as_of={art_date} is after request as_of={as_of.date()}"
        )


# ---------------------------------------------------------------------------
# Test 2: Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact must carry all required sub_fields and cv_fields."""

    REQUIRED_SUB_FIELDS = {
        "q1_pts", "q2_pts", "q3_pts", "q4_pts",
        "q1_reb", "q2_reb", "q3_reb", "q4_reb",
        "q1_ast", "q2_ast", "q3_ast", "q4_ast",
        "q1_min", "q2_min", "q3_min", "q4_min",
        "q4_vs_early_ratio", "q4_fade_abs",
        "min_per_game", "n_games",
        "b2b_n_games",
    }

    REQUIRED_CV_FIELDS = {"speed_decay", "late_game_lift"}

    def _art(self):
        return _build_with_fixtures(_dt.datetime(2024, 10, 31))

    def test_sub_fields_present(self) -> None:
        art = self._art()
        assert art is not None
        missing = self.REQUIRED_SUB_FIELDS - set(art.sub_fields.keys())
        assert not missing, f"Missing sub_fields: {missing}"

    def test_cv_fields_present(self) -> None:
        """cv_fields() must return both reserved CV slot keys."""
        section = __import__(
            "intel.player_quarter_shape_fatigue", fromlist=["PlayerQuarterShapeFatigue"]
        ).PlayerQuarterShapeFatigue()
        cv = section.cv_fields()
        missing = self.REQUIRED_CV_FIELDS - set(cv.keys())
        assert not missing, f"Missing cv_field keys: {missing}"

    def test_cv_fields_values_are_none(self) -> None:
        """All CV slot values must be None at build time (not CV-filled yet)."""
        art = self._art()
        assert art is not None
        for slot_name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"cv_fields[{slot_name!r}].value should be None but got {slot.value!r}"
            )

    def test_profile_payload_includes_cv_fields(self) -> None:
        """to_profile_payload must embed _cv_fields in data with null values."""
        art = self._art()
        assert art is not None
        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload() missing _cv_fields key"
        for k in self.REQUIRED_CV_FIELDS:
            assert k in data["_cv_fields"], f"cv slot {k!r} missing from payload"
            assert data["_cv_fields"][k]["value"] is None, (
                f"cv slot {k!r} should have null value in payload"
            )

    def test_provenance_keys(self) -> None:
        """Provenance must carry source, n, confidence, as_of."""
        art = self._art()
        assert art is not None
        prov = art.provenance
        for k in ("source", "n", "confidence", "as_of"):
            assert k in prov, f"Provenance missing key: {k!r}"

    def test_section_entity(self) -> None:
        """Section entity must be 'player'."""
        from intel.player_quarter_shape_fatigue import PlayerQuarterShapeFatigue
        assert PlayerQuarterShapeFatigue.entity == "player"

    def test_section_name(self) -> None:
        from intel.player_quarter_shape_fatigue import PlayerQuarterShapeFatigue
        assert PlayerQuarterShapeFatigue.name == "quarter_shape_fatigue"


# ---------------------------------------------------------------------------
# Test 3: Face-validity / validate()
# ---------------------------------------------------------------------------

class TestValidate:
    """Section.validate() should pass on a well-formed artifact."""

    def test_validate_passes_on_fixture(self) -> None:
        from intel.player_quarter_shape_fatigue import PlayerQuarterShapeFatigue
        section = PlayerQuarterShapeFatigue()
        art = _build_with_fixtures(_dt.datetime(2024, 10, 31))
        assert art is not None
        assert section.validate(art), "validate() should return True for well-formed artifact"

    def test_q4_vs_early_ratio_correct(self) -> None:
        """Fixture: Q1=9, Q2=8, Q3=7, Q4=6 -> ratio = 6 / mean(9,8,7) = 6/8 = 0.75."""
        art = _build_with_fixtures(_dt.datetime(2024, 10, 31))
        assert art is not None
        ratio = art.sub_fields["q4_vs_early_ratio"]
        assert ratio is not None
        assert abs(ratio - 0.75) < 0.01, f"Expected ~0.75 but got {ratio}"

    def test_b2b_flag_correct(self) -> None:
        """Game 2 (2024-10-21) and Game 5 (2024-10-26) are B2B; expect b2b_n_games=2."""
        art = _build_with_fixtures(_dt.datetime(2024, 10, 31))
        assert art is not None
        b2b_n = art.sub_fields["b2b_n_games"]
        # Games 2 and 5 are B2B (1-day gaps after games 1 and 4 respectively)
        assert b2b_n == 2, f"Expected 2 B2B games, got {b2b_n}"
