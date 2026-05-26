"""Tests for scripts/execute_loop/L07_pnl_ledger.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L07_ledger.py -v
"""
from __future__ import annotations

import importlib
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd

# ---------------------------------------------------------------------------
# Ensure project root on path
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub heavy imports before importing the module under test
_api_patch_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_patch_stub)

# Stub settle_tonight so tests don't need a live NBA API
_rlc = types.ModuleType("scripts.validation.real_lines_check")
_stn = types.ModuleType("scripts.validation.real_lines_check.settle_tonight")
_stn.fetch_boxscore_player_stats = MagicMock(return_value={})
sys.modules.setdefault("scripts.validation.real_lines_check", _rlc)
sys.modules.setdefault("scripts.validation.real_lines_check.settle_tonight", _stn)

import scripts.execute_loop.L07_pnl_ledger as L07  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    """Redirect all ledger I/O to a fresh tmp_path for every test."""
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")
    monkeypatch.setattr(L07, "_CONTESTS_FILE", tmp_path / "contests.parquet")
    monkeypatch.setattr(L07, "_CONTESTS_CSV", tmp_path / "contests.csv")
    yield


def _jokic_bet(side="OVER", line=25.5, stake=1.0, odds=-110) -> L07.BetRow:
    return L07.BetRow(
        player="Nikola Jokic",
        stat="pts",
        line=line,
        side=side,
        stake=stake,
        odds=odds,
        book="DK",
        market="player_prop_pts",
        game_id="0022500123",
        test_mode=True,
    )


# ---------------------------------------------------------------------------
# Test 1 — place_bet round-trip
# ---------------------------------------------------------------------------
def test_place_bet_round_trip():
    """place_bet returns a bet_id and get_open_bets includes the bet."""
    row = _jokic_bet()
    bet_id = L07.place_bet(row)

    assert bet_id, "bet_id should be non-empty"

    open_bets = L07.get_open_bets()
    assert len(open_bets) == 1
    bet = open_bets[0]
    assert bet.player == "Nikola Jokic"
    assert bet.stat == "pts"
    assert bet.line == 25.5
    assert bet.status == "OPEN"
    assert bet.bet_id == bet_id


# ---------------------------------------------------------------------------
# Test 2 — duplicate bet_id idempotency
# ---------------------------------------------------------------------------
def test_duplicate_bet_id_idempotent():
    """Placing the same bet_id twice keeps ledger length at 1."""
    row = _jokic_bet()
    row.bet_id = "my-fixed-id-001"
    L07.place_bet(row)

    row2 = _jokic_bet()
    row2.bet_id = "my-fixed-id-001"  # same id
    L07.place_bet(row2)

    df = L07._load_bets()
    assert len(df) == 1, f"Expected 1 row, got {len(df)}"


# ---------------------------------------------------------------------------
# Test 3 — settle_unsettled with monkeypatched boxscore → WON
# ---------------------------------------------------------------------------
def test_settle_jokic_pts_over_won(monkeypatch):
    """Jokic PTS line=25.5 OVER, actual=30 → WON."""
    _fake_box = {
        "nikola jokic": {
            "pts": 30.0,
            "reb": 12.0,
            "ast": 7.0,
            "fg3m": 1.0,
            "stl": 1.0,
            "blk": 0.0,
            "tov": 2.0,
            "min": "32:15",
        }
    }

    row = _jokic_bet(side="OVER", line=25.5)
    L07.place_bet(row)

    # Retrieve the stub already wired into sys.modules (avoids real import)
    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    orig = _stn_mod.fetch_boxscore_player_stats
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value=_fake_box)
    try:
        count = L07.settle_unsettled()
    finally:
        _stn_mod.fetch_boxscore_player_stats = orig

    assert count == 1, f"Expected 1 settled, got {count}"
    df = L07._load_bets()
    assert df.iloc[0]["status"] == "WON"
    assert float(df.iloc[0]["actual_value"]) == 30.0
    pnl = float(df.iloc[0]["pnl"])
    assert pnl == pytest.approx(100 / 110, rel=1e-3)


