"""tests for scripts.platformkit.odds_provider.market_join -- per-file only.

Covers the _safe_float guard and join_quotes_to_edges robustness:
  (a) edge with model_prob=None still joins (degrades to 0.0, no crash)
  (b) quote with odds=None or odds<=1.0 is SKIPPED; other valid pairs still join
  (c) fully valid edge+quote produces a JoinedRow with correct fields
  (d) malformed edge key (missing game_id) is silently skipped
No network; no data files.
"""
import pytest

from scripts.platformkit.odds_provider.market_join import (
    JoinedRow,
    join_quotes_to_edges,
    _safe_float,
)
from scripts.platformkit.odds_provider.markets import MarketQuote


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _quote(game_id="G001", market_type="moneyline", side="home",
           odds=1.91, book="TestBook", captured_at="2026-01-01T00:00:00+00:00",
           line=None, devigged_prob=0.52):
    """Build a minimal valid MarketQuote for testing."""
    return MarketQuote(
        sport="nba",
        game_id=game_id,
        home="TeamA",
        away="TeamB",
        market_type=market_type,
        side=side,
        line=line,
        odds=odds,
        book=book,
        captured_at=captured_at,
        devigged_prob=devigged_prob,
    )


def _edge(game_id="G001", market_type="moneyline", side="home",
          model_prob=0.55, market_prob=0.52, ev=0.03, tier="A",
          book="EdgeBook", line=None, clv_is_proxy=False):
    """Build a minimal valid edge dict for testing."""
    return {
        "game_id": game_id,
        "market_type": market_type,
        "side": side,
        "model_prob": model_prob,
        "market_prob": market_prob,
        "ev": ev,
        "tier": tier,
        "book": book,
        "line": line,
        "clv_is_proxy": clv_is_proxy,
    }


# --------------------------------------------------------------------------- #
# Unit tests for _safe_float
# --------------------------------------------------------------------------- #

def test_safe_float_valid_number():
    assert _safe_float(1.91) == pytest.approx(1.91)


def test_safe_float_string_number():
    assert _safe_float("0.55") == pytest.approx(0.55)


def test_safe_float_none_returns_default():
    assert _safe_float(None) is None
    assert _safe_float(None, 0.0) == pytest.approx(0.0)


def test_safe_float_bad_string_returns_default():
    assert _safe_float("abc", 0.0) == pytest.approx(0.0)
    assert _safe_float("", None) is None


# --------------------------------------------------------------------------- #
# (c) fully valid edge + quote -> correct JoinedRow fields
# --------------------------------------------------------------------------- #

def test_valid_join_produces_correct_fields():
    edge = _edge(game_id="G001", market_type="moneyline", side="home",
                 model_prob=0.55, market_prob=0.52, ev=0.03)
    q = _quote(game_id="G001", market_type="moneyline", side="home",
               odds=1.91, book="DraftKings",
               captured_at="2026-01-01T00:00:00+00:00",
               devigged_prob=0.52)
    rows = join_quotes_to_edges([edge], [q])
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, JoinedRow)
    assert row.game_id == "G001"
    assert row.market_type == "moneyline"
    assert row.side == "home"
    assert row.model_prob == pytest.approx(0.55)
    assert row.market_prob == pytest.approx(0.52)
    assert row.ev == pytest.approx(0.03)
    assert row.quote_book == "DraftKings"
    assert row.quote_odds == pytest.approx(1.91)
    assert row.quote_captured_at == "2026-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# (a) edge with model_prob=None still joins (model_prob -> 0.0, no crash)
# --------------------------------------------------------------------------- #

def test_none_model_prob_degrades_to_zero_no_crash():
    edge = _edge(game_id="G002", model_prob=None, market_prob=None, ev=None)
    q = _quote(game_id="G002", odds=1.85)
    rows = join_quotes_to_edges([edge], [q])
    # The join should NOT crash and should produce exactly one row
    assert len(rows) == 1
    row = rows[0]
    assert row.model_prob == pytest.approx(0.0)
    assert row.market_prob == pytest.approx(0.0)
    assert row.ev == pytest.approx(0.0)


def test_none_numeric_fields_in_batch_do_not_abort_other_rows():
    """A malformed edge does not crash the whole batch."""
    good_edge = _edge(game_id="G003", model_prob=0.60)
    bad_edge = _edge(game_id="G004", model_prob=None, market_prob=None, ev=None)
    q_good = _quote(game_id="G003", odds=1.91)
    q_bad = _quote(game_id="G004", odds=1.80)
    rows = join_quotes_to_edges([good_edge, bad_edge], [q_good, q_bad])
    assert len(rows) == 2
    game_ids = {r.game_id for r in rows}
    assert "G003" in game_ids
    assert "G004" in game_ids


# --------------------------------------------------------------------------- #
# (b) quote with odds=None or odds<=1.0 is SKIPPED; valid pairs still join
# --------------------------------------------------------------------------- #

def test_quote_with_none_odds_is_skipped():
    edge = _edge(game_id="G005")
    q_bad = _quote(game_id="G005", odds=None)
    rows = join_quotes_to_edges([edge], [q_bad])
    assert rows == []


def test_quote_with_odds_leq_1_is_skipped():
    edge = _edge(game_id="G006")
    q_bad = _quote(game_id="G006", odds=1.0)
    rows = join_quotes_to_edges([edge], [q_bad])
    assert rows == []

    q_bad2 = _quote(game_id="G006", odds=0.9)
    rows2 = join_quotes_to_edges([edge], [q_bad2])
    assert rows2 == []


def test_bad_odds_quote_skipped_but_valid_quote_retained():
    """When two quotes for the same side have odds=None and odds=1.91, only
    the valid one is emitted -- the batch is NOT aborted."""
    edge = _edge(game_id="G007")
    q_bad = _quote(game_id="G007", odds=None, book="BadBook")
    q_good = _quote(game_id="G007", odds=1.91, book="GoodBook")
    rows = join_quotes_to_edges([edge], [q_bad, q_good])
    assert len(rows) == 1
    assert rows[0].quote_book == "GoodBook"
    assert rows[0].quote_odds == pytest.approx(1.91)


# --------------------------------------------------------------------------- #
# (d) malformed edge key (missing game_id) is silently skipped
# --------------------------------------------------------------------------- #

def test_edge_missing_game_id_is_skipped():
    bad_edge = {"market_type": "moneyline", "side": "home", "model_prob": 0.5,
                "market_prob": 0.5, "ev": 0.0, "tier": None,
                "book": "X", "line": None, "clv_is_proxy": False}
    good_edge = _edge(game_id="G008")
    q = _quote(game_id="G008")
    rows = join_quotes_to_edges([bad_edge, good_edge], [q])
    # bad_edge skipped; good_edge joins
    assert len(rows) == 1
    assert rows[0].game_id == "G008"


def test_edge_with_empty_game_id_is_skipped():
    bad_edge = _edge(game_id="")
    q = _quote(game_id="")
    rows = join_quotes_to_edges([bad_edge], [q])
    assert rows == []
