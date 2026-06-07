"""Tests for intel/team_rebounding_scheme.py.

Contract assertions:
  1. Leak-safety: build(..., as_of=cutoff) must never return data after the cutoff.
  2. Schema conformance: artifact contains all required sub_fields and all cv_fields slots.
  3. Validation: TeamReboundingScheme.validate() accepts a well-formed artifact.
  4. Categorical label: reb_identity matches crash_rate_z thresholds.
  5. Z-score bounds: crash_rate_z / dreb_identity_z satisfy |z| < 5 for real data.
  6. CV slot schema: cv_fields() returns both reserved slots with value=None.

Uses NBA_OFFLINE=1 convention; no API calls. Injects a minimal synthetic parquet
so the tests pass even when the real data/team_reb_context.parquet is absent.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure repo root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.team_rebounding_scheme import (
    TeamReboundingScheme,
    _clean,
    _reb_identity_label,
    build_all,
)
from src.loop.atlas import AtlasArtifact, CVSlot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_reb_df(seed: int = 42) -> pd.DataFrame:
    """Create a synthetic team_reb_context-shaped DataFrame covering 3 teams."""
    rng = np.random.default_rng(seed)
    rows = []
    for tricode, oreb_base, dreb_base in [
        ("LAK", 0.33, 0.72),   # crash_heavy
        ("MID", 0.28, 0.72),   # balanced
        ("GTB", 0.22, 0.73),   # get_back
    ]:
        for i in range(50):
            game_date = (
                _dt.date(2024, 10, 1) + _dt.timedelta(days=i * 3)
            ).isoformat()
            rows.append({
                "game_id": f"00220{i:04d}",
                "game_date": game_date,
                "team_tricode": tricode,
                "oreb_pct": float(np.clip(rng.normal(oreb_base, 0.04), 0.05, 0.60)),
                "dreb_pct": float(np.clip(rng.normal(dreb_base, 0.04), 0.40, 0.95)),
                "possessions": float(rng.integers(90, 115)),
            })
    return pd.DataFrame(rows)


def _inject_fake_parquet(fake_df: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch the module-level cache so tests don't need real disk files."""
    import intel.team_rebounding_scheme as mod
    monkeypatch.setattr(mod, "_REB_DF", fake_df)
    monkeypatch.setattr(mod, "_ADV_DF", None)


