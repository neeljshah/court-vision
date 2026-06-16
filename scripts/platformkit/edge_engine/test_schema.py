"""Per-file test for edge_engine.schema. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_schema.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from scripts.platformkit.edge_engine.schema import (  # noqa: E402
    BANNED_FIELDS, ExtractedSignal, NewsItem, RawSource, SIGNAL_TYPES, SPORTS,
    to_signal, validate_signal,
)


def _item(**kw) -> NewsItem:
    base = dict(
        source_id="x:1", text="Doncic ruled OUT (calf).", url="https://x.com/beat/status/1",
        captured_at="2026-01-15T11:00:00+00:00", sport="nba", doc_date="2026-01-15",
    )
    base.update(kw)
    return NewsItem(**base)


def _signal(**kw) -> dict:
    base = dict(
        signal_type="injury_status", entity="1629029",
        value_facts={"status": "OUT", "body_part": "calf"}, confidence=0.85,
        availability_ts="2026-01-15T11:30:00+00:00", source="https://x.com/beat/status/1",
        sport="nba", game_date="2026-01-15",
    )
    base.update(kw)
    return ExtractedSignal(**base).as_dict()


def test_extracted_signal_has_no_probability_field():
    fields = set(ExtractedSignal.__dataclass_fields__)
    assert "probability" not in fields and "win_prob" not in fields and "prob" not in fields
    # the only numeric output is the extraction confidence
    assert "confidence" in fields


def test_validate_signal_accepts_clean_row():
    validate_signal(_signal())  # no raise


def test_validate_signal_rejects_bad_signal_type():
    with pytest.raises(AssertionError):
        validate_signal(_signal(signal_type="not_a_type"))


def test_validate_signal_rejects_bad_sport():
    with pytest.raises(AssertionError):
        validate_signal(_signal(sport="cricket"))


def test_validate_signal_rejects_out_of_range_confidence():
    with pytest.raises(AssertionError):
        validate_signal(_signal(confidence=1.4))


def test_validate_signal_rejects_banned_top_level_field():
    d = _signal()
    d["win_prob"] = 0.61
    with pytest.raises(AssertionError):
        validate_signal(d)


def test_validate_signal_rejects_banned_field_inside_value_facts():
    with pytest.raises(AssertionError):
        validate_signal(_signal(value_facts={"status": "OUT", "edge": "0.03"}))


def test_validate_signal_rejects_empty_value_facts():
    with pytest.raises(AssertionError):
        validate_signal(_signal(value_facts={}))


def test_validate_signal_rejects_bad_timestamp():
    with pytest.raises(AssertionError):
        validate_signal(_signal(availability_ts="not-a-date"))


def test_banned_fields_cover_the_obvious_outcome_words():
    for w in ("probability", "edge", "roi", "ev", "spread", "total", "price", "odds"):
        assert w in BANNED_FIELDS


def test_to_signal_builds_validated_signal():
    sig = to_signal(
        _item(), signal_type="injury_status", entity="1629029",
        value_facts={"status": "OUT"}, confidence=0.9,
        availability_ts="2026-01-15T11:30:00+00:00", game_date="2026-01-15",
    )
    assert isinstance(sig, ExtractedSignal)
    assert sig.sport == "nba"
    assert sig.source == "https://x.com/beat/status/1"


def test_to_signal_rejects_availability_before_capture():
    # a fact cannot be known before its source was captured -- this is a leak floor
    with pytest.raises(AssertionError):
        to_signal(
            _item(captured_at="2026-01-15T12:00:00+00:00"),
            signal_type="injury_status", entity="1629029",
            value_facts={"status": "OUT"}, confidence=0.9,
            availability_ts="2026-01-15T11:00:00+00:00",
        )


def test_rawsource_and_newsitem_roundtrip_dicts():
    rs = RawSource(source_id="x:1", url="u", captured_at="2026-01-15T11:00:00+00:00")
    assert rs.as_dict()["source_id"] == "x:1"
    assert _item().as_dict()["sport"] == "nba"


def test_enums_are_nonempty():
    assert SIGNAL_TYPES and SPORTS