# ---------------------------------------------------------------------------
# Test 4 — PnL math
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("odds,status,stake,expected_pnl", [
    (-110, "WON",  1.0, 100 / 110),   # ≈ 0.9091
    (-110, "LOST", 1.0, -1.0),
    (-110, "PUSH", 1.0,  0.0),
    (+150, "WON",  1.0,  1.5),
])
def test_pnl_math(odds, status, stake, expected_pnl):
    pnl = L07._compute_pnl(stake, odds, status)
    assert abs(pnl - expected_pnl) < 1e-4, f"pnl={pnl!r} expected≈{expected_pnl}"


# ---------------------------------------------------------------------------
# Test 5 — PUSH detection when actual == line
# ---------------------------------------------------------------------------
def test_push_detection(monkeypatch):
    """actual_value == line → PUSH, pnl=0."""
    _fake_box = {
        "nikola jokic": {"pts": 25.5, "min": "35:00"},
    }

    row = _jokic_bet(side="OVER", line=25.5)
    L07.place_bet(row)

    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value=_fake_box)

    count = L07.settle_unsettled()

    assert count == 1
    df = L07._load_bets()
    assert df.iloc[0]["status"] == "PUSH"
    assert float(df.iloc[0]["pnl"]) == 0.0


# ---------------------------------------------------------------------------
# Test 6 — DNP (MIN==0) → VOID, pnl=0, notes="DNP"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("min_val", ["0", "0:00", "0.0", ""])
def test_dnp_void(min_val, monkeypatch):
    """Player with MIN==0 or empty → VOID."""
    _fake_box = {
        "nikola jokic": {"pts": 0.0, "min": min_val},
    }

    row = _jokic_bet()
    L07.place_bet(row)

    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value=_fake_box)

    count = L07.settle_unsettled()

    assert count == 1
    df = L07._load_bets()
    assert df.iloc[0]["status"] == "VOID"
    assert float(df.iloc[0]["pnl"]) == 0.0
    assert "DNP" in str(df.iloc[0]["notes"])


# ---------------------------------------------------------------------------
# Test 7 — close_contest updates DFS lineup row pnl
# ---------------------------------------------------------------------------
def test_close_contest():
    """close_contest stores pnl = total_payout (no prior entry_fee)."""
    L07.close_contest("contest-abc-001", entry_position=3, total_payout=150.0)

    df = L07._load_contests()
    assert len(df) == 1
    row = df.iloc[0]
    assert str(row["contest_id"]) == "contest-abc-001"
    assert int(row["entry_position"]) == 3
    assert float(row["total_payout"]) == 150.0
    assert float(row["pnl"]) == 150.0
    assert str(row["status"]) == "SETTLED"


def test_close_contest_updates_existing():
    """Calling close_contest twice on same id updates, not duplicates."""
    L07.close_contest("cid-002", 5, 50.0)
    L07.close_contest("cid-002", 2, 200.0)

    df = L07._load_contests()
    assert len(df) == 1
    assert float(df.iloc[0]["total_payout"]) == 200.0
    assert int(df.iloc[0]["entry_position"]) == 2


