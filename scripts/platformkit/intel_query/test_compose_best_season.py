"""Per-file tests for the season-awareness gap fix: compose_best() answering
a season-scoped "best X" question ("this season" / an explicit season token)
must never silently answer a DIFFERENT season than asked.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_compose_best_season.py -q

Acceptance criteria (see compose_best_season.py + compose_best.py docstrings):
  1. No season token in the question -> compose_best(aspect) byte-stable
     (identical dict, no new keys) whether requested_season is omitted or
     passed explicitly as None.
  2. A season token that mismatches the gate-selected primary claim's own
     window, WITH a declared+VERIFIED season_fallback claim -> that claim's
     own ranking/caveats/provenance are used verbatim, labelled
     "season-matched VERIFIED ranking (not gate-canonical)".
  3. Same mismatch with NO declared/available fallback -> the original
     canonical claim stays primary, with an honest season-mismatch caveat
     prepended -- never a silent wrong-season answer.
  4. Both hyphen conventions ('2024-25' / '2024_25' / 'season_2024-25') in
     a claim's criteria.window normalize to the same season for comparison.
  5. detect_requested_season parses 'this season'/'current season' and
     explicit 'YYYY-YY'/'YYYY YY'/'YYYY_YY' tokens.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import compose_best as cb_mod
from scripts.platformkit.intel_query import compose_best_season as season_mod

_PRIMARY_2024 = "fixture_canonical_2024_25"
_FALLBACK_2025 = "fixture_asof_approx_2025_26"


def _ranking_claim(claim_id: str, window: str, top_name: str, caveats: list[str]) -> dict:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": "Who is the best fixture shooter?",
        "criteria": {"metric": "fixture_metric", "formula": "fixture_metric", "entity_key": "player_id", "window": window},
        "ranking": [{"rank": 1, "player_id": 1, "player_name": top_name, "value": 0.9, "n": 40}],
        "source_files": [f"data/fake/{claim_id}.parquet"],
        "computed_at": "2026-07-18T00:00:00+00:00",
        "n_considered": 10,
        "n_excluded_below_floor": 0,
        "caveats": caveats,
    }


@pytest.fixture
def season_claims(tmp_path, monkeypatch):
    claims_path = tmp_path / "nba_canonical_shooter_claims.jsonl"
    validation_path = tmp_path / "validation.json"

    primary = _ranking_claim(_PRIMARY_2024, "2024-25", "Old Canonical Player", ["2024-25 canonical caveat"])
    fallback = _ranking_claim(_FALLBACK_2025, "2025-26", "New Season Player",
                               ["ATLAS-UNAVAILABLE-2025-26 caveat", "PREDICTIVE_VERIFIED receipt caveat"])

    with open(claims_path, "w", encoding="ascii") as f:
        for row in (primary, fallback):
            f.write(json.dumps(row) + "\n")

    validation_summary = {
        "component": "fixture_validation",
        "n_claims": 2,
        "details": [
            {"claim_id": _PRIMARY_2024, "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": _FALLBACK_2025, "verdict": "VERIFIED", "reason": "ok"},
        ],
    }
    validation_path.write_text(json.dumps(validation_summary), encoding="ascii")
    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))
    return claims_path, validation_path


def _season_config(verdict_file, season_fallback=None):
    return cb_mod._AspectConfig(
        verdict_file=verdict_file,
        verdict_to_primary_claim={"REJECT_X": _PRIMARY_2024},
        attribution_axes=(),
        domain_filter=None,
        season_fallback=season_fallback,
    )


@pytest.fixture
def season_aspect_with_fallback(tmp_path, monkeypatch, season_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_X"}), encoding="ascii")
    config = _season_config(verdict_file, season_fallback={"2025-26": _FALLBACK_2025})
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_season": config})
    return verdict_file


@pytest.fixture
def season_aspect_no_fallback(tmp_path, monkeypatch, season_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_X"}), encoding="ascii")
    config = _season_config(verdict_file, season_fallback=None)
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_season": config})
    return verdict_file


# --- 1. no-token byte stability -----------------------------------------------

def test_no_token_omitted_vs_explicit_none_are_identical(season_aspect_with_fallback):
    a = cb_mod.compose_best("fixture_season")
    b = cb_mod.compose_best("fixture_season", requested_season=None)
    a.pop("computed_at"); b.pop("computed_at")  # real wall-clock timestamp, not a behavior field
    assert a == b
    assert "requested_season" not in a["primary"]
    assert "authority" not in a["primary"]
    assert a["conclusion"] == "Old Canonical Player"


# --- 2. season-matched substitution -------------------------------------------

def test_season_matched_substitution_carries_receipts_and_caveats(season_aspect_with_fallback):
    result = cb_mod.compose_best("fixture_season", requested_season="2025-26")
    assert result["conclusion"] == "New Season Player"
    assert result["primary"]["claim_id"] == _FALLBACK_2025
    assert result["primary"]["authority"] == "season-matched VERIFIED ranking (not gate-canonical)"
    assert result["primary"]["requested_season"] == "2025-26"
    assert "gate_verdict" not in result["primary"]
    # caveats + provenance carried VERBATIM from the fallback claim, not merged/rewritten
    assert "ATLAS-UNAVAILABLE-2025-26 caveat" in result["caveats"]
    assert "PREDICTIVE_VERIFIED receipt caveat" in result["caveats"]
    assert "2024-25 canonical caveat" not in result["caveats"]
    assert {e["claim_id"] for e in result["provenance"]} == {_FALLBACK_2025}


def test_fallback_found_in_its_own_asof_approx_store(tmp_path, monkeypatch):
    """Store-split regression (review fix): the 2025-26 asof_approx claim now
    lives in shooter_composite_v2_asof_approx_claims.jsonl. That name must be
    in _BEST_STORES or pairs_for_claim_stores filters it out and the
    substitution silently degrades to the mismatch-caveat path."""
    primary_path = tmp_path / "nba_canonical_shooter_claims.jsonl"
    fallback_path = tmp_path / "shooter_composite_v2_asof_approx_claims.jsonl"
    primary = _ranking_claim(_PRIMARY_2024, "2024-25", "Old Canonical Player", ["c1"])
    fallback = _ranking_claim(_FALLBACK_2025, "2025-26", "New Season Player", ["c2"])
    primary_path.write_text(json.dumps(primary) + "\n", encoding="ascii")
    fallback_path.write_text(json.dumps(fallback) + "\n", encoding="ascii")
    validation_path = tmp_path / "validation.json"
    validation_path.write_text(json.dumps({
        "component": "fixture_validation", "n_claims": 2,
        "details": [{"claim_id": _PRIMARY_2024, "verdict": "VERIFIED", "reason": "ok"},
                    {"claim_id": _FALLBACK_2025, "verdict": "VERIFIED", "reason": "ok"}],
    }), encoding="ascii")
    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS",
                        ((validation_path, primary_path), (validation_path, fallback_path)))

    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_X"}), encoding="ascii")
    config = _season_config(verdict_file, season_fallback={"2025-26": _FALLBACK_2025})
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_season": config})

    result = cb_mod.compose_best("fixture_season", requested_season="2025-26")
    assert result["conclusion"] == "New Season Player"
    assert result["primary"]["claim_id"] == _FALLBACK_2025


def test_season_matching_primary_directly_needs_no_substitution(season_aspect_with_fallback):
    # requesting the season the gate-canonical claim ALREADY carries -- no
    # substitution, no caveat, just labelled gate-canonical.
    result = cb_mod.compose_best("fixture_season", requested_season="2024-25")
    assert result["conclusion"] == "Old Canonical Player"
    assert result["primary"]["claim_id"] == _PRIMARY_2024
    assert result["primary"]["authority"] == "gate-canonical"
    assert not any("season mismatch" in c for c in result["caveats"])


# --- 3. no-matching-season caveat path ----------------------------------------

def test_no_fallback_declared_prepends_honest_mismatch_caveat(season_aspect_no_fallback):
    result = cb_mod.compose_best("fixture_season", requested_season="2025-26")
    assert result["conclusion"] == "Old Canonical Player"  # canonical answer preserved
    assert result["primary"]["claim_id"] == _PRIMARY_2024
    assert result["primary"]["authority"] == "gate-canonical"
    assert result["caveats"][0] == (
        "season mismatch: requested 2025-26, canonical ranking is 2024-25 (gate-backed); "
        "no season-matching canonical exists"
    )


def test_fallback_declared_but_not_verified_falls_to_caveat_path(tmp_path, monkeypatch, season_claims):
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_X"}), encoding="ascii")
    config = _season_config(verdict_file, season_fallback={"2025-26": "claim_id_never_verified"})
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_season": config})
    result = cb_mod.compose_best("fixture_season", requested_season="2025-26")
    assert result["primary"]["claim_id"] == _PRIMARY_2024
    assert "season mismatch" in result["caveats"][0]


# --- 4. both hyphen/underscore window conventions -----------------------------

def test_underscore_window_convention_matches_hyphen_request(tmp_path, monkeypatch):
    claims_path = tmp_path / "nba_canonical_shooter_claims.jsonl"
    validation_path = tmp_path / "validation.json"
    primary = _ranking_claim(_PRIMARY_2024, "2024_25", "Underscore Window Player", ["caveat"])
    with open(claims_path, "w", encoding="ascii") as f:
        f.write(json.dumps(primary) + "\n")
    validation_path.write_text(json.dumps({
        "component": "fixture_validation", "n_claims": 1,
        "details": [{"claim_id": _PRIMARY_2024, "verdict": "VERIFIED", "reason": "ok"}],
    }), encoding="ascii")
    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))

    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps({"verdict": "REJECT_X"}), encoding="ascii")
    config = _season_config(verdict_file, season_fallback=None)
    monkeypatch.setattr(cb_mod, "_ASPECT_CONFIGS", {"fixture_season": config})

    result = cb_mod.compose_best("fixture_season", requested_season="2024-25")
    # window "2024_25" normalizes to "2024-25" == requested -> no mismatch caveat
    assert not any("season mismatch" in c for c in result["caveats"])
    assert result["primary"]["authority"] == "gate-canonical"


def test_normalize_season_handles_both_conventions():
    assert season_mod.normalize_season("2024-25") == "2024-25"
    assert season_mod.normalize_season("2024_25") == "2024-25"
    assert season_mod.normalize_season("season_2024-25") == "2024-25"
    assert season_mod.normalize_season("season_2024_25") == "2024-25"


# --- 5. season token detection -------------------------------------------------

def test_detect_requested_season_this_season_and_current_season():
    assert season_mod.detect_requested_season("who are the best shooters this season") == season_mod.CURRENT_SEASON
    assert season_mod.detect_requested_season("current season leaders?") == season_mod.CURRENT_SEASON


def test_detect_requested_season_explicit_tokens():
    assert season_mod.detect_requested_season("best shooter in 2024-25") == "2024-25"
    assert season_mod.detect_requested_season("best shooter in 2025 26") == "2025-26"
    assert season_mod.detect_requested_season("best shooter in 2025_26") == "2025-26"


def test_detect_requested_season_no_token_returns_none():
    assert season_mod.detect_requested_season("who is the best shooter?") is None


def test_explicit_season_wins_over_this_season_phrasing():
    # both an explicit token and "this season" present -- explicit is more
    # specific and wins (matches the task's ordering: explicit > keyword).
    assert season_mod.detect_requested_season("this season's 2024-25 leaders") == "2024-25"


# --- ask() end-to-end: real probe phrasing routes through the hook -----------

def test_ask_this_season_phrasing_passes_current_season_to_compose_best(monkeypatch):
    captured = {}

    def _fake_compose_best(aspect, requested_season=None):
        captured["aspect"] = aspect
        captured["requested_season"] = requested_season
        return {"aspect": aspect, "conclusion": "Fixture Winner", "edge_claimed": False}

    monkeypatch.setattr(
        "scripts.platformkit.intel_query.compose_best.compose_best", _fake_compose_best
    )
    result = ask_mod.ask("who are the best shooters in the nba this season")
    assert result["family"] == ask_mod.FAMILY_BEST
    assert captured["aspect"] == "shooter"
    assert captured["requested_season"] == season_mod.CURRENT_SEASON
