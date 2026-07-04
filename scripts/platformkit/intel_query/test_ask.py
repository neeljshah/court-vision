"""Per-file tests for intel_query.ask + intel_query.families.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_ask.py -q

Acceptance criteria:
  1. top_n question against a VERIFIED ranking claim returns the ranking,
     evidence carries claim_id + source_files + as_of + VERIFIED verdict.
  2. entity_lookup finds a named player's rank inside a VERIFIED claim.
  3. provenance returns criteria + caveats for a named VERIFIED claim_id.
  4. A claim_id that is MISMATCH or UNVERIFIABLE in the validation summary
     is INVISIBLE to ask() (never answered from).
  5. An unclassifiable question is honestly unanswerable with
     nearest_supported_families populated.
  6. A well-formed question with no VERIFIED claim covering it is honestly
     unanswerable (never falls back to raw computation).
  7. families.classify buckets top_n / entity_lookup / provenance /
     gate_verdict / None correctly, including a window= hint.
  8. gate_verdict question against a VERIFIED claim_kind=verdict row returns
     gate_module/verdict/primary_number/provenance; a MISMATCH verdict-claim
     row is invisible; an uncovered gate topic is honestly unanswerable.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import families


def _ranking_claim(claim_id: str, metric: str, window: str, ranking: list[dict]) -> dict:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": f"Top by {metric} in window={window}?",
        "criteria": {"metric": metric, "window": window, "formula": "sum(x)/sum(y)"},
        "ranking": ranking,
        "source_files": ["data/fake/source.parquet"],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 100,
        "n_excluded_below_floor": 10,
        "caveats": ["fixture caveat"],
    }


@pytest.fixture
def fixture_sources(tmp_path, monkeypatch):
    """One validation-summary + producer-claims pair with a VERIFIED ranking
    claim, a MISMATCH claim, and an UNVERIFIABLE claim -- so tests can assert
    only the VERIFIED one is ever answerable."""
    claims_path = tmp_path / "claims.jsonl"
    validation_path = tmp_path / "validation.json"

    verified_row = _ranking_claim(
        "fixture_composite_last_20", "composite", "last_20",
        [
            {"rank": 1, "player_id": 1, "player_name": "Alpha Player", "value": 0.9, "n": 20},
            {"rank": 2, "player_id": 2, "player_name": "Beta Player", "value": 0.8, "n": 20},
        ],
    )
    mismatch_row = _ranking_claim(
        "fixture_composite_mismatch", "composite", "last_20",
        [{"rank": 1, "player_id": 3, "player_name": "Gamma Player", "value": 0.95, "n": 20}],
    )
    unverifiable_row = {
        "claim_id": "fixture_gate_verdict",
        "kind": "gate_verdict",
        "question": "Does X beat Y?",
        "criteria": {"gate": "3a"},
        "computed_at": "2026-07-04T00:00:00+00:00",
    }

    with open(claims_path, "w", encoding="ascii") as f:
        for row in (verified_row, mismatch_row, unverifiable_row):
            f.write(json.dumps(row) + "\n")

    validation_summary = {
        "component": "intel_claims_validation",
        "n_claims": 3,
        "details": [
            {"claim_id": "fixture_composite_last_20", "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": "fixture_composite_mismatch", "verdict": "MISMATCH", "reason": "bad"},
            {"claim_id": "fixture_gate_verdict", "verdict": "UNVERIFIABLE", "reason": "no formula"},
        ],
    }
    validation_path.write_text(json.dumps(validation_summary), encoding="ascii")

    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))
    return validation_path, claims_path


def test_top_n_answers_from_verified_claim_with_evidence(fixture_sources):
    result = ask_mod.ask("Who are the top 2 best shooters (composite) in window=last_20?")
    assert result["answerable"] is True
    assert result["family"] == families.FAMILY_TOP_N
    ranking = result["answer"]["ranking"]
    assert [r["player_name"] for r in ranking] == ["Alpha Player", "Beta Player"]
    evidence = result["evidence"][0]
    assert evidence["claim_id"] == "fixture_composite_last_20"
    assert evidence["validator_verdict"] == "VERIFIED"
    assert evidence["source_files"] == ["data/fake/source.parquet"]
    assert evidence["as_of"] == "2026-07-04T00:00:00+00:00"


def test_entity_lookup_finds_named_player(fixture_sources):
    result = ask_mod.ask("Where does Alpha Player rank on composite in window=last_20?")
    assert result["answerable"] is True
    assert result["answer"]["entity_name"] == "Alpha Player"
    assert result["answer"]["rankings"][0]["rank"] == 1


def test_provenance_returns_criteria_and_caveats(fixture_sources):
    result = ask_mod.ask("How do you know? Show the evidence for fixture_composite_last_20.")
    assert result["answerable"] is True
    assert result["answer"]["claim_id"] == "fixture_composite_last_20"
    assert result["answer"]["caveats"] == ["fixture caveat"]


def test_mismatch_claim_never_surfaces(fixture_sources):
    # Same metric/window as the verified claim, but only the VERIFIED one's
    # players should ever appear -- Gamma Player (mismatch) must be excluded.
    result = ask_mod.ask("Who are the top 10 best shooters (composite) in window=last_20?")
    names = [r["player_name"] for r in result["answer"]["ranking"]]
    assert "Gamma Player" not in names

    lookup = ask_mod.ask("Where does Gamma Player rank on composite in window=last_20?")
    assert lookup["answerable"] is False


def test_unverifiable_gate_claim_never_answerable_via_provenance(fixture_sources):
    result = ask_mod.ask("How do you know? Show the evidence for fixture_gate_verdict.")
    assert result["answerable"] is False
    assert "nearest_supported_families" in result


def test_unclassifiable_question_is_honest_unanswerable(fixture_sources):
    result = ask_mod.ask("What is the weather in Boston tomorrow?")
    assert result["answerable"] is False
    assert len(result["nearest_supported_families"]) == 4


def test_wellformed_question_no_covering_claim_is_honest_unanswerable(fixture_sources):
    result = ask_mod.ask("Who are the top 5 best shooters (composite) in window=season_1999-00?")
    assert result["answerable"] is False


def _verdict_claim(claim_id: str, verdict: str, gate_module: str) -> dict:
    return {
        "claim_id": claim_id,
        "kind": "verdict",
        "question": f"What did {gate_module} find?",
        "gate_module": gate_module,
        "verdict_file": "data/fake/verdict.json",
        "verdict": verdict,
        "primary_number": 0.00042,
        "corpus_ids": ["fixture_corpus"],
        "planted_null_passed": True,
        "edge_claimed": False,
        "field_paths": {
            "verdict": "verdict",
            "primary_number": "delta",
            "planted_null_passed": "planted_null_dies",
        },
        "computed_at": "2026-07-04T00:00:00+00:00",
        "caveats": ["fixture verdict caveat"],
    }


@pytest.fixture
def fixture_sources_with_verdicts(tmp_path, monkeypatch):
    """A VERIFIED gate_verdict claim (tennis surface topic) plus a MISMATCH
    gate_verdict claim (also tennis-topic, different claim_id) so tests can
    assert only the VERIFIED one is ever answerable."""
    claims_path = tmp_path / "claims.jsonl"
    validation_path = tmp_path / "validation.json"

    verified_verdict = _verdict_claim(
        "fixture_tennis_surface_verdict", "REJECT", "tennis surface hold-prior gate"
    )
    mismatch_verdict = _verdict_claim(
        "fixture_tennis_surface_verdict_bad", "SHIP", "tennis surface hold-prior gate"
    )

    with open(claims_path, "w", encoding="ascii") as f:
        for row in (verified_verdict, mismatch_verdict):
            f.write(json.dumps(row) + "\n")

    validation_summary = {
        "component": "intel_verdict_claims_validation",
        "n_claims": 2,
        "details": [
            {"claim_id": "fixture_tennis_surface_verdict", "verdict": "VERIFIED", "reason": "ok"},
            {"claim_id": "fixture_tennis_surface_verdict_bad", "verdict": "MISMATCH", "reason": "bad"},
        ],
    }
    validation_path.write_text(json.dumps(validation_summary), encoding="ascii")

    monkeypatch.setattr(ask_mod, "CLAIM_SOURCE_PAIRS", ((validation_path, claims_path),))
    return validation_path, claims_path


def test_gate_verdict_answers_from_verified_claim(fixture_sources_with_verdicts):
    result = ask_mod.ask("What did the tennis surface gate find?")
    assert result["answerable"] is True
    assert result["family"] == families.FAMILY_GATE_VERDICT
    assert result["answer"]["verdict"] == "REJECT"
    assert result["answer"]["edge_claimed"] is False
    evidence = result["evidence"][0]
    assert evidence["claim_id"] == "fixture_tennis_surface_verdict"
    assert evidence["validator_verdict"] == "VERIFIED"


def test_gate_verdict_mismatch_claim_never_surfaces(fixture_sources_with_verdicts):
    result = ask_mod.ask("What did the tennis surface gate find?")
    assert result["answer"]["verdict"] != "SHIP"


def test_gate_verdict_uncovered_topic_is_honest_unanswerable(fixture_sources_with_verdicts):
    result = ask_mod.ask("What did the soccer tier gate find?")
    assert result["answerable"] is False
    assert "nearest_supported_families" in result


def test_classify_families_and_window_hint():
    top_n = families.classify("Who are the top 10 best shooters (composite) in window=last_20?")
    assert top_n.family == families.FAMILY_TOP_N
    assert top_n.top_n == 10
    assert top_n.window_hint == "last_20"

    lookup = families.classify("Where does Stephen Curry rank on fg3_pct in window=season_2024-25?")
    assert lookup.family == families.FAMILY_ENTITY_LOOKUP
    assert lookup.entity_name == "Stephen Curry"
    assert lookup.window_hint == "season_2024-25"

    provenance = families.classify("How do you know? Show the evidence for nba_shooting_composite_last_20.")
    assert provenance.family == families.FAMILY_PROVENANCE
    assert provenance.claim_id == "nba_shooting_composite_last_20"

    gate_verdict = families.classify("What did the tennis surface gate find?")
    assert gate_verdict.family == families.FAMILY_GATE_VERDICT
    assert "tennis_surface" in gate_verdict.topic_hints

    unknown = families.classify("What time is it?")
    assert unknown.family is None
