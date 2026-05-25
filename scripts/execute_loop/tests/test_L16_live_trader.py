"""test_L16_live_trader.py — Tests for L16_live_trader.py (PAPER MODE STRICT)

Seven focused tests covering:
  1. evaluate_position — no existing, edge=10pp → action="OPEN"
  2. evaluate_position — existing same-side, edge=7pp → action="ADD"
  3. evaluate_position — existing opposite-side, edge=7pp → action="CLOSE"
  4. evaluate_position — edge=1pp → action="HOLD"
  5. exit_all_positions — closes all open ledger entries (tmp_path ledger)
  6. Drawdown trip — L18.check_risk_limits returns (False, "drawdown") →
       exit_all_positions invoked, positions closed
  7. live_engine ImportError → subscribe_live_engine yields nothing
"""
from __future__ import annotations

import importlib
import json
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — find repo root and insert so L16 can be imported
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
_REPO_ROOT = _LOOP_DIR.parents[1]   # nba-ai-system/

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(_LOOP_DIR))

# ---------------------------------------------------------------------------
# Module loader — always imports fresh (controls soft-import side-effects)
# ---------------------------------------------------------------------------
_MODULE_NAME = "scripts.execute_loop.L16_live_trader"


def _load_L16(extra_mocks: dict | None = None):
    """Import L16 with soft-import stubs pre-injected into sys.modules."""
    # Remove stale copy
    for key in list(sys.modules):
        if "L16_live_trader" in key:
            del sys.modules[key]

    # Stub out the soft-import targets so they don't need real installs
    stubs = {
        "src.prediction.live_engine": None,           # default: unavailable
        "scripts.execute_loop.L13_cross_exchange_ev": MagicMock(),
        "scripts.execute_loop.L14_order_manager": MagicMock(),
        "scripts.execute_loop.L18_bankroll_manager": MagicMock(),
        "scripts.execute_loop.L22_alerting": MagicMock(),
    }
    if extra_mocks:
        stubs.update(extra_mocks)

    for mod_name, obj in stubs.items():
        if obj is None:
            # Simulate ImportError by not putting module in sys.modules;
            # live_engine is the one that should yield nothing when absent.
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = obj

    return importlib.import_module(_MODULE_NAME)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def L16(tmp_path, monkeypatch):
    """Return freshly imported L16 with paper ledger redirected to tmp_path."""
    mod = _load_L16()
    ledger_path = tmp_path / "paper_live_positions.json"
    monkeypatch.setattr(mod, "_PAPER_LEDGER", ledger_path)
    return mod


@pytest.fixture()
def sample_prediction():
    return {
        "player": "LeBron James",
        "stat": "pts",
        "period": "endQ1",
        "q50": 26.5,
        "p_over": 0.62,
        "p_under": 0.38,
        "side": "OVER",
        "market_id": "LeBron_pts_OVER",
        "exchange": "kalshi",
        "ts": "2026-05-25T20:00:00Z",
    }


@pytest.fixture()
def sample_quote():
    """Market quote with p=0.50 → 12pp edge when model=0.62."""
    return {
        "market_p": 0.50,
        "side": "OVER",
        "market_id": "LeBron_pts_OVER",
    }


def _make_position(
    side="OVER",
    qty=100.0,
    avg_price=0.50,
    model_p=0.62,
    market_p=0.50,
    action="HOLD",
) -> "LivePosition":
    """Build a LivePosition for use in tests (imported via fixture)."""
    from scripts.execute_loop.L16_live_trader import LivePosition
    return LivePosition(
        position_id=str(uuid.uuid4()),
        exchange="kalshi",
        market_id="LeBron_pts_OVER",
        player="LeBron James",
        stat="pts",
        side=side,
        qty=qty,
        avg_price=avg_price,
        opened_at_period="endQ1",
        current_model_p=model_p,
        current_market_p=market_p,
        action=action,
    )


# ---------------------------------------------------------------------------
# Test 1 — No existing position + edge=10pp → action="OPEN"
# ---------------------------------------------------------------------------

