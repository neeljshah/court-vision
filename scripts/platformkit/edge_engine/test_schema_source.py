"""Per-file test for edge_engine.schema_source (the typed SOURCE + FACT contract).

Asserts the honesty rails the whole machine rests on:
  - a fact has NO probability/outcome field by construction; validate_fact TRIPS on any banned
    number that tries to ride on a FACT row (top-level smuggling);
  - enum + range + ISO-timestamp validation is enforced;
  - a SourceDoc's shape is validated (the vintage floor lives on published_ts).

Standalone-runnable (full suite freezes the box):
  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/tests/test_schema_source.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pytest  # noqa: E402

from scripts.platformkit.edge_engine.schema_source import (  # noqa: E402
    BANNED_FIELDS, EdgeFact, FACT_KINDS, SPORTS, SourceDoc,
    validate_fact, validate_source,
)


def _fact(**kw) -> EdgeFact:
    base = dict(
        fact_kind="travel_disruption", sport="nba", subject_id="1610612743",
        game_date="2026-01-15", value_text="charter delayed; 4am arrival",
        source="https://x.com/beat/status/1", availability_ts="2026-01-15T11:00:00",
        confidence=0.8,
    )
    base.update(kw)
    return EdgeFact(**base)


def _doc(**kw) -> SourceDoc:
    base = dict(
        doc_id="d1", sport="nba", published_ts="2026-01-15T11:00:00",
        text="charter was diverted; late arrival", source="https://x.com/beat/status/1",
        doc_date="2026-01-15",
    )
    base.update(kw)
    return SourceDoc(**base)


# --- the FACT has no probability by construction --------------------------------

def test_edgefact_has_no_probability_field():
    d = _fact().as_dict()
    for banned in BANNED_FIELDS:
        assert banned not in d, f"a FACT must not expose {banned}"
    # only numeric field present is the EXTRACTION confidence
    numeric = [k for k, v in d.items() if isinstance(v, (int, float))]
    assert numeric == ["confidence"]


def test_validate_fact_accepts_clean_row():
    validate_fact(_fact().as_dict())  # no raise


def test_validate_fact_trips_on_smuggled_outcome_number():
    for banned in ("win_prob", "edge", "price", "roi", "implied"):
        d = _fact().as_dict()
        d[banned] = 0.61  # an outcome/price number must never ride on a FACT
        with pytest.raises(AssertionError):
            validate_fact(d)


def test_validate_fact_rejects_bad_kind_and_sport():
    with pytest.raises(AssertionError):
        validate_fact(_fact(fact_kind="not_a_kind").as_dict())
    with pytest.raises(AssertionError):
        validate_fact(_fact(sport="cricket").as_dict())


def test_validate_fact_rejects_out_of_range_confidence():
    with pytest.raises(AssertionError):
        validate_fact(_fact(confidence=1.5).as_dict())
    with pytest.raises(AssertionError):
        validate_fact(_fact(confidence=-0.1).as_dict())


def test_validate_fact_rejects_non_iso_timestamps():
    with pytest.raises(AssertionError):
        validate_fact(_fact(availability_ts="not-a-time").as_dict())
    with pytest.raises(AssertionError):
        validate_fact(_fact(game_date="15/01/2026").as_dict())


# --- SourceDoc (the vintage floor) ---------------------------------------------

def test_validate_source_accepts_clean_doc():
    validate_source(_doc().as_dict())  # no raise


def test_validate_source_rejects_bad_sport_and_ts():
    with pytest.raises(AssertionError):
        validate_source(_doc(sport="cricket").as_dict())
    with pytest.raises(AssertionError):
        validate_source(_doc(published_ts="yesterday").as_dict())


def test_enums_cover_four_sports_and_named_kinds():
    assert set(SPORTS) == {"nba", "mlb", "soccer", "tennis"}
    assert "lineup_status" in FACT_KINDS and "travel_disruption" in FACT_KINDS
