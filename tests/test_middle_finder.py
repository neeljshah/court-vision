"""Tests for scripts/middle_finder_daemon.py — middle detection, juice filter,
model-confirmed flag, atomic write."""
from __future__ import annotations

import json
import os
import sys
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

import middle_finder_daemon as mfd


def _idx_from_rows(rows):
    """Helper: rows = list of (book, player, stat, line, over_price, under_price)."""
    index = {}
    for book, player, stat, line, op, up in rows:
        pkey = (player, stat)
        bdict = index.setdefault(pkey, {})
        blist = bdict.setdefault(book, [])
        blist.append({"line": line, "over_price": op, "under_price": up})
    return index


def test_middle_detection_basic():
    """Classic 1-wide middle: FD OVER 28.5 / BOV UNDER 29.5."""
    rows = [
        ("fd",  "LeBron James", "pts", 28.5, -110, -110),
        ("bov", "LeBron James", "pts", 29.5, -110, -110),
    ]
    middles = mfd.find_middles(_idx_from_rows(rows),
                                min_width=0.5, max_juice_each_side=-135)
    # We should find at least the FD-OVER / BOV-UNDER middle of width 1.0.
    found = [m for m in middles
             if m["over_book"] == "fd" and m["under_book"] == "bov"
             and m["middle_width"] == 1.0]
    assert len(found) == 1, f"expected one 1-wide middle, got {middles}"
    m = found[0]
    assert m["over_line"] == 28.5 and m["under_line"] == 29.5
    assert m["over_price"] == -110 and m["under_price"] == -110
    assert m["free_arb"] is False
    # No same-book pairings.
    assert all(x["over_book"] != x["under_book"] for x in middles)


def test_juice_filter_excludes_heavy_juice():
    """A middle where one leg is -160 must be filtered out at -135 cap.

    Setup: fd offers OVER 4.5 @ -160 (heavy juice on the OVER) and
    bov offers UNDER 5.5 @ -105. Pair forms a 1-wide middle but the OVER
    leg is -160 -> dropped at the -135 cap, kept at the -200 cap.
    """
    rows = [
        ("fd",  "Stephen Curry", "fg3m", 4.5, -160, +130),
        ("bov", "Stephen Curry", "fg3m", 5.5, -110, -105),
    ]
    idx = _idx_from_rows(rows)
    middles_loose = mfd.find_middles(idx, min_width=0.5,
                                       max_juice_each_side=-200)
    middles_strict = mfd.find_middles(idx, min_width=0.5,
                                        max_juice_each_side=-135)
    # the (fd OVER 4.5 @ -160) leg should appear in loose, vanish in strict
    has_neg160_loose = any(m["over_price"] == -160 for m in middles_loose)
    has_neg160_strict = any(m["over_price"] == -160 for m in middles_strict)
    assert has_neg160_loose, ("loose juice cap (-200) should keep the -160 "
                                f"leg; got {middles_loose}")
    assert not has_neg160_strict, ("strict juice cap (-135) should drop the "
                                     f"-160 leg; got {middles_strict}")


def test_free_arb_flagged():
    """Both sides positive American odds => free arb (guaranteed +EV)."""
    rows = [
        ("fd",  "Anthony Edwards", "reb", 5.5, +105, -130),
        ("bov", "Anthony Edwards", "reb", 6.5, -120, +110),
    ]
    middles = mfd.find_middles(_idx_from_rows(rows),
                                min_width=0.5, max_juice_each_side=-135)
    # OVER 5.5 @ fd (+105) / UNDER 6.5 @ bov (+110): both positive -> free arb
    free = [m for m in middles if m["free_arb"]]
    assert len(free) >= 1, f"expected at least one free arb, got {middles}"
    m = next(x for x in free
              if x["over_price"] == 105 and x["under_price"] == 110)
    assert m["arb_profit_pct"] is not None and m["arb_profit_pct"] > 0
    # Free arbs should sort first.
    assert middles[0]["free_arb"] is True


def test_model_confirmed_flag():
    """Inject a stub predictor that returns a q-int centered inside the band;
    expect model_confirmed=True. Move the band out of range -> False."""
    middles = [
        {"player": "Test Player", "stat": "pts",
         "over_book": "fd", "over_line": 20.0, "over_price": -110,
         "under_book": "bov", "under_line": 24.0, "under_price": -110,
         "middle_width": 4.0, "worst_price": -110, "free_arb": False,
         "arb_profit_pct": None},
        {"player": "Test Player", "stat": "pts",
         "over_book": "fd", "over_line": 40.0, "over_price": -110,
         "under_book": "bov", "under_line": 44.0, "under_price": -110,
         "middle_width": 4.0, "worst_price": -110, "free_arb": False,
         "arb_profit_pct": None},
    ]

    def stub_predictor(player, stat):
        # q50 = 22 (inside [20,24]); q10/q90 give sigma ~ 1.56
        return {"q10": 20.0, "q50": 22.0, "q90": 24.0}

    # Monkeypatch the quantile calibrator to a passthrough.
    orig_apply = mfd.apply_quantile_calibration
    mfd.apply_quantile_calibration = lambda stat, q10, q50, q90: (q10, q90)
    try:
        out = mfd.annotate_model_confirmed(middles, stub_predictor,
                                             min_band_prob=0.10)
    finally:
        mfd.apply_quantile_calibration = orig_apply

    # The first middle straddles the q50 -> high band prob -> confirmed.
    assert out[0]["model_confirmed"] is True, out[0]
    assert out[0]["model_band_prob"] >= 0.50
    # The second middle is 20pts above q50 -> band prob ~ 0 -> NOT confirmed.
    assert out[1]["model_confirmed"] is False, out[1]
    assert out[1]["model_band_prob"] < 0.01


def test_atomic_write_round_trip():
    """atomic_write_json must produce valid JSON and replace any prior file."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "sub", "middles.json")
        payload = {"generated_at": "now", "n_middles": 2,
                   "middles": [{"player": "X", "middle_width": 1.0}]}
        mfd.atomic_write_json(path, payload)
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        assert got["n_middles"] == 2
        # Overwrite with a new payload.
        payload2 = {"generated_at": "later", "n_middles": 0, "middles": []}
        mfd.atomic_write_json(path, payload2)
        with open(path, encoding="utf-8") as f:
            got2 = json.load(f)
        assert got2["n_middles"] == 0
        assert got2["generated_at"] == "later"
        # No stray .tmp files left behind.
        leftovers = [f for f in os.listdir(os.path.dirname(path))
                     if f.startswith("middles.json.tmp")]
        assert leftovers == [], f"tmp leftovers: {leftovers}"


def test_min_width_filter():
    """Bonus: width=0.5 keeps; raising min-width to 1.0 drops it."""
    rows = [
        ("fd",  "Jayson Tatum", "ast", 5.5, -110, -110),
        ("bov", "Jayson Tatum", "ast", 6.0, -110, -110),
    ]
    idx = _idx_from_rows(rows)
    keep = mfd.find_middles(idx, min_width=0.5, max_juice_each_side=-135)
    drop = mfd.find_middles(idx, min_width=1.0, max_juice_each_side=-135)
    assert any(m["middle_width"] == 0.5 for m in keep)
    assert not any(m["middle_width"] == 0.5 for m in drop)


if __name__ == "__main__":
    test_middle_detection_basic()
    test_juice_filter_excludes_heavy_juice()
    test_free_arb_flagged()
    test_model_confirmed_flag()
    test_atomic_write_round_trip()
    test_min_width_filter()
    print("OK")
