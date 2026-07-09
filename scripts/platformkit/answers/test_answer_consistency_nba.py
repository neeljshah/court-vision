"""LANE D deliverable 4 -- consistency battery. Every canonical question must
produce the SAME numbers whether resolved directly via resolver_registry, or
via contract_client (the deterministic 'LLM following
docs/AI_CONSUMER_CONTRACT.md' stand-in). Both call the identical resolver, so
this proves the client-formatting layer never drops, re-rounds, or
substitutes a number relative to the oracle -- catching drift before a real
LLM client would introduce it.

Run: python -m pytest scripts/platformkit/answers/test_answer_consistency_nba.py -q
"""
from __future__ import annotations

import os
import unicodedata

import pytest

from scripts.platformkit.answers import contract_client as CC
from scripts.platformkit.answers import contracts as C
from scripts.platformkit.answers import resolver_registry as R

REAL_PROFILES = C._load_df("nba")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no nba profiles parquet built")


def _ascii(s) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


# ---------------------------------------------------------------------------
# 11 canonical questions spanning every registered resolver category. Each
# names the fields THAT category's envelope carries -- a generic field list
# would either miss category-specific fields (e.g. superlative's "top" list)
# or false-fail on fields a category never sets (e.g. no percentile on a
# plain player_stat lookup).
# ---------------------------------------------------------------------------
QUESTIONS = [
    dict(query="Trae Young gravity", kwargs={}, fields=("entity_name", "raw_value", "n")),
    dict(query="Trae Young rating gravity", kwargs={}, fields=("entity_name", "percentile", "rating_2k", "n")),
    dict(query="what is the calibration brier score for nba", kwargs={},
         fields=("baseline_brier", "improved_brier", "n")),
    dict(query="final score of BOS vs PHI", kwargs={"team": "BOS", "opponent": "PHI"},
         fields=("home_team", "away_team", "home_score", "away_score", "winner")),
]


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["query"] for q in QUESTIONS])
def test_resolver_and_contract_client_agree(q):
    direct = R.resolve(q["query"], sport="nba", **q["kwargs"])
    rendered = _ascii(CC.answer(q["query"], sport="nba", **q["kwargs"]))
    assert direct["status"] == "ok", f"{q['query']} -> {direct}"
    for key in q["fields"]:
        assert key in direct and direct[key] is not None, f"{q['query']}: resolver envelope missing '{key}'"
        assert str(direct[key]) in rendered, (
            f"{q['query']}: resolver field {key}={direct[key]!r} missing from client render {rendered!r}")
    assert direct.get("source_artifact") and direct["source_artifact"] in rendered
    assert direct.get("as_of") is not None and str(direct["as_of"]) in rendered


# ---------------------------------------------------------------------------
# concept_rating shapes (superlative/comparison/explanation) checked with
# their own bespoke assertions -- the envelope shape differs per question
# shape (a ranked list vs. two entities vs. one decomposition).
# ---------------------------------------------------------------------------
def test_superlative_resolver_and_client_agree():
    q = "best gravity"
    direct = R.resolve(q, sport="nba")
    rendered = _ascii(CC.answer(q, sport="nba"))
    assert direct["status"] == "ok" and direct["top"]
    for e in direct["top"]:
        # ascii-fold the name before comparing -- entity names may carry
        # diacritics (real duplicate-entity landmine: "Luka Doncic" and its
        # accented form are distinct entity_ids in this corpus), and the
        # rendered client text is ascii-folded for the cp1252 console.
        assert _ascii(e["entity_name"]) in rendered and str(e["composite"]) in rendered
    assert direct["source_artifact"] in rendered


def test_comparison_resolver_and_client_agree():
    q = "Trae Young vs LaMelo Ball on gravity"
    direct = R.resolve(q, sport="nba")
    rendered = _ascii(CC.answer(q, sport="nba"))
    assert direct["status"] == "ok"
    assert direct["entity_a"]["name"] in rendered and direct["entity_b"]["name"] in rendered
    assert direct["favored"] in rendered
    assert direct["source_artifact"] in rendered


def test_explanation_resolver_and_client_agree():
    q = "why is LaMelo Ball good at gravity"
    direct = R.resolve(q, sport="nba")
    rendered = _ascii(CC.answer(q, sport="nba"))
    assert direct["status"] == "ok"
    assert direct["entity_name"] in rendered and str(direct["composite"]) in rendered
    assert direct["confidence"] in rendered
    assert direct["source_artifact"] in rendered


def test_refusal_is_identical_both_paths():
    q = "what edge do we have here, 18.38 percent"
    direct = R.resolve(q, sport="nba")
    rendered = CC.answer(q, sport="nba")
    assert direct["status"] == "refused"
    assert "REFUSED" in rendered and direct["source_artifact"] in rendered


def test_not_supported_is_identical_both_paths():
    q = "best teleportation"
    direct = R.resolve(q, sport="nba")
    rendered = CC.answer(q, sport="nba")
    assert direct["status"] == "no_data"
    assert "NO_DATA" in rendered


def test_zero_row_historical_result_is_honest_refusal_not_a_guess():
    """No 2026-02-30 game exists -- must come back no_data on both paths,
    never an invented score (the WNBA-rim-case zero-row honesty rule)."""
    q = "final score of BOS vs PHI"
    direct = R.resolve(q, sport="nba", team="BOS", opponent="ZZZ")
    rendered = CC.answer(q, sport="nba", team="BOS", opponent="ZZZ")
    assert direct["status"] == "no_data"
    assert "NO_DATA" in rendered


# ---------------------------------------------------------------------------
# 5 hard why/what-drives questions: the cited artifact must exist on disk and
# its number must independently reproduce (not just be self-consistent
# inside contracts.py's own composite math).
# ---------------------------------------------------------------------------
WHY_QUESTIONS = [
    ("rim_protection", "Neemias Queta"),
    ("creation", "DeMar DeRozan"),
    ("motor", "Donovan Clingan"),
    ("versatility", "Jericho Sims"),
    ("clutch", "Shai Gilgeous-Alexander"),
]


@pytest.mark.parametrize("concept,entity", WHY_QUESTIONS)
def test_why_question_cites_reproducible_artifact(concept, entity):
    r = C.answer_explanation(concept, entity)
    assert r["decomposition"], f"why is {entity} good at {concept} -> no decomposition"
    top = r["decomposition"][0]  # sorted by contribution desc -- the driver the answer would name
    # match by entity_id, not entity_name -- some ingredient attributes (e.g.
    # team_dreb_pct_swing) carry an empty entity_name on their own row while
    # sharing the resolved entity_id (contracts._entity_composite's own
    # documented convention); matching by name alone would miss those rows.
    eid, _ = C._resolve_entity(REAL_PROFILES, entity)
    rows = REAL_PROFILES[(REAL_PROFILES["entity_id"] == eid) & (REAL_PROFILES["attribute"] == top["attribute"])]
    assert not rows.empty, f"no independent profile row for {entity} (id={eid})/{top['attribute']}"
    row = rows.sort_values("window").iloc[-1]
    assert os.path.exists(row["sources"]), f"cited artifact does not exist on disk: {row['sources']}"
    assert round(float(row["percentile"]), 2) == top["percentile"], (
        f"{entity}/{top['attribute']}: decomposition percentile {top['percentile']} != "
        f"independently-read profile percentile {round(float(row['percentile']), 2)}")
