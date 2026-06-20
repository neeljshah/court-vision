"""Per-file tests for scripts.platformkit.pm_best_trades.

Acceptance criteria (PT-8):
  1. 10 synthetic rows -> ranked in divergence-descending order.
  2. grade_available=True only on settled rows with clv_status=true_close
     and non-null clv_pct and clv_is_proxy=False.
  3. pct_beat_close computed from real CLV (grade_available=True rows only).
  4. Proxy CLV -> clv_pct=0.0, grade_available=False (not fabricated).
  5. No $ / dollar / roi / profit / pnl field on any row.
  6. executed=False always.
  7. Empty ledger -> ok status, count=0, pct_beat_close=None.
  8. sport filter and top_n limit work correctly.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_pm_best_trades.py -q
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.pm_best_trades import best_trades

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FORBIDDEN_FIELDS = {"dollar", "roi", "profit", "pnl", "revenue", "bankroll"}


def _make_row(
    *,
    sport: str = "nba",
    matchup: str = "TeamA@TeamB",
    side: str = "home",
    taken_decimal: float = 2.0,
    model_prob: float = 0.55,
    status: str = "open",
    clv_pct: float | None = None,
    clv_status: str | None = None,
    clv_is_proxy: bool = False,
    beat_close: bool | None = None,
    outcome: str | None = None,
    tier: str | None = None,
    taken_book: str = "espn:DraftKings",
    stake: float = 1.0,
    bet_id: str | None = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_decimal": taken_decimal,
        "model_prob": model_prob,
        "stake": stake,
        "status": status,
        "executed": False,
        "taken_book": taken_book,
        "ts": "2026-06-01T10:00:00+00:00",
    }
    if tier is not None:
        row["tier"] = tier
    if status == "settled":
        row["settled_at"] = "2026-06-01T23:59:00+00:00"
        row["outcome"] = outcome or "win"
        row["clv_pct"] = clv_pct
        row["beat_close"] = beat_close
        row["clv_status"] = clv_status or "no_close"
        row["clv_is_proxy"] = clv_is_proxy
        row["graded"] = True
    if bet_id is not None:
        row["bet_id"] = bet_id
    return row


def _write_ledger(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _no_dollar_fields(row: Dict[str, Any]) -> None:
    """Assert no forbidden $ / dollar / roi / pnl fields exist."""
    for key in row:
        assert key.lower() not in _FORBIDDEN_FIELDS, (
            f"Forbidden field '{key}' found in row"
        )


# ---------------------------------------------------------------------------
# 1. Ranked order by divergence descending (10 rows)
# ---------------------------------------------------------------------------

def test_ranked_order_10_rows(tmp_path):
    """10 rows -> output ranked divergence-descending (model_prob - market_implied)."""
    rows = [
        _make_row(model_prob=0.70, taken_decimal=2.0, bet_id="high"),   # div=0.20
        _make_row(model_prob=0.60, taken_decimal=2.0, bet_id="mid"),    # div=0.10
        _make_row(model_prob=0.55, taken_decimal=2.0, bet_id="low"),    # div=0.05
        _make_row(model_prob=0.52, taken_decimal=2.0, bet_id="tiny"),   # div=0.02
        _make_row(model_prob=0.50, taken_decimal=2.0, bet_id="zero"),   # div=0.00
        _make_row(model_prob=0.48, taken_decimal=2.0, bet_id="neg1"),   # div=-0.02
        _make_row(model_prob=0.45, taken_decimal=2.0, bet_id="neg2"),   # div=-0.05
        _make_row(model_prob=0.40, taken_decimal=2.0, bet_id="neg3"),   # div=-0.10
        _make_row(model_prob=0.35, taken_decimal=2.0, bet_id="neg4"),   # div=-0.15
        _make_row(model_prob=0.30, taken_decimal=2.0, bet_id="neg5"),   # div=-0.20
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=10)

    assert result["status"] == "ok"
    assert result["count"] == 10

    divs = [r["divergence"] for r in result["trades"]]
    # Must be non-increasing
    for i in range(len(divs) - 1):
        assert divs[i] >= divs[i + 1], (
            f"Divergence not sorted at position {i}: {divs[i]} < {divs[i+1]}"
        )

    # Best trade should be model_prob=0.70
    assert result["trades"][0]["model_prob"] == pytest.approx(0.70, abs=1e-6)
    assert result["trades"][0]["divergence"] == pytest.approx(0.20, abs=1e-4)


# ---------------------------------------------------------------------------
# 2. grade_available=True only on settled true-close rows
# ---------------------------------------------------------------------------

def test_grade_available_only_on_true_close(tmp_path):
    """grade_available=True only for settled + clv_status=true_close + not proxy."""
    rows = [
        _make_row(status="open", bet_id="open1"),                      # open -> False
        _make_row(status="settled", clv_status="no_close", bet_id="no_close"),  # -> False
        _make_row(status="settled", clv_status="proxy", clv_pct=1.5,
                  clv_is_proxy=True, beat_close=True, bet_id="proxy"),  # proxy -> False
        _make_row(status="settled", clv_status="true_close", clv_pct=2.3,
                  clv_is_proxy=False, beat_close=True, bet_id="true"),  # -> True
        _make_row(status="settled", clv_status="true_close", clv_pct=-1.1,
                  clv_is_proxy=False, beat_close=False, bet_id="true2"), # -> True
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=10)
    assert result["status"] == "ok"

    by_id = {r["bet_id"]: r for r in result["trades"] if r.get("bet_id")}

    assert by_id["open1"]["grade_available"] is False
    assert by_id["no_close"]["grade_available"] is False
    assert by_id["proxy"]["grade_available"] is False
    assert by_id["true"]["grade_available"] is True
    assert by_id["true2"]["grade_available"] is True

    # grade_available_n should be 2
    assert result["grade_available_n"] == 2


# ---------------------------------------------------------------------------
# 3. pct_beat_close computed from real CLV rows only
# ---------------------------------------------------------------------------

def test_pct_beat_close_from_real_clv(tmp_path):
    """pct_beat_close = 100 * beat_close True / grade_available count."""
    rows = [
        _make_row(status="settled", clv_status="true_close",
                  clv_pct=3.0, beat_close=True, bet_id="b1"),
        _make_row(status="settled", clv_status="true_close",
                  clv_pct=-1.0, beat_close=False, bet_id="b2"),
        _make_row(status="settled", clv_status="true_close",
                  clv_pct=2.5, beat_close=True, bet_id="b3"),
        _make_row(status="settled", clv_status="no_close",
                  clv_pct=None, bet_id="b4"),  # no_close -> excluded
        _make_row(status="open", bet_id="b5"),  # open -> excluded
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=10)
    # 3 grade_available; 2 beat_close True -> 66.6667%
    assert result["pct_beat_close"] == pytest.approx(66.6667, abs=0.01)
    assert result["grade_available_n"] == 3


# ---------------------------------------------------------------------------
# 4. Proxy CLV -> clv_pct=0.0, grade_available=False
# ---------------------------------------------------------------------------

def test_proxy_clv_zero_not_fabricated(tmp_path):
    """Proxy CLV rows: clv_pct=0.0 (honest zero), grade_available=False."""
    rows = [
        _make_row(status="settled", clv_status="proxy",
                  clv_pct=5.0, clv_is_proxy=True, beat_close=True, bet_id="px"),
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=10)
    assert result["count"] == 1
    row = result["trades"][0]

    assert row["grade_available"] is False, "Proxy row must not be grade_available"
    assert row["clv_pct"] == pytest.approx(0.0), "Proxy CLV must be 0.0 (not the raw 5.0)"
    assert row["clv_is_proxy"] is True
    # beat_close must be None (not leaked from proxy)
    assert row["beat_close"] is None

    # pct_beat_close must be None (no true-close rows)
    assert result["pct_beat_close"] is None


# ---------------------------------------------------------------------------
# 5. No forbidden $ / pnl / dollar fields
# ---------------------------------------------------------------------------

def test_no_dollar_or_pnl_fields(tmp_path):
    """No row must contain a dollar / roi / pnl / profit field."""
    rows = [
        _make_row(model_prob=0.60, taken_decimal=1.8, bet_id=f"r{i}")
        for i in range(5)
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=10)
    for row in result["trades"]:
        _no_dollar_fields(row)
    # Also check top-level keys
    for key in result:
        assert key.lower() not in _FORBIDDEN_FIELDS, f"Forbidden top-level key: {key}"


# ---------------------------------------------------------------------------
# 6. executed=False always
# ---------------------------------------------------------------------------

def test_executed_always_false(tmp_path):
    """executed must be False on every returned row."""
    rows = [
        _make_row(bet_id=f"x{i}", model_prob=0.5 + i * 0.01)
        for i in range(5)
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=10)
    for row in result["trades"]:
        assert row["executed"] is False


# ---------------------------------------------------------------------------
# 7. Empty ledger -> ok, count=0, pct_beat_close=None
# ---------------------------------------------------------------------------

def test_empty_ledger(tmp_path):
    """Empty ledger returns ok status with no trades and None pct_beat_close."""
    p = tmp_path / "empty.jsonl"
    p.write_text("", encoding="utf-8")

    result = best_trades(p, top_n=10)

    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["trades"] == []
    assert result["pct_beat_close"] is None
    assert result["grade_available_n"] == 0


# ---------------------------------------------------------------------------
# 8. sport filter and top_n limit
# ---------------------------------------------------------------------------

def test_sport_filter(tmp_path):
    """sport filter returns only rows matching that sport."""
    rows = [
        _make_row(sport="nba", bet_id="nba1", model_prob=0.60),
        _make_row(sport="nba", bet_id="nba2", model_prob=0.55),
        _make_row(sport="mlb", bet_id="mlb1", model_prob=0.70),
        _make_row(sport="mlb", bet_id="mlb2", model_prob=0.65),
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, sport="nba", top_n=10)
    sports = {r["sport"] for r in result["trades"]}
    assert sports == {"nba"}, f"Expected only nba, got {sports}"
    assert result["count"] == 2


def test_top_n_limit(tmp_path):
    """top_n limits the returned rows."""
    rows = [
        _make_row(bet_id=f"t{i}", model_prob=0.5 + i * 0.01)
        for i in range(15)
    ]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=5)
    assert result["count"] == 5
    assert len(result["trades"]) == 5


# ---------------------------------------------------------------------------
# 9. Divergence calculation accuracy
# ---------------------------------------------------------------------------

def test_divergence_calculation(tmp_path):
    """Divergence = model_prob - 1/taken_decimal, to 6 decimal places."""
    # model_prob=0.60, taken_decimal=2.5 -> market_implied=0.4, div=0.20
    rows = [_make_row(model_prob=0.60, taken_decimal=2.5, bet_id="d1")]
    p = tmp_path / "clv_ledger.jsonl"
    _write_ledger(rows, p)

    result = best_trades(p, top_n=1)
    trade = result["trades"][0]
    assert trade["divergence"] == pytest.approx(0.20, abs=1e-5)
    assert trade["market_implied_prob"] == pytest.approx(0.40, abs=1e-5)


# ---------------------------------------------------------------------------
# 10. Integration: real live ledger (smoke test, no asserts on counts)
# ---------------------------------------------------------------------------

def test_live_ledger_smoke():
    """Smoke test against the real local ledger if it exists; skip if absent."""
    default_p = (
        Path(__file__).resolve().parents[2]
        / "data" / "frontend" / "clv_ledger.jsonl"
    )
    if not default_p.exists():
        pytest.skip("Live ledger not present; skipping smoke test")

    result = best_trades(top_n=10)

    assert result["status"] == "ok"
    assert "trades" in result
    assert "pct_beat_close" in result
    assert "grade_available_n" in result
    assert "honest_note" in result
    assert "clv_summary" in result
    # No forbidden fields on any trade
    for row in result["trades"]:
        _no_dollar_fields(row)
        assert row["executed"] is False
