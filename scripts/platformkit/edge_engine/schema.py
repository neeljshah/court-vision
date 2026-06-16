"""edge_engine -- the GENERIC information-edge contract (the typed spine of the machine).

THESIS (binding): the edge is NOT better prediction (the market is efficient on price).
It is a PROPRIETARY + PREDICTIVE + TIMELY input the market has not priced yet, manufactured
by intelligence-at-scale (an LLM extracting unstructured sources faster/more completely than
the market), then combined into ONE bounded net adjustment that fires only before the line move.

This module generalizes the freshness X1 shape (freshness/schema.py InjuryDelta,
freshness/extract_stub.py InjuryExtraction) from the injury/lineup special-case to ANY
information-edge FACT in ANY of the 4 sports. The schedule_fatigue_map FatigueFact is one
concrete instance; ExtractedSignal here is the sport-blind superset every adapter emits.

HONESTY RAILS (non-negotiable, enforced by SHAPE + validate_signal):
  - The LLM extracts FACTS + an EXTRACTION confidence ONLY. There is NO probability field by
    construction; the only numeric output is `confidence` (confidence in the EXTRACTION, never
    in any game outcome). Deterministic downstream code computes every number that enters a
    prediction; the LLM NEVER authors a number that enters the prediction chain.
  - Every signal carries availability_ts; the vintage guard (freshness.as_of_reader) asserts
    it < line/pred time. A signal known only after the move is hindsight, not an edge.
  - NO edge is CLAIMED here. These are typed CONTAINERS; the eval_gate is the JUDGE and an
    honest REJECT is a SUCCESS. No $/ROI/+EV/"money printer" language anywhere.

Self-contained: stdlib only (no pydantic dep so it runs in CI without installs), <=300 LOC.
Per-file test: test_schema.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

SPORTS: Tuple[str, ...] = ("nba", "mlb", "soccer", "tennis")

# The 3 tests every candidate signal MUST clear (else honest REJECT, recorded as success).
TESTS: Tuple[str, ...] = ("PROPRIETARY", "PREDICTIVE", "TIMELY_EXECUTABLE")

# The information-edge FACT families an LLM may extract. Generic across sports; a sport adapter
# (e.g. schedule_fatigue_map FACT_KINDS) refines these into sport-specific kinds. Each maps to
# an EXISTING deterministic model knob -- the FACT selects/conditions the knob, never its value.
SIGNAL_TYPES: Tuple[str, ...] = (
    "injury_status",       # player availability / severity (the freshness X1 special-case)
    "lineup_intent",       # stated rotation / starter / minutes-restriction facts
    "travel_disruption",   # charter delay, late arrival, who actually traveled
    "venue_condition",     # weather / wind / altitude / surface / pitch-state facts
    "morale_disruption",   # locker-room / suspension / illness-sweep / off-court facts
    "tactical_intent",     # coach-stated scheme / matchup / load-management plan
    "market_microfact",    # publicly-stated but unaggregated fact (lineup leak, presser quote)
)

# Numeric/outcome field names that MUST NEVER appear on a fact-carrying row. The single permitted
# numeric output is `confidence` (extraction confidence). This is the honesty rail, in code.
BANNED_FIELDS: Tuple[str, ...] = (
    "win_prob", "probability", "prob", "edge", "ev", "roi", "spread",
    "total", "price", "odds", "moneyline", "implied", "kelly",
)


@dataclass(frozen=True)
class RawSource:
    """Provenance metadata for one unstructured document an adapter captured.

    Captured BEFORE any extraction so the vintage key (captured_at) is the document's, not the
    LLM's. captured_at is the load-bearing leak key: the downstream availability_ts can never be
    earlier than when we actually saw the source.
    """
    source_id: str          # stable id for the feed/document (dedupe + audit key)
    url: str                # provenance url / feed name
    captured_at: str        # ISO datetime WE captured it -- the vintage floor
    publisher: str = ""     # optional: outlet / handle / domain
    kind: str = ""          # optional: 'tweet' / 'presser' / 'beat' / 'weather_api'

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "url": self.url,
            "captured_at": self.captured_at, "publisher": self.publisher,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class NewsItem:
    """One raw unstructured document the LLM will read (pre-extraction).

    The text + its provenance, stamped with captured_at. This is what a SourceAdapter yields;
    nothing here is a fact yet -- extraction turns a NewsItem into zero or more ExtractedSignals.
    """
    source_id: str          # ties back to a RawSource
    text: str               # the verbatim unstructured content
    url: str                # provenance url / feed name
    captured_at: str        # ISO datetime WE captured this item -- the vintage floor
    sport: str = ""         # optional hint: one of SPORTS (extractor may refine)
    doc_date: Optional[str] = None  # optional ISO date the doc is about (hallucination guard)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "text": self.text, "url": self.url,
            "captured_at": self.captured_at, "sport": self.sport,
            "doc_date": self.doc_date,
        }


@dataclass(frozen=True)
class ExtractedSignal:
    """One information-edge FACT the LLM pulled from ONE NewsItem, stamped with its vintage key.

    The sport-blind superset of FatigueDelta/InjuryDelta. EXTRACTION-confidence only -- there is
    NO probability field by construction. value_facts holds the structured verbatim FACTS (e.g.
    {"status": "OUT", "player": "Doncic"} or {"wind_mph": "18", "dir": "out_to_RF"}); the LLM
    never converts these into an outcome number -- deterministic downstream code does.
    """
    signal_type: str                 # one of SIGNAL_TYPES
    entity: str                       # team_id / player_id the fact attaches to
    value_facts: Dict[str, str]       # structured verbatim FACTS (strings only, no probs)
    confidence: float                 # [0,1] EXTRACTION confidence ONLY (never an outcome prob)
    availability_ts: str              # ISO datetime the fact became publicly known -- vintage key
    source: str                       # provenance url / feed (ties to a RawSource/NewsItem)
    sport: str = ""                   # one of SPORTS
    game_date: str = ""               # ISO date the fact applies to
    note: str = ""                    # verbatim evidence span the LLM read
    is_fallback_proxy: bool = False   # True => reconstructed post-hoc (outcome-conditioned)

    def as_dict(self) -> dict:
        return {
            "signal_type": self.signal_type, "entity": self.entity,
            "value_facts": dict(self.value_facts), "confidence": self.confidence,
            "availability_ts": self.availability_ts, "source": self.source,
            "sport": self.sport, "game_date": self.game_date, "note": self.note,
            "is_fallback_proxy": self.is_fallback_proxy,
        }


def _assert_iso(ts: str, label: str) -> None:
    """Raise AssertionError if ts is not parseable ISO-8601 (Py3.9: normalise trailing Z)."""
    try:
        datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise AssertionError(f"{label} not ISO-8601: {ts!r}")


def validate_signal(d: dict) -> None:
    """Raise AssertionError on a malformed / dishonest ExtractedSignal row.

    Runs DOWNSTREAM of any LLM extraction (constrained decoding still fails ~12% semantically).
    Enforces: required fields present, signal_type/sport enum membership, confidence in [0,1],
    ISO timestamps, and -- the honesty rail -- that NO banned probability/outcome field sneaked
    into the top level OR into value_facts.
    """
    req = ("signal_type", "entity", "value_facts", "confidence",
           "availability_ts", "source")
    for k in req:
        assert k in d and d[k] not in (None, ""), f"missing/empty field {k}"
    assert d["signal_type"] in SIGNAL_TYPES, f"bad signal_type {d['signal_type']}"
    if d.get("sport"):
        assert d["sport"] in SPORTS, f"bad sport {d['sport']}"
    try:
        conf = float(d["confidence"])
    except (TypeError, ValueError):
        raise AssertionError("confidence not numeric")
    assert 0.0 <= conf <= 1.0, "confidence out of [0,1]"
    facts = d["value_facts"]
    assert isinstance(facts, dict) and facts, "value_facts must be a non-empty dict"
    # honesty rail: no banned outcome/numeric field at top level...
    for k in d:
        assert k.lower() not in BANNED_FIELDS, (
            f"FORBIDDEN outcome field on a FACT row: {k}"
        )
    # ...nor smuggled into the structured facts.
    for k in facts:
        assert str(k).lower() not in BANNED_FIELDS, (
            f"FORBIDDEN outcome field inside value_facts: {k}"
        )
    _assert_iso(d["availability_ts"], "availability_ts")
    if d.get("game_date"):
        _assert_iso(d["game_date"], "game_date")


def to_signal(item: NewsItem, signal_type: str, entity: str,
              value_facts: Dict[str, str], confidence: float, availability_ts: str,
              game_date: str = "", note: str = "",
              is_fallback_proxy: bool = False) -> ExtractedSignal:
    """Resolve a NewsItem + extracted facts into a validated ExtractedSignal.

    availability_ts must be >= the item's captured_at (we cannot have known a fact before we
    captured the document). Entity resolution (name -> id) is a deterministic caller lookup,
    NEVER the LLM. Validates before returning.
    """
    cap = datetime.fromisoformat(str(item.captured_at).replace("Z", "+00:00"))
    avail = datetime.fromisoformat(str(availability_ts).replace("Z", "+00:00"))
    assert avail >= cap, (
        f"availability_ts {availability_ts} precedes captured_at {item.captured_at} "
        f"-- a fact cannot be known before its source was captured"
    )
    sig = ExtractedSignal(
        signal_type=signal_type, entity=entity, value_facts=dict(value_facts),
        confidence=float(confidence), availability_ts=availability_ts,
        source=item.url, sport=item.sport, game_date=game_date, note=note,
        is_fallback_proxy=is_fallback_proxy,
    )
    validate_signal(sig.as_dict())
    return sig
