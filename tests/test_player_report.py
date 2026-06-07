"""Tests for src/intel/player_report.py -- the player intelligence dossier synthesizer.

These tests run against the SHIPPED atlas parquets + profile factory (offline,
read-only). They assert structural contract + that deterministic archetype rules
produce the right reads for known player types:

  * Jokic (203999)            -> playmaking-heavy big (elite passer + rebounder)
  * a 3&D wing (Taurean Prince, 1627752) -> low usage, high catch-and-shoot
  * a lead guard (SGA, 1628983) -> high-usage primary initiator

If the atlas parquets are not present (fresh checkout / CI without data) the
data-dependent tests skip rather than fail.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("NBA_OFFLINE", "1")

from src.intel import player_report as pr  # noqa: E402

JOKIC = 203999
PRINCE_3D = 1627752     # Taurean Prince -- low-usage 3&D wing
SGA = 1628983           # Shai Gilgeous-Alexander -- lead guard

_DATA_PRESENT = (pr._ATLAS_DIR / "atlas_player_usage_role.parquet").exists()
_needs_data = pytest.mark.skipif(not _DATA_PRESENT, reason="atlas parquets not present")


# --------------------------------------------------------------------------- #
# Pure helpers (no data needed)
# --------------------------------------------------------------------------- #
def test_as_dict_handles_json_string_and_dict_and_none():
    assert pr._as_dict('{"a": 1}') == {"a": 1}
    assert pr._as_dict({"b": 2}) == {"b": 2}
    assert pr._as_dict(None) == {}
    assert pr._as_dict("not json") == {}


def test_num_coerces_and_filters_nan():
    assert pr._num("3.5") == 3.5
    assert pr._num(None) is None
    assert pr._num(float("nan")) is None
    assert pr._num(float("inf")) is None


def test_safe_nested_get():
    d = {"a": {"b": {"c": 7}}}
    assert pr._safe(d, "a", "b", "c") == 7
    assert pr._safe(d, "a", "x") is None
    assert pr._safe(d, "z") is None


def test_pct_word_ladder():
    assert pr._pct_word(99) == "elite"
    assert pr._pct_word(80) == "above-average"
    assert pr._pct_word(50) == "average"
    assert pr._pct_word(5) == "poor"
    assert pr._pct_word(None) == ""


# --------------------------------------------------------------------------- #
# Percentile engine
# --------------------------------------------------------------------------- #
@_needs_data
def test_league_percentile_orientation():
    # higher-is-better: a huge usage value should land near the top
    p_hi = pr.league_percentile("usage_rate", 0.45)
    assert p_hi is not None and p_hi >= 90
    # lower-is-better metric (foul_rate) -> a tiny value should rank high (elite discipline)
    p_lo = pr.league_percentile("foul_rate", 0.5)
    if p_lo is not None:
        assert 0 <= p_lo <= 100
    # unknown metric / None value -> None
    assert pr.league_percentile("does_not_exist", 1.0) is None
    assert pr.league_percentile("usage_rate", None) is None


# --------------------------------------------------------------------------- #
# Report structure contract
# --------------------------------------------------------------------------- #
@_needs_data
def test_report_schema_contract():
    rep = pr.build_player_report(JOKIC)
    assert rep["schema_version"] == pr.SCHEMA_VERSION
    assert rep["player_id"] == JOKIC
    for block in ("archetype_role", "scoring", "playmaking", "rebounding",
                  "defense", "situational", "consistency_durability"):
        assert block in rep, block
        assert "data" in rep[block] and "provenance" in rep[block]
    # strengths/weaknesses
    sw = rep["strengths_weaknesses"]
    assert "ranked" in sw and "strengths" in sw and "weaknesses" in sw
    # completeness
    dc = rep["data_completeness"]
    assert 0.0 <= dc["score"] <= 1.0
    assert dc["sections_total"] == len(pr.ATLAS_SECTIONS)
    assert dc["sections_present"] <= dc["sections_total"]
    # narrative is a non-trivial string
    assert isinstance(rep["narrative"], str) and len(rep["narrative"]) > 40


@_needs_data
def test_provenance_stamped_per_section():
    rep = pr.build_player_report(JOKIC)
    prov = rep["playmaking"]["provenance"]
    for key in ("source", "n", "confidence", "as_of", "present"):
        assert key in prov, key
    assert prov["source"].endswith("playmaking_network.parquet")


@_needs_data
def test_missing_sections_flagged_in_completeness():
    rep = pr.build_player_report(JOKIC)
    dc = rep["data_completeness"]
    # Jokic has no atlas defensive_profile row -> must be flagged as low/missing
    assert "defensive_profile" in dc["low_or_missing_sections"]


# --------------------------------------------------------------------------- #
# Archetype reads -- the headline behavioral assertions
# --------------------------------------------------------------------------- #
@_needs_data
def test_jokic_reads_as_playmaking_big():
    rep = pr.build_player_report(JOKIC)
    arch = rep["archetype_role"]["data"]["archetype"]
    assert arch["label"] == "Playmaking Big"
    assert "high_playmaking" in arch["tags"]
    assert "big" in arch["tags"]
    # elite passer + rebounder should both surface as strengths
    strength_metrics = {s["metric"] for s in rep["strengths_weaknesses"]["strengths"]}
    assert "ast_pts_created" in strength_metrics or "ast_pct" in strength_metrics
    assert "total_reb_rate" in strength_metrics
    # narrative mentions passing and elite
    narr = rep["narrative"].lower()
    assert "passer" in narr or "passing" in narr
    assert "elite" in narr


@_needs_data
def test_3d_wing_reads_as_low_usage_high_catch_shoot():
    rep = pr.build_player_report(PRINCE_3D)
    arch = rep["archetype_role"]["data"]["archetype"]
    assert arch["label"] == "3&D Wing"
    assert "low_usage" in arch["tags"]
    assert "catch_and_shoot" in arch["tags"]
    # usage percentile must be low
    assert rep["archetype_role"]["data"]["usage_pct_rank"] <= 40
    # catch-shoot efficiency must rank high
    cs_rank = rep["scoring"]["data"].get("catch_shoot_pct_rank")
    assert cs_rank is not None and cs_rank >= 60


@_needs_data
def test_lead_guard_is_high_usage_initiator():
    rep = pr.build_player_report(SGA)
    arch = rep["archetype_role"]["data"]["archetype"]
    assert "high_usage" in arch["tags"]
    # one of the guard-creator labels
    assert arch["label"] in (
        "Primary Initiator / Lead Guard",
        "High-Usage Shot Creator",
        "Playmaking Guard",
        "High-Usage Scorer",
    )


@_needs_data
def test_builder_class_matches_function():
    a = pr.PlayerReportBuilder().build(JOKIC)
    b = pr.build_player_report(JOKIC)
    assert a["player_id"] == b["player_id"]
    assert a["archetype_role"]["data"]["archetype"]["label"] == \
        b["archetype_role"]["data"]["archetype"]["label"]


@_needs_data
def test_unknown_player_degrades_gracefully():
    # a player id with no atlas rows / no profile must not crash
    rep = pr.build_player_report(999999999)
    assert rep["player_id"] == 999999999
    assert rep["data_completeness"]["sections_present"] == 0
    assert isinstance(rep["narrative"], str)
