"""test_bet_db_strip.py -- Phase-7 honesty contract (TC).

CONTRACT UNDER TEST
-------------------
database/bet_db.py is the SQLite ledger. Its rows legitimately store
$-denominated bookkeeping columns (pnl, stake, roi_pct, total_pnl,
total_stake, bankroll, daily_pnl) -- a ledger may hold them internally.

But those columns must be STRIPPED before any of this data reaches API JSON
(units / probability only -- .claude/rules/no-edge-claims.md). This test
locks a shared scrubber that the API layer is REQUIRED to apply to every
bet_db row / summary it serves.

WHY A SCRUBBER HERE
-------------------
api/ is human-gated, so we cannot edit the endpoints. We instead define and
test the canonical strip function (BANNED_DB_KEYS + strip_money) that the API
PROPOSED fix must call. The test PROVES:
  1. bet_db genuinely emits money columns (so stripping is necessary), and
  2. after stripping, no banned key survives -- including nested rows.

PROPOSED FIX (for the human, in api/ wherever bet_db rows are serialised)
-------------------------------------------------------------------------
    from tests-mirrored helper or a shared util:  return strip_money(row)
    Apply strip_money() to BetDB.recent_bets / list_bets / daily_summary /
    daily_pnl_series outputs before they enter a JSON response.
"""
from __future__ import annotations

import pytest

bet_db = pytest.importorskip("database.bet_db")

# Ledger columns that may live in SQLite but must NOT reach API JSON.
BANNED_DB_KEYS = {
    "pnl", "stake", "roi_pct", "roi", "total_pnl", "total_stake",
    "bankroll", "daily_pnl", "daily_stake", "profit", "profit_loss",
    "open_stake",
}


def strip_money(obj):
    """Canonical scrubber the API layer must apply to every bet_db payload.

    Recursively drops any dict key in BANNED_DB_KEYS. Returns a new object.
    """
    if isinstance(obj, dict):
        return {
            k: strip_money(v)
            for k, v in obj.items()
            if not (isinstance(k, str) and k.lower() in BANNED_DB_KEYS)
        }
    if isinstance(obj, list):
        return [strip_money(v) for v in obj]
    return obj


def _banned_in(obj):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in BANNED_DB_KEYS:
                found.append(k)
            found.extend(_banned_in(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_banned_in(v))
    return found


@pytest.fixture
def db(tmp_path):
    return bet_db.BetDB(path=str(tmp_path / "test_ledger.db"))


# ---------------------------------------------------------------------------
# 1. The ledger really does emit money columns (strip is necessary).
# ---------------------------------------------------------------------------

def test_bet_row_contains_money_columns_before_strip(db):
    db.insert_bet({
        "player_name": "Test Player", "stat": "pts", "line": 22.5,
        "side": "over", "book": "dk", "odds": -110, "stake": 50.0,
        "pnl": 12.3,
    })
    rows = db.recent_bets(5)
    assert rows, "expected at least one row"
    leaked = _banned_in(rows)
    assert "stake" in leaked and "pnl" in leaked, (
        "bet_db row is expected to carry money columns internally; "
        f"got keys without them: {set(rows[0].keys())}"
    )


def test_daily_summary_contains_roi_pct_before_strip(db):
    db.insert_bet({
        "player_name": "P", "stat": "pts", "line": 1.0, "side": "over",
        "book": "dk", "odds": -110, "stake": 10.0,
    })
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = db.daily_summary(today)
    assert "roi_pct" in summary and "total_pnl" in summary, (
        f"daily_summary expected to carry roi_pct/total_pnl; got {summary}"
    )


# ---------------------------------------------------------------------------
# 2. After strip_money, NO banned key survives (the contract the API must meet).
# ---------------------------------------------------------------------------

def test_strip_removes_all_money_keys_from_bet_rows(db):
    db.insert_bet({
        "player_name": "Test Player", "stat": "pts", "line": 22.5,
        "side": "over", "book": "dk", "odds": -110, "stake": 50.0,
        "pnl": 12.3,
    })
    cleaned = strip_money(db.recent_bets(5))
    leaked = _banned_in(cleaned)
    assert not leaked, f"strip_money left money keys behind: {leaked}"
    # Sanity: non-money fields survive.
    assert cleaned[0]["player_name"] == "Test Player"
    assert cleaned[0]["stat"] == "pts"


def test_strip_removes_money_keys_from_daily_summary(db):
    db.insert_bet({
        "player_name": "P", "stat": "pts", "line": 1.0, "side": "over",
        "book": "dk", "odds": -110, "stake": 10.0,
    })
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cleaned = strip_money(db.daily_summary(today))
    leaked = _banned_in(cleaned)
    assert not leaked, f"strip_money left money keys in daily_summary: {leaked}"
    assert cleaned["n_bets"] >= 1  # count survives


def test_strip_handles_nested_and_lists():
    sample = {
        "rows": [{"stake": 1.0, "player_name": "x"}, {"pnl": 2.0, "stat": "reb"}],
        "summary": {"roi_pct": 5.0, "n_bets": 3},
    }
    cleaned = strip_money(sample)
    assert _banned_in(cleaned) == []
    assert cleaned["rows"][0]["player_name"] == "x"
    assert cleaned["summary"]["n_bets"] == 3
