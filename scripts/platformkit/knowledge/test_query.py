"""Per-file tests for query.py.

cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/knowledge/test_query.py -q
"""
from __future__ import annotations

from scripts.platformkit.knowledge import query


def test_load_knowledge_reads_all_four_sports():
    rows = query.load_knowledge()
    assert len(rows) > 400
    assert all("label" in r and "sport" in r for r in rows)
    assert {r["sport"] for r in rows} == set(query.SPORTS)


def test_classify_intent_routes_all_six_intents():
    cases = [
        ("what in-game factors matter for MLB totals", "factors_for_matchup"),
        ("what has been tested and failed for NBA", "what_failed"),
        ("what is provisional for tennis", "what_is_provisional"),
        ("which mechanisms replicate across corpora", "validated_edges"),
        ("give a coverage summary of the knowledge store", "coverage"),
        ("what does the evidence say about back to back rest", "mechanism_lookup"),
    ]
    for question, expected in cases:
        assert query.classify_intent(question) == expected, question


def test_label_verbatim_in_factors_answer():
    result = query.answer("what in-game factors matter for NBA", "nba")
    assert result["claims"], "expected at least one backing claim"
    for claim in result["claims"]:
        assert claim["label"] in result["answer_text"], claim["label"]


def test_null_and_reject_rows_never_surface_as_factors_or_validated():
    for sport in query.SPORTS:
        factors = query.answer("what in-game factors matter for %s" % sport, sport)
        for claim in factors["claims"]:
            assert not query.is_failed(claim), claim
        edges = query.answer("which mechanisms replicate for %s" % sport, sport)
        for claim in edges["claims"]:
            assert not query.is_failed(claim), claim


def test_what_failed_only_returns_failed_rows():
    result = query.answer("what has been tested and failed for NBA", "nba")
    assert result["claims"]
    assert all(query.is_failed(c) for c in result["claims"])


def test_what_is_provisional_caveat_present():
    result = query.answer("what is provisional for tennis", "tennis")
    assert result["claims"]
    assert all(query.is_provisional(c) for c in result["claims"])
    assert any("PROVISIONAL" in c for c in result["caveats"])


def test_unknown_question_is_honest_refusal():
    result = query.answer("asdkjhasdkjh totally unrelated nonsense zzz")
    assert result["answer_text"].startswith("cannot answer")
    assert result["claims"] == []
    assert result["labels_present"] is False
    assert "closest supported intents" in result["answer_text"]


def test_unrecognized_sport_is_honest_refusal():
    result = query.answer("what in-game factors matter for atlantis", "atlantis")
    assert result["answer_text"].startswith("cannot answer")
    assert result["claims"] == []


def test_all_ten_canonical_questions_are_recognized_and_label_bearing():
    assert len(query.CANONICAL_QUESTIONS) == 10
    for question, sport in query.CANONICAL_QUESTIONS:
        intent = query.classify_intent(question)
        assert intent is not None, question
        result = query.answer(question, sport)
        assert result["answer_text"], question
        if intent == "coverage":
            assert "FAILED=" in result["answer_text"] and "VALIDATED=" in result["answer_text"]
        else:
            assert result["claims"], "expected backing claims for: %s" % question
            assert any(c.get("label") for c in result["claims"]), question