# ---------------------------------------------------------------------------
# 1. LEAK-SAFETY: build with a cutoff before the last game must not see later rows
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """build() must never return data after the as_of date."""

    def test_artifact_as_of_lte_decision_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """artifact.as_of must be <= the as_of date passed to build()."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        # Use a cutoff in the middle of the fake data range
        cutoff = _dt.datetime(2025, 1, 1)
        section = TeamReboundingScheme()
        art = section.build("LAK", cutoff)

        assert art is not None, "Expected artifact for LAK within data range"
        assert art.as_of is not None, "artifact.as_of must be set"
        assert art.as_of <= cutoff.date().isoformat(), (
            f"Artifact as_of {art.as_of!r} is AFTER the decision cutoff "
            f"{cutoff.date().isoformat()!r} — LEAK!"
        )

    def test_no_future_games_in_aggregate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """n_games in sub_fields must equal rows on or before the cutoff."""
        fake_df = _make_fake_reb_df()
        cutoff_iso = "2024-12-31"
        expected_n = int((fake_df[fake_df["team_tricode"] == "LAK"]["game_date"] <= cutoff_iso).sum())

        _inject_fake_parquet(fake_df, monkeypatch)
        section = TeamReboundingScheme()
        art = section.build("LAK", _dt.datetime(2024, 12, 31))

        assert art is not None
        assert art.sub_fields["n_games"] == expected_n, (
            f"n_games={art.sub_fields['n_games']} but expected {expected_n} "
            f"(only games on or before {cutoff_iso} should be visible)"
        )

    def test_empty_before_data_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build() must return None when no rows exist before the as_of date."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        very_early = _dt.datetime(2020, 1, 1)  # before any fake game
        section = TeamReboundingScheme()
        art = section.build("LAK", very_early)
        assert art is None, "Expected None when no qualifying data before as_of"


# ---------------------------------------------------------------------------
# 2. SCHEMA CONFORMANCE: all required sub_fields and cv_fields present
# ---------------------------------------------------------------------------

class TestSchemaConformance:
    """Artifact must carry all required sub_fields keys and cv_fields slots."""

    REQUIRED_SUBFIELDS = [
        "oreb_pct_mean", "oreb_pct_std", "dreb_pct_mean", "dreb_pct_std",
        "crash_rate_z", "dreb_identity_z", "oreb_pct_l10", "dreb_pct_l10",
        "oreb_pct_season_rank", "dreb_pct_season_rank", "reb_identity",
        "n_games", "crash_vs_get_back_rate",
    ]
    REQUIRED_CV_SLOTS = ["team_oreb_crash_freq", "team_dreb_position_z"]

    def test_all_subfield_keys_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All documented sub_fields keys must appear in the artifact."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        section = TeamReboundingScheme()
        art = section.build("MID", _dt.datetime(2025, 6, 1))
        assert art is not None

        for key in self.REQUIRED_SUBFIELDS:
            assert key in art.sub_fields, f"Missing sub_field key: {key!r}"

    def test_crash_vs_get_back_rate_is_none_deferred(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """crash_vs_get_back_rate is DEFER -- must be None (CV fills later)."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        section = TeamReboundingScheme()
        art = section.build("MID", _dt.datetime(2025, 6, 1))
        assert art is not None
        assert art.sub_fields["crash_vs_get_back_rate"] is None, (
            "crash_vs_get_back_rate is a DEFER field; its value must be None until CV fills it"
        )

    def test_cv_fields_method_returns_correct_slots(self) -> None:
        """cv_fields() must return both reserved slots with value=None."""
        section = TeamReboundingScheme()
        cv = section.cv_fields()

        for slot_name in self.REQUIRED_CV_SLOTS:
            assert slot_name in cv, f"Missing CV slot: {slot_name!r}"
            slot = cv[slot_name]
            assert isinstance(slot, CVSlot), f"cv_fields[{slot_name!r}] must be a CVSlot"
            assert slot.value is None, (
                f"CV slot {slot_name!r} must have value=None until CV fills it"
            )

    def test_artifact_cv_fields_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """artifact.cv_fields must contain all reserved CV slot names."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        section = TeamReboundingScheme()
        art = section.build("GTB", _dt.datetime(2025, 6, 1))
        assert art is not None

        for slot_name in self.REQUIRED_CV_SLOTS:
            assert slot_name in art.cv_fields, (
                f"CV slot {slot_name!r} missing from artifact.cv_fields"
            )
            assert art.cv_fields[slot_name].value is None

    def test_to_profile_payload_embeds_cv_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """to_profile_payload() must embed _cv_fields under data."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        section = TeamReboundingScheme()
        art = section.build("MID", _dt.datetime(2025, 6, 1))
        assert art is not None

        data, prov = art.to_profile_payload()
        assert "_cv_fields" in data, "to_profile_payload() must include '_cv_fields'"
        for slot_name in self.REQUIRED_CV_SLOTS:
            assert slot_name in data["_cv_fields"], (
                f"CV slot {slot_name!r} missing from profile payload _cv_fields"
            )
        # Values in payload must be None (reserved, not yet filled)
        for slot_name in self.REQUIRED_CV_SLOTS:
            assert data["_cv_fields"][slot_name]["value"] is None

    def test_provenance_fields_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provenance dict must have source, n, confidence, and as_of."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        section = TeamReboundingScheme()
        art = section.build("LAK", _dt.datetime(2025, 6, 1))
        assert art is not None

        for key in ("source", "n", "confidence", "as_of"):
            assert key in art.provenance, f"Missing provenance key: {key!r}"
        assert art.provenance["confidence"] in ("low", "med", "high")
        assert isinstance(art.provenance["n"], int)


# ---------------------------------------------------------------------------
# 3. VALIDATION: TeamReboundingScheme.validate() accepts a well-formed artifact
# ---------------------------------------------------------------------------

