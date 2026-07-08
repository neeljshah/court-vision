"""Per-file tests for fill_sim (synthetic book fixtures only -- no live data).

  python -m pytest scripts/platformkit/pm_trading/test_fill_sim.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.pm_trading import fill_sim as F

NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)


def _book(ts=None, yes_bids=None, no_bids=None, ticker="KXMLBGAME-26JUL07MILSTL-STL"):
    return {
        "ts": (ts or NOW).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": "mlb", "ticker": ticker,
        "event_ticker": "KXMLBGAME-26JUL07MILSTL",
        # ladders ASC by price, like depth_capture writes them
        "yes_bids": yes_bids if yes_bids is not None else [[0.50, 10.0], [0.54, 20.0]],
        "yes_asks": no_bids if no_bids is not None else [[0.40, 50.0], [0.45, 100.0]],
    }


def test_vwap_walk_two_levels():
    # buy YES 150: best NO bid 0.45 -> YES@0.55 x100, then 0.40 -> YES@0.60 x50
    res = F.fill_price("yes", 150, _book(), now=NOW)
    assert res is not None
    assert res["fill_prob"] == pytest.approx((0.55 * 100 + 0.60 * 50) / 150, abs=1e-6)
    assert res["n_filled"] == 150
    # mid_yes = (0.54 + 0.55)/2 = 0.545
    assert res["slippage_prob"] == pytest.approx(res["fill_prob"] - 0.545, abs=1e-6)
    assert res["book_age_sec"] == 0.0


def test_no_side_crosses_yes_bids():
    res = F.fill_price("no", 10, _book(), now=NOW)
    assert res is not None
    assert res["fill_prob"] == pytest.approx(1.0 - 0.54, abs=1e-6)  # best yes bid
    assert res["slippage_prob"] == pytest.approx(0.46 - (1.0 - 0.545), abs=1e-6)


def test_partial_fill_when_depth_short():
    res = F.fill_price("yes", 200, _book(), now=NOW)
    assert res is not None
    assert res["n_filled"] == 150  # total NO-bid depth
    assert res["fill_prob"] == pytest.approx((0.55 * 100 + 0.60 * 50) / 150, abs=1e-6)


def test_stale_book_returns_none():
    old = _book(ts=NOW - timedelta(seconds=999))
    assert F.fill_price("yes", 10, old, now=NOW, max_age_sec=120) is None
    # generous bar -> same book prices fine
    assert F.fill_price("yes", 10, old, now=NOW, max_age_sec=1500) is not None


def test_missing_or_empty_book_fails_closed():
    assert F.fill_price("yes", 10, None, now=NOW) is None
    assert F.fill_price("yes", 10, _book(no_bids=[]), now=NOW) is None
    assert F.fill_price("no", 10, _book(yes_bids=[]), now=NOW) is None
    assert F.fill_price("maybe", 10, _book(), now=NOW) is None
    assert F.fill_price("yes", 0, _book(), now=NOW) is None


def _depth_dir(tmp_path, rows):
    d = tmp_path / "mlb"
    d.mkdir(parents=True)
    with (d / "2026-07-07.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return tmp_path


def test_simulate_fill_book_quality(tmp_path):
    base = _depth_dir(tmp_path, [_book()])
    res = F.simulate_fill("KXMLBGAME-26JUL07MILSTL-STL", "yes", 1.0,
                          ts=NOW.isoformat(), base_dir=base)
    assert res["fill_quality"] == "book"
    assert res["n_filled"] == 100.0  # 1 unit * CONTRACTS_PER_UNIT
    assert res["fill_prob"] == pytest.approx(0.55, abs=1e-6)


def test_simulate_fill_no_book_stamping(tmp_path):
    base = _depth_dir(tmp_path, [_book()])
    res = F.simulate_fill("KXMLBGAME-UNKNOWN-XXX", "yes", 1.0,
                          ts=NOW.isoformat(), base_dir=base)
    assert res == {"fill_prob": None, "n_filled": 0.0, "slippage_prob": None,
                   "book_age_sec": None, "fill_quality": "no_book"}
    # book exists but stale -> no_book WITH the age reported
    stale = F.simulate_fill("KXMLBGAME-26JUL07MILSTL-STL", "yes", 1.0,
                            ts=(NOW + timedelta(seconds=99999)).isoformat(), base_dir=base)
    assert stale["fill_quality"] == "no_book"
    assert stale["book_age_sec"] == pytest.approx(99999.0, abs=1.0)
    assert F.simulate_fill("", "yes", 1.0, base_dir=base)["fill_quality"] == "no_book"


def test_freshest_book_picks_latest_row(tmp_path):
    older = _book(ts=NOW - timedelta(minutes=40))
    newer = _book(ts=NOW - timedelta(minutes=5))
    base = _depth_dir(tmp_path, [older, newer])
    row = F.freshest_book("KXMLBGAME-26JUL07MILSTL-STL", base_dir=base)
    assert row is not None and row["ts"] == newer["ts"]


def test_event_side_tickers(tmp_path):
    ev = "KXMLBGAME-26JUL07MILSTL"
    base = _depth_dir(tmp_path, [
        _book(ticker=ev + "-STL"), _book(ticker=ev + "-MIL")])
    out = F.event_side_tickers(ev, base_dir=base)
    assert out == {"home": ev + "-STL", "away": ev + "-MIL"}  # event ends with HOME code
    assert F.event_side_tickers("", base_dir=base) == {"home": None, "away": None}


def test_stamp_fill_never_raises():
    out = F.stamp_fill("T", "yes", 1.0, base_dir="not-a-real-dir")  # type: ignore[arg-type]
    assert out["fill_quality"] == "no_book"


def test_arb_leg_row_carries_fill_fields():
    from scripts.platformkit.pm_trading import run_cross_venue_arb as R
    arb = {"sport": "mlb", "home": "H", "away": "A", "locked_prob": 0.02,
           "leg_a": {"venue": "pinnacle", "side": "home", "decimal": 2.1,
                     "age_sec": 5.0, "game_id": "g1"},
           "leg_b": {"venue": "kalshi", "side": "away", "decimal": 2.2,
                     "age_sec": 5.0, "game_id": "g1"}}
    fake = {"fill_prob": 0.5, "n_filled": 100.0, "slippage_prob": 0.01,
            "book_age_sec": 3.0, "fill_quality": "book"}
    row = R._leg_row(arb, "leg_b", "leg_a", 1.0, fill_fn=lambda *a: fake)
    for k, v in fake.items():
        assert row[k] == v
    assert row["taken_decimal"] == 2.2 and row["executed"] is False  # unchanged
    # default fill_fn on a non-kalshi leg -> honest no_book stamp
    row2 = R._leg_row(arb, "leg_a", "leg_b", 1.0)
    assert row2["fill_quality"] == "no_book" and row2["fill_prob"] is None


def test_pm_ledger_row_carries_fill_fields(tmp_path, monkeypatch):
    from scripts.platformkit.pm_trading import pm_game_placer as P
    from scripts.platformkit.pm_trading import fill_sim as fs
    fresh = _book(ts=datetime.now(timezone.utc))  # fresh vs the placer's real now
    monkeypatch.setattr(fs, "DEFAULT_DEPTH_DIR", _depth_dir(tmp_path, [fresh]))
    p = {"venue": "kalshi", "game_id": "g1", "ticker": "KXMLBGAME-26JUL07MILSTL-STL",
         "side": "home", "team": "STL", "matchup": "H vs A", "sport": "mlb",
         "model_prob": 0.6, "market_prob": 0.55, "taken_decimal": 1.8182,
         "ev": 0.09, "tier": "B", "flat_unit": 1.0, "quarter_kelly": 0.2}
    row = P._ledger_row(p)
    assert row["fill_quality"] == "book"
    assert row["fill_prob"] == pytest.approx(0.55, abs=1e-6)
    assert row["taken_decimal"] == 1.8182 and row["bet_id"] == "pm|kalshi|g1|home"
