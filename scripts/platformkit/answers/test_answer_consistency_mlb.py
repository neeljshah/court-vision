"""LANE D deliverable 4 -- consistency battery (MLB). Mirrors
test_answer_consistency_nba.py: every canonical question must produce the
SAME numbers whether resolved directly via resolver_registry, or via
contract_client (the deterministic 'LLM following
docs/AI_CONSUMER_CONTRACT.md' stand-in). Both call the identical resolver.

Run: python -m pytest scripts/platformkit/answers/test_answer_consistency_mlb.py -q
"""
from __future__ import annotations

import json
import os
import unicodedata

import pytest

from scripts.platformkit.answers import contract_client as CC
from scripts.platformkit.answers import contracts as C
from scripts.platformkit.answers import resolver_registry as R

REAL_PROFILES = C._load_df("mlb")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no mlb profiles parquet built")


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def _source_paths(sources) -> list[str]:
    """MLB's `sources` column is a JSON-stringified list (unlike NBA's bare
    path string) -- e.g. '["data/cache/statcast/savant_hitcoords__2024.parquet"]'."""
    s = str(sources)
    return json.loads(s) if s.startswith("[") else [s]


# ---------------------------------------------------------------------------
# Simple-field questions: one resolver category, one expected field set
# ---------------------------------------------------------------------------
QUESTIONS = [
    dict(query="Charlie Blackmon platoon resilience", kwargs={}, fields=("entity_name", "raw_value", "n")),
    dict(query="Charlie Blackmon rating platoon resilience", kwargs={},
         fields=("entity_name", "percentile", "rating_2k", "n")),
    dict(query="what is the calibration brier score for mlb", kwargs={},
         fields=("baseline_brier", "improved_brier", "n")),
    dict(query="final score of BOS vs NYY", kwargs={"team": "BOS", "opponent": "NYY"},
         fields=("home_team", "away_team", "home_score", "away_score", "winner")),
]


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["query"] for q in QUESTIONS])
def test_resolver_and_contract_client_agree(q):
    direct = R.resolve(q["query"], sport="mlb", **q["kwargs"])
    rendered = _ascii(CC.answer(q["query"], sport="mlb", **q["kwargs"]))
    assert direct["status"] == "ok", f"{q['query']} -> {direct}"
    for key in q["fields"]:
        assert key in direct and direct[key] is not None, f"{q['query']}: resolver envelope missing '{key}'"
        assert str(direct[key]) in rendered, (
            f"{q['query']}: resolver field {key}={direct[key]!r} missing from client render {rendered!r}")
    assert direct.get("source_artifact") and direct["source_artifact"] in rendered
    assert direct.get("as_of") is not None and str(direct["as_of"]) in rendered


# ---------------------------------------------------------------------------
# concept_rating shapes checked with their own bespoke assertions
# ---------------------------------------------------------------------------
def test_superlative_resolver_and_client_agree():
    q = "best power"
    direct = R.resolve(q, sport="mlb")
    rendered = _ascii(CC.answer(q, sport="mlb"))
    assert direct["status"] == "ok" and direct["top"]
    for e in direct["top"]:
        assert _ascii(e["entity_name"]) in rendered and str(e["composite"]) in rendered
    assert direct["source_artifact"] in rendered


def test_comparison_resolver_and_client_agree():
    q = "Aaron Judge vs Shohei Ohtani on power"
    direct = R.resolve(q, sport="mlb")
    rendered = _ascii(CC.answer(q, sport="mlb"))
    assert direct["status"] == "ok"
    assert direct["entity_a"]["name"] in rendered and direct["entity_b"]["name"] in rendered
    assert direct["favored"] in rendered
    assert direct["source_artifact"] in rendered


def test_explanation_resolver_and_client_agree():
    q = "why is Felix Bautista good at stuff"
    direct = R.resolve(q, sport="mlb")
    rendered = _ascii(CC.answer(q, sport="mlb"))
    assert direct["status"] == "ok"
    assert _ascii(direct["entity_name"]) in rendered and str(direct["composite"]) in rendered
    assert direct["confidence"] in rendered
    assert direct["source_artifact"] in rendered


def test_refusal_is_identical_both_paths():
    q = "what edge do we have here, 18.38 percent"
    direct = R.resolve(q, sport="mlb")
    rendered = CC.answer(q, sport="mlb")
    assert direct["status"] == "refused"
    assert "REFUSED" in rendered and direct["source_artifact"] in rendered


def test_not_supported_is_identical_both_paths():
    q = "best teleportation"
    direct = R.resolve(q, sport="mlb")
    rendered = CC.answer(q, sport="mlb")
    assert direct["status"] == "no_data"
    assert "NO_DATA" in rendered


def test_zero_row_historical_result_is_honest_refusal_not_a_guess():
    """No BOS-vs-ZZZ game exists -- must come back no_data on both paths,
    never an invented score (zero-row honesty rule)."""
    q = "final score of BOS vs ZZZ"
    direct = R.resolve(q, sport="mlb", team="BOS", opponent="ZZZ")
    rendered = CC.answer(q, sport="mlb", team="BOS", opponent="ZZZ")
    assert direct["status"] == "no_data"
    assert "NO_DATA" in rendered


# ---------------------------------------------------------------------------
# 5 hard why/what-drives questions: cited artifact must exist on disk and its
# number must independently reproduce off the real profiles parquet.
# ---------------------------------------------------------------------------
WHY_QUESTIONS = [
    ("clutch", "Juan Soto"),
    ("command", "Shane Bieber"),
    ("discipline", "Ha-Seong Kim"),
    ("power", "Aaron Judge"),
    ("stuff", "Felix Bautista"),
]


@pytest.mark.parametrize("concept,entity", WHY_QUESTIONS)
def test_why_question_cites_reproducible_artifact(concept, entity):
    r = C.answer_explanation(concept, entity, sport="mlb")
    assert r["decomposition"], f"why is {entity} good at {concept} -> no decomposition"
    top = r["decomposition"][0]  # sorted by contribution desc -- the driver the answer would name
    eid, _ = C._resolve_entity(REAL_PROFILES, entity)
    rows = REAL_PROFILES[(REAL_PROFILES["entity_id"] == eid) & (REAL_PROFILES["attribute"] == top["attribute"])]
    assert not rows.empty, f"no independent profile row for {entity} (id={eid})/{top['attribute']}"
    row = rows.sort_values("window").iloc[-1]
    paths = _source_paths(row["sources"])
    assert paths and all(os.path.exists(p) for p in paths), f"cited artifact missing on disk: {paths}"
    assert round(float(row["percentile"]), 2) == top["percentile"], (
        f"{entity}/{top['attribute']}: decomposition percentile {top['percentile']} != "
        f"independently-read profile percentile {round(float(row['percentile']), 2)}")
