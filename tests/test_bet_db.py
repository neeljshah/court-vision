"""tests/test_bet_db.py — Unit tests for database.bet_db (BetDB).

Uses a temporary SQLite file per test so nothing touches the real DB.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Ensure project root is importable.
import sys
_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from database.bet_db import BetDB  # noqa: E402


# ── fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Fresh BetDB backed by a temp file."""
    return BetDB(path=str(tmp_path / "test_cv.db"))


def _sample_bet(**overrides):
    base = {
        "date":        "2026-05-27",
        "player_name": "LeBron James",
        "stat":        "pts",
        "line":        26.5,
        "side":        "over",
        "book":        "dk",
        "odds":        -110,
        "stake":       50.0,
        "kelly_size":  0.05,
        "model_ev_pct": 0.06,
        "model_p_hit":  0.55,
        "status":      "pending",
        "source":      "test",
    }
    base.update(overrides)
    return base


# ── insert ───────────────────────────────────────────────────────────────────────

class TestInsert:
    def test_insert_returns_bet_id(self, db):
        bet_id = db.insert_bet(_sample_bet())
        assert isinstance(bet_id, str) and len(bet_id) > 0

    def test_inserted_bet_retrievable(self, db):
        bet_id = db.insert_bet(_sample_bet(player_name="Jayson Tatum"))
        row = db.get_bet(bet_id)
        assert row is not None
        assert row["player_name"] == "Jayson Tatum"

    def test_insert_auto_generates_uuid(self, db):
        b1 = db.insert_bet(_sample_bet())
        b2 = db.insert_bet(_sample_bet())
        assert b1 != b2

    def test_insert_explicit_bet_id(self, db):
        uid = str(uuid.uuid4())
        returned = db.insert_bet(_sample_bet(bet_id=uid))
        assert returned == uid
        assert db.get_bet(uid) is not None

    def test_insert_idempotent(self, db):
        """INSERT OR IGNORE: second call with same bet_id must not raise."""
        uid = str(uuid.uuid4())
        db.insert_bet(_sample_bet(bet_id=uid))
        db.insert_bet(_sample_bet(bet_id=uid, stake=999.0))  # should be ignored
        row = db.get_bet(uid)
        assert row["stake"] == 50.0  # original value preserved


# ── settle ────────────────────────────────────────────────────────────────────

class TestSettle:
    def test_settle_updates_status(self, db):
        bid = db.insert_bet(_sample_bet())
        db.settle_bet(bid, status="won", actual_stat=28.0, pnl=45.45)
        row = db.get_bet(bid)
        assert row["status"] == "won"
        assert row["actual_stat"] == 28.0
        assert abs(row["pnl"] - 45.45) < 0.01

    def test_settle_sets_settled_at(self, db):
        bid = db.insert_bet(_sample_bet())
        db.settle_bet(bid, status="lost", actual_stat=22.0, pnl=-50.0)
        row = db.get_bet(bid)
        assert row["settled_at"] is not None

    def test_settle_clv_fields(self, db):
        bid = db.insert_bet(_sample_bet())
        db.settle_bet(bid, status="won", actual_stat=30.0, pnl=45.45,
                      clv_bps=12, closing_line=26.0, closing_odds=-112)
        row = db.get_bet(bid)
        assert row["clv_bps"] == 12
        assert row["closing_line"] == 26.0
        assert row["closing_odds"] == -112

    def test_settle_push_zero_pnl(self, db):
        bid = db.insert_bet(_sample_bet())
        db.settle_bet(bid, status="push", actual_stat=26.5, pnl=0.0)
        assert db.get_bet(bid)["status"] == "push"

    def test_settle_voided(self, db):
        bid = db.insert_bet(_sample_bet())
        db.settle_bet(bid, status="voided", actual_stat=None, pnl=0.0)
        assert db.get_bet(bid)["status"] == "voided"


# ── list_bets ─────────────────────────────────────────────────────────────────

class TestListFilters:
    def _insert_many(self, db):
        ids = []
        ids.append(db.insert_bet(_sample_bet(date="2026-05-25", player_name="LeBron James",
                                              stat="pts", status="won")))
        ids.append(db.insert_bet(_sample_bet(date="2026-05-26", player_name="Jayson Tatum",
                                              stat="reb", status="pending")))
        ids.append(db.insert_bet(_sample_bet(date="2026-05-27", player_name="LeBron James",
                                              stat="ast", status="lost")))
        ids.append(db.insert_bet(_sample_bet(date="2026-05-27", player_name="Steph Curry",
                                              stat="fg3m", status="pending")))
        return ids

    def test_filter_by_date(self, db):
        self._insert_many(db)
        rows = db.list_bets(date="2026-05-27")
        assert len(rows) == 2
        assert all(r["date"] == "2026-05-27" for r in rows)

    def test_filter_by_status(self, db):
        self._insert_many(db)
        rows = db.list_bets(status="pending")
        assert len(rows) == 2
        assert all(r["status"] == "pending" for r in rows)

    def test_filter_by_player_substring(self, db):
        self._insert_many(db)
        rows = db.list_bets(player="LeBron")
        assert len(rows) == 2
        assert all("LeBron" in r["player_name"] for r in rows)

    def test_combined_filters(self, db):
        self._insert_many(db)
        rows = db.list_bets(date="2026-05-27", status="pending")
        assert len(rows) == 1
        assert rows[0]["player_name"] == "Steph Curry"

    def test_limit(self, db):
        for i in range(10):
            db.insert_bet(_sample_bet(player_name=f"Player {i}"))
        rows = db.list_bets(limit=3)
        assert len(rows) == 3

    def test_empty_result(self, db):
        rows = db.list_bets(date="2000-01-01")
        assert rows == []

    def test_recent_bets(self, db):
        self._insert_many(db)
        rows = db.recent_bets(3)
        assert len(rows) == 3


