"""FIX-WAVE lane e2 (gap ledger rank 10) -- consistency battery (tennis).
Mirrors test_answer_consistency_nba.py/_mlb.py: every canonical question must
produce the SAME numbers whether resolved directly via resolver_registry, or
via contract_client (the deterministic 'LLM following
docs/AI_CONSUMER_CONTRACT.md' stand-in). Both call the identical resolver.

Run: python -m pytest scripts/platformkit/answers/test_answer_consistency_tennis.py -q
"""
from __future__ import annotations

import unicodedata

import pytest

from scripts.platformkit.answers import contract_client as CC
from scripts.platformkit.answers import contracts as C
from scripts.platformkit.answers import resolver_registry as R

REAL_PROFILES = C._load_df("tennis")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no tennis profiles parquet built")


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def _source_paths(sources) -> list[str]:
    """Tennis's `sources` column is semicolon-joined (its own shape, distinct
    from soccer/MLB's JSON-list and NBA's bare path) -- see answer_rules.md
    category 1 adjudication a."""
    return [p for p in str(sources).split(";") if p]


# ---------------------------------------------------------------------------
# Simple-field questions: one resolver category, one expected field set
# ---------------------------------------------------------------------------
QUESTIONS = [
    dict(query="Roger Federer serve_dominance", kwargs={}, fields=("entity_name", "raw_value", "n")),
    dict(query="Roger Federer rating serve_dominance", kwargs={},
         fields=("entity_name", "percentile", "rating_2k", "n")),
    dict(query="what is the calibration brier score for tennis", kwargs={},
         fields=("baseline_brier", "improved_brier", "n")),
]


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["query"] for q in QUESTIONS])
def test_resolver_and_contract_client_agree(q):
    direct = R.resolve(q["query"], sport="tennis", **q["kwargs"])
    rendered = _ascii(CC.answer(q["query"], sport="tennis", **q["kwargs"]))
    assert direct["status"] == "ok", f"{q['query']} -> {direct}"
    for key in q["fields"]:
        assert key in direct and direct[key] is not None, f"{q['query']}: resolver envelope missing '{key}'"
        assert str(direct[key]) in rendered, (
            f"{q['query']}: resolver field {key}={direct[key]!r} missing from client render {rendered!r}")
    assert direct.get("source_artifact") and direct["source_artifact"] in rendered
    assert direct.get("as_of") is not None and str(direct["as_of"]) in rendered


# ---------------------------------------------------------------------------
# concept_rating comparison shape, incl. the tennis-specific
# `what_would_flip_it` field (answer_rules.md category 3).
# ---------------------------------------------------------------------------
def test_comparison_resolver_and_client_agree():
    q = "Roger Federer vs Rafael Nadal on serve_weapon"
    direct = R.resolve(q, sport="tennis")
    rendered = _ascii(CC.answer(q, sport="tennis"))
    assert direct["status"] == "ok"
    assert direct["entity_a"]["name"] in rendered and direct["entity_b"]["name"] in rendered
    assert direct["favored"] in rendered
    assert direct["source_artifact"] in rendered


def test_explanation_resolver_and_client_agree():
    q = "why is Roger Federer good at serve_weapon"
    direct = R.resolve(q, sport="tennis")
    rendered = _ascii(CC.answer(q, sport="tennis"))
    assert direct["status"] == "ok"
    assert direct["entity_name"] in rendered and str(direct["composite"]) in rendered
    assert direct["confidence"] in rendered
    assert direct["source_artifact"] in rendered


# ---------------------------------------------------------------------------
# historical_result is NOT wired for tennis (answer_rules.md category 6) --
# must come back not_supported on both paths.
# ---------------------------------------------------------------------------
def test_historical_result_not_wired_both_paths():
    q = "final score of Federer vs Nadal"
    direct = R.resolve(q, sport="tennis", team="Federer", opponent="Nadal")
    rendered = CC.answer(q, sport="tennis", team="Federer", opponent="Nadal")
    assert direct["status"] == "not_supported"
    assert "not wired" in direct["note"]
    assert "NOT_SUPPORTED" in rendered


# ---------------------------------------------------------------------------
# mechanism_effect -- the anti-folklore receipts.
# ---------------------------------------------------------------------------
def test_mechanism_effect_lefty_folklore_reversed_both_paths():
    """lefty_advantage_on_return: CONFIRMED but REVERSED vs the popular
    'lefty advantage' folklore (answer_rules.md category 7)."""
    q = "is there evidence for the lefty advantage on return folklore"
    direct = R.resolve(q, sport="tennis")
    rendered = _ascii(CC.answer(q, sport="tennis"))
    assert direct["status"] == "ok"
    assert direct["hypothesis"] == "lefty_advantage_on_return"
    finding = direct["findings"][0]
    assert finding["verdict"] == "CONFIRMED_LOCAL"
    assert finding["effect_local"] == 0.035
    assert finding["n"] == 4189
    assert "CONFIRMED_LOCAL" in rendered and direct["source_artifact"] in rendered


def test_mechanism_effect_upset_rate_by_round_reversed_both_paths():
    q = "what does the evidence say about upset rate by round"
    direct = R.resolve(q, sport="tennis")
    rendered = _ascii(CC.answer(q, sport="tennis"))
    assert direct["status"] == "ok"
    finding = direct["findings"][0]
    assert finding["verdict"] == "CONFIRMED_LOCAL"
    assert finding["n"] == 40794
    assert "not a market-beating or causal claim" in rendered


# ---------------------------------------------------------------------------
# Refusal / not-supported paths -- identical shape to NBA/MLB.
# ---------------------------------------------------------------------------
def test_refusal_is_identical_both_paths():
    q = "what edge do we have here, 18.38 percent"
    direct = R.resolve(q, sport="tennis")
    rendered = CC.answer(q, sport="tennis")
    assert direct["status"] == "refused"
    assert "REFUSED" in rendered and direct["source_artifact"] in rendered


def test_not_supported_is_identical_both_paths():
    q = "best teleportation"
    direct = R.resolve(q, sport="tennis")
    rendered = CC.answer(q, sport="tennis")
    assert direct["status"] == "no_data"
    assert "NO_DATA" in rendered
