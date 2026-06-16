"""edge_engine -- the EXTRACTOR (LLM-in-one-box + deterministic rule fallback).

The LLM sits in EXACTLY one box: it reads a SourceDoc's unstructured text and returns typed
EdgeFacts. It emits fact_kind / subject_id / a verbatim value_text and an EXTRACTION confidence
ONLY -- it NEVER predicts a game, estimates a win probability, or outputs any number that enters
the prediction chain. Two contracts make that binding:

  1. extract_llm() is a STUB that raises NotImplementedError -- CI never makes a live API call,
     no secret is referenced, and the live wiring (instructor.from_anthropic, key from env) is a
     HUMAN-RUN step. This mirrors freshness.extract_stub.extract_doc.
  2. Whatever path produces facts, every fact is re-validated by schema_source.validate_fact
     (which trips on any banned outcome/price field) AND its availability_ts is re-asserted
     against the SourceDoc's published_ts (a fact cannot predate the document that stated it).

extract_rule() is a DETERMINISTIC keyword fallback so the pipeline is exercisable hermetically
and the per-file test can plant text and get a stable fact out -- no model, no randomness.

Stdlib only. <=300 LOC. Per-file test: test_extract.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:  # package import
    from scripts.platformkit.edge_engine.schema_source import (  # type: ignore
        EdgeFact, SourceDoc, FACT_KINDS, validate_fact, validate_source,
    )
except ImportError:  # direct-script / per-file-test fallback
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine.schema_source import (  # type: ignore
        EdgeFact, SourceDoc, FACT_KINDS, validate_fact, validate_source,
    )

# The binding invariant, stated to the model verbatim. The schema has NO probability field; the
# only numeric output is `confidence` (confidence in the EXTRACTION, not any game outcome).
SYSTEM_PROMPT = (
    "You are a sports-data EXTRACTION tool. You read unstructured news/presser/lineup/travel "
    "text and return structured FACTS. You do NOT predict games, estimate win probability, "
    "project minutes, price a market, or output ANY number except the schema's `confidence` "
    "field -- and that field is your confidence in the EXTRACTION, never in a game outcome. If "
    "a fact is not stated in the text, do not emit it -- never guess. Quote the verbatim "
    "evidence span in value_text. LLMs lean optimistic; resist it and extract conservatively."
)

# Deterministic keyword -> fact_kind map for the rule fallback. Order matters: first hit wins.
# These are coarse on purpose -- the fallback is a hermetic stand-in, not the production model.
_RULE_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("charter", "travel_disruption"),
    ("diverted", "travel_disruption"),
    ("late arrival", "travel_disruption"),
    ("stayed back", "actual_travel_party"),
    ("did not travel", "actual_travel_party"),
    ("minutes restriction", "coach_rotation_intent"),
    ("load manage", "coach_rotation_intent"),
    ("sitting", "coach_rotation_intent"),
    ("wind", "weather_field"),
    ("bullpen", "pitcher_usage"),
    ("probable pitcher", "pitcher_usage"),
    ("surface", "surface_condition"),
    ("illness", "local_disruption"),
    ("flu", "local_disruption"),
    ("trap game", "narrative_framing"),
    ("letdown", "narrative_framing"),
    ("out", "lineup_status"),
    ("questionable", "lineup_status"),
)


def _to_dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def extract_llm(doc: SourceDoc, model: str = "claude-haiku-4-5",
                max_retries: int = 3) -> List[EdgeFact]:
    """STUB. The live LLM extraction is a HUMAN-RUN step (needs an API key from env).

    The real implementation uses instructor.from_anthropic with a response_model whose shape is
    EdgeFact (no probability field by construction) and max_retries to fix SHAPE failures;
    revalidate() below catches the semantic miss retries do not. We raise here so CI stays
    hermetic and no secret is referenced -- mirroring freshness.extract_stub.extract_doc.
    """
    raise NotImplementedError(
        "live LLM call is a HUMAN-RUN step (set the Anthropic key in env and wire "
        "instructor.from_anthropic with a response_model shaped as EdgeFact); the STUB exists "
        "so CI stays hermetic and the LLM never emits a number that enters predictions."
    )


def extract_rule(doc: SourceDoc, subject_id: str, game_date: str,
                 confidence: float = 0.6) -> List[EdgeFact]:
    """DETERMINISTIC keyword fallback: scan the doc text, emit one EdgeFact per matched kind.

    No model, no randomness -- the SAME text always yields the SAME facts (the test relies on
    this). availability_ts is set to the document's published_ts (the earliest the fact could be
    known). Every emitted fact is validated before it is returned.
    """
    validate_source(doc.as_dict())
    low = doc.text.lower()
    seen: set = set()
    facts: List[EdgeFact] = []
    for kw, kind in _RULE_PATTERNS:
        if kw in low and kind not in seen:
            seen.add(kind)
            # value_text = the sentence containing the keyword (verbatim span), capped.
            span = _span_for(doc.text, kw)
            f = EdgeFact(
                fact_kind=kind, sport=doc.sport, subject_id=subject_id,
                game_date=game_date, value_text=span, source=doc.source,
                availability_ts=doc.published_ts, confidence=float(confidence),
            )
            validate_fact(f.as_dict())
            facts.append(f)
    return facts


def _span_for(text: str, kw: str, width: int = 120) -> str:
    """Return the verbatim window of `text` around the first case-insensitive `kw` hit."""
    i = text.lower().find(kw)
    if i < 0:
        return text[:width]
    start = max(0, i - 20)
    return text[start:start + width].strip()


def revalidate(fact: EdgeFact, doc: SourceDoc) -> EdgeFact:
    """Non-negotiable post-extraction gate, whatever path produced the fact.

    Asserts (a) the fact shape is honest (validate_fact -> trips on any banned outcome number),
    and (b) availability_ts is NOT before the SourceDoc's published_ts -- a fact cannot have been
    knowable before the document that stated it (a hallucinated-early timestamp is a leak in the
    making). Returns the fact unchanged on success; raises AssertionError otherwise.
    """
    d = fact.as_dict()
    validate_fact(d)  # honesty re-validation (no probability/outcome field)
    avail = _to_dt(fact.availability_ts)
    published = _to_dt(doc.published_ts)
    assert avail >= published, (
        f"availability_ts {fact.availability_ts} predates source published_ts "
        f"{doc.published_ts} -- impossible vintage (fabricated-early fact)"
    )
    return fact


def assert_no_probability(fact_dict: Dict) -> None:
    """Belt-and-suspenders: re-run the honesty rail in isolation (used by callers/tests).

    validate_fact already enforces this, but exposing it standalone documents the contract:
    the extractor's output is FACTS only; any number-that-enters-prediction is rejected here.
    """
    validate_fact(fact_dict)