# ── daily_summary ─────────────────────────────────────────────────────────────

class TestDailySummary:
    def test_empty_date(self, db):
        s = db.daily_summary("2099-01-01")
        assert s["n_bets"] == 0
        assert s["total_stake"] == 0.0
        assert s["roi_pct"] == 0.0

    def test_summary_correct(self, db):
        date = "2026-05-27"
        b1 = db.insert_bet(_sample_bet(date=date, stake=100.0))
        b2 = db.insert_bet(_sample_bet(date=date, stake=50.0))
        db.settle_bet(b1, status="won",  actual_stat=30.0, pnl=90.91)
        db.settle_bet(b2, status="lost", actual_stat=20.0, pnl=-50.0)

        s = db.daily_summary(date)
        assert s["n_bets"] == 2
        assert abs(s["total_stake"] - 150.0) < 0.01
        assert abs(s["total_pnl"] - 40.91) < 0.01
        assert s["roi_pct"] > 0


# ── bankroll ──────────────────────────────────────────────────────────────────

class TestBankroll:
    def test_initial_bankroll_zero(self, db):
        assert db.current_bankroll() == 0.0

    def test_update_bankroll(self, db):
        db.update_bankroll(1000.0, notes="initial deposit")
        assert db.current_bankroll() == 1000.0

    def test_bankroll_series(self, db):
        db.update_bankroll(1000.0)
        db.update_bankroll(1050.0, notes="won")
        assert db.current_bankroll() == 1050.0

    def test_open_bet_value(self, db):
        db.insert_bet(_sample_bet(stake=100.0, status="pending"))
        db.insert_bet(_sample_bet(stake=50.0,  status="pending"))
        bid = db.insert_bet(_sample_bet(stake=200.0, status="pending"))
        db.settle_bet(bid, status="won", actual_stat=30.0, pnl=180.0)
        # Only the 2 still-pending bets count.
        assert db.open_bet_value() == 150.0

    def test_high_water_mark(self, db):
        db.update_bankroll(900.0)
        db.update_bankroll(1200.0)
        db.update_bankroll(1100.0)
        hwm = db.high_water_mark(90)
        assert hwm == 1200.0

    def test_drawdown_pct(self, db):
        db.update_bankroll(1000.0)
        db.update_bankroll(800.0)
        dd = db.drawdown_pct(90)
        assert abs(dd - 20.0) < 0.1


# ── settled_actuals ───────────────────────────────────────────────────────────

class TestActuals:
    def test_upsert_and_get(self, db):
        db.upsert_actual("GAME1", "PLAYER1", "pts", 28.0)
        assert db.get_actual("GAME1", "PLAYER1", "pts") == 28.0

    def test_upsert_replaces(self, db):
        db.upsert_actual("GAME1", "PLAYER1", "pts", 28.0)
        db.upsert_actual("GAME1", "PLAYER1", "pts", 32.0)
        assert db.get_actual("GAME1", "PLAYER1", "pts") == 32.0

    def test_get_missing(self, db):
        assert db.get_actual("NOPE", "NOPE", "pts") is None


# ── clv daily upsert ──────────────────────────────────────────────────────────

class TestCLVDaily:
    def test_upsert_and_idempotent(self, db):
        db.upsert_clv_daily("2026-05-27", {
            "n_bets": 5, "avg_clv_bps": 12.5, "win_pct": 60.0,
            "roi_pct": 8.3, "total_stake": 500.0, "total_pnl": 41.5,
        })
        # Second call with same date must not raise.
        db.upsert_clv_daily("2026-05-27", {
            "n_bets": 6, "avg_clv_bps": 14.0, "win_pct": 66.7,
            "roi_pct": 9.1, "total_stake": 600.0, "total_pnl": 54.6,
        })


# ── daily pnl series ─────────────────────────────────────────────────────────

class TestDailyPnlSeries:
    def test_empty_returns_list(self, db):
        series = db.daily_pnl_series(30)
        assert isinstance(series, list)

    def test_series_aggregates_by_date(self, db):
        db.insert_bet(_sample_bet(date="2026-05-26", stake=100.0))
        db.insert_bet(_sample_bet(date="2026-05-26", stake=50.0))
        db.insert_bet(_sample_bet(date="2026-05-27", stake=75.0))
        series = db.daily_pnl_series(30)
        dates = [r["date"] for r in series]
        assert len(dates) == len(set(dates))  # one row per date
