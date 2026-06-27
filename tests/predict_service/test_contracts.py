"""Per-file test: predict_service.contracts round-trip + honesty invariants.

Run: python -m pytest tests/predict_service/test_contracts.py -q
"""
from __future__ import annotations

import json

from predict_service.contracts import (
    SCHEMA_VERSION,
    EdgeRow,
    MarketRow,
    PredictionRecord,
    SnapshotEnvelope,
)


def _sample_envelope() -> SnapshotEnvelope:
    mkt = MarketRow(
        sport="nba", game_id="g1", market_type="moneyline", side="home",
        line=None, odds=1.91, book="bookA", devigged_prob=0.52,
        captured_at="2026-06-18T00:00:00+00:00", is_close=True, clv_is_proxy=True,
    )
    edge = EdgeRow(
        game_id="g1", market_type="moneyline", side="home",
        model_prob=0.58, market_prob=0.52, ev=0.11, tier="B", book="bookA",
        line=None, clv_is_proxy=True,
    )
    pred = PredictionRecord(
        sport="nba", game_id="g1", home="NYK", away="SAS",
        tipoff="2026-06-18T23:00:00+00:00",
        pregame_probs={"home_ml": 0.58, "away_ml": 0.42},
        markets=[mkt], leak_guard={"in_sample": False},
        produced_at="2026-06-18T22:00:00+00:00", note="calibrated",
    )
    return SnapshotEnvelope(
        sport="nba", generated_at="2026-06-18T22:00:00+00:00",
        status="ok", predictions=[pred], markets=[mkt], edges=[edge],
    )


def test_schema_version_present():
    env = _sample_envelope()
    d = env.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION
    assert SCHEMA_VERSION  # non-empty


def test_envelope_round_trip_equal():
    env = _sample_envelope()
    again = SnapshotEnvelope.from_dict(env.to_dict())
    assert again == env


def test_json_round_trip_equal():
    env = _sample_envelope()
    blob = json.dumps(env.to_dict())
    again = SnapshotEnvelope.from_dict(json.loads(blob))
    assert again == env


def test_marketrow_round_trip():
    m = MarketRow(sport="mlb", game_id="m1", market_type="total", side="over",
                  line=8.5, odds=1.95, book="bk", devigged_prob=0.49,
                  captured_at="2026-06-18T00:00:00+00:00", is_close=False,
                  clv_is_proxy=False)
    assert MarketRow.from_dict(m.to_dict()) == m


def test_edgerow_round_trip():
    e = EdgeRow(game_id="m1", market_type="total", side="over", model_prob=0.55,
                market_prob=0.49, ev=0.07, tier="A", book="bk", line=8.5)
    assert EdgeRow.from_dict(e.to_dict()) == e


def test_no_dollar_edge_field_anywhere():
    """HONESTY: no $ / dollar edge field on any schema. Edges are prob/EV only."""
    env = _sample_envelope()
    blob = json.dumps(env.to_dict()).lower()
    for banned in ("$edge", "dollar", "roi", "profit"):
        assert banned not in blob
    edge_keys = set(env.edges[0].to_dict().keys())
    assert "ev" in edge_keys
    for banned in ("edge", "dollars", "stake", "bankroll"):
        # EdgeRow carries probability/EV + tier, never a money field.
        assert banned not in edge_keys


def test_unknown_fields_ignored_on_read():
    """Forward-compat: a snapshot with extra keys still parses (extras dropped)."""
    d = _sample_envelope().to_dict()
    d["future_field"] = 123
    d["edges"][0]["future_dollar_edge"] = 9.99
    env = SnapshotEnvelope.from_dict(d)
    assert env.status == "ok"
    assert not hasattr(env.edges[0], "future_dollar_edge")


def test_leak_guard_default_in_sample_false():
    p = PredictionRecord(sport="nba", game_id="g", home="A", away="B")
    assert p.leak_guard == {"in_sample": False}
    p2 = PredictionRecord.from_dict({"sport": "nba", "game_id": "g",
                                     "home": "A", "away": "B",
                                     "leak_guard": {"in_sample": True}})
    assert p2.leak_guard == {"in_sample": True}


def test_unavailable_sentinel_shape():
    env = SnapshotEnvelope.unavailable("nba", reason="missing")
    assert env.status == "unavailable"
    assert env.sport == "nba"
    assert env.schema_version == SCHEMA_VERSION
    assert SnapshotEnvelope.from_dict(env.to_dict()) == env
