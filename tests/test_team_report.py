"""Tests for src/intel/team_report.py — the team intelligence dossier assembler.

Deterministic assembly over the shipped atlas_team_*.parquet sections. These
tests use the real atlas parquets when present and otherwise synthesize a tiny
fixture so the suite is runnable on a fresh clone.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.intel import team_report as tr  # noqa: E402

_ATLAS_DIR = ROOT / "data" / "cache"
_HAVE_REAL = (_ATLAS_DIR / "atlas_team_offensive_scheme.parquet").exists()


# ---------------------------------------------------------------------------
# Pure-helper tests (no data dependency)
# ---------------------------------------------------------------------------

def test_coerce_parses_json_string_cell():
    cell = '{"pace_pg": 101.25, "pace_identity": "FAST"}'
    out = tr._coerce(cell)
    assert isinstance(out, dict)
    assert out["pace_identity"] == "FAST"


def test_coerce_passes_through_non_json():
    assert tr._coerce("FAST") == "FAST"
    assert tr._coerce(3.14) == 3.14
    assert tr._coerce(None) is None


def test_get_nested_from_json_string():
    row = pd.Series({"pace": '{"pace_pg": 101.25, "pace_identity": "FAST"}'})
    assert tr._get(row, "pace", "pace_pg") == 101.25
    assert tr._get(row, "pace", "pace_identity") == "FAST"
    assert tr._get(row, "pace", "missing") is None


def test_get_treats_defer_stub_as_missing():
    row = pd.Series({"iso_rate": '{"_note": "DEFER: not available"}'})
    assert tr._get(row, "iso_rate") is None


def test_clean_handles_nan_and_numpy():
    import numpy as np
    assert tr.clean(np.float64("nan")) is None
    assert tr.clean(np.int64(5)) == 5
    assert tr.clean(np.float64(1.23456)) == 1.2346  # rounded to 4dp


def test_pctile_word_bands():
    assert tr._pctile_word(0.95) == "elite"
    assert tr._pctile_word(0.75) == "strong"
    assert tr._pctile_word(0.5) == "average"
    assert tr._pctile_word(0.25) == "below-average"
    assert tr._pctile_word(0.05) == "poor"
    assert tr._pctile_word(None) == "unknown"


# ---------------------------------------------------------------------------
# Synthetic-fixture tests (always runnable)
# ---------------------------------------------------------------------------

def _synthetic_atlases():
    """Minimal 3-team atlas covering enough sections to exercise the pipeline."""
    def osc(tri, pace, off):
        return {
            "team_tricode": tri,
            "pace": json.dumps({"pace_pg": pace, "pace_identity":
                                "FAST" if pace > 100 else "SLOW"}),
            "shot_diet": json.dumps({"off_rtg": off, "efg_pct": 0.55,
                                     "ast_pct": 0.6, "tov_ratio": 12.0}),
            "pnr": json.dumps({"pnr_ppp": 0.97}),
            "drive_rate": json.dumps({"drives_per_g_mean": 4.5}),
            "ball_movement": json.dumps({"passes_made_per_g_mean": 23.0}),
            "tempo_spacing_cv": json.dumps({"team_transition_share_z": 0.6,
                                            "team_avg_spacing_z": 0.6}),
            "n": 245, "confidence": "high", "as_of": "2026-05-31",
        }
    def dsc(tri, drtg):
        return {
            "team_tricode": tri,
            "coverage_scheme": json.dumps({"dominant_tag": "DROP COVERAGE",
                                           "all_tags": ["DROP COVERAGE"]}),
            "scheme_axes": json.dumps({"drop_score": 0.4,
                                       "paint_protection_score": 0.4}),
            "ratings_context": json.dumps({"def_rtg": drtg}),
            "switch_rate": json.dumps({"_note": "DEFER"}),
            "top_impact_players": json.dumps([{"player_name": "Star One"}]),
            "n": 245, "confidence": "high", "as_of": "2026-05-31",
        }
    teams = [("AAA", 102.0, 118.0, 108.0),
             ("BBB", 98.0, 112.0, 112.0),
             ("CCC", 100.0, 110.0, 115.0)]
    return {
        "offensive_scheme": pd.DataFrame([osc(t, p, o) for t, p, o, _ in teams]),
        "defensive_scheme": pd.DataFrame([dsc(t, d) for t, _, _, d in teams]),
    }


def test_league_context_ranks_best_first():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    off = ctx["offensive_scheme.off_rtg"]["teams"]
    # AAA has highest off_rtg -> rank 1, pctile 1.0
    assert off["AAA"]["rank"] == 1
    assert off["AAA"]["pctile"] == 1.0
    # CCC lowest off_rtg -> rank 3, pctile 0.0
    assert off["CCC"]["rank"] == 3
    assert off["CCC"]["pctile"] == 0.0
    # def_rtg is lower-is-better: AAA best (108) -> rank 1
    drt = ctx["defensive_scheme.def_rtg"]["teams"]
    assert drt["AAA"]["rank"] == 1
    assert drt["CCC"]["rank"] == 3


def test_build_report_synthetic_structure():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    d = tr.build_team_report("AAA", atlases, ctx, build_date="2026-05-31")
    assert d["team_tricode"] == "AAA"
    assert d["schema_version"] == tr.SCHEMA_VERSION
    assert "blocks" in d and "how_they_play" in d and "completeness" in d
    # offensive + defensive present, others missing (graceful)
    assert d["blocks"]["offensive_identity"]["present"] is True
    assert d["blocks"]["defensive_identity"]["present"] is True
    assert d["blocks"]["rebounding"]["present"] is False
    # narrative mentions the team and is non-empty
    assert "AAA" in d["how_they_play"]
    assert len(d["how_they_play"]) > 20


def test_provenance_stamped_on_present_blocks():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    d = tr.build_team_report("AAA", atlases, ctx)
    prov = d["blocks"]["offensive_identity"]["provenance"]
    assert prov is not None
    assert prov["confidence"] in tr.CONF_ORDER
    assert any("atlas_team_offensive_scheme" in s for s in prov["sources"])
    assert prov["as_of"] == "2026-05-31"


def test_completeness_summary_counts():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    d = tr.build_team_report("AAA", atlases, ctx)
    c = d["completeness"]
    assert c["n_blocks_expected"] == 8  # 7 builders + strengths_weaknesses
    assert "offensive_identity" in c["present"]
    assert "rebounding" in c["missing"]
    assert 0 <= c["coverage_pct"] <= 100


def test_strengths_weaknesses_polarity():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    d = tr.build_team_report("AAA", atlases, ctx)
    sw = d["blocks"]["strengths_weaknesses"]["data"]
    assert sw is not None
    # AAA is best off_rtg AND best def_rtg -> both should be top-tier (pctile 1.0).
    # (the displayed strengths list is capped at 6, so assert on all_ranks.)
    by_label = {r["label"]: r for r in sw["all_ranks"]}
    assert by_label["offensive efficiency"]["pctile"] == 1.0
    assert by_label["defensive efficiency"]["pctile"] == 1.0
    assert by_label["offensive efficiency"]["tier"] == "elite"


def test_missing_team_yields_empty_but_valid_dossier():
    atlases = _synthetic_atlases()
    ctx = tr.build_league_context(atlases)
    d = tr.build_team_report("ZZZ", atlases, ctx)  # not in fixture
    assert d["team_tricode"] == "ZZZ"
    assert d["completeness"]["n_blocks_present"] == 0
    assert d["how_they_play"].startswith("Insufficient data")


# ---------------------------------------------------------------------------
# Real-data tests (skipped on a fresh clone without the atlas parquets)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_REAL, reason="atlas_team_*.parquet not present")
def test_real_all_teams_build_and_serialize():
    reports = tr.build_all_team_reports()
    assert len(reports) >= 28  # ~30 teams
    for tri, d in reports.items():
        # every dossier must be JSON-serializable (no numpy/NaN leakage)
        json.dumps(d, default=str)
        assert d["completeness"]["coverage_pct"] > 0
        assert isinstance(d["how_they_play"], str) and d["how_they_play"]


@pytest.mark.skipif(not _HAVE_REAL, reason="atlas_team_*.parquet not present")
def test_real_okc_is_elite_defense():
    """OKC (2024-25) was the #1 defense — sanity-check the percentile engine."""
    d = tr.build_team_report("OKC")
    sw = d["blocks"]["strengths_weaknesses"]["data"]
    labels = {s["label"] for s in sw["strengths"]}
    assert "defensive efficiency" in labels
    drtg_block = d["blocks"]["defensive_identity"]["data"]
    assert drtg_block["coverage_scheme"] is not None


@pytest.mark.skipif(not _HAVE_REAL, reason="atlas_team_*.parquet not present")
def test_real_narrative_has_offense_and_defense():
    d = tr.build_team_report("BOS")
    narr = d["how_they_play"]
    assert "offense" in narr.lower()
    assert "defensively" in narr.lower()