def test_evaluate_open_when_no_existing_and_large_edge(L16, sample_prediction, sample_quote):
    """Edge is 12pp (model 0.62 vs market 0.50) → should open a new position."""
    result = L16.evaluate_position(sample_prediction, sample_quote, existing_position=None)
    assert result.action == "OPEN", f"Expected OPEN, got {result.action}"
    assert result.qty > 0
    assert result.side == "OVER"
    assert result.player == "LeBron James"


# ---------------------------------------------------------------------------
# Test 2 — Existing same-side position + edge=7pp → action="ADD"
# ---------------------------------------------------------------------------

def test_evaluate_add_same_side_sufficient_edge(L16, sample_prediction, sample_quote):
    """Same side (OVER), model=0.57 vs market=0.50 (7pp edge) → ADD."""
    pred = {**sample_prediction, "p_over": 0.57, "p_under": 0.43}
    quote = {**sample_quote, "market_p": 0.50}
    existing = _make_position(side="OVER", qty=50.0, avg_price=0.50, model_p=0.55, market_p=0.50)
    result = L16.evaluate_position(pred, quote, existing_position=existing)
    assert result.action == "ADD", f"Expected ADD, got {result.action}"
    assert result.qty > existing.qty  # qty grew
    # Verify 2x cap is not exceeded
    assert result.qty <= existing.qty * L16._MAX_ADD_MULTIPLIER


# ---------------------------------------------------------------------------
# Test 3 — Existing opposite-side position + edge=7pp → action="CLOSE"
# ---------------------------------------------------------------------------

def test_evaluate_close_opposite_side_sufficient_edge(L16, sample_prediction, sample_quote):
    """Existing position is UNDER, new signal is OVER with 7pp edge → CLOSE."""
    pred = {**sample_prediction, "p_over": 0.57, "side": "OVER"}
    quote = {**sample_quote, "market_p": 0.50}
    # Existing is UNDER (opposite)
    existing = _make_position(side="UNDER", qty=50.0, avg_price=0.50, model_p=0.45, market_p=0.50)
    result = L16.evaluate_position(pred, quote, existing_position=existing)
    assert result.action == "CLOSE", f"Expected CLOSE, got {result.action}"


# ---------------------------------------------------------------------------
# Test 4 — Edge=1pp (< 3pp) → action="HOLD"
# ---------------------------------------------------------------------------

def test_evaluate_hold_when_edge_too_small(L16, sample_prediction):
    """Model=0.51 vs market=0.50 → only 1pp edge, no existing → HOLD."""
    pred = {**sample_prediction, "p_over": 0.51, "p_under": 0.49}
    quote = {"market_p": 0.50, "side": "OVER", "market_id": "LeBron_pts_OVER"}
    result = L16.evaluate_position(pred, quote, existing_position=None)
    assert result.action == "HOLD", f"Expected HOLD, got {result.action}"


# ---------------------------------------------------------------------------
# Test 5 — exit_all_positions closes every open ledger entry
# ---------------------------------------------------------------------------

def test_exit_all_positions_closes_open_entries(tmp_path, monkeypatch):
    """Populate ledger with 3 open positions; exit_all should close all 3."""
    mod = _load_L16()
    ledger_path = tmp_path / "paper_live_positions.json"
    monkeypatch.setattr(mod, "_PAPER_LEDGER", ledger_path)

    # Write 3 open positions to the tmp ledger
    from dataclasses import asdict
    positions = []
    for i in range(3):
        pos = _make_position(side="OVER", action="HOLD")
        pos.position_id = str(uuid.uuid4())
        positions.append(asdict(pos))

    ledger_path.write_text(
        json.dumps({"positions": positions}), encoding="utf-8"
    )

    closed = mod.exit_all_positions()
    assert closed == 3

    # Verify all persisted with CLOSE
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    actions = {p["action"] for p in raw["positions"]}
    assert actions == {"CLOSE"}


