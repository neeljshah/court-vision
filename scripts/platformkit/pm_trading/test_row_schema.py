"""Per-file tests for row_schema.py (PT-2: canonical PM paper-ledger row).

Acceptance criteria (from BACKLOG.md PT-2):
  * Signal -> canonical_pm_row has is_pm=True, market_id set, venue present,
    units (not $).
  * Missing market_id -> REJECTED / UNAVAILABLE, not silent default.
  * Missing venue -> REJECTED / UNAVAILABLE.
  * No dollar/pnl key in any returned row.

Run: python -m pytest scripts/platformkit/pm_trading/test_row_schema.py -q
"""
from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import edge_signal as ES                  # noqa: E402
import row_schema as RS                   # noqa: E402
from venues.base import Side              # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sig(market_id: str = "KALSHI-NBA-2026-BOS-WIN",
         fair_prob: float = 0.62,
         market_price: float = 0.55) -> ES.Signal:
    return ES.build_signal(market_id, fair_prob=fair_prob,
                           market_price=market_price)


# ---------------------------------------------------------------------------
# Core acceptance tests (PT-2)
# ---------------------------------------------------------------------------

def test_happy_path_is_pm_true_and_fields_present():
    """Signal -> canonical_pm_row: is_pm=True, market_id set, venue present."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="kalshi", sport="nba",
                              matchup="BOS@NYK", stake_units=2.0)
    assert row["is_pm"] is True, "is_pm must be True"
    assert row["market_id"] == "KALSHI-NBA-2026-BOS-WIN", "market_id must be set"
    assert row["venue"] == "kalshi", "venue must be present"
    assert row["channel"] == RS.CHANNEL_PAPER, "channel must be 'paper'"
    assert row["executed"] is False, "executed must be False"
    assert row["status"] == RS.STATUS_OPEN, "status must be 'open'"


def test_stake_units_not_dollars():
    """stake_units carries units; no dollar/pnl key exists."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="polymarket", stake_units=3.5)
    assert "stake_units" in row, "stake_units must be present"
    assert row["stake_units"] == 3.5
    # The forbidden keys must NOT appear
    forbidden = {"dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
                 "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl"}
    found = forbidden & set(row.keys())
    assert not found, "dollar/pnl keys must not appear in row: %s" % found


def test_missing_market_id_returns_rejected_not_silent():
    """Signal with empty market_id -> REJECTED row, never a silent default."""
    sig = ES.build_signal("  ", fair_prob=0.6, market_price=0.5)  # blank id
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert row["status"] == RS.STATUS_REJECTED, \
        "empty market_id must produce REJECTED row"
    assert row["rejection_reason"] == "MISSING_MARKET_ID"
    # market_id in rejected row is UNAVAILABLE sentinel, not the blank string
    assert row["market_id"] == "UNAVAILABLE", \
        "rejected row market_id must be UNAVAILABLE"


def test_missing_venue_returns_rejected():
    """Missing venue -> REJECTED, reason=MISSING_VENUE."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue=None)
    assert row["status"] == RS.STATUS_REJECTED
    assert row["rejection_reason"] == "MISSING_VENUE"
    assert row["venue"] == "UNAVAILABLE"
    assert row["market_id"] == sig.market_id


def test_blank_venue_string_rejected():
    """Blank venue string is treated as missing."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="   ")
    assert row["status"] == RS.STATUS_REJECTED
    assert row["rejection_reason"] == "MISSING_VENUE"


def test_rejected_row_has_no_dollar_keys():
    """Even rejected rows must carry no dollar/pnl keys."""
    sig = ES.build_signal("", fair_prob=0.6, market_price=0.5)
    row = RS.canonical_pm_row(sig, venue="kalshi")
    forbidden = {"dollar", "pnl", "roi", "profit"}
    assert not (forbidden & set(row.keys())), \
        "rejected row must also have no dollar/pnl keys"


def test_rejected_row_is_not_valid():
    """is_valid_pm_row must return False for a REJECTED row."""
    sig = _sig(market_id="")
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert not RS.is_valid_pm_row(row)


# ---------------------------------------------------------------------------
# Additional field / correctness tests
# ---------------------------------------------------------------------------

def test_side_buy_on_positive_edge():
    """BUY side when fair_prob > market_price."""
    sig = _sig(fair_prob=0.65, market_price=0.55)
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert row["side"] == "BUY"


def test_side_sell_on_negative_edge():
    """SELL side when fair_prob < market_price."""
    sig = _sig(fair_prob=0.40, market_price=0.55)
    row = RS.canonical_pm_row(sig, venue="polymarket")
    assert row["side"] == "SELL"


def test_market_price_and_edge_carried():
    """market_price and edge are carried from Signal."""
    sig = _sig(fair_prob=0.62, market_price=0.55)
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert abs(row["market_price"] - 0.55) < 1e-9
    assert abs(row["edge"] - 0.07) < 1e-9
    assert abs(row["edge_bps"] - 700.0) < 1e-6


def test_optional_sport_matchup_included():
    """sport and matchup appear in the row when supplied."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="kalshi", sport="nba", matchup="BOS@NYK")
    assert row.get("sport") == "nba"
    assert row.get("matchup") == "BOS@NYK"


def test_optional_devig_prob_carried():
    """consensus_edge_bps present when Signal has devig_prob."""
    sig = ES.build_signal("M", fair_prob=0.62, market_price=0.55, devig_prob=0.58)
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert "devig_prob" in row
    assert "consensus_edge_bps" in row


def test_fair_prob_override():
    """fair_prob kwarg overrides signal.fair_prob in the row."""
    sig = _sig(fair_prob=0.60, market_price=0.55)
    row = RS.canonical_pm_row(sig, venue="kalshi", fair_prob=0.70)
    assert abs(row["fair_prob"] - 0.70) < 1e-9


def test_venue_lowercased():
    """venue is stored as lower-case for normalisation."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="Kalshi")
    assert row["venue"] == "kalshi"


def test_placed_at_present():
    """placed_at is an ISO timestamp string."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="paper")
    assert "placed_at" in row and "T" in row["placed_at"]


def test_is_valid_pm_row_happy():
    """is_valid_pm_row returns True for a well-formed row."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert RS.is_valid_pm_row(row)


def test_is_valid_pm_row_false_if_no_market_id():
    """is_valid_pm_row returns False when market_id empty."""
    row = RS.canonical_pm_row(_sig(), venue="kalshi")
    row["market_id"] = ""
    assert not RS.is_valid_pm_row(row)


def test_is_valid_pm_row_false_if_dollar_key_injected():
    """is_valid_pm_row returns False when a dollar key is injected."""
    sig = _sig()
    row = RS.canonical_pm_row(sig, venue="kalshi")
    row["pnl"] = 99.0
    assert not RS.is_valid_pm_row(row)


def test_rejected_row_executed_always_false():
    """Even REJECTED rows carry executed=False (never triggers real order)."""
    sig = _sig(market_id="")
    row = RS.canonical_pm_row(sig, venue="kalshi")
    assert row["executed"] is False


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print("PASS", fn.__name__)
            passed += 1
        except Exception as exc:
            print("FAIL", fn.__name__, "->", exc)
    print("%d/%d green" % (passed, len(fns)))
    if passed < len(fns):
        sys.exit(1)
