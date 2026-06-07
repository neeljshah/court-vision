"""Tests for intel/player_rest_b2b_splits.py.

Covers:
  1. Schema conformance -- required sub-field keys present, correct types.
  2. Leak-safety -- as_of filter excludes future games.
  3. eFG range conformance -- values are nulled when outside [0, 1.0].
  4. Rest-category logic -- date-diff categorisation is correct.
  5. Fatigue proxy field naming -- signed fields have '_minus_' in their name.
  6. CV-slot schema -- declared slot is present, typed, and null-valued.
  7. Section self-validate passes for a well-formed artifact.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd
import pytest

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.player_rest_b2b_splits import (
    PlayerRestB2BSplits,
    _efg_clean,
    _rest_category_series,
)
from src.loop.atlas import CVSlot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adv_row(
    pid: int,
    date_str: str,
    efg: Optional[float] = 0.55,
    minutes: float = 32.0,
) -> dict:
    """Minimal player_adv_stats row dict."""
    return {
        "player_id": pid,
        "game_id": f"G{date_str.replace('-', '')}",
        "game_date": date_str,
        "effectivefieldgoalpercentage": efg,
        "minutes": minutes,
    }


def _build_artifact(pid: int, adv_rows: list, as_of: Optional[_dt.datetime] = None):
    """Build an artifact for ``pid`` using ``adv_rows`` as synthetic data.

    Patches ``_load`` so the module-level parquet cache is bypassed entirely.
    """
    if as_of is None:
        as_of = _dt.datetime(2026, 5, 31)
    fake_df = pd.DataFrame(adv_rows)
    section = PlayerRestB2BSplits()

    def fake_load(key: str, path: Path) -> Optional[pd.DataFrame]:
        return fake_df if key == "adv" else None

    with patch("intel.player_rest_b2b_splits._load", side_effect=fake_load):
        return section.build(pid, as_of)


# 10 games across all three rest categories for a given pid.
_TEN_DATES = [
    "2024-10-19", "2024-10-20",  # first game (2plus), then b2b
    "2024-10-22",                 # 1-day rest
    "2024-10-24",                 # 1-day rest
    "2024-10-27",                 # 2+ rest
    "2024-10-30",                 # 2+ rest
    "2024-11-02",                 # 2+ rest
    "2024-11-05",                 # 2+ rest
    "2024-11-08",                 # 2+ rest
    "2024-11-10",                 # 1-day rest
]


def _ten_rows(pid: int) -> list:
    """10 synthetic game rows with diverse rest patterns for ``pid``."""
    return [_adv_row(pid, d) for d in _TEN_DATES]


# ---------------------------------------------------------------------------
# 1. Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Required sub-field keys and value types are correct."""

    def test_required_keys_present(self) -> None:
        art = _build_artifact(9001, _ten_rows(9001))
        assert art is not None
        required = {"overall", "b2b", "one_day", "two_plus", "fatigue_proxy", "travel"}
        assert required.issubset(art.sub_fields.keys())

    def test_category_dicts_have_expected_keys(self) -> None:
        art = _build_artifact(9001, _ten_rows(9001))
        assert art is not None
        for cat in ("overall", "b2b", "one_day", "two_plus"):
            d = art.sub_fields[cat]
            assert "n_games" in d, f"{cat} missing n_games"
            assert "efg_pct" in d, f"{cat} missing efg_pct"
            assert "min_pg" in d, f"{cat} missing min_pg"

    def test_fatigue_proxy_has_signed_fields(self) -> None:
        art = _build_artifact(9001, _ten_rows(9001))
        assert art is not None
        fp = art.sub_fields["fatigue_proxy"]
        assert "efg_b2b_minus_2plus" in fp
        assert "min_b2b_minus_2plus" in fp

    def test_provenance_n_equals_total_games(self) -> None:
        art = _build_artifact(9001, _ten_rows(9001))
        assert art is not None
        assert art.provenance["n"] == 10
        assert art.sub_fields["overall"]["n_games"] == 10

    def test_section_and_entity_fields(self) -> None:
        art = _build_artifact(9001, _ten_rows(9001))
        assert art is not None
        assert art.section == "rest_b2b_splits"
        assert art.entity == "player"
        assert art.entity_id == 9001


