"""test_gate_coverage_report.py — Light acceptance tests for gate_coverage_report.

N-GATE-001 done-criteria:
- every flag in src/brain/flags.py appears EXACTLY once in the map
- every prediction surface appears EXACTLY once
- output is a clean markdown table + gap list
- runtime < 5 s

Python 3.9 compatible. No app boot. No torch. No large parquet loads.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))

from gate_coverage_report import (  # noqa: E402
    _parse_flags_from_source,
    _enumerate_prediction_surfaces,
    build_coverage_map,
    emit_report,
    REPO_ROOT,
)

# ---------------------------------------------------------------------------
# Known flags from src/brain/flags.py (must each appear exactly once)
# ---------------------------------------------------------------------------
BRAIN_FLAGS = {
    "CV_AGENT_DEF_SUPP",
    "CV_AGENT_PLAYTYPE",
    "CV_AGENT_FOUL_STATE",
    "CV_AGENT_FATIGUE",
    "CV_BRAIN_GLS",
    "CV_BRAIN_WEIGHTS",
    "CV_INGAME_STATE",
    "CV_INGAME_SHRINK",
    "CV_INGAME_UNIVERSAL_WP",
    "CV_NARRATE",
    "CV_LLM_SCHEME",
}

# Pre-existing flags documented in flags.py
PREEXISTING_FLAGS = {
    "CV_LLM_CONTEXT",
    "CV_INGAME_SBS",
    "CV_LIVE_SIM",
    "CV_AVAIL_PARQUET_FALLBACK",
    "CV_ENSEMBLE16_DECORR",
    "CV_ENGINE_RELIABILITY_WEIGHTS",
}


# ---------------------------------------------------------------------------
# 1. Source parser returns all brain flags exactly once
# ---------------------------------------------------------------------------

def test_parse_flags_returns_all_brain_flags():
    parsed = _parse_flags_from_source()
    names = [f["name"] for f in parsed]
    missing = BRAIN_FLAGS - set(names)
    assert not missing, f"Missing brain flags in parsed output: {missing}"


def test_parse_flags_no_duplicates():
    parsed = _parse_flags_from_source()
    names = [f["name"] for f in parsed]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"Duplicate flag names in parsed output: {duplicates}"


def test_all_brain_flags_have_phase():
    parsed = _parse_flags_from_source()
    no_phase = [f["name"] for f in parsed if not f.get("phase")]
    assert not no_phase, f"Flags missing phase: {no_phase}"


# ---------------------------------------------------------------------------
# 2. Surface enumerator returns each surface exactly once
# ---------------------------------------------------------------------------

def test_surfaces_no_duplicates():
    surfaces = _enumerate_prediction_surfaces()
    names = [s["name"] for s in surfaces]
    duplicates = {n for n in names if names.count(n) > 1}
    assert not duplicates, f"Duplicate surface names: {duplicates}"


def test_surfaces_required_fields():
    surfaces = _enumerate_prediction_surfaces()
    for s in surfaces:
        assert "name" in s, f"Surface missing 'name': {s}"
        assert "category" in s, f"Surface missing 'category': {s}"
        assert "source" in s, f"Surface missing 'source': {s}"


def test_prop_quantile_surfaces_cover_all_stats_and_quantiles():
    """7 stats × 3 quantiles = 21 prop_quantile surfaces must all be present."""
    surfaces = _enumerate_prediction_surfaces()
    pq_names = {s["name"] for s in surfaces if s["category"] == "prop_quantile"}
    stats = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
    quantiles = ("q10", "q50", "q90")
    expected = {f"prop:{stat}:{q}" for stat in stats for q in quantiles}
    missing = expected - pq_names
    assert not missing, f"Missing prop_quantile surfaces: {missing}"
    assert len(pq_names) == 21, f"Expected 21 prop_quantile surfaces, got {len(pq_names)}"


# ---------------------------------------------------------------------------
# 3. build_coverage_map returns complete structured data
# ---------------------------------------------------------------------------

def test_build_coverage_map_returns_required_keys():
    data = build_coverage_map()
    for key in ("flags", "surfaces", "gaps", "generated_at"):
        assert key in data, f"Missing key in coverage map: {key}"


def test_build_coverage_map_all_brain_flags_present_exactly_once():
    data = build_coverage_map()
    flag_names = [f["flag_name"] for f in data["flags"]]
    for flag in BRAIN_FLAGS:
        count = flag_names.count(flag)
        assert count == 1, f"Flag {flag!r} appears {count} times (expected exactly 1)"


def test_build_coverage_map_preexisting_flags_present():
    data = build_coverage_map()
    flag_names = {f["flag_name"] for f in data["flags"]}
    missing = PREEXISTING_FLAGS - flag_names
    assert not missing, f"Pre-existing flags missing from map: {missing}"


def test_build_coverage_map_each_surface_exactly_once():
    data = build_coverage_map()
    surface_names = [s["surface_name"] for s in data["surfaces"]]
    duplicates = {n for n in surface_names if surface_names.count(n) > 1}
    assert not duplicates, f"Duplicate surface names in coverage map: {duplicates}"


def test_build_coverage_map_flag_rows_have_required_fields():
    data = build_coverage_map()
    required = {"flag_name", "registry", "phase", "has_gate_text", "verdict", "desc"}
    for f in data["flags"]:
        missing = required - set(f.keys())
        assert not missing, f"Flag row {f.get('flag_name')} missing fields: {missing}"


def test_build_coverage_map_surface_rows_have_required_fields():
    data = build_coverage_map()
    required = {"surface_name", "category", "source", "verdict"}
    for s in data["surfaces"]:
        missing = required - set(s.keys())
        assert not missing, f"Surface row {s.get('surface_name')} missing fields: {missing}"


def test_build_coverage_map_gaps_are_list():
    data = build_coverage_map()
    assert isinstance(data["gaps"], list)
    for g in data["gaps"]:
        assert "item" in g
        assert "kind" in g
        assert "gap_type" in g
        assert "candidate_action" in g


# ---------------------------------------------------------------------------
# 4. emit_report writes a valid markdown file
# ---------------------------------------------------------------------------

def test_emit_report_writes_file(tmp_path: Path):
    data = build_coverage_map()
    out = tmp_path / "GATE_COVERAGE.md"
    emit_report(data, out)
    assert out.exists(), "emit_report did not create the output file"
    content = out.read_text(encoding="utf-8")
    assert "## 1. Feature Flags" in content
    assert "## 2. Prediction Surfaces" in content
    assert "## 3. Coverage Gaps" in content
    assert "## 4. Coverage Summary" in content


def test_emit_report_contains_all_brain_flags(tmp_path: Path):
    data = build_coverage_map()
    out = tmp_path / "GATE_COVERAGE.md"
    emit_report(data, out)
    content = out.read_text(encoding="utf-8")
    for flag in BRAIN_FLAGS:
        assert flag in content, f"Brain flag {flag!r} not found in GATE_COVERAGE.md"


def test_emit_report_contains_prop_surfaces(tmp_path: Path):
    data = build_coverage_map()
    out = tmp_path / "GATE_COVERAGE.md"
    emit_report(data, out)
    content = out.read_text(encoding="utf-8")
    # At least pts and ast prop surfaces should appear
    assert "prop:pts:q50" in content
    assert "prop:ast:q50" in content


# ---------------------------------------------------------------------------
# 5. Runtime gate — full pipeline < 5 s
# ---------------------------------------------------------------------------

def test_build_coverage_map_runtime_under_5s():
    t0 = time.perf_counter()
    build_coverage_map()
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"build_coverage_map took {elapsed:.2f}s (limit: 5s)"
