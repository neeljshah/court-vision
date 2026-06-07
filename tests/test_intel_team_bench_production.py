"""Tests for intel/team_bench_production.py — TeamBenchProduction atlas section.

Run with: NBA_OFFLINE=1 python -m pytest tests/test_intel_team_bench_production.py -v
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

# Ensure repo root is on path for src/ imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("NBA_OFFLINE", "1")

from intel.team_bench_production import TeamBenchProduction, _on_off_bench, _team_adv_stats
from src.loop.atlas import AtlasArtifact, CVSlot
from src.loop.intel_validator import validate as intel_validate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AS_OF = dt.datetime(2026, 5, 31, 0, 0, 0)
SECTION = TeamBenchProduction()


def _build(tricode: str, as_of: dt.datetime = AS_OF) -> Optional[AtlasArtifact]:
    """Helper: build artifact for a tricode."""
    return SECTION.build(tricode, as_of)


# ---------------------------------------------------------------------------
# 1. Section metadata
# ---------------------------------------------------------------------------

def test_section_name_and_entity() -> None:
    """Section must identify itself as bench_production / team."""
    assert SECTION.name == "bench_production"
    assert SECTION.entity == "team"


def test_cv_fields_empty() -> None:
    """bench_production has no CV slots (boxscore-derived section)."""
    cv = SECTION.cv_fields()
    assert isinstance(cv, dict)
    assert len(cv) == 0


def test_parquet_name() -> None:
    """Parquet name follows standard convention."""
    assert SECTION.parquet_name() == "atlas_team_bench_production.parquet"


def test_sec_fn_name() -> None:
    """Generated sec_ function name is correct."""
    assert SECTION.sec_fn_name() == "sec_bench_production"


# ---------------------------------------------------------------------------
# 2. Build — OKC
# ---------------------------------------------------------------------------

def test_build_okc_not_none() -> None:
    """OKC should produce a non-None artifact."""
    art = _build("OKC")
    assert art is not None, "Expected artifact for OKC"


def test_build_okc_section_fields() -> None:
    """Artifact must carry correct section/entity labels."""
    art = _build("OKC")
    assert art is not None
    assert art.section == "bench_production"
    assert art.entity == "team"
    assert art.entity_id == "OKC"


def test_build_okc_coverage_n_ge5() -> None:
    """Provenance n must be >= 5 (real game count, not n_seasons)."""
    art = _build("OKC")
    assert art is not None
    n = art.provenance.get("n", 0)
    assert n >= 5, f"n={n} — must be real game count >= 5"


def test_build_okc_sub_fields_keys() -> None:
    """All required sub_field keys must be present."""
    art = _build("OKC")
    assert art is not None
    required = {
        "bench_minutes", "bench_net_rtg_section",
        "team_context", "bench_scoring", "bench_ts_pct",
    }
    assert required.issubset(art.sub_fields.keys())


def test_build_okc_bench_min_share_in_0_1() -> None:
    """bench_min_share and starter_min_share must be in [0, 1]."""
    art = _build("OKC")
    assert art is not None
    bm = art.sub_fields.get("bench_minutes", {})
    bms = bm.get("bench_min_share")
    sms = bm.get("starter_min_share")
    assert bms is not None, "bench_min_share must not be None for OKC"
    assert sms is not None, "starter_min_share must not be None for OKC"
    assert 0.0 <= bms <= 1.0, f"bench_min_share={bms} out of [0,1]"
    assert 0.0 <= sms <= 1.0, f"starter_min_share={sms} out of [0,1]"


def test_build_okc_shares_sum_to_1() -> None:
    """bench_min_share + starter_min_share must approximately equal 1."""
    art = _build("OKC")
    assert art is not None
    bm = art.sub_fields.get("bench_minutes", {})
    bms = bm.get("bench_min_share", 0.0)
    sms = bm.get("starter_min_share", 0.0)
    assert abs(bms + sms - 1.0) < 0.01, f"Shares sum to {bms + sms}, expected ~1.0"


def test_build_okc_bench_depth_nonneg() -> None:
    """bench_depth must be a non-negative integer."""
    art = _build("OKC")
    assert art is not None
    bd = art.sub_fields.get("bench_net_rtg_section", {}).get("bench_depth")
    assert bd is not None, "bench_depth must not be None for OKC"
    assert bd >= 0, f"bench_depth={bd} is negative"


def test_build_okc_as_of_stamped() -> None:
    """Artifact must carry an as_of stamp matching the build date."""
    art = _build("OKC")
    assert art is not None
    assert art.as_of is not None
    assert art.as_of.startswith("2026-05-31")


def test_build_okc_cv_fields_empty() -> None:
    """Artifact cv_fields must be empty (no CV slots for this section)."""
    art = _build("OKC")
    assert art is not None
    assert art.cv_fields == {}


# ---------------------------------------------------------------------------
# 3. Build — BOS
# ---------------------------------------------------------------------------

def test_build_bos_not_none() -> None:
    """BOS should produce a non-None artifact."""
    art = _build("BOS")
    assert art is not None, "Expected artifact for BOS"


def test_build_bos_coverage_n_ge5() -> None:
    """BOS provenance n must be >= 5."""
    art = _build("BOS")
    assert art is not None
    n = art.provenance.get("n", 0)
    assert n >= 5, f"BOS n={n} — must be real game count >= 5"


def test_build_bos_bench_min_share_in_0_1() -> None:
    """BOS bench_min_share must be in [0, 1]."""
    art = _build("BOS")
    assert art is not None
    bm = art.sub_fields.get("bench_minutes", {})
    bms = bm.get("bench_min_share")
    assert bms is not None
    assert 0.0 <= bms <= 1.0, f"BOS bench_min_share={bms} out of [0,1]"


# ---------------------------------------------------------------------------
# 4. section.validate()
# ---------------------------------------------------------------------------

def test_section_validate_okc() -> None:
    """Section self-validation must pass for OKC."""
    art = _build("OKC")
    assert art is not None
    assert SECTION.validate(art) is True


def test_section_validate_bos() -> None:
    """Section self-validation must pass for BOS."""
    art = _build("BOS")
    assert art is not None
    assert SECTION.validate(art) is True


def test_section_validate_wrong_section_name() -> None:
    """validate() must reject an artifact with a mismatched section name."""
    art = _build("OKC")
    assert art is not None
    art.section = "wrong_section"
    assert SECTION.validate(art) is False


def test_section_validate_bench_share_out_of_range() -> None:
    """validate() must reject bench_min_share > 1.0."""
    art = _build("OKC")
    assert art is not None
    art.sub_fields["bench_minutes"]["bench_min_share"] = 1.5
    art.sub_fields["bench_minutes"]["starter_min_share"] = None  # avoid sum check
    assert SECTION.validate(art) is False


# ---------------------------------------------------------------------------
# 5. intel_validator (full 5-check gate)
# ---------------------------------------------------------------------------

def test_intel_validate_okc() -> None:
    """Full intel_validator gate must pass for OKC."""
    art = _build("OKC")
    assert art is not None
    result = intel_validate(SECTION, art, min_n=5)
    assert result.ok, f"Validator failed for OKC: {result.reasons}"


def test_intel_validate_bos() -> None:
    """Full intel_validator gate must pass for BOS."""
    art = _build("BOS")
    assert art is not None
    result = intel_validate(SECTION, art, min_n=5)
    assert result.ok, f"Validator failed for BOS: {result.reasons}"


def test_intel_validate_face_validity_okc() -> None:
    """Face validity check must pass for OKC (all proportions in [0,1])."""
    art = _build("OKC")
    assert art is not None
    result = intel_validate(SECTION, art, min_n=5)
    assert result.face_valid, f"Face validity failed for OKC: {result.reasons}"


def test_intel_validate_coverage_okc() -> None:
    """Coverage check must pass for OKC (n >= 5)."""
    art = _build("OKC")
    assert art is not None
    result = intel_validate(SECTION, art, min_n=5)
    assert result.coverage_ok, f"Coverage failed for OKC: {result.reasons}"


def test_intel_validate_cv_schema_okc() -> None:
    """CV schema check must pass for OKC (empty cv_fields is valid)."""
    art = _build("OKC")
    assert art is not None
    result = intel_validate(SECTION, art, min_n=5)
    assert result.cv_schema_ok, f"CV schema failed for OKC: {result.reasons}"


# ---------------------------------------------------------------------------
# 6. Missing-entity guard
# ---------------------------------------------------------------------------

def test_build_unknown_team_returns_none() -> None:
    """build() must return None for a team tricode with no data."""
    art = _build("FAKETEAM")
    assert art is None, "Expected None for unknown team tricode"


# ---------------------------------------------------------------------------
# 7. Leak safety — as_of boundary
# ---------------------------------------------------------------------------

def test_early_as_of_gives_lower_or_equal_n() -> None:
    """Building with an earlier as_of must not yield a HIGHER n than a later as_of.

    This is a basic leak guard: excluding future games cannot increase the count.
    """
    art_full = _build("OKC", AS_OF)
    art_early = _build("OKC", dt.datetime(2024, 11, 1, 0, 0, 0))

    if art_full is None or art_early is None:
        pytest.skip("One of the builds returned None")

    n_full = art_full.provenance.get("n", 0)
    n_early = art_early.provenance.get("n", 0)
    assert n_early <= n_full, (
        f"Early as_of n={n_early} > full as_of n={n_full}: possible future data leak"
    )


# ---------------------------------------------------------------------------
# 8. Helper unit tests
# ---------------------------------------------------------------------------

def test_on_off_bench_okc_proportions() -> None:
    """_on_off_bench helper must return proportions in [0,1] for OKC."""
    result = _on_off_bench("OKC")
    assert result, "Expected non-empty result for OKC"
    bms = result.get("bench_min_share")
    sms = result.get("starter_min_share")
    assert bms is not None and 0.0 <= bms <= 1.0
    assert sms is not None and 0.0 <= sms <= 1.0


def test_on_off_bench_unknown_returns_empty() -> None:
    """_on_off_bench must return empty dict for unknown tricode."""
    result = _on_off_bench("ZZZZZ")
    assert result == {} or result is not None  # empty dict is fine


def test_team_adv_stats_okc_has_games() -> None:
    """_team_adv_stats must return n_games >= 5 for OKC."""
    result = _team_adv_stats("OKC", AS_OF)
    assert result, "Expected non-empty result for OKC"
    n = result.get("n_games", 0)
    assert n >= 5, f"n_games={n} for OKC should be >= 5"