# ---------------------------------------------------------------------------
# Test 8 — get_pnl_summary by="stat" returns dict keyed by stat
# ---------------------------------------------------------------------------
def test_get_pnl_summary_by_stat(monkeypatch):
    """get_pnl_summary(by='stat') keys = stat values of settled bets."""
    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]

    # Place two bets on different stats
    row_pts = L07.BetRow(
        player="Nikola Jokic", stat="pts", line=25.5, side="OVER",
        stake=1.0, odds=-110, book="DK", game_id="0022500001", test_mode=True,
    )
    row_reb = L07.BetRow(
        player="Nikola Jokic", stat="reb", line=11.5, side="OVER",
        stake=2.0, odds=-115, book="DK", game_id="0022500001", test_mode=True,
    )
    L07.place_bet(row_pts)
    L07.place_bet(row_reb)

    _fake_box = {
        "nikola jokic": {"pts": 30.0, "reb": 14.0, "min": "35:00"},
    }
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value=_fake_box)
    L07.settle_unsettled()

    summary = L07.get_pnl_summary(by="stat")

    assert isinstance(summary, dict)
    assert "pts" in summary, f"Keys: {list(summary.keys())}"
    assert "reb" in summary, f"Keys: {list(summary.keys())}"
    assert summary["pts"]["won"] == 1
    assert summary["reb"]["won"] == 1


# ---------------------------------------------------------------------------
# Test 9 — parquet fallback to CSV when pyarrow not installed
# ---------------------------------------------------------------------------
def test_csv_fallback(tmp_path, monkeypatch):
    """When _HAS_PARQUET is False, bets are written/read as CSV."""
    monkeypatch.setattr(L07, "_HAS_PARQUET", False)
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")

    row = _jokic_bet()
    bet_id = L07.place_bet(row)

    csv_path = tmp_path / "bets.csv"
    assert csv_path.exists(), "CSV file should have been created"
    assert not (tmp_path / "bets.parquet").exists(), "Parquet should NOT be created"

    df = pd.read_csv(csv_path)
    assert len(df) == 1
    assert df.iloc[0]["bet_id"] == bet_id


# ---------------------------------------------------------------------------
# Bonus: bet_id auto-generation + composite key
# ---------------------------------------------------------------------------
def test_bet_id_auto_generated():
    """bet_id is auto-generated when not supplied."""
    row = _jokic_bet()
    assert row.bet_id == ""

    bet_id = L07.place_bet(row)
    assert bet_id != ""


def test_bet_id_composite_when_fields_set():
    """Composite bet_id includes book:player:stat:line:placed_at_iso."""
    row = _jokic_bet()
    row.placed_at_iso = "2026-05-25T10:00:00+00:00"
    # bet_id still empty → triggers composite generation
    assert row.bet_id == ""
    bet_id = L07.place_bet(row)
    assert "DK" in bet_id
    assert "Nikola Jokic" in bet_id


def test_settle_no_game_id_skipped():
    """Bets without game_id are ignored by settle_unsettled."""
    row = L07.BetRow(
        player="LeBron James", stat="pts", line=20.0, side="OVER",
        stake=1.0, odds=-110, book="FD",
        game_id="",  # no game_id
    )
    L07.place_bet(row)
    count = L07.settle_unsettled()
    assert count == 0
    assert L07.get_open_bets()[0].status == "OPEN"


# ---------------------------------------------------------------------------
# v2 field tests
# ---------------------------------------------------------------------------

def test_betrow_v2_fields_default_none():
    """New v2 fields on BetRow all default to None."""
    row = L07.BetRow(player="Test Player", stat="pts", line=20.0, side="OVER")
    assert row.ip is None
    assert row.model_p_var is None
    assert row.clv_units is None
    assert row.clv_prob_pts is None
    assert row.line_at_close is None


def test_ip_round_trip_csv(tmp_path, monkeypatch):
    """ip field survives a CSV round-trip (forces _HAS_PARQUET=False)."""
    monkeypatch.setattr(L07, "_HAS_PARQUET", False)
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")

    row = _jokic_bet()
    row.ip = "192.168.1.1"
    L07.place_bet(row)

    loaded = L07.get_open_bets()
    assert len(loaded) == 1
    assert loaded[0].ip == "192.168.1.1"