# ---------------------------------------------------------------------------
# Test 6 — Drawdown trip: check_risk_limits returns (False, "drawdown") →
#           exit_all_positions is invoked, all positions closed
# ---------------------------------------------------------------------------

def test_drawdown_trip_exits_all_positions(tmp_path, monkeypatch):
    """When L18.check_risk_limits signals drawdown, run_live_session exits all."""
    # Build a fake L18 module whose check_risk_limits trips immediately
    fake_l18 = types.ModuleType("scripts.execute_loop.L18_bankroll_manager")
    fake_l18.check_risk_limits = MagicMock(return_value=(False, "drawdown"))
    fake_l18.kelly_fraction = MagicMock(return_value=0.02)

    # Build a fake live_engine that yields one prediction
    fake_engine = types.ModuleType("src.prediction.live_engine")
    fake_engine.predict_live = MagicMock(return_value=[
        {
            "player": "Stephen Curry",
            "stat": "pts",
            "period": "endQ1",
            "q50": 28.0,
            "p_over": 0.65,
            "p_under": 0.35,
            "side": "OVER",
            "market_id": "curry_pts_OVER",
            "market_p": 0.50,
            "exchange": "kalshi",
            "ts": "2026-05-25T20:00:00Z",
        }
    ])

    stubs = {
        "src.prediction.live_engine": fake_engine,
        "scripts.execute_loop.L13_cross_exchange_ev": MagicMock(),
        "scripts.execute_loop.L14_order_manager": MagicMock(),
        "scripts.execute_loop.L18_bankroll_manager": fake_l18,
        "scripts.execute_loop.L22_alerting": MagicMock(),
    }
    mod = _load_L16(extra_mocks=stubs)
    ledger_path = tmp_path / "paper_live_positions.json"
    monkeypatch.setattr(mod, "_PAPER_LEDGER", ledger_path)
    # Wire the soft import directly
    monkeypatch.setattr(mod, "_check_risk_limits", fake_l18.check_risk_limits)
    monkeypatch.setattr(mod, "_kelly_fraction", fake_l18.kelly_fraction)
    monkeypatch.setattr(mod, "_predict_live", fake_engine.predict_live)

    # Seed two open positions in ledger
    from dataclasses import asdict
    positions = []
    for _ in range(2):
        pos = _make_position(side="OVER", action="HOLD")
        pos.position_id = str(uuid.uuid4())
        positions.append(asdict(pos))
    ledger_path.write_text(json.dumps({"positions": positions}), encoding="utf-8")

    result = mod.run_live_session(game_id="0042500207", polling_sec=0)

    # Session exits early (0 new opens) and positions are closed
    assert result == 0

    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    actions = {p["action"] for p in raw["positions"]}
    assert "CLOSE" in actions, f"Expected CLOSE action, got {actions}"


# ---------------------------------------------------------------------------
# Test 7 — live_engine ImportError → subscribe_live_engine yields nothing
# ---------------------------------------------------------------------------

def test_subscribe_live_engine_yields_nothing_when_unavailable(tmp_path, monkeypatch):
    """If live_engine is not importable, subscribe_live_engine must be empty."""
    # Force _predict_live to None (simulates ImportError path)
    mod = _load_L16()  # loads with live_engine absent by default
    ledger_path = tmp_path / "paper_live_positions.json"
    monkeypatch.setattr(mod, "_PAPER_LEDGER", ledger_path)
    monkeypatch.setattr(mod, "_predict_live", None)

    results = list(mod.subscribe_live_engine(period="endQ1"))
    assert results == [], f"Expected empty iterator, got {results}"


# ---------------------------------------------------------------------------
# FakeLivePredictor — returns rising win-probs for endQ1/endQ2/endQ3
# ---------------------------------------------------------------------------

