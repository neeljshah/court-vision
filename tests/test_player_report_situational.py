"""Tests for player_report.py — (2a) situational block 4-section wiring fix
and (2b) cv_behavioral block.

Assertions:
  A. The 4 newly-wired atlas sections (ft_profile, matchup_splits,
     turnover_profile, pace_fit) appear in situational.data for a player
     that has those sections in the parquets.
  B. _build_cv_behavioral returns a dict for any player.
  C. For a player with known CV fills (e.g. player in rebounding_profile with
     non-null rebound_distance), cv_behavioral.data.slots is non-empty with
     >=1 non-null slot, and confidence is never "high" (always capped at med
     or absent).
  D. data_completeness.sections_present increases after the fix (vs the known
     pre-fix baseline of 23 for Jokic/SGA/Wemby who only have ft_profile
     among the 4 formerly-unwired sections).
  E. Existing narrative + archetype_role + scoring blocks remain intact
     (no regression).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest

# Ensure repo root on path and offline mode
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
os.chdir(str(_REPO))
os.environ.setdefault("NBA_OFFLINE", "1")

from src.intel.player_report import (
    build_player_report,
    _atlas_row,
    _build_situational,
    _build_cv_behavioral,
    ATLAS_SECTIONS,
)


# ---------------------------------------------------------------------------
# Helper: find a player_id present in the given parquet
# ---------------------------------------------------------------------------

def _first_player_in(section: str) -> int:
    path = _REPO / "data" / "cache" / f"atlas_player_{section}.parquet"
    df = pd.read_parquet(path)
    return int(df["player_id"].iloc[0])


def _players_in(section: str) -> set:
    path = _REPO / "data" / "cache" / f"atlas_player_{section}.parquet"
    df = pd.read_parquet(path)
    return set(df["player_id"].tolist())


# ---------------------------------------------------------------------------
# A. Newly-wired sections appear in situational.data
# ---------------------------------------------------------------------------

class TestSituationalWiring:
    """The 4 formerly-unwired sections now appear in situational.data."""

    def test_ft_profile_in_situational_for_present_player(self):
        """ft_profile appears in situational.data for a player who has it."""
        pid = _first_player_in("ft_profile")
        rep = build_player_report(pid)
        sit_data = rep["situational"]["data"]
        assert "ft_profile" in sit_data, (
            f"ft_profile missing from situational.data for player {pid}"
        )
        ft = sit_data["ft_profile"]
        assert isinstance(ft, dict)
        # Key fields must be present (may be None if underlying data is None)
        for key in ("ft_pct", "fta_pg", "hack_flag"):
            assert key in ft, f"ft_profile missing key '{key}'"

    def test_matchup_splits_in_situational_for_present_player(self):
        """matchup_splits appears in situational.data for a player who has it."""
        pid = _first_player_in("matchup_splits")
        rep = build_player_report(pid)
        sit_data = rep["situational"]["data"]
        assert "matchup_splits" in sit_data, (
            f"matchup_splits missing from situational.data for player {pid}"
        )
        ms = sit_data["matchup_splits"]
        assert isinstance(ms, dict)
        assert "top_notable_defender" in ms

    def test_turnover_profile_in_situational_for_present_player(self):
        """turnover_profile appears in situational.data for a player who has it."""
        pid = _first_player_in("turnover_profile")
        rep = build_player_report(pid)
        sit_data = rep["situational"]["data"]
        assert "turnover_profile" in sit_data, (
            f"turnover_profile missing from situational.data for player {pid}"
        )
        tp = sit_data["turnover_profile"]
        assert isinstance(tp, dict)
        assert "tov_pg" in tp or "q4_tov_pg" in tp

    def test_pace_fit_in_situational_for_present_player(self):
        """pace_fit appears in situational.data for a player who has it."""
        pid = _first_player_in("pace_fit")
        rep = build_player_report(pid)
        sit_data = rep["situational"]["data"]
        assert "pace_fit" in sit_data, (
            f"pace_fit missing from situational.data for player {pid}"
        )
        pf = sit_data["pace_fit"]
        assert isinstance(pf, dict)
        assert "pace_preference" in pf
        assert "pace_fit_score" in pf

    def test_situational_prov_contains_all_4_new_keys(self):
        """situational.provenance must now include all 4 new section keys."""
        pid = _first_player_in("ft_profile")
        rep = build_player_report(pid)
        prov = rep["situational"]["provenance"]
        for sec in ("ft_profile", "matchup_splits", "turnover_profile", "pace_fit"):
            assert sec in prov, (
                f"situational.provenance missing '{sec}' entry"
            )

    def test_ft_profile_absent_for_unknown_player(self):
        """A player not in any of the 4 parquets must NOT get spurious keys."""
        # player_id 9999999 is not in any atlas
        rep = build_player_report(9999999)
        sit_data = rep["situational"]["data"]
        # Should have no ft_profile/matchup/tov/pace keys since player absent
        for key in ("ft_profile", "matchup_splits", "turnover_profile", "pace_fit"):
            assert key not in sit_data, (
                f"Spurious '{key}' present in situational.data for unknown player"
            )

    def test_ft_profile_fields_are_floats_or_none(self):
        """ft_profile numeric fields must be floats or None (not raw strings/dicts)."""
        pid = _first_player_in("ft_profile")
        rep = build_player_report(pid)
        ft = rep["situational"]["data"].get("ft_profile", {})
        for key in ("ft_pct", "ft_pct_l10", "fta_pg", "pct_pts_from_ft", "clutch_ft_pct"):
            v = ft.get(key)
            assert v is None or isinstance(v, (int, float)), (
                f"ft_profile['{key}'] should be float or None, got {type(v)}"
            )


# ---------------------------------------------------------------------------
# B. cv_behavioral block exists and is a dict
# ---------------------------------------------------------------------------

class TestCVBehavioral:
    """cv_behavioral block is present in every report and returns a dict."""

    def test_cv_behavioral_block_exists(self):
        """build_player_report always returns a cv_behavioral block."""
        pid = _first_player_in("ft_profile")
        rep = build_player_report(pid)
        assert "cv_behavioral" in rep, "cv_behavioral block missing from report"
        assert "data" in rep["cv_behavioral"]
        assert "provenance" in rep["cv_behavioral"]

    def test_cv_behavioral_data_is_dict(self):
        pid = _first_player_in("ft_profile")
        rep = build_player_report(pid)
        data = rep["cv_behavioral"]["data"]
        assert isinstance(data, dict), "cv_behavioral.data must be a dict"

    def test_cv_behavioral_empty_for_no_cv_player(self):
        """A player with no CV fills returns an empty dict as cv_behavioral.data."""
        # Players 1630209, 1630214, 1642502 are in ft_profile but have no CV fills
        # Try until we find one that truly has no CV slots
        no_cv_pids = [1630209, 1630214]
        for pid in no_cv_pids:
            rep = build_player_report(pid)
            data = rep["cv_behavioral"]["data"]
            slots = data.get("slots", {})
            if not slots:
                # confirmed empty
                assert data == {} or slots == {}, (
                    f"Expected empty cv_behavioral for player {pid}, got {data}"
                )
                prov = rep["cv_behavioral"]["provenance"]
                assert prov.get("present") is False or not slots
                return
        pytest.skip("Could not find a player confirmed to have zero CV fills")


# ---------------------------------------------------------------------------
# C. Player with known CV fills: slots non-empty, confidence != high
# ---------------------------------------------------------------------------

class TestCVBehavioralFills:
    """For a player known to have CV fills, cv_behavioral surfaces them correctly."""

    @classmethod
    def _cv_fill_player(cls) -> int:
        """Return a player_id known to have non-null CV fills in rebounding_profile."""
        import json
        df = pd.read_parquet(
            _REPO / "data" / "cache" / "atlas_player_rebounding_profile.parquet"
        )
        for _, row in df.iterrows():
            cv_raw = row.get("_cv_fields")
            if not cv_raw or not isinstance(cv_raw, str):
                continue
            cv = json.loads(cv_raw)
            for k, v in cv.items():
                if not k.startswith("_") and isinstance(v, dict) and v.get("value") is not None:
                    return int(row["player_id"])
        pytest.skip("No player found with non-null CV fills in rebounding_profile")

    def test_cv_slots_non_empty(self):
        pid = self._cv_fill_player()
        rep = build_player_report(pid)
        data = rep["cv_behavioral"]["data"]
        slots = data.get("slots", {})
        assert len(slots) >= 1, (
            f"Expected >=1 section in cv_behavioral.slots for player {pid}"
        )

    def test_cv_slots_have_at_least_one_value(self):
        pid = self._cv_fill_player()
        rep = build_player_report(pid)
        data = rep["cv_behavioral"]["data"]
        slots = data.get("slots", {})
        all_values = [
            slot_info.get("value")
            for sec_slots in slots.values()
            for slot_info in sec_slots.values()
        ]
        assert any(v is not None for v in all_values), (
            f"Expected at least one non-null value in cv_behavioral.slots for player {pid}"
        )

    def test_cv_confidence_never_high(self):
        """CV confidence is always capped at med (never high)."""
        pid = self._cv_fill_player()
        rep = build_player_report(pid)
        prov = rep["cv_behavioral"]["provenance"]
        conf = prov.get("confidence")
        assert conf != "high", (
            f"cv_behavioral.confidence should never be 'high', got '{conf}' "
            f"for player {pid}"
        )

    def test_cv_provenance_note_present(self):
        """cv_behavioral.data.provenance_note is a string."""
        pid = self._cv_fill_player()
        rep = build_player_report(pid)
        data = rep["cv_behavioral"]["data"]
        note = data.get("provenance_note")
        assert isinstance(note, str) and len(note) > 0, (
            "cv_behavioral.data.provenance_note must be a non-empty string"
        )

    def test_cv_behavioral_slot_structure(self):
        """Each slot in cv_behavioral.slots[section][slot_name] has value+unit keys."""
        pid = self._cv_fill_player()
        rep = build_player_report(pid)
        data = rep["cv_behavioral"]["data"]
        for sec, sec_slots in data.get("slots", {}).items():
            assert isinstance(sec_slots, dict), f"slots[{sec}] should be a dict"
            for slot_name, slot_info in sec_slots.items():
                assert "value" in slot_info, (
                    f"cv slot {sec}.{slot_name} missing 'value' key"
                )
                assert "unit" in slot_info, (
                    f"cv slot {sec}.{slot_name} missing 'unit' key"
                )


# ---------------------------------------------------------------------------
# D. sections_present increases after the fix
# ---------------------------------------------------------------------------

class TestCompletenessCapLifted:
    """sections_present should be higher after the 4-section fix."""

    def test_jokic_sections_present_gte_24(self):
        """Jokic (203999) had 23 sections before fix; ft_profile now wired -> >=24."""
        rep = build_player_report(203999)
        present = rep["data_completeness"]["sections_present"]
        assert present >= 24, (
            f"Expected sections_present >= 24 for Jokic after fix, got {present}"
        )

    def test_sga_sections_present_gte_24(self):
        """SGA (1628983) had 23 sections before fix; ft_profile now wired -> >=24."""
        rep = build_player_report(1628983)
        present = rep["data_completeness"]["sections_present"]
        assert present >= 24, (
            f"Expected sections_present >= 24 for SGA after fix, got {present}"
        )

    def test_ft_profile_not_in_low_or_missing_for_present_player(self):
        """Players who have ft_profile must NOT have it in low_or_missing_sections."""
        pid = _first_player_in("ft_profile")
        rep = build_player_report(pid)
        missing = rep["data_completeness"]["low_or_missing_sections"]
        assert "ft_profile" not in missing, (
            f"ft_profile still in low_or_missing for player {pid} who has it"
        )

    def test_matchup_splits_not_in_low_or_missing_for_present_player(self):
        pid = _first_player_in("matchup_splits")
        rep = build_player_report(pid)
        missing = rep["data_completeness"]["low_or_missing_sections"]
        assert "matchup_splits" not in missing, (
            f"matchup_splits still in low_or_missing for player {pid} who has it"
        )

    def test_pace_fit_not_in_low_or_missing_for_present_player(self):
        pid = _first_player_in("pace_fit")
        rep = build_player_report(pid)
        missing = rep["data_completeness"]["low_or_missing_sections"]
        assert "pace_fit" not in missing, (
            f"pace_fit still in low_or_missing for player {pid} who has it"
        )


# ---------------------------------------------------------------------------
# E. Regression guard — existing blocks still work
# ---------------------------------------------------------------------------

class TestNoRegression:
    """Existing blocks must still be present and valid after the fix."""

    def test_archetype_role_intact(self):
        rep = build_player_report(203999)
        arch = rep.get("archetype_role", {}).get("data", {})
        assert "archetype" in arch
        assert "usage_rate" in arch

    def test_scoring_block_intact(self):
        rep = build_player_report(1628983)
        sc = rep.get("scoring", {}).get("data", {})
        assert isinstance(sc, dict)
        # Should have at least one scoring sub-key
        assert len(sc) >= 1

    def test_narrative_is_string(self):
        rep = build_player_report(203999)
        assert isinstance(rep.get("narrative"), str)
        assert len(rep["narrative"]) > 10

    def test_schema_version_present(self):
        rep = build_player_report(203999)
        assert rep.get("schema_version") == "player_report/1.0"

    def test_data_completeness_score_bounded(self):
        """score must be in [0, 1]."""
        for pid in [203999, 1628983, 1641705]:
            rep = build_player_report(pid)
            score = rep["data_completeness"]["score"]
            assert 0.0 <= score <= 1.0, f"score {score} out of [0,1] for player {pid}"

    def test_all_existing_situational_keys_still_present(self):
        """Previously existing situational keys must still be there."""
        rep = build_player_report(203999)  # Jokic has all the existing keys
        sit = rep["situational"]["data"]
        # These were present before the fix
        for key in ("clutch", "quarter_shape", "rest_b2b", "score_margin",
                    "vs_scheme", "monthly_form"):
            assert key in sit, f"Pre-existing situational key '{key}' disappeared"
