"""tests/test_decision_engine_gates.py — guard the projection-sanity gate.

Regression for the in-play "EV +205%" false signal seen during the
SAS @ OKC game on 2026-05-26: the live engine sometimes returns
projected_final=0.0 for players who haven't played yet, which makes
hit_probability(under) ≈ 1.0 and EV explode at any positive odds.
"""
from __future__ import annotations

from src.prediction.decision_engine import (
    _gate_projection_sane,
    _passes_gates,
)


def _line(over=110, under=-130, val=20.5):
    return {"line": val, "over_price": over, "under_price": under,
            "book": "fd", "market_status": "open"}


def test_projection_sane_blocks_exact_zero_pts():
    rec = {"projected_final": 0.0, "stat": "pts", "current": 0,
           "delta": 0.0, "name": "Ghost", "player_id": "g"}
    assert _gate_projection_sane(rec, _line()) is False


def test_projection_sane_blocks_exact_zero_reb():
    rec = {"projected_final": 0.0, "stat": "reb", "current": 0,
           "delta": 0.0, "name": "Ghost", "player_id": "g"}
    assert _gate_projection_sane(rec, _line()) is False


def test_projection_sane_allows_low_bench_player_projection():
    """A real bench projection (e.g., 0.5 PTS) must still pass — the gate
    only rejects exact-zero / sub-floor sentinels."""
    rec = {"projected_final": 0.5, "stat": "pts", "current": 0,
           "delta": 0.0, "name": "Bench", "player_id": "b"}
    assert _gate_projection_sane(rec, _line()) is True


def test_passes_gates_rejects_zero_projection_in_full_pipeline():
    """End-to-end: an exact-zero projection should fail _passes_gates."""
    rec = {"projected_final": 0.0, "stat": "pts", "current": 0,
           "delta": 0.0, "name": "Ghost", "player_id": "g"}
    ok, gate = _passes_gates(rec, _line())
    assert ok is False
    assert gate == "projection_sane"


def test_filter_three_book_consensus():
    from src.prediction.decision_engine import _filter_three_book_consensus
    lines = [
        # Player X has all three books at line=10.5 → must survive
        {"book": "pin", "line": 10.5, "over_price": -110, "under_price": -110},
        {"book": "bov", "line": 10.5, "over_price": -120, "under_price": 100},
        {"book": "fd",  "line": 10.5, "over_price": -115, "under_price": -105},
        # Same player at line=11.5 — only Bovada → must be dropped
        {"book": "bov", "line": 11.5, "over_price": -150, "under_price": 130},
        # Player Y two books at 8.5 (pin + bov, missing fd) → dropped
        {"book": "pin", "line": 8.5,  "over_price": -110, "under_price": -110},
        {"book": "bov", "line": 8.5,  "over_price": -125, "under_price": 105},
    ]
    out = _filter_three_book_consensus(lines)
    surviving_values = sorted({float(l["line"]) for l in out})
    assert surviving_values == [10.5], surviving_values
    surviving_books = sorted({l["book"] for l in out})
    assert surviving_books == ["bov", "fd", "pin"]


def test_ev_ceiling_blocks_phantom_edge():
    """When the in-play model extrapolates a hot streak to 43 PTS for a
    role player whose line is 11.5, the resulting EV (+205% at +205 odds)
    is always model failure rather than a real edge. rank_for_game must
    drop these instead of alerting on them."""
    from src.prediction.decision_engine import DecisionEngine
    eng = DecisionEngine(emit_floor_ev=0.01)
    # Stub the line cache so we don't touch disk
    eng.line_cache._by_key[("p1", "pts")] = [{
        "line": 11.5, "over_price": 205, "under_price": -300,
        "book": "bov", "market_status": "open",
    }]
    eng._latest_rows["g"] = [{
        "player_id": "p1", "name": "Phantom Hot Bench",
        "stat": "pts", "projected_final": 43.9,
        "current": 5, "delta": 32.4,
    }]
    bets = eng.rank_for_game("g")
    assert bets == [], f"expected no bets but got {bets}"
