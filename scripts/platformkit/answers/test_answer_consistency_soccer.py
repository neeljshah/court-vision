"""FIX-WAVE lane e2 (gap ledger rank 10) -- consistency battery (soccer).
Mirrors test_answer_consistency_nba.py/_mlb.py: every canonical question must
produce the SAME numbers whether resolved directly via resolver_registry, or
via contract_client (the deterministic 'LLM following
docs/AI_CONSUMER_CONTRACT.md' stand-in). Both call the identical resolver.

Run: python -m pytest scripts/platformkit/answers/test_answer_consistency_soccer.py -q
"""
from __future__ import annotations

import json
import unicodedata

import pytest

from scripts.platformkit.answers import contract_client as CC
from scripts.platformkit.answers import contracts as C
from scripts.platformkit.answers import resolver_registry as R

REAL_PROFILES = C._load_df("soccer", "team")  # soccer profiles are TEAM-level only, see answer_rules.md category 1
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no soccer profiles parquet built")


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def _source_paths(sources) -> list[str]:
    """Soccer's `sources` column is a JSON-stringified list (MLB's convention,
    not NBA's bare path string) -- see answer_rules.md category 1 adjudication a."""
    s = str(sources)
    return json.loads(s) if s.startswith("[") else [s]


# ---------------------------------------------------------------------------
# Simple-field questions: one resolver category, one expected field set.
# Uses "Manchester City WFC" (unambiguous) rather than "Arsenal" (the
# documented two-disjoint-id landmine: bare "Arsenal" is ambiguous across
# the men's/women's clubs -- see answer_rules.md zero-row/entity-id section).
# ---------------------------------------------------------------------------
QUESTIONS = [
    dict(query="Manchester City WFC defensive_solidity", kwargs={}, fields=("entity_name", "raw_value", "n")),
    dict(query="Manchester City WFC rating defensive_solidity", kwargs={},
         fields=("entity_name", "percentile", "rating_2k", "n")),
    dict(query="what is the calibration brier score for soccer", kwargs={},
         fields=("baseline_brier", "improved_brier", "n")),
]


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["query"] for q in QUESTIONS])
def test_resolver_and_contract_client_agree(q):
    direct = R.resolve(q["query"], sport="soccer", **q["kwargs"])
    rendered = _ascii(CC.answer(q["query"], sport="soccer", **q["kwargs"]))
    assert direct["status"] == "ok", f"{q['query']} -> {direct}"
    for key in q["fields"]:
        assert key in direct and direct[key] is not None, f"{q['query']}: resolver envelope missing '{key}'"
        assert str(direct[key]) in rendered, (
            f"{q['query']}: resolver field {key}={direct[key]!r} missing from client render {rendered!r}")
    assert direct.get("source_artifact") and direct["source_artifact"] in rendered
    assert direct.get("as_of") is not None and str(direct["as_of"]) in rendered


# ---------------------------------------------------------------------------
# historical_result is NOT wired for soccer (answer_rules.md category 6) --
# must come back not_supported on both paths, never a hand-rolled guess.
# ---------------------------------------------------------------------------
def test_historical_result_not_wired_both_paths():
    q = "final score of Arsenal vs Chelsea"
    direct = R.resolve(q, sport="soccer", team="Arsenal", opponent="Chelsea")
    rendered = CC.answer(q, sport="soccer", team="Arsenal", opponent="Chelsea")
    assert direct["status"] == "not_supported"
    assert "not wired" in direct["note"]
    assert "NOT_SUPPORTED" in rendered


# ---------------------------------------------------------------------------
# mechanism_effect -- the anti-folklore receipts (fresh category as of this
# session's resolver_registry.py mechanism_effect addition).
# ---------------------------------------------------------------------------
def test_mechanism_effect_confirmed_inverted_folklore_both_paths():
    """leading_team_shot_rate_suppression: CONFIRMED but INVERTED vs the
    'defensive shell' folklore (answer_rules.md category 7)."""
    q = "does the data support leading team shot rate suppression"
    direct = R.resolve(q, sport="soccer")
    rendered = _ascii(CC.answer(q, sport="soccer"))
    assert direct["status"] == "ok"
    assert direct["hypothesis"] == "leading_team_shot_rate_suppression"
    finding = direct["findings"][0]
    assert finding["verdict"] == "CONFIRMED_LOCAL"
    assert finding["effect_local"] == 0.02423
    assert finding["n"] == 3352
    assert "CONFIRMED_LOCAL" in rendered and direct["source_artifact"] in rendered


def test_mechanism_effect_pressing_ppda_both_paths():
    q = "what does the evidence say about pressing ppda vs turnover rate"
    direct = R.resolve(q, sport="soccer")
    rendered = _ascii(CC.answer(q, sport="soccer"))
    assert direct["status"] == "ok"
    finding = direct["findings"][0]
    assert finding["verdict"] == "CONFIRMED_LOCAL"
    assert finding["n"] == 6886
    assert "not a market-beating or causal claim" in rendered


# ---------------------------------------------------------------------------
# Refusal / not-supported paths -- identical shape to NBA/MLB.
# ---------------------------------------------------------------------------
def test_refusal_is_identical_both_paths():
    q = "what edge do we have here, 18.38 percent"
    direct = R.resolve(q, sport="soccer")
    rendered = CC.answer(q, sport="soccer")
    assert direct["status"] == "refused"
    assert "REFUSED" in rendered and direct["source_artifact"] in rendered


def test_not_supported_is_identical_both_paths():
    q = "best teleportation"
    direct = R.resolve(q, sport="soccer")
    rendered = CC.answer(q, sport="soccer")
    assert direct["status"] == "no_data"
    assert "NO_DATA" in rendered


# ---------------------------------------------------------------------------
# concept_rating thin-population floor (answer_rules.md category 3
# adjudication b) -- an empty `top` with `ok` status is an honest answer,
# not a bug; both paths must agree it is empty, not silently invent an entry.
# ---------------------------------------------------------------------------
def test_superlative_thin_population_empty_top_both_paths():
    q = "best threat"
    direct = R.resolve(q, sport="soccer")
    rendered = _ascii(CC.answer(q, sport="soccer"))
    assert direct["status"] == "ok"
    assert direct["top"] == []
    assert "no entities met the min-n floor" in direct["note"]
    assert direct["source_artifact"] in rendered