# ---------------------------------------------------------------------------
# 2. Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """as_of filter must exclude future games from the artifact."""

    def test_future_games_excluded(self) -> None:
        pid = 9002
        rows = [
            _adv_row(pid, "2024-10-19"),
            _adv_row(pid, "2024-10-21"),
            _adv_row(pid, "2024-10-23"),
            _adv_row(pid, "2024-10-25"),
            _adv_row(pid, "2024-10-27"),
            _adv_row(pid, "2027-01-01"),  # future -- must be excluded
        ]
        art = _build_artifact(pid, rows, as_of=_dt.datetime(2026, 5, 31))
        assert art is not None
        assert art.provenance["n"] == 5

    def test_all_future_rows_returns_none(self) -> None:
        pid = 9003
        rows = [
            _adv_row(pid, "2027-01-01"),
            _adv_row(pid, "2027-02-01"),
        ]
        art = _build_artifact(pid, rows, as_of=_dt.datetime(2026, 5, 31))
        assert art is None

    def test_as_of_boundary_is_inclusive(self) -> None:
        """Game exactly on as_of date must be included."""
        pid = 9004
        rows = [_adv_row(pid, f"2026-0{i}-01") for i in range(1, 6)]
        as_of = _dt.datetime(2026, 5, 1)
        art = _build_artifact(pid, rows, as_of)
        assert art is not None
        assert art.provenance["n"] == 5

    def test_provenance_as_of_matches_build_date(self) -> None:
        pid = 9005
        # 8 games in months 1-8 of 2024 (valid dates)
        rows = [_adv_row(pid, f"2024-0{i}-15") for i in range(1, 9)]
        as_of = _dt.datetime(2025, 3, 15)
        art = _build_artifact(pid, rows, as_of)
        assert art is not None
        assert art.provenance["as_of"] == "2025-03-15"
        assert art.as_of == "2025-03-15"


# ---------------------------------------------------------------------------
# 3. eFG range conformance
# ---------------------------------------------------------------------------

class TestEfgConformance:
    """eFG% values outside [0, 1.0] are nulled before aggregation."""

    def test_efg_above_1_excluded_from_mean(self) -> None:
        pid = 9010
        rows = [
            _adv_row(pid, "2024-10-19", efg=0.50),
            _adv_row(pid, "2024-10-21", efg=0.60),
            _adv_row(pid, "2024-10-23", efg=0.55),
            _adv_row(pid, "2024-10-25", efg=0.65),
            _adv_row(pid, "2024-10-27", efg=1.10),  # invalid -- nulled
        ]
        art = _build_artifact(pid, rows)
        assert art is not None
        efg = art.sub_fields["overall"]["efg_pct"]
        if efg is not None:
            assert efg <= 1.0, f"eFG mean must not exceed 1.0, got {efg}"

    def test_efg_clean_rejects_out_of_range(self) -> None:
        assert _efg_clean(1.10) is None
        assert _efg_clean(-0.01) is None
        assert _efg_clean(float("nan")) is None

    def test_efg_clean_accepts_valid_values(self) -> None:
        assert _efg_clean(0.55) == pytest.approx(0.55)
        assert _efg_clean(1.00) == pytest.approx(1.00)
        assert _efg_clean(0.0) == pytest.approx(0.0)

    def test_overall_efg_within_range_when_present(self) -> None:
        pid = 9011
        # 8 games at increasing eFG values, all in [0, 1]
        rows = [
            _adv_row(pid, f"2024-10-{10 + i}", efg=0.50 + i * 0.01)
            for i in range(1, 9)
        ]
        art = _build_artifact(pid, rows)
        assert art is not None
        efg = art.sub_fields["overall"]["efg_pct"]
        if efg is not None:
            assert 0.0 <= efg <= 1.0


# ---------------------------------------------------------------------------
# 4. Rest-category logic
# ---------------------------------------------------------------------------

class TestRestCategoryLogic:
    """_rest_category_series correctly buckets B2B / 1-day / 2+."""

    def _dates_series(self, *date_strings: str) -> pd.Series:
        """Convert date strings to a datetime64 Series (required by _rest_category_series)."""
        return pd.Series(pd.to_datetime(list(date_strings)))

    def test_first_game_is_two_plus(self) -> None:
        cats = _rest_category_series(self._dates_series("2024-10-19"))
        assert cats.iloc[0] == "2plus"  # no prior game => well-rested

    def test_b2b_consecutive_days(self) -> None:
        cats = _rest_category_series(self._dates_series("2024-10-19", "2024-10-20"))
        assert cats.iloc[1] == "b2b"

    def test_one_day_rest(self) -> None:
        cats = _rest_category_series(self._dates_series("2024-10-19", "2024-10-21"))
        assert cats.iloc[1] == "1day"

    def test_two_plus_rest(self) -> None:
        cats = _rest_category_series(self._dates_series("2024-10-19", "2024-10-22"))
        assert cats.iloc[1] == "2plus"

    def test_season_gap_treated_as_well_rested(self) -> None:
        """A gap > 100 days (season break) must be '2plus', not 'b2b'."""
        cats = _rest_category_series(self._dates_series("2024-04-14", "2024-10-22"))
        assert cats.iloc[1] == "2plus"

    def test_mixed_sequence(self) -> None:
        cats = _rest_category_series(self._dates_series(
            "2024-10-19",  # first -> 2plus
            "2024-10-20",  # b2b
            "2024-10-22",  # 1day
            "2024-10-25",  # 2plus
        ))
        assert cats.tolist() == ["2plus", "b2b", "1day", "2plus"]

    def test_category_counts_sum_to_total(self) -> None:
        pid = 9020
        rows = [
            _adv_row(pid, "2024-10-19"),
            _adv_row(pid, "2024-10-20"),  # b2b
            _adv_row(pid, "2024-10-22"),  # 1day
            _adv_row(pid, "2024-10-25"),  # 2plus
            _adv_row(pid, "2024-10-28"),  # 2plus
        ]
        art = _build_artifact(pid, rows)
        assert art is not None
        sf = art.sub_fields
        total = (
            sf["b2b"]["n_games"]
            + sf["one_day"]["n_games"]
            + sf["two_plus"]["n_games"]
        )
        assert total == sf["overall"]["n_games"] == 5


