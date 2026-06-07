"""Tests for intel/team_halfcourt_offense.py (ARM-B atlas section).

Runs offline (NBA_OFFLINE=1); reads real data parquets if present, stubs them
otherwise.  All assertions validate the AtlasSection contract:
  1. Build returns AtlasArtifact with correct metadata.
  2. Provenance n is a real game count (>= 5 for real data).
  3. Proportions / freq_pct in [0, 1]; efg/ts in [0, 1.6]; off_rtg in plausible range.
  4. CV slots are reserved (value=None, correct dtype).
  5. validate() gate passes on well-formed artifacts.
  6. Build returns None for unknown teams.
  7. Leak-safe: as_of boundary excludes future games.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("NBA_OFFLINE", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intel.team_halfcourt_offense import (  # noqa: E402
    TeamHalfcourtOffense,
    build_and_register,
    _adv_stats,
    _playtypes,
    _ball_movement,
    _SRC_CACHE,
)
from src.loop.atlas import AtlasArtifact, CVSlot  # noqa: E402
from src.loop.intel_validator import validate as intel_validate  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AS_OF = _dt.datetime(2026, 5, 30)
_TEAM = "OKC"


def _make_adv_df(team: str = _TEAM, n: int = 30) -> pd.DataFrame:
    """Minimal team_advanced_stats rows."""
    dates = pd.date_range("2025-10-01", periods=n, freq="3D")
    return pd.DataFrame({
        "game_id": [f"00{i:07d}" for i in range(n)],
        "game_date": dates,
        "team_tricode": [team] * n,
        "off_rtg": [115.0 + (i % 5) for i in range(n)],
        "efg_pct": [0.52 + 0.001 * i for i in range(n)],
        "ts_pct": [0.58 + 0.001 * i for i in range(n)],
        "tov_ratio": [12.0 + 0.1 * i for i in range(n)],
        "pace": [100.0 + 0.2 * i for i in range(n)],
    })


def _make_playtypes_df() -> pd.DataFrame:
    """Minimal playtypes rows for two players."""
    types = ["PRBallHandler", "Isolation", "Postup", "Spotup",
             "Handoff", "Cut", "OffScreen", "PRRollMan",
             "Transition", "OffRebound", "Misc"]
    rows = []
    for pid in [100001, 100002]:
        for pt in types:
            rows.append({
                "player_id": pid,
                "season": "2025-26",
                "play_type": pt,
                "freq_pct": round(1.0 / len(types), 3),
                "ppp": 1.0 + 0.01 * types.index(pt),
            })
    return pd.DataFrame(rows)


def _make_pf_df(team: str = _TEAM) -> pd.DataFrame:
    """Minimal player_pf rows for two players."""
    return pd.DataFrame({
        "player_id": [100001, 100002],
        "team_abbreviation": [team, team],
        "game_date": [_dt.date(2025, 11, 1), _dt.date(2025, 11, 1)],
        "pf": [2, 3],
        "min": ["30:00", "28:00"],
    })


def _make_tracking_df(team: str = _TEAM) -> pd.DataFrame:
    """Minimal player_tracking_features rows."""
    return pd.DataFrame({
        "player_id": [100001, 100002],
        "player_name": ["Alice", "Bob"],
        "season": ["2024-25", "2024-25"],
        "drives_team": [team, team],
        "drives_per_g": [4.0, 3.0],
        "drive_fg_pct": [0.45, 0.50],
        "drive_pts_pct": [0.20, 0.18],
        "drive_ast_per_drive": [0.35, 0.30],
        "passes_made_per_g": [40.0, 35.0],
        "ast_to_pass_pct": [0.18, 0.16],
        "ast_to_pass_pct_adj": [0.19, 0.17],
        "passing_team": [team, team],
        "cs_team": [team, team],
    })


def _patch_cache(**overrides) -> None:
    """Replace _SRC_CACHE entries for a test (mutates the module-level cache)."""
    _SRC_CACHE.clear()
    _SRC_CACHE.update(overrides)


# ---------------------------------------------------------------------------
# Fixture: patch parquet loads with synthetic data
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def stub_data():
    """Stub parquet loads with synthetic DataFrames for unit tests."""
    _patch_cache(
        team_adv=_make_adv_df(_TEAM, n=30),
        team_adv_disc=_make_adv_df(_TEAM, n=30),
        pt_2526=_make_playtypes_df(),
        player_pf=_make_pf_df(_TEAM),
        trk_feat=_make_tracking_df(_TEAM),
    )
    yield
    _SRC_CACHE.clear()


# ---------------------------------------------------------------------------
# 1. Build returns a valid AtlasArtifact
# ---------------------------------------------------------------------------

def test_build_returns_artifact(stub_data):
    """build() with stub data returns a populated AtlasArtifact."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    assert isinstance(art, AtlasArtifact)
    assert art.section == "halfcourt_offense"
    assert art.entity == "team"
    assert art.entity_id == _TEAM


def test_build_unknown_team(stub_data):
    """build() returns None for a team not in team_advanced_stats."""
    section = TeamHalfcourtOffense()
    art = section.build("ZZZ", _AS_OF)
    assert art is None


# ---------------------------------------------------------------------------
# 2. Provenance n is real game count (not n_seasons)
# ---------------------------------------------------------------------------

