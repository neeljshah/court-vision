"""edge_engine -- schedule-fatigue INFORMATION-EDGE candidate map (the MAP, not a found edge).

THESIS (binding): the edge is NOT better schedule physics. Raw rest / b2b / 3-in-4 are
DETERMINISTIC from the public calendar -- the market prices them, and our own
proof_nba.totals_with_rest expects an honest null on b2b/rest as a totals feature.
So every candidate here is an information-edge ONLY where an LLM can extract a FACT the
market cannot process at our scale/speed and that flips a generic schedule spot into a
sharp one BEFORE the line move (travel logistics, charter/arrival disruptions, who actually
traveled, altitude-acclimatization windows, coach-stated rotation intent on a fatigue spot).

HONESTY RAILS (non-negotiable):
  - The LLM extracts FACTS + an EXTRACTION confidence ONLY. It NEVER authors a probability
    or any number that enters the prediction chain. Deterministic code computes the schedule
    physics; the FACT only conditions WHICH physics multiplier (an EXISTING knob) applies.
  - Every candidate carries an availability_timestamp; the vintage guard
    (freshness.as_of_reader.assert_vintage) asserts it < line/pred time.
  - NO edge is CLAIMED. A candidate is a HYPOTHESIS until it passes the REAL gate on >=2
    corpora with forward CLV. An honest REJECT is a SUCCESS. No $/ROI/+EV language.

This module is a typed registry + a leak-free vintage stamp helper. It does NOT predict.
Stdlib only. <=300 LOC. Per-file test: test_schedule_fatigue_map.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# Reuse the existing vintage guard -- do NOT reimplement leak checking.
try:  # package import
    from scripts.platformkit.freshness.as_of_reader import assert_vintage  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "freshness"))
    from as_of_reader import assert_vintage  # type: ignore

# The 3 tests every candidate must clear (else honest REJECT, recorded as success).
TESTS: Tuple[str, ...] = ("PROPRIETARY", "PREDICTIVE", "TIMELY_EXECUTABLE")

# Verdict an LLM-extracted FACT can carry. It NEVER carries a probability.
FACT_FIELDS: Tuple[str, ...] = (
    "fact_kind",        # which physics knob this FACT conditions (enum below)
    "subject_id",       # team_id / player_id the fact attaches to
    "game_date",        # ISO date the fact applies to
    "value_text",       # verbatim extracted fact (e.g. 'charter delayed to 4am arrival')
    "source",           # provenance url / feed
    "availability_ts",  # ISO datetime the fact became publicly known -- the vintage key
    "confidence",       # [0,1] EXTRACTION confidence ONLY (never an outcome prob)
)

# The schedule-fatigue FACT kinds the LLM may extract. Each maps to an EXISTING deterministic
# schedule-physics knob; the FACT only selects/conditions the knob, never authors its value.
FACT_KINDS: Tuple[str, ...] = (
    "travel_disruption",     # charter delay, weather diversion, late arrival time
    "actual_travel_party",   # who flew vs stayed back / flew commercial / arrived separately
    "altitude_acclimatize",  # days in Denver/Utah area before tip (pre-arrival vs day-of)
    "coach_rotation_intent", # presser FACT: 'minutes restriction', 'sitting starters tonight'
    "schedule_loss_spot",    # stated 'trap'/letdown framing from beat (revenge/lookahead)
    "local_disruption",      # arena/hotel/curfew/illness-sweep facts that compound fatigue
)


@dataclass(frozen=True)
class FatigueFact:
    """One schedule-fatigue FACT extracted from ONE document, stamped with its vintage key.

    EXTRACTION-confidence only -- there is NO probability field by construction.
    """
    fact_kind: str
    subject_id: str
    game_date: str
    value_text: str
    source: str
    availability_ts: str
    confidence: float

    def as_dict(self) -> dict:
        return {
            "fact_kind": self.fact_kind, "subject_id": self.subject_id,
            "game_date": self.game_date, "value_text": self.value_text,
            "source": self.source, "availability_ts": self.availability_ts,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class Candidate:
    """One enumerated information-edge candidate, scored on the 3 tests. A HYPOTHESIS only."""
    signal: str
    fact_kind: str
    source: str
    llm_extracts: str        # FACTS only -- what the LLM pulls
    proprietary: str         # high/medium/low
    predictive_hypothesis: str
    timely_window: str
    leak_free_capture: str
    priority: str            # P0/P1/P2
    prior_evidence: str
    tests: Tuple[str, ...] = field(default_factory=lambda: TESTS)


def validate_fact(d: dict) -> None:
    """Raise AssertionError on a malformed FACT row. Runs DOWNSTREAM of any LLM extraction.

    Enforces: required fields present, enum membership, confidence in [0,1], and crucially
    that NO probability/number-that-enters-prediction sneaked in.
    """
    for k in FACT_FIELDS:
        assert k in d and d[k] not in (None, ""), f"missing/empty field {k}"
    assert d["fact_kind"] in FACT_KINDS, f"bad fact_kind {d['fact_kind']}"
    try:
        conf = float(d["confidence"])
    except (TypeError, ValueError):
        raise AssertionError("confidence not numeric")
    assert 0.0 <= conf <= 1.0, "confidence out of [0,1]"
    # honesty rail: the only numeric field is the EXTRACTION confidence.
    banned = ("win_prob", "probability", "edge", "ev", "roi", "spread", "total", "price")
    for k in d:
        assert k not in banned, f"FORBIDDEN numeric/outcome field on a FACT row: {k}"


def stamp_leak_free(fact: FatigueFact, line_move_ts: str) -> dict:
    """Validate the FACT and assert its availability_ts is STRICTLY before the line move.

    Returns the leak-free delta dict; raises AssertionError (with 'LEAK') if the fact was
    not known before the move -- the difference between an information edge and hindsight.
    """
    d = fact.as_dict()
    validate_fact(d)
    # Reuse the freshness vintage guard: it keys on extracted_at, so map our field onto it.
    assert_vintage({"extracted_at": fact.availability_ts,
                    "player_id": fact.subject_id}, line_move_ts)
    return d


def candidates() -> List[Candidate]:
    """The enumerated schedule-fatigue information-edge candidates (hypotheses to be gated)."""
    return [
        Candidate(
            signal="charter_arrival_disruption",
            fact_kind="travel_disruption",
            source="beat-reporter X posts + flight-tracker text snapshots, vintage-stamped",
            llm_extracts="FACT: delayed/diverted charter, actual arrival local-time, "
                         "miles + tz crossed (from public itinerary), verbatim span",
            proprietary="high",
            predictive_hypothesis="late/cross-tz arrival deepens an ALREADY-priced b2b "
                                  "spot the market treats as generic; conditions the b2b knob",
            timely_window="night-before / morning-of, hours before the total tightens",
            leak_free_capture="availability_ts = post timestamp; assert < line_move_ts",
            priority="P0",
            prior_evidence="totals_with_rest expects b2b/rest as priced (null); the DETAIL "
                           "(this specific arrival) is what the calendar cannot show",
        ),
        Candidate(
            signal="actual_travel_party",
            fact_kind="actual_travel_party",
            source="beat-reporter availability/shootaround reports, vintage-stamped",
            llm_extracts="FACT: which players flew vs stayed/were-sent-home, arrived "
                         "separately, on minutes-watch from the road trip -- names only",
            proprietary="high",
            predictive_hypothesis="schedule fatigue is player-specific; the box calendar "
                                  "assumes the full roster traveled -- often false on long trips",
            timely_window="shootaround ~10am-noon, before lineup-driven moves",
            leak_free_capture="availability_ts = report timestamp; assert < line_move_ts",
            priority="P0",
            prior_evidence="edge-taxonomy 11/14/55 treat travel as roster-wide; per-player "
                           "travel facts are not in any retail feed",
        ),
        Candidate(
            signal="altitude_acclimatization_window",
            fact_kind="altitude_acclimatize",
            source="team itinerary / beat reports of early arrival in DEN/UTA, vintage-stamped",
            llm_extracts="FACT: days the visitor spent at altitude before tip (flew in "
                         "early vs day-of), prior leg also at altitude -- dates only",
            proprietary="medium",
            predictive_hypothesis="Denver/Utah altitude effect (taxonomy 12) is priced as a "
                                  "binary venue flag; acclimatization days modulate its SIZE",
            timely_window="1-2 days pre-tip when itinerary becomes public",
            leak_free_capture="availability_ts = itinerary/report timestamp; assert < move",
            priority="P1",
            prior_evidence="taxonomy edge 12 is a binary visit-Denver flag; the acclimatize "
                           "window is the un-priced detail",
        ),
        Candidate(
            signal="coach_stated_rotation_on_fatigue_spot",
            fact_kind="coach_rotation_intent",
            source="pre-game presser transcripts / beat quotes, vintage-stamped",
            llm_extracts="FACT: coach said minutes-restriction / 'sitting starters' / "
                         "'load manage on the back-end' -- verbatim quote, player names",
            proprietary="high",
            predictive_hypothesis="on a known 3-in-4/4-in-5 spot, a stated rotation plan "
                                  "redistributes minutes the market hasn't yet priced",
            timely_window="presser ~1-3h pre-tip, the live-minutes pricing window",
            leak_free_capture="availability_ts = transcript timestamp; assert < line_move_ts",
            priority="P0",
            prior_evidence="taxonomy 14 (load mgmt) is a classifier; a coach's verbatim "
                           "stated intent is a higher-confidence FACT than a prediction",
        ),
        Candidate(
            signal="schedule_loss_letdown_framing",
            fact_kind="schedule_loss_spot",
            source="beat/national 'trap game' / 'letdown' / 'lookahead' text, vintage-stamped",
            llm_extracts="FACT: presence + intensity of letdown/lookahead framing tied to "
                         "the schedule spot (post-big-win, pre-marquee) -- verbatim span",
            proprietary="medium",
            predictive_hypothesis="schedule-loss road spots (taxonomy 18) are partly priced; "
                                  "extracted narrative flags which generic spots are LIVE",
            timely_window="day-of, before public money firms the side",
            leak_free_capture="availability_ts = article timestamp; assert < line_move_ts",
            priority="P2",
            prior_evidence="soft/narrative signal; weakest of the set -- expect REJECT unless "
                           "it survives the gate on >=2 corpora; recorded as honest null",
        ),
        Candidate(
            signal="trip_illness_or_local_disruption",
            fact_kind="local_disruption",
            source="beat reports of illness sweeps / hotel / curfew issues, vintage-stamped",
            llm_extracts="FACT: team-wide illness, disrupted sleep/hotel, late practice on "
                         "the road -- verbatim span, affected players if named",
            proprietary="high",
            predictive_hypothesis="compounds a priced fatigue spot with a fact the calendar "
                                  "cannot contain; conditions the same b2b/density knob",
            timely_window="morning-of to a few hours pre-tip",
            leak_free_capture="availability_ts = report timestamp; assert < line_move_ts",
            priority="P1",
            prior_evidence="adjacent to taxonomy 58 (injury word parsing); team-level "
                           "disruption facts are not aggregated by any retail feed",
        ),
    ]
