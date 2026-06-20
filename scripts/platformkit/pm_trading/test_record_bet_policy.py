"""Per-file tests for scripts.platformkit.pm_trading.record_bet_policy (PT-1).

Run ONLY this file (the full suite freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_record_bet_policy.py -q

Acceptance criteria (PT-1):
  * policy_stamp row carries tier + flat_unit + quarter_kelly.
  * stamped bet_id matches the open row's bet_id.
  * UNITS only -- no $ / pnl key anywhere on the stamp.
  * tier=None when EV is below the C floor.
  * flat_unit=0.0 when tier=None.
  * quarter_kelly=0.0 when model_prob / taken_decimal are absent.
  * Original open row is never mutated by the stamp operation.
  * load_policy_stamps can round-trip the stamp back from the ledger.
  * Raises ValueError when open_row lacks bet_id or has wrong status.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.platformkit import clv_ledger as L
from scripts.platformkit.pm_trading.record_bet_policy import (
    load_policy_stamps,
    stamp_policy,
)
from scripts.platformkit.pm_trading.policy import EV_FLOOR_C


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _open_row(tmp_path: Path, *, sport: str = "nba",
              matchup: str = "BOS@NYK", side: str = "home",
              price: float = 1.95, prob: float = 0.60) -> Dict[str, Any]:
    """Place a paper open row in a temp ledger and return the record."""
    lpath = tmp_path / "ledger.jsonl"
    return L.record_bet(sport, matchup, side, "paper_book", price,
                        model_prob=prob, path=lpath)


# ---------------------------------------------------------------------------
# core acceptance: stamp carries the 3 required fields + correct bet_id
# ---------------------------------------------------------------------------

def test_stamp_carries_tier_flat_unit_quarter_kelly(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    ev = 0.10  # above A floor (0.08) -> tier "A"
    stamp = stamp_policy(row, ev=ev, model_prob=0.60, taken_decimal=1.95, path=lpath)

    assert stamp["tier"] == "A", "tier must be A for ev=0.10"
    assert "flat_unit" in stamp, "flat_unit must be present"
    assert "quarter_kelly" in stamp, "quarter_kelly must be present"
    assert stamp["flat_unit"] == 1.0, "flat_unit should be 1.0 for a tiered bet"
    assert stamp["quarter_kelly"] >= 0.0, "quarter_kelly must be non-negative"


def test_stamped_bet_id_matches_open_row(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    stamp = stamp_policy(row, ev=0.06, model_prob=0.60, taken_decimal=1.95,
                         path=lpath)

    assert stamp["bet_id"] == row["bet_id"], \
        "stamped bet_id must equal the open row's bet_id"


# ---------------------------------------------------------------------------
# UNITS only -- no $ / pnl key on the stamp
# ---------------------------------------------------------------------------

def test_no_dollar_field_on_stamp(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    stamp = stamp_policy(row, ev=0.05, model_prob=0.60, taken_decimal=1.95,
                         path=lpath)

    forbidden = {"dollar", "pnl", "profit", "loss", "bankroll_pct", "roi"}
    for key in stamp:
        assert key.lower() not in forbidden, \
            "policy_stamp must carry UNITS only, got forbidden key %r" % key


# ---------------------------------------------------------------------------
# tier=None when EV is below the C floor
# ---------------------------------------------------------------------------

def test_no_tier_when_ev_below_c_floor(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    ev_below = EV_FLOOR_C - 0.005  # definitely below floor
    stamp = stamp_policy(row, ev=ev_below, model_prob=0.60, taken_decimal=1.95,
                         path=lpath)

    assert stamp["tier"] is None, "tier must be None when EV is below C floor"
    assert stamp["flat_unit"] == 0.0, "flat_unit must be 0.0 when tier is None"
    assert stamp["quarter_kelly"] == 0.0, "quarter_kelly must be 0.0 when tier is None"


# ---------------------------------------------------------------------------
# tier B / tier C tiering
# ---------------------------------------------------------------------------

def test_tier_b_and_c_thresholds(tmp_path):
    from scripts.platformkit.pm_trading.policy import EV_FLOOR_B, EV_FLOOR_A
    lpath = tmp_path / "ledger.jsonl"

    row_b = L.record_bet("nba", "LAL@DEN", "home", "pb", 2.0, path=lpath)
    # EV exactly at B floor + 0.001 -> tier B (not A)
    ev_b = EV_FLOOR_B + 0.001
    assert ev_b < EV_FLOOR_A, "sanity: ev_b should be below A floor"
    stamp_b = stamp_policy(row_b, ev=ev_b, path=lpath)
    assert stamp_b["tier"] == "B"

    row_c = L.record_bet("nba", "GSW@MEM", "away", "pb", 2.0, path=lpath)
    ev_c = EV_FLOOR_C + 0.001
    assert ev_c < EV_FLOOR_B, "sanity: ev_c should be below B floor"
    stamp_c = stamp_policy(row_c, ev=ev_c, path=lpath)
    assert stamp_c["tier"] == "C"


# ---------------------------------------------------------------------------
# quarter_kelly is 0.0 when model_prob / taken_decimal are absent
# ---------------------------------------------------------------------------

def test_quarter_kelly_zero_without_prob_or_price(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    stamp = stamp_policy(row, ev=0.09, path=lpath)  # no model_prob, no taken_decimal
    assert stamp["quarter_kelly"] == 0.0, \
        "quarter_kelly must be 0.0 when model_prob/taken_decimal are absent"
    assert stamp["flat_unit"] == 1.0, "flat_unit still 1.0 when tiered"


# ---------------------------------------------------------------------------
# original open row must NOT be mutated
# ---------------------------------------------------------------------------

def test_original_open_row_not_mutated(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    before = dict(row)  # shallow copy of original

    stamp_policy(row, ev=0.09, model_prob=0.60, taken_decimal=1.95, path=lpath)

    assert row == before, "stamp_policy must not mutate the open_row in-place"


# ---------------------------------------------------------------------------
# round-trip: load_policy_stamps returns the stamp from the ledger file
# ---------------------------------------------------------------------------

def test_load_policy_stamps_round_trip(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    ev = 0.07  # tier B
    stamp = stamp_policy(row, ev=ev, model_prob=0.60, taken_decimal=1.95,
                         path=lpath)

    stamps = load_policy_stamps(row["bet_id"], path=lpath)
    assert len(stamps) == 1, "exactly one stamp row expected"
    assert stamps[0]["tier"] == stamp["tier"]
    assert stamps[0]["flat_unit"] == stamp["flat_unit"]
    assert stamps[0]["quarter_kelly"] == stamp["quarter_kelly"]
    assert stamps[0]["bet_id"] == row["bet_id"]


def test_load_policy_stamps_no_match_returns_empty(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    stamp_policy(row, ev=0.05, path=lpath)

    stamps = load_policy_stamps("nonexistent_bet_id", path=lpath)
    assert stamps == [], "no stamps for an unknown bet_id"


# ---------------------------------------------------------------------------
# error guards
# ---------------------------------------------------------------------------

def test_raises_when_no_bet_id(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    bad_row: Dict[str, Any] = {"status": "open", "matchup": "A@B"}
    with pytest.raises(ValueError, match="bet_id"):
        stamp_policy(bad_row, ev=0.05, path=lpath)


def test_raises_when_status_not_open(tmp_path):
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)
    settled_row = dict(row)
    settled_row["status"] = "settled"
    with pytest.raises(ValueError, match="open row"):
        stamp_policy(settled_row, ev=0.05, path=lpath)


# ---------------------------------------------------------------------------
# clv_is_proxy raises EV floor so C-floor bet no longer passes
# ---------------------------------------------------------------------------

def test_clv_is_proxy_tightens_floor(tmp_path):
    from scripts.platformkit.pm_trading.policy import EV_PROXY_PENALTY
    lpath = tmp_path / "ledger.jsonl"
    row = _open_row(tmp_path)

    # EV just above C floor but below C+penalty
    ev_just_above_c = EV_FLOOR_C + 0.001
    assert ev_just_above_c < EV_FLOOR_C + EV_PROXY_PENALTY

    stamp = stamp_policy(row, ev=ev_just_above_c, clv_is_proxy=True, path=lpath)
    assert stamp["tier"] is None, \
        "proxy penalty should push this EV below the raised C floor"
    assert stamp["clv_is_proxy"] is True
