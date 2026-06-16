"""Per-file test for edge_engine.extract. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_extract.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from scripts.platformkit.edge_engine.extract import (  # noqa: E402
    SYSTEM_PROMPT, assert_no_probability, extract_llm, extract_rule, revalidate,
)
from scripts.platformkit.edge_engine.schema_source import (  # noqa: E402
    EdgeFact, SourceDoc,
)


def _doc(text: str, published_ts: str = "2026-01-15T11:00:00") -> SourceDoc:
    return SourceDoc(
        doc_id="d1", sport="nba", published_ts=published_ts, text=text,
        source="https://x.com/beat/status/1", doc_date="2026-01-15",
    )


# --- rule-based fallback ----------------------------------------------------

def test_extract_rule_is_deterministic_and_extracts_known_kind():
    doc = _doc("Beat report: the charter was diverted; team had a 4am late arrival.")
    a = extract_rule(doc, subject_id="1610612743", game_date="2026-01-15")
    b = extract_rule(doc, subject_id="1610612743", game_date="2026-01-15")
    assert [f.as_dict() for f in a] == [f.as_dict() for f in b]  # deterministic
    kinds = {f.fact_kind for f in a}
    assert "travel_disruption" in kinds


def test_extract_rule_stamps_availability_at_doc_publish():
    doc = _doc("Coach said minutes restriction tonight.", published_ts="2026-01-15T10:30:00")
    facts = extract_rule(doc, subject_id="201939", game_date="2026-01-15")
    assert facts and all(f.availability_ts == "2026-01-15T10:30:00" for f in facts)


def test_extract_rule_emits_no_probability_field():
    doc = _doc("Star is out; illness swept the locker room.")
    for f in extract_rule(doc, subject_id="201939", game_date="2026-01-15"):
        d = f.as_dict()
        assert "win_prob" not in d and "edge" not in d and "price" not in d
        assert_no_probability(d)  # no raise -> honest FACT


def test_extract_rule_empty_when_no_keywords():
    doc = _doc("Nothing notable in tonight's pregame availability report.")
    assert extract_rule(doc, subject_id="201939", game_date="2026-01-15") == []


# --- honesty rail re-validation --------------------------------------------

def test_assert_no_probability_trips_on_outcome_number():
    f = EdgeFact(
        fact_kind="lineup_status", sport="nba", subject_id="201939",
        game_date="2026-01-15", value_text="is out", source="beat",
        availability_ts="2026-01-15T10:00:00", confidence=0.8,
    )
    d = f.as_dict()
    d["win_prob"] = 0.61  # an outcome number must never ride on a FACT row
    with pytest.raises(AssertionError):
        assert_no_probability(d)


# --- vintage re-assertion (a fact cannot predate its source) ----------------

def test_revalidate_passes_when_fact_known_at_or_after_publish():
    doc = _doc("is out", published_ts="2026-01-15T11:00:00")
    f = EdgeFact(
        fact_kind="lineup_status", sport="nba", subject_id="201939",
        game_date="2026-01-15", value_text="is out", source="beat",
        availability_ts="2026-01-15T11:00:00", confidence=0.8,
    )
    assert revalidate(f, doc) is f  # no raise


def test_revalidate_trips_on_fact_predating_source():
    doc = _doc("is out", published_ts="2026-01-15T11:00:00")
    f = EdgeFact(
        fact_kind="lineup_status", sport="nba", subject_id="201939",
        game_date="2026-01-15", value_text="is out", source="beat",
        availability_ts="2026-01-15T09:00:00",  # before the document existed -> impossible
        confidence=0.8,
    )
    with pytest.raises(AssertionError):
        revalidate(f, doc)


# --- the live LLM path is a guarded, hermetic stub --------------------------

def test_extract_llm_is_a_hermetic_stub():
    with pytest.raises(NotImplementedError):
        extract_llm(_doc("Star is out."))


def test_system_prompt_states_facts_only_invariant():
    assert "do not predict" in SYSTEM_PROMPT.lower() or "not predict" in SYSTEM_PROMPT.lower()
    assert "confidence" in SYSTEM_PROMPT.lower()
