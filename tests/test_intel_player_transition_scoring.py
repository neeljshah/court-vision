"""Tests for intel/player_transition_scoring.py.

Checks:
  1. Schema conformance — all required sub-field keys present + types correct.
  2. Proportion range — freq_pct in [0,1], transition_poss_share in [0,1].
  3. Leak-safety — build at an earlier as_of never uses data from after that date.
  4. CV slot schema — sprint_speed_transition reserved and value=None.
  5. n from real game count — provenance n reflects actual per-game rows (>= 5 for
     well-covered players like Jokic and Curry).
  6. validate() gate — out-of-range proportion causes validate() to return False.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

# Ensure repo root on sys.path for offline import
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("NBA_OFFLINE", "1")

from intel.player_transition_scoring import PlayerTransitionScoring, _SRC_CACHE
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JOKIC = 203999
CURRY = 201939
# A fixed recent as_of that is safely after the 2024-25 season
AS_OF = _dt.datetime(2025, 10, 25, 0, 0, 0)
# An earlier as_of to test leak-safety (mid-season 2024-25)
AS_OF_EARLY = _dt.datetime(2024, 12, 1, 0, 0, 0)


def _build(pid: int, as_of: _dt.datetime = AS_OF) -> Optional[AtlasArtifact]:
    """Build artifact for a player, clearing the module cache first for isolation."""
    _SRC_CACHE.clear()
    section = PlayerTransitionScoring()
    return section.build(pid, as_of)


# ---------------------------------------------------------------------------
# 1. Schema conformance
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact has required keys and correct metadata."""

    def test_jokic_artifact_not_none(self):
        art = _build(JOKIC)
        assert art is not None, "Jokic should produce an artifact (data available)"

    def test_curry_artifact_not_none(self):
        art = _build(CURRY)
        assert art is not None, "Curry should produce an artifact (data available)"

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_required_sub_fields_present(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        required = {
            "playtypes", "pbp_volume", "push_after_rebound_proxy",
            "leak_out_tendency", "finishing_splits",
        }
        assert required.issubset(art.sub_fields.keys()), (
            f"Missing keys: {required - set(art.sub_fields.keys())}"
        )

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_section_and_entity_correct(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        assert art.section == "transition_scoring"
        assert art.entity == "player"
        assert art.entity_id == pid

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_as_of_is_string_date(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        assert isinstance(art.as_of, str), "as_of must be an ISO date string"
        assert len(art.as_of) == 10, "as_of must be YYYY-MM-DD format"

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_confidence_valid_level(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        assert art.confidence in ("low", "med", "high"), (
            f"Unexpected confidence: {art.confidence}"
        )

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_validate_returns_true(self, pid):
        section = PlayerTransitionScoring()
        _SRC_CACHE.clear()
        art = section.build(pid, AS_OF)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        assert section.validate(art), "validate() must return True for a well-formed artifact"


# ---------------------------------------------------------------------------
# 2. Proportion range constraints
# ---------------------------------------------------------------------------

class TestProportionRanges:
    """Proportion sub-fields stay within [0,1]."""

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_freq_pct_in_unit_interval(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        freq = art.sub_fields.get("playtypes", {}).get("freq_pct")
        if freq is not None:
            assert 0.0 <= freq <= 1.0, f"freq_pct={freq} out of [0,1]"

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_transition_poss_share_in_unit_interval(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        share = art.sub_fields.get("pbp_volume", {}).get("transition_poss_share")
        if share is not None:
            assert 0.0 <= share <= 1.0, f"transition_poss_share={share} out of [0,1]"

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_per_game_rates_non_negative(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        vol = art.sub_fields.get("pbp_volume", {})
        for key in ["transition_pg", "and1_pg"]:
            v = vol.get(key)
            if v is not None:
                assert v >= 0, f"{key}={v} is negative"

    def test_validate_rejects_out_of_range_freq_pct(self):
        """validate() must return False when freq_pct > 1.0."""
        section = PlayerTransitionScoring()
        # Manually construct an artifact with a bad freq_pct
        art = AtlasArtifact(
            section="transition_scoring",
            entity="player",
            entity_id=JOKIC,
            sub_fields={
                "playtypes": {"freq_pct": 1.5, "ppp": 1.2},   # bad: > 1.0
                "pbp_volume": {},
                "push_after_rebound_proxy": {},
                "leak_out_tendency": {},
                "finishing_splits": {},
            },
            provenance={"source": "test", "n": 10, "confidence": "med", "as_of": "2025-10-25"},
            confidence="med",
            as_of="2025-10-25",
            cv_fields=section.cv_fields(),
        )
        assert not section.validate(art), "validate() should reject freq_pct=1.5"

    def test_validate_rejects_negative_transition_pg(self):
        """validate() must return False when transition_pg is negative."""
        section = PlayerTransitionScoring()
        art = AtlasArtifact(
            section="transition_scoring",
            entity="player",
            entity_id=CURRY,
            sub_fields={
                "playtypes": {},
                "pbp_volume": {"transition_pg": -1.0},   # bad: negative
                "push_after_rebound_proxy": {},
                "leak_out_tendency": {},
                "finishing_splits": {},
            },
            provenance={"source": "test", "n": 10, "confidence": "med", "as_of": "2025-10-25"},
            confidence="med",
            as_of="2025-10-25",
            cv_fields=section.cv_fields(),
        )
        assert not section.validate(art), "validate() should reject negative transition_pg"


# ---------------------------------------------------------------------------
# 3. Leak-safety
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Building at an earlier as_of must not expose future game data."""

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_early_as_of_has_fewer_or_equal_games(self, pid):
        """n at an early as_of must be <= n at a later as_of (more data = more games)."""
        _SRC_CACHE.clear()
        section = PlayerTransitionScoring()
        art_early = section.build(pid, AS_OF_EARLY)
        _SRC_CACHE.clear()
        art_late = section.build(pid, AS_OF)

        if art_early is None or art_late is None:
            pytest.skip(f"One build returned None for player {pid}")

        n_early = art_early.provenance.get("n", 0)
        n_late = art_late.provenance.get("n", 0)
        assert n_early <= n_late, (
            f"Early as_of n={n_early} > late as_of n={n_late}; "
            "this suggests future data is leaking into the early build."
        )

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_early_as_of_stamp_matches(self, pid):
        """as_of in the built artifact must match the date passed in."""
        _SRC_CACHE.clear()
        section = PlayerTransitionScoring()
        art = section.build(pid, AS_OF_EARLY)
        if art is None:
            pytest.skip(f"No artifact for player {pid} at early as_of")
        assert art.as_of == AS_OF_EARLY.date().isoformat(), (
            f"as_of stamp {art.as_of!r} does not match build date {AS_OF_EARLY.date()}"
        )

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_provenance_as_of_not_after_artifact_as_of(self, pid):
        """provenance['as_of'] must be <= artifact.as_of (no future provenance leak)."""
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        prov_as_of = art.provenance.get("as_of", "")
        assert prov_as_of <= art.as_of, (
            f"provenance as_of={prov_as_of!r} is after artifact as_of={art.as_of!r}"
        )


# ---------------------------------------------------------------------------
# 4. CV slot schema
# ---------------------------------------------------------------------------

class TestCVSlotSchema:
    """Reserved CV slots are present with correct schema and null values."""

    def test_sprint_speed_transition_slot_exists(self):
        section = PlayerTransitionScoring()
        slots = section.cv_fields()
        assert "sprint_speed_transition" in slots, (
            "sprint_speed_transition CV slot must be reserved"
        )

    def test_sprint_speed_transition_slot_value_is_none(self):
        section = PlayerTransitionScoring()
        slot = section.cv_fields()["sprint_speed_transition"]
        assert slot.value is None, "CV slot value must be None (CV branch fills later)"

    def test_sprint_speed_transition_slot_dtype_and_unit(self):
        section = PlayerTransitionScoring()
        slot = section.cv_fields()["sprint_speed_transition"]
        assert slot.dtype == "float"
        assert slot.unit == "ft/s"

    @pytest.mark.parametrize("pid", [JOKIC, CURRY])
    def test_artifact_cv_fields_all_null(self, pid):
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for player {pid}")
        for name, slot in art.cv_fields.items():
            assert slot.value is None, (
                f"CV slot {name!r} value={slot.value!r} must be None before CV branch runs"
            )

    def test_validate_rejects_filled_cv_slot(self):
        """validate() must return False when a CV slot has been pre-filled."""
        section = PlayerTransitionScoring()
        filled_slots = section.cv_fields()
        filled_slots["sprint_speed_transition"] = CVSlot(
            name="sprint_speed_transition", dtype="float", unit="ft/s",
            description="test", value=12.5,  # should not be pre-filled
        )
        art = AtlasArtifact(
            section="transition_scoring",
            entity="player",
            entity_id=JOKIC,
            sub_fields={
                "playtypes": {},
                "pbp_volume": {},
                "push_after_rebound_proxy": {},
                "leak_out_tendency": {},
                "finishing_splits": {},
            },
            provenance={"source": "test", "n": 10, "confidence": "med", "as_of": "2025-10-25"},
            confidence="med",
            as_of="2025-10-25",
            cv_fields=filled_slots,
        )
        assert not section.validate(art), (
            "validate() should reject an artifact with a pre-filled CV slot"
        )


# ---------------------------------------------------------------------------
# 5. Provenance n >= 5 for well-covered players
# ---------------------------------------------------------------------------

class TestCoverage:
    """n in provenance reflects real game count and is >= 5 for Jokic and Curry."""

    @pytest.mark.parametrize("pid,name", [(JOKIC, "Jokic"), (CURRY, "Curry")])
    def test_n_at_least_five(self, pid, name):
        """Well-covered players must reach n>=5 so confidence hits 'med' or 'high'."""
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for {name}")
        n = art.provenance.get("n", 0)
        assert n >= 5, (
            f"{name} (pid={pid}) has n={n} — expected >= 5 from real game rows. "
            "Check that n is being set from actual game-count, not n_seasons."
        )

    @pytest.mark.parametrize("pid,name", [(JOKIC, "Jokic"), (CURRY, "Curry")])
    def test_confidence_not_low(self, pid, name):
        """With n>=5, confidence must be 'med' or 'high'."""
        art = _build(pid)
        if art is None:
            pytest.skip(f"No artifact for {name}")
        assert art.confidence in ("med", "high"), (
            f"{name} confidence={art.confidence!r}; expected 'med' or 'high' (n>=5)"
        )