def test_model_p_var_round_trip(tmp_path, monkeypatch):
    """model_p_var float field survives a CSV round-trip."""
    monkeypatch.setattr(L07, "_HAS_PARQUET", False)
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")

    row = _jokic_bet()
    row.model_p_var = 0.042
    L07.place_bet(row)

    loaded = L07.get_open_bets()
    assert loaded[0].model_p_var == pytest.approx(0.042, rel=1e-4)


def test_backward_compat_legacy_csv_load(tmp_path, monkeypatch):
    """A CSV written with only the original (v1) columns loads without error; v2 fields are None."""
    monkeypatch.setattr(L07, "_HAS_PARQUET", False)
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")

    # Write a CSV with only v1 columns (no ip, model_p_var, clv_*, line_at_close)
    v1_cols = [
        "bet_id", "placed_at_iso", "book", "market", "player", "stat",
        "line", "side", "stake", "odds", "model_q50", "model_p_side",
        "model_edge_pp", "test_mode", "status", "settled_at_iso",
        "actual_value", "pnl", "game_id", "notes",
    ]
    legacy_df = pd.DataFrame([{c: ("" if c != "line" else "25.5") for c in v1_cols}])
    legacy_df["bet_id"] = "legacy-001"
    legacy_df["status"] = "OPEN"
    legacy_df.to_csv(tmp_path / "bets.csv", index=False)

    bets = L07.get_open_bets()
    assert len(bets) == 1
    bet = bets[0]
    assert bet.bet_id == "legacy-001"
    assert bet.ip is None
    assert bet.model_p_var is None
    assert bet.clv_units is None
    assert bet.clv_prob_pts is None
    assert bet.line_at_close is None


def test_settle_invokes_l19_compute_clv(monkeypatch):
    """settle_unsettled calls _compute_clv_for_bet and stores clv_units."""
    import datetime as _dt

    # Wire a fake boxscore so the bet actually settles
    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _fake_box = {
        "nikola jokic": {"pts": 30.0, "min": "35:00"},
    }
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value=_fake_box)

    # Monkeypatch _compute_clv_for_bet to return fixed values
    monkeypatch.setattr(
        L07, "_compute_clv_for_bet",
        lambda bet: (26.0, 0.5, 1.23),
    )

    row = _jokic_bet(side="OVER", line=25.5)
    row.placed_at_iso = "2026-05-25T10:00:00+00:00"
    L07.place_bet(row)

    count = L07.settle_unsettled()
    assert count == 1

    df = L07._load_bets()
    assert df.iloc[0]["status"] == "WON"
    assert float(df.iloc[0]["clv_units"]) == pytest.approx(0.5, rel=1e-4)
    assert float(df.iloc[0]["clv_prob_pts"]) == pytest.approx(1.23, rel=1e-4)
    assert float(df.iloc[0]["line_at_close"]) == pytest.approx(26.0, rel=1e-4)


def test_settle_no_snapshot_leaves_clv_none(monkeypatch):
    """When _compute_clv_for_bet returns (None,None,None) settlement still succeeds."""
    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _fake_box = {
        "nikola jokic": {"pts": 30.0, "min": "35:00"},
    }
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value=_fake_box)

    monkeypatch.setattr(
        L07, "_compute_clv_for_bet",
        lambda bet: (None, None, None),
    )

    row = _jokic_bet(side="OVER", line=25.5)
    row.placed_at_iso = "2026-05-25T10:00:00+00:00"
    L07.place_bet(row)

    count = L07.settle_unsettled()
    assert count == 1

    df = L07._load_bets()
    assert df.iloc[0]["status"] == "WON"
    # v2 CLV columns should be empty/blank (None serialized to "")
    clv_val = df.iloc[0].get("clv_units", "")
    assert clv_val in (None, "", float("nan")) or (
        isinstance(clv_val, float) and pd.isna(clv_val)
    )