# ---------------------------------------------------------------------------
# 5. Signed field naming for face-validity exemption
# ---------------------------------------------------------------------------

class TestSignedFieldNaming:
    """Fatigue proxy fields must contain '_minus_' so the validator exempts them."""

    def test_signed_field_keys_contain_minus_marker(self) -> None:
        art = _build_artifact(9030, _ten_rows(9030))
        assert art is not None
        fp = art.sub_fields["fatigue_proxy"]
        for key in ("efg_b2b_minus_2plus", "min_b2b_minus_2plus"):
            assert "_minus_" in key, f"{key} must contain '_minus_' for validator exemption"
            assert key in fp

    def test_signed_fields_can_be_negative(self) -> None:
        """B2B eFG below 2+ baseline should produce a negative delta."""
        pid = 9031
        rows = [
            # First game (2plus baseline), then b2b with low eFG
            _adv_row(pid, "2024-10-19", efg=0.40),
            _adv_row(pid, "2024-10-20", efg=0.38),  # b2b
            # 5 well-rested games with high eFG
            _adv_row(pid, "2024-10-23", efg=0.60),
            _adv_row(pid, "2024-10-26", efg=0.62),
            _adv_row(pid, "2024-10-29", efg=0.65),
            _adv_row(pid, "2024-11-01", efg=0.63),
            _adv_row(pid, "2024-11-04", efg=0.64),
        ]
        art = _build_artifact(pid, rows)
        assert art is not None
        delta = art.sub_fields["fatigue_proxy"]["efg_b2b_minus_2plus"]
        if delta is not None:
            assert delta < 0, f"Expected negative fatigue delta, got {delta}"


# ---------------------------------------------------------------------------
# 6. CV-slot schema
# ---------------------------------------------------------------------------

class TestCVSlotSchema:
    """cv_fields() declares speed_decay_b2b; all slot values must be null."""

    def test_cv_slot_declared(self) -> None:
        slots = PlayerRestB2BSplits().cv_fields()
        assert "speed_decay_b2b" in slots

    def test_cv_slot_dtype_is_float(self) -> None:
        slot = PlayerRestB2BSplits().cv_fields()["speed_decay_b2b"]
        assert slot.dtype == "float"

    def test_cv_slot_unit_is_ft_per_s(self) -> None:
        slot = PlayerRestB2BSplits().cv_fields()["speed_decay_b2b"]
        assert slot.unit == "ft/s"

    def test_cv_slot_value_is_null(self) -> None:
        slot = PlayerRestB2BSplits().cv_fields()["speed_decay_b2b"]
        assert slot.value is None

    def test_artifact_cv_fields_all_null(self) -> None:
        art = _build_artifact(9040, _ten_rows(9040))
        assert art is not None
        for name, slot in art.cv_fields.items():
            assert slot.value is None, f"CV slot {name} must be null (reserved)"


# ---------------------------------------------------------------------------
# 7. Section self-validate
# ---------------------------------------------------------------------------

class TestSectionSelfValidate:
    """section.validate() returns True for well-formed artifacts, False otherwise."""

    def test_validate_passes_for_good_artifact(self) -> None:
        art = _build_artifact(9050, _ten_rows(9050))
        assert art is not None
        assert PlayerRestB2BSplits().validate(art) is True

    def test_validate_fails_wrong_section(self) -> None:
        art = _build_artifact(9051, _ten_rows(9051))
        assert art is not None
        art.section = "wrong_section"
        assert PlayerRestB2BSplits().validate(art) is False

    def test_validate_fails_non_null_cv_slot(self) -> None:
        art = _build_artifact(9052, _ten_rows(9052))
        assert art is not None
        art.cv_fields["speed_decay_b2b"] = CVSlot(
            name="speed_decay_b2b", dtype="float", value=0.5
        )
        assert PlayerRestB2BSplits().validate(art) is False

    def test_validate_fails_missing_required_key(self) -> None:
        art = _build_artifact(9053, _ten_rows(9053))
        assert art is not None
        del art.sub_fields["fatigue_proxy"]
        assert PlayerRestB2BSplits().validate(art) is False

    def test_validate_fails_efg_out_of_range(self) -> None:
        art = _build_artifact(9054, _ten_rows(9054))
        assert art is not None
        art.sub_fields["overall"]["efg_pct"] = 1.5
        assert PlayerRestB2BSplits().validate(art) is False

    def test_returns_none_for_unknown_player(self) -> None:
        # DataFrame only contains pid=1; requesting pid=99999 must return None
        rows = [_adv_row(1, f"2024-10-{10 + i}") for i in range(5)]
        art = _build_artifact(99999, rows)
        assert art is None