def test_provenance_n_equals_game_count(stub_data):
    """Provenance n must equal len(game rows) not 1 or 2."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    n = art.provenance["n"]
    assert n >= 5, f"n={n} fails min_n=5 gate (probably n_seasons not n_games)"
    assert n == 30  # stub has 30 rows


# ---------------------------------------------------------------------------
# 3. Proportion / range guards
# ---------------------------------------------------------------------------

def test_efficiency_ranges(stub_data):
    """off_rtg plausible; efg_pct, ts_pct in [0, 1.6]."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    eff = art.sub_fields["efficiency"]
    off_rtg = eff["off_rtg"]
    assert 80.0 <= off_rtg <= 160.0, f"off_rtg={off_rtg} out of range"
    for key in ("efg_pct", "ts_pct"):
        v = eff.get(key)
        if v is not None:
            assert 0.0 <= v <= 1.6, f"{key}={v} out of [0, 1.6]"


def test_freq_pct_in_unit_interval(stub_data):
    """All *_freq values in play_mix must be in [0, 1]."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    pm = art.sub_fields["play_mix"]
    freq_keys = [k for k in pm if k.endswith("_freq")]
    assert len(freq_keys) > 0, "no freq_pct keys found in play_mix"
    for k in freq_keys:
        v = pm[k]
        if v is not None:
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0, 1]"


def test_ppp_non_negative(stub_data):
    """ppp values must be non-negative when present."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    for k, v in art.sub_fields["ppp"].items():
        if isinstance(v, float):
            assert v >= 0.0, f"{k}={v} is negative"


# ---------------------------------------------------------------------------
# 4. CV slots are reserved (null values, correct dtype)
# ---------------------------------------------------------------------------

def test_cv_slots_reserved(stub_data):
    """avg_passes_per_poss slot must exist with value=None."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    assert "avg_passes_per_poss" in art.cv_fields
    slot = art.cv_fields["avg_passes_per_poss"]
    assert isinstance(slot, CVSlot)
    assert slot.value is None
    assert slot.dtype == "float"


def test_cv_fields_method_matches_artifact(stub_data):
    """cv_fields() declared slots match what build() embeds."""
    section = TeamHalfcourtOffense()
    declared = section.cv_fields()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    for name in declared:
        assert name in art.cv_fields


# ---------------------------------------------------------------------------
# 5. validate() passes on well-formed artifacts
# ---------------------------------------------------------------------------

def test_section_validate_passes(stub_data):
    """section.validate() returns True for a correctly built artifact."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    assert section.validate(art) is True


def test_intel_validator_passes(stub_data):
    """Full intel_validator suite passes (leak-free, face-valid, coverage, cv-schema)."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    result = intel_validate(section, art, min_n=5)
    assert result.coverage_ok, f"coverage failed: {result.reasons}"
    assert result.face_valid, f"face-validity failed: {result.reasons}"
    assert result.cv_schema_ok, f"cv-schema failed: {result.reasons}"
    assert result.leak_free, f"leak check failed: {result.reasons}"


# ---------------------------------------------------------------------------
# 6. Leak-safety: as_of boundary trims games
# ---------------------------------------------------------------------------

def test_leak_safe_as_of(stub_data):
    """Building with an earlier as_of returns fewer games (n strictly less)."""
    section = TeamHalfcourtOffense()
    art_full = section.build(_TEAM, _AS_OF)
    # as_of before the stub data starts -> should return None
    art_empty = section.build(_TEAM, _dt.datetime(2020, 1, 1))
    assert art_full is not None
    assert art_empty is None  # all 30 stub rows are after 2025-10-01


# ---------------------------------------------------------------------------
# 7. Required sub-field keys are always present
# ---------------------------------------------------------------------------

def test_required_sub_fields_present(stub_data):
    """All six top-level sub-field keys must be present regardless of data gaps."""
    section = TeamHalfcourtOffense()
    art = section.build(_TEAM, _AS_OF)
    assert art is not None
    required = {"efficiency", "play_mix", "ppp", "ball_movement",
                "halfcourt_ppp_direct", "motion_score"}
    assert required.issubset(art.sub_fields.keys())


# ---------------------------------------------------------------------------
# 8. Out-of-range proportion is nulled (not shipped > 1)
# ---------------------------------------------------------------------------

def test_bad_proportion_nulled(stub_data):
    """_clamp_pct removes values outside [0, ceil]."""
    from intel.team_halfcourt_offense import _clamp_pct
    assert _clamp_pct(1.5) is None       # > 1.0 -> null
    assert _clamp_pct(-0.1) is None      # < 0 -> null
    assert _clamp_pct(0.5) == 0.5        # valid
    assert _clamp_pct(1.5, ceil=1.6) == 1.5  # within efg/ts ceil


# ---------------------------------------------------------------------------
# 9. build_and_register dry_run smoke test
# ---------------------------------------------------------------------------

def test_build_and_register_dry_run(stub_data):
    """build_and_register with dry_run=True returns a valid manifest."""
    manifest = build_and_register(
        team_tricodes=[_TEAM],
        as_of=_AS_OF,
        dry_run=True,
    )
    assert manifest["section"] == "halfcourt_offense"
    assert manifest["n_entities"] >= 1
    assert "avg_passes_per_poss" in manifest["cv_fields"]