def test_csv_columns_include_v2_fields(tmp_path, monkeypatch):
    """CSV written by place_bet contains all five v2 column headers."""
    monkeypatch.setattr(L07, "_HAS_PARQUET", False)
    monkeypatch.setattr(L07, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L07, "_BETS_FILE", tmp_path / "bets.parquet")
    monkeypatch.setattr(L07, "_BETS_CSV", tmp_path / "bets.csv")

    row = _jokic_bet()
    L07.place_bet(row)

    df = pd.read_csv(tmp_path / "bets.csv")
    for col in ("ip", "model_p_var", "clv_units", "clv_prob_pts", "line_at_close"):
        assert col in df.columns, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# L46 EventBus integration tests
# ---------------------------------------------------------------------------

def test_settle_publishes_event_when_l46_present(monkeypatch):
    """settle_unsettled publishes bet.settled with correct fields when L46 is available."""
    import scripts.execute_loop.L46_event_bus as real_L46

    # Use a fresh EventBus so this test is isolated from any prior subscribers
    fresh_bus = real_L46.EventBus()

    # Build a fake L46 module that delegates publish/subscribe to the fresh bus
    import types
    fake_L46 = types.SimpleNamespace(
        publish=fresh_bus.publish,
        subscribe=fresh_bus.subscribe,
        get_default_bus=lambda: fresh_bus,
    )
    monkeypatch.setattr(L07, "_L46", fake_L46)

    received: list = []

    def _handler(event):
        received.append(event)

    fresh_bus.subscribe("bet.settled", _handler, layer="test")

    # Wire boxscore
    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value={
        "nikola jokic": {"pts": 30.0, "min": "35:00"},
    })
    monkeypatch.setattr(L07, "_compute_clv_for_bet", lambda bet: (None, None, None))

    row = _jokic_bet(side="OVER", line=25.5, stake=5.0, odds=-110)
    L07.place_bet(row)

    count = L07.settle_unsettled()
    assert count == 1, f"Expected 1 settled bet, got {count}"

    assert len(received) == 1, f"Expected 1 event, got {len(received)}"
    evt = received[0]
    assert evt.name == "bet.settled"
    assert evt.source == "L7"
    assert evt.payload["status"] == "WON"
    assert evt.payload["stake"] == pytest.approx(5.0)
    assert evt.payload["player"] == "Nikola Jokic"
    assert evt.payload["stat"] == "pts"
    assert "settled_at" in evt.payload
    assert evt.payload["pnl"] == pytest.approx(5.0 * 100 / 110, rel=1e-3)


def test_settle_works_when_l46_absent(monkeypatch):
    """settle_unsettled succeeds (no exception) when _L46 is None."""
    monkeypatch.setattr(L07, "_L46", None)

    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value={
        "nikola jokic": {"pts": 20.0, "min": "30:00"},
    })
    monkeypatch.setattr(L07, "_compute_clv_for_bet", lambda bet: (None, None, None))

    row = _jokic_bet(side="OVER", line=25.5)
    L07.place_bet(row)

    count = L07.settle_unsettled()
    assert count == 1

    df = L07._load_bets()
    assert df.iloc[0]["status"] == "LOST"


def test_settle_publish_failure_does_not_break_settlement(monkeypatch):
    """If L46.publish raises, the settlement still completes successfully."""
    import types

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated L46 publish failure")

    fake_L46 = types.SimpleNamespace(publish=_boom)
    monkeypatch.setattr(L07, "_L46", fake_L46)

    _stn_mod = sys.modules["scripts.validation.real_lines_check.settle_tonight"]
    _stn_mod.fetch_boxscore_player_stats = MagicMock(return_value={
        "nikola jokic": {"pts": 30.0, "min": "35:00"},
    })
    monkeypatch.setattr(L07, "_compute_clv_for_bet", lambda bet: (None, None, None))

    row = _jokic_bet(side="OVER", line=25.5)
    L07.place_bet(row)

    # Must not raise
    count = L07.settle_unsettled()
    assert count == 1

    df = L07._load_bets()
    assert df.iloc[0]["status"] == "WON"