class FakeLivePredictor:
    """Stub predictor returning a single prediction per quarter call."""

    _WINPROBS = {"endQ1": 0.55, "endQ2": 0.62, "endQ3": 0.71}

    def __init__(self):
        self.calls: list[str] = []

    def predict_live(self, period: str) -> list[dict]:
        self.calls.append(period)
        p_over = self._WINPROBS.get(period, 0.55)
        return [
            {
                "player": "Team_A",
                "stat": "winprob",
                "period": period,
                "q50": p_over,
                "p_over": p_over,
                "p_under": round(1.0 - p_over, 4),
                "side": "OVER",
                "market_id": "TEAM_A_WIN",
                "market_p": 0.50,
                "exchange": "paper",
                "ts": "2026-05-25T20:00:00Z",
            }
        ]


# ---------------------------------------------------------------------------
# Test 8 — Full 3-quarter trading lifecycle: open Q1, hold/add Q2, hold Q3,
#           then exit_all_positions closes everything.
# ---------------------------------------------------------------------------

def test_full_live_session_three_quarter_hold_then_exit(tmp_path, monkeypatch):
    """FakeLivePredictor drives endQ1 OPEN, Q2 ADD, Q3 ADD/HOLD, then exit closes 1 row."""
    fake = FakeLivePredictor()

    # Fake L18 with permissive risk limits
    fake_l18 = types.ModuleType("scripts.execute_loop.L18_bankroll_manager")
    fake_l18.kelly_fraction = MagicMock(return_value=0.02)
    fake_l18.check_risk_limits = MagicMock(return_value=(True, "ok"))

    # Fake L14 order manager (track_order must be a real MagicMock we can inspect)
    fake_l14 = types.ModuleType("scripts.execute_loop.L14_order_manager")
    fake_l14.track_order = MagicMock(return_value=None)

    stubs = {
        "src.prediction.live_engine": None,           # we'll monkeypatch _predict_live directly
        "scripts.execute_loop.L13_cross_exchange_ev": MagicMock(),
        "scripts.execute_loop.L14_order_manager": fake_l14,
        "scripts.execute_loop.L18_bankroll_manager": fake_l18,
        "scripts.execute_loop.L22_alerting": MagicMock(),
    }
    mod = _load_L16(extra_mocks=stubs)

    ledger_path = tmp_path / "paper_live_positions.json"
    monkeypatch.setattr(mod, "_PAPER_LEDGER", ledger_path)
    monkeypatch.setattr(mod, "_predict_live", fake.predict_live)
    monkeypatch.setattr(mod, "_check_risk_limits", fake_l18.check_risk_limits)
    monkeypatch.setattr(mod, "_kelly_fraction", fake_l18.kelly_fraction)
    monkeypatch.setattr(mod, "_track_order", fake_l14.track_order)
    # Suppress real sleeps
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    opened = mod.run_live_session(game_id="0042500207", polling_sec=0)

    # --- predictor was called for all three periods ---
    assert fake.calls == ["endQ1", "endQ2", "endQ3"], (
        f"Expected calls for all three quarters, got {fake.calls}"
    )

    # --- at least 1 position opened ---
    assert opened >= 1, f"Expected at least 1 opened position, got {opened}"

    # --- ledger has exactly 1 row (upsert deduplicates by position_id) ---
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    positions = raw["positions"]
    assert len(positions) == 1, (
        f"Expected 1 position row (upserted), got {len(positions)}: {positions}"
    )

    # --- the row is on the correct side at the correct price ---
    row = positions[0]
    assert row["side"] == "OVER", f"Expected side=OVER, got {row['side']}"
    assert abs(row["avg_price"] - 0.50) < 0.01, (
        f"Expected avg_price≈0.50, got {row['avg_price']}"
    )
    assert row["action"] in ("OPEN", "ADD", "HOLD"), (
        f"Unexpected action after session: {row['action']}"
    )

    # --- _track_order was called exactly once (only for OPEN, not ADD/HOLD) ---
    assert fake_l14.track_order.call_count == 1, (
        f"Expected _track_order called once, got {fake_l14.track_order.call_count}"
    )

    # --- no real Kalshi client was touched ---
    assert "L09_kalshi_client" not in sys.modules

    # --- exit_all_positions closes the single position ---
    closed = mod.exit_all_positions()
    assert closed == 1, f"Expected 1 position closed, got {closed}"

    raw2 = json.loads(ledger_path.read_text(encoding="utf-8"))
    row2 = raw2["positions"][0]
    assert row2["action"] == "CLOSE", f"Expected CLOSE after exit, got {row2['action']}"
    assert abs(row2["avg_price"] - 0.50) < 0.01, (
        f"avg_price should be unchanged after exit, got {row2['avg_price']}"
    )