class TestValidation:
    """validate() must accept good artifacts and reject malformed ones."""

    def _build_good_artifact(self, monkeypatch: pytest.MonkeyPatch,
                              tricode: str = "MID") -> AtlasArtifact:
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)
        section = TeamReboundingScheme()
        art = section.build(tricode, _dt.datetime(2025, 6, 1))
        assert art is not None, "Pre-condition: artifact must build"
        return art, section

    def test_validate_accepts_good_artifact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        assert section.validate(art) is True

    def test_validate_rejects_wrong_section(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        art.section = "wrong_section"
        assert section.validate(art) is False

    def test_validate_rejects_wrong_entity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        art.entity = "player"
        assert section.validate(art) is False

    def test_validate_rejects_oreb_out_of_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        art.sub_fields["oreb_pct_mean"] = 1.5   # > 1.0 -- invalid
        assert section.validate(art) is False

    def test_validate_rejects_z_score_extreme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        art.sub_fields["crash_rate_z"] = 99.0   # |z| > 5 -- sanity fail
        assert section.validate(art) is False

    def test_validate_rejects_invalid_identity_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        art.sub_fields["reb_identity"] = "super_crasher"  # not in allowed set
        assert section.validate(art) is False

    def test_validate_rejects_zero_n_games(self, monkeypatch: pytest.MonkeyPatch) -> None:
        art, section = self._build_good_artifact(monkeypatch)
        art.sub_fields["n_games"] = 0
        assert section.validate(art) is False


# ---------------------------------------------------------------------------
# 4. CATEGORICAL LABEL: reb_identity matches crash_rate_z thresholds
# ---------------------------------------------------------------------------

class TestRebIdentityLabel:
    """_reb_identity_label() must produce correct categorical labels."""

    def test_crash_heavy_above_threshold(self) -> None:
        assert _reb_identity_label(0.68) == "crash_heavy"
        assert _reb_identity_label(2.5) == "crash_heavy"

    def test_get_back_below_threshold(self) -> None:
        assert _reb_identity_label(-0.68) == "get_back"
        assert _reb_identity_label(-3.0) == "get_back"

    def test_balanced_in_middle(self) -> None:
        assert _reb_identity_label(0.0) == "balanced"
        assert _reb_identity_label(0.5) == "balanced"
        assert _reb_identity_label(-0.5) == "balanced"

    def test_unknown_on_none(self) -> None:
        assert _reb_identity_label(None) == "unknown"

    def test_crash_heavy_team_has_correct_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LAK has oreb_base=0.33 (highest in fake data) -> crash_heavy."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)
        section = TeamReboundingScheme()
        art = section.build("LAK", _dt.datetime(2025, 6, 1))
        assert art is not None
        assert art.sub_fields["reb_identity"] == "crash_heavy", (
            f"LAK with highest OREB should be crash_heavy, got {art.sub_fields['reb_identity']!r}"
        )

    def test_get_back_team_has_correct_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GTB has oreb_base=0.22 (lowest in fake data) -> get_back."""
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)
        section = TeamReboundingScheme()
        art = section.build("GTB", _dt.datetime(2025, 6, 1))
        assert art is not None
        assert art.sub_fields["reb_identity"] == "get_back", (
            f"GTB with lowest OREB should be get_back, got {art.sub_fields['reb_identity']!r}"
        )


# ---------------------------------------------------------------------------
# 5. Z-SCORE BOUNDS
# ---------------------------------------------------------------------------

class TestZScoreBounds:
    """crash_rate_z and dreb_identity_z must be plausible (|z| < 5)."""

    def test_z_scores_bounded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)
        section = TeamReboundingScheme()

        for tricode in ("LAK", "MID", "GTB"):
            art = section.build(tricode, _dt.datetime(2025, 6, 1))
            assert art is not None
            z_crash = art.sub_fields.get("crash_rate_z")
            z_dreb = art.sub_fields.get("dreb_identity_z")
            if z_crash is not None:
                assert abs(z_crash) < 5.0, (
                    f"{tricode} crash_rate_z={z_crash} exceeds |5| sanity bound"
                )
            if z_dreb is not None:
                assert abs(z_dreb) < 5.0, (
                    f"{tricode} dreb_identity_z={z_dreb} exceeds |5| sanity bound"
                )


# ---------------------------------------------------------------------------
# 6. CV SLOT SCHEMA: cv_fields() returns correct structure
# ---------------------------------------------------------------------------

class TestCVSlotSchema:
    """cv_fields() must return properly typed CVSlot objects with value=None."""

    def test_cv_fields_types(self) -> None:
        section = TeamReboundingScheme()
        cv = section.cv_fields()
        assert isinstance(cv, dict)
        for name, slot in cv.items():
            assert isinstance(slot, CVSlot), f"{name!r} must be a CVSlot"
            assert slot.name == name, f"slot.name {slot.name!r} must match key {name!r}"
            assert slot.value is None, f"slot {name!r} must have value=None"
            assert slot.dtype in ("float", "dist", "list", "categorical"), (
                f"slot {name!r} dtype {slot.dtype!r} not in allowed set"
            )

    def test_cv_fields_descriptions_non_empty(self) -> None:
        section = TeamReboundingScheme()
        for name, slot in section.cv_fields().items():
            assert slot.description, f"CV slot {name!r} must have a non-empty description"


# ---------------------------------------------------------------------------
# 7. build_all() smoke test (dry_run=True, no disk writes)
# ---------------------------------------------------------------------------

class TestBuildAll:
    """build_all() should process multiple teams and return a manifest."""

    def test_build_all_dry_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_df = _make_fake_reb_df()
        _inject_fake_parquet(fake_df, monkeypatch)

        manifest = build_all(
            as_of=_dt.datetime(2025, 6, 1),
            dry_run=True,
            limit=3,
        )
        assert isinstance(manifest, dict)
        assert manifest.get("section") == "rebounding_scheme"
        assert manifest.get("n_entities", 0) > 0, "Expected at least one entity processed"
        assert "cv_fields" in manifest
        assert "team_oreb_crash_freq" in manifest["cv_fields"]
        assert "team_dreb_position_z" in manifest["cv_fields"]

    def test_build_all_empty_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_all() with empty data returns a safe zero-entity manifest."""
        import intel.team_rebounding_scheme as mod
        monkeypatch.setattr(mod, "_REB_DF", pd.DataFrame())

        manifest = build_all(as_of=_dt.datetime(2025, 6, 1), dry_run=True)
        assert manifest.get("n_entities") == 0 or "error" in manifest
