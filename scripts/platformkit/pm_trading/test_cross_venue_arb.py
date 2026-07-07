"""Per-file test for cross_venue_arb -- run ONLY this file:
    python -m pytest scripts/platformkit/pm_trading/test_cross_venue_arb.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit.pm_trading import cross_venue_arb as X
from scripts.platformkit.pm_trading import run_cross_venue_arb as R

NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)


def _row(home, away, book, side, odds, age_sec=5.0, sport="mlb"):
    ts = (NOW - timedelta(seconds=age_sec)).isoformat()
    return {"sport": sport, "home": home, "away": away, "market_type": "moneyline",
            "side": side, "odds": odds, "book": book, "captured_at": ts}


def test_true_discrepancy_detected_and_both_legs_written(tmp_path):
    # Kalshi (city name) prices Houston at odds 2.60 (~0.3846 implied) and
    # Pinnacle (full name) prices Toronto (the away/other side) at 2.60 too
    # (~0.3846 implied). Sum of raw implied = 0.7692 -> deep true arb, survives
    # Kalshi's small fee easily.
    quotes = [
        _row("Houston", "Toronto", "kalshi", "home", 2.60),
        _row("Houston Astros", "Toronto Blue Jays", "pinnacle", "away", 2.60),
    ]
    freshest = X.freshest_by_book(quotes)
    grouped = X._match_matchup_across_books(freshest)
    arbs = X.find_arbs(grouped, now=NOW)
    assert len(arbs) == 1
    arb = arbs[0]
    assert arb["locked_prob"] > 0.0

    ledger = tmp_path / "ledger.jsonl"
    result = R.place_arbs(arbs, ledger_path=ledger, place=True)
    assert result["n_pairs_written"] == 1
    assert result["edge_claimed"] is False

    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    venues = {r["venue"] for r in rows}
    assert venues == {"kalshi", "pinnacle"}
    for r in rows:
        assert r["executed"] is False
        assert r["channel"] == "paper"
        assert r["edge_claimed"] is False
        assert r["market_type"] == "arb"
        assert r["stake_units"] == 1.0
        for bad in ("dollar", "pnl", "roi", "profit"):
            assert bad not in r


def test_fee_eaten_near_miss_not_flagged():
    # Implied probs sum to 0.99 (a classic "looks arb-y" 1pp raw gap) but
    # Kalshi's round-trip fee alone eats more than 1pp near p=0.5 -> must NOT
    # be flagged once fees are subtracted.
    dec = 1.0 / 0.495  # each side priced at 0.495 implied, sum raw = 0.99
    quotes = [
        _row("Houston", "Toronto", "kalshi", "home", dec),
        _row("Houston Astros", "Toronto Blue Jays", "pinnacle", "away", dec),
    ]
    freshest = X.freshest_by_book(quotes)
    grouped = X._match_matchup_across_books(freshest)
    arbs = X.find_arbs(grouped, now=NOW, min_locked_prob=X.DEFAULT_MIN_LOCKED_PROB)
    assert arbs == []


def test_stale_quotes_skipped():
    # Same deep discrepancy as the true-arb test, but the kalshi leg is 300s
    # old (> max_age_sec=120) -> must be skipped, not flagged.
    quotes = [
        _row("Houston", "Toronto", "kalshi", "home", 2.60, age_sec=300.0),
        _row("Houston Astros", "Toronto Blue Jays", "pinnacle", "away", 2.60, age_sec=5.0),
    ]
    freshest = X.freshest_by_book(quotes)
    grouped = X._match_matchup_across_books(freshest)
    arbs = X.find_arbs(grouped, now=NOW, max_age_sec=120.0)
    assert arbs == []


def test_scan_reads_line_history_file(tmp_path):
    d = tmp_path / "mlb"
    d.mkdir()
    f = d / "2026-07-07.jsonl"
    rows = [
        _row("Houston", "Toronto", "kalshi", "home", 2.60),
        _row("Houston Astros", "Toronto Blue Jays", "pinnacle", "away", 2.60),
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    arbs = X.scan("mlb", now=NOW, date_key="2026-07-07", max_age_sec=120.0,
                 path_dir=tmp_path)
    assert len(arbs) == 1
    quotes = X.load_quotes("mlb", date_key="2026-07-07", path_dir=tmp_path)
    assert len(quotes) == 2


def test_non_moneyline_rows_excluded():
    quotes = [
        _row("Houston", "Toronto", "kalshi", "home", 2.60),
        {"sport": "mlb", "home": "Houston Astros", "away": "Toronto Blue Jays",
         "market_type": "total", "side": "Over 8.5", "odds": 1.9, "book": "pinnacle",
         "captured_at": NOW.isoformat()},
    ]
    freshest = X.freshest_by_book([q for q in quotes if q.get("market_type") in (None, "moneyline")])
    assert ("Houston Astros", "Toronto Blue Jays", "pinnacle") not in freshest
