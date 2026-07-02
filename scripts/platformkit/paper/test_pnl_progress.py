"""Per-file tests for pnl_progress -- realized money + getting-better-at-winning view.

Offline: synthetic settled rows injected (no ledger, no network). Covers the binding
honesty rails: getting-better is ANCHORED ON CLV (a rising units curve without rising
CLV is variance, not a signal), off-market rows never poison the CLV trend, and small
windows degrade to INSUFFICIENT_DATA.

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_pnl_progress.py -q
"""
from __future__ import annotations

from scripts.platformkit.paper import pnl_progress as P


def _row(outcome, unit_result, clv_pct=None, side="home",
         taken=2.0, ch=2.0, ca=2.0):
    r = {"status": "settled", "outcome": outcome, "unit_result": unit_result,
         "side": side, "taken_decimal": taken,
         "closing_decimal_home": ch, "closing_decimal_away": ca, "sport": "mlb"}
    if clv_pct is not None:
        r["clv_pct"] = clv_pct
    return r


def test_empty_is_insufficient_not_fabricated():
    p = P.progress([])
    assert p["n_settled"] == 0
    assert p["net_units"] is None
    assert "INSUFFICIENT" in p["making_money"]
    assert "INSUFFICIENT" in p["getting_better"]
    assert p["edge_claimed"] is False and p["executed"] is False


def test_rising_clv_both_windows_is_getting_better():
    # earlier half: CLV -1.0; recent half: CLV +2.0 -- both windows have >= MIN_CLV rows
    # and >= MIN_DECIDED decided bets -> a real, CLV-anchored "GETTING BETTER".
    earlier = [_row("win" if i % 2 else "loss", 0.5 if i % 2 else -1.0, clv_pct=-1.0)
               for i in range(10)]
    recent = [_row("win" if i % 2 else "loss", 0.5 if i % 2 else -1.0, clv_pct=2.0)
              for i in range(10)]
    p = P.progress(earlier + recent)
    assert p["recent"]["mean_clv_pct"] == 2.0
    assert p["earlier"]["mean_clv_pct"] == -1.0
    assert p["getting_better"].startswith("GETTING BETTER")


def test_rising_units_without_clv_is_variance_not_signal():
    # Win-rate / units climb sharply recent-vs-earlier, but NO captured closes -> the
    # honest verdict is VARIANCE, never "getting better" (CLV-over-ROI discipline).
    earlier = [_row("loss", -1.0) for _ in range(10)]   # all losses, no clv
    recent = [_row("win", 1.0) for _ in range(10)]       # all wins, no clv
    p = P.progress(earlier + recent)
    assert p["recent"]["mean_clv_pct"] is None  # no trustworthy CLV
    gb = p["getting_better"]
    assert "VARIANCE" in gb and "GETTING BETTER" not in gb


def test_offmarket_row_does_not_poison_clv_trend():
    # A single off-market garbage row (taken 12.0 on a pick'em close -> +497% CLV) in the
    # recent window must be excluded, so it cannot manufacture a fake "GETTING BETTER".
    earlier = [_row("win" if i % 2 else "loss", 0.5 if i % 2 else -1.0, clv_pct=-1.0)
               for i in range(10)]
    recent = [_row("loss", -1.0, clv_pct=-1.0) for _ in range(9)]
    recent.append(_row("win", 11.0, clv_pct=497.0, side="away", taken=12.0,
                       ch=1.95, ca=1.95))  # off-market -> suspect
    p = P.progress(earlier + recent)
    assert p["n_clv_suspect_excluded"] >= 1
    # recent CLV is ~ -1.0 (the garbage +497 excluded), NOT positive -> not "getting better"
    assert p["recent"]["mean_clv_pct"] is not None and p["recent"]["mean_clv_pct"] < 0
    assert not p["getting_better"].startswith("GETTING BETTER")


def test_making_money_descriptive_and_units_only():
    rows = [_row("win", 1.0, clv_pct=1.0) for _ in range(12)]
    p = P.progress(rows)
    assert p["net_units"] == 12.0
    assert "YES" in p["making_money"]
    # UNITS ONLY: no banned $ field anywhere in the payload.
    banned = {"dollars", "usd", "roi", "pnl", "profit", "bankroll_usd"}
    txt = str(p).lower()
    assert not any(b in txt for b in banned)


def test_render_runs():
    rows = [_row("win", 1.0, clv_pct=1.0) for _ in range(12)]
    txt = P.render(P.progress(rows))
    assert "MAKING MONEY?" in txt and "GETTING BETTER?" in txt