# ---------------------------------------------------------------------------
# Test 9 — Edge collapses: Q1 opens, Q2 hold (51pp), Q3 model < market → CLOSE
# ---------------------------------------------------------------------------

def test_live_session_holds_when_edge_collapses(tmp_path, monkeypatch):
    """Probs [0.55, 0.51, 0.49]: Q1 opens (5pp edge), Q2 insufficient edge,
    Q3 model < market → evaluate closes the position. track_order called once."""

    _WINPROBS_COLLAPSE = {"endQ1": 0.55, "endQ2": 0.51, "endQ3": 0.49}

    class CollapsingPredictor:
        def __init__(self):
            self.calls: list[str] = []

        def predict_live(self, period: str) -> list[dict]:
            self.calls.append(period)
            p_over = _WINPROBS_COLLAPSE.get(period, 0.50)
            return [
                {
                    "player": "Team_A",
                    "stat": "winprob",
                    "period": period,
                    "q50": p_over,
                    "p_over": p_over,
                    "p_under": round(1.0 - p_over, 4),
                    "side": "OVER",
                    "market_id": "TEAM_A_WIN",
                    "market_p": 0.50,
                    "exchange": "paper",
                    "ts": "2026-05-25T20:00:00Z",
                }
            ]

    fake = CollapsingPredictor()

    fake_l18 = types.ModuleType("scripts.execute_loop.L18_bankroll_manager")
    fake_l18.kelly_fraction = MagicMock(return_value=0.02)
    fake_l18.check_risk_limits = MagicMock(return_value=(True, "ok"))

    fake_l14 = types.ModuleType("scripts.execute_loop.L14_order_manager")
    fake_l14.track_order = MagicMock(return_value=None)

    stubs = {
        "src.prediction.live_engine": None,
        "scripts.execute_loop.L13_cross_exchange_ev": MagicMock(),
        "scripts.execute_loop.L14_order_manager": fake_l14,
        "scripts.execute_loop.L18_bankroll_manager": fake_l18,
        "scripts.execute_loop.L22_alerting": MagicMock(),
    }
    mod = _load_L16(extra_mocks=stubs)

    ledger_path = tmp_path / "paper_live_positions.json"
    monkeypatch.setattr(mod, "_PAPER_LEDGER", ledger_path)
    monkeypatch.setattr(mod, "_predict_live", fake.predict_live)
    monkeypatch.setattr(mod, "_check_risk_limits", fake_l18.check_risk_limits)
    monkeypatch.setattr(mod, "_kelly_fraction", fake_l18.kelly_fraction)
    monkeypatch.setattr(mod, "_track_order", fake_l14.track_order)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    mod.run_live_session(game_id="0042500207", polling_sec=0)

    # Predictor called for all three periods
    assert fake.calls == ["endQ1", "endQ2", "endQ3"], (
        f"Expected all three quarter calls, got {fake.calls}"
    )

    # track_order called exactly once (Q1 OPEN only; Q2/Q3 are HOLD/CLOSE)
    assert fake_l14.track_order.call_count == 1, (
        f"Expected track_order called once, got {fake_l14.track_order.call_count}"
    )

    # Final ledger state: position should be CLOSE (Q3 model_p=0.49 < market_p=0.50)
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(raw["positions"]) == 1
    assert raw["positions"][0]["action"] == "CLOSE", (
        f"Expected CLOSE when edge inverts, got {raw['positions'][0]['action']}"
    )
