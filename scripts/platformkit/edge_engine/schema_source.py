"""edge_engine -- the SOURCE + FACT schema for the information-edge pipeline (sport-agnostic).

THESIS (binding): the edge is a PROPRIETARY + PREDICTIVE + TIMELY input the market has not
priced yet, manufactured by LLM extraction of unstructured sources FASTER/more completely
than the market. This module is the typed contract the extractor fills. It GENERALIZES the
freshness X1 InjuryDelta shape (which was injury-only) to any sport / any fact kind, while
keeping the SAME honesty rails:

  - An LLM emits FACTS + an EXTRACTION confidence ONLY. There is NO probability / outcome
    field by construction -- the shape itself enforces "the LLM never authors a number that
    enters the prediction chain".
  - Every fact carries availability_ts (ISO datetime the fact became publicly known). The
    vintage guard (freshness.as_of_reader.assert_vintage) asserts availability_ts < line/pred
    time downstream; this module re-validates the SHAPE.

A SourceDoc is one unstructured document (presser transcript, beat post, lineup report) with
its own publish timestamp -- the upper bound for any fact pulled from it. An EdgeFact is one
typed fact pulled from a SourceDoc.

Stdlib only. <=300 LOC. Per-file test: tests/test_schema_source.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

# Sports the pipeline spans (the 4-sport predictor).
SPORTS: Tuple[str, ...] = ("nba", "mlb", "soccer", "tennis")

# The fact KINDS the LLM may extract. Each maps to an EXISTING deterministic model knob;
# the fact only conditions WHICH knob applies, never authors the knob's value. Generic across
# sports -- the schedule_fatigue_map enumerates the NBA-specific instances of these.
FACT_KINDS: Tuple[str, ...] = (
    "lineup_status",        # player availability / role change (the freshness X1 base case)
    "travel_disruption",    # charter delay, diversion, late/cross-tz arrival
    "actual_travel_party",  # who actually traveled vs stayed back
    "coach_rotation_intent",# stated minutes restriction / rest plan / starter sit
    "weather_field",        # wind/precip/field-condition fact (mlb/soccer)
    "pitcher_usage",        # bullpen burned / probable-pitcher change (mlb)
    "surface_condition",    # court speed / surface change (tennis/soccer)
    "local_disruption",     # illness sweep, hotel/curfew, sleep disruption
    "narrative_framing",    # letdown/lookahead/revenge framing (weakest; expect REJECT)
)

# A fact carries EXACTLY these fields. Note: NO probability / outcome / price field exists.
FACT_FIELDS: Tuple[str, ...] = (
    "fact_kind",        # one of FACT_KINDS -- the knob this fact conditions
    "sport",            # one of SPORTS
    "subject_id",       # team_id / player_id the fact attaches to
    "game_date",        # ISO date the fact applies to
    "value_text",       # verbatim extracted fact (e.g. 'charter delayed; 4am arrival')
    "source",           # provenance url / feed name
    "availability_ts",  # ISO datetime the fact became publicly known -- the vintage key
    "confidence",       # [0,1] EXTRACTION confidence ONLY (never an outcome prob)
)

# Fields that must NEVER appear on a fact row -- any of these means a number that could enter
# the prediction chain rode in on a FACT. validate_fact() trips on them.
BANNED_FIELDS: Tuple[str, ...] = (
    "win_prob", "probability", "prob", "edge", "ev", "roi", "spread",
    "total", "price", "odds", "line", "implied", "calibrated_prob", "stake",
)


@dataclass(frozen=True)
class SourceDoc:
    """One unstructured document the extractor reads, stamped with its publish time.

    published_ts is the UPPER BOUND for any fact's availability_ts: a fact cannot have been
    knowable before the document that stated it existed (the extractor re-asserts this).
    """
    doc_id: str
    sport: str
    published_ts: str       # ISO datetime the document was published
    text: str               # raw unstructured content
    source: str             # provenance url / feed name
    doc_date: Optional[str] = None  # ISO date the doc is about (for date-sanity checks)

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id, "sport": self.sport,
            "published_ts": self.published_ts, "text": self.text,
            "source": self.source, "doc_date": self.doc_date,
        }


@dataclass(frozen=True)
class EdgeFact:
    """One typed FACT pulled from ONE SourceDoc, stamped with its vintage key.

    EXTRACTION-confidence only -- there is NO probability field by construction. This is the
    only thing the LLM produces; deterministic code computes every downstream number.
    """
    fact_kind: str
    sport: str
    subject_id: str
    game_date: str
    value_text: str
    source: str
    availability_ts: str
    confidence: float

    def as_dict(self) -> dict:
        return {
            "fact_kind": self.fact_kind, "sport": self.sport,
            "subject_id": self.subject_id, "game_date": self.game_date,
            "value_text": self.value_text, "source": self.source,
            "availability_ts": self.availability_ts, "confidence": self.confidence,
        }


def _iso_ok(ts: str, date_only: bool = False) -> bool:
    """True if ts parses as ISO. date_only=True for YYYY-MM-DD dates."""
    try:
        if date_only:
            datetime.fromisoformat(ts[:10])
        else:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return True
    except (ValueError, TypeError):
        return False


def validate_source(d: Dict) -> None:
    """Raise AssertionError on a malformed SourceDoc dict."""
    for k in ("doc_id", "sport", "published_ts", "text", "source"):
        assert k in d and d[k] not in (None, ""), f"missing/empty source field {k}"
    assert d["sport"] in SPORTS, f"bad sport {d['sport']}"
    assert _iso_ok(d["published_ts"]), f"published_ts not ISO: {d['published_ts']}"


def validate_fact(d: Dict) -> None:
    """Raise AssertionError on a malformed / dishonest FACT row.

    Enforces: required fields present, enum membership, confidence in [0,1], ISO timestamps,
    and crucially that NO probability/outcome/price number rode in on the fact (BANNED_FIELDS).
    Runs DOWNSTREAM of any LLM extraction -- this is the non-negotiable honesty re-validation.
    """
    for k in FACT_FIELDS:
        assert k in d and d[k] not in (None, ""), f"missing/empty fact field {k}"
    assert d["fact_kind"] in FACT_KINDS, f"bad fact_kind {d['fact_kind']}"
    assert d["sport"] in SPORTS, f"bad sport {d['sport']}"
    try:
        conf = float(d["confidence"])
    except (TypeError, ValueError):
        raise AssertionError("confidence not numeric")
    assert 0.0 <= conf <= 1.0, "confidence out of [0,1]"
    assert _iso_ok(d["availability_ts"]), f"availability_ts not ISO: {d['availability_ts']}"
    assert _iso_ok(d["game_date"], date_only=True), f"game_date not ISO date: {d['game_date']}"
    # honesty rail: the ONLY numeric field is the EXTRACTION confidence.
    for k in d:
        assert k not in BANNED_FIELDS, f"FORBIDDEN outcome/price field on a FACT row: {k}"
