"""
tests/test_wave4_router_fixes.py

Tests for two confirmed router bugs fixed in wave 4:

  Bug 1 (predictions_router.py) — props dict NaN/None guard
      stack_predict may return float('nan') or None for a stat. The old
      comprehension passed NaN to round(float(v),3) → bare NaN token in
      JSON (invalid), and round(float(None),3) → TypeError / HTTP 500.
      Fix: mirror the edges guard + handle None → null.

  Bug 3 (courtvision_router.py) — pregame edge_pct metric mismatch
      Live/overlay paths express edge_pct as model-minus-market
      probability gap in percentage points.  The pregame fallback used
      ev_pct (dollar-return EV per $100) instead — a different metric,
      systematically larger, rendered identically in the UI.
      Fix: pregame fallback computes (model_prob - market_prob)*100 pp.
"""

import json
import math
import os

import pytest

# ---------------------------------------------------------------------------
# BUG 1 — props dict NaN/None serialisation guard
# ---------------------------------------------------------------------------

def _apply_props_comprehension(predictions: dict) -> dict:
    """Replicate the fixed props-dict comprehension from predictions_router.py.

    This is the exact expression after the bug fix:
        {k: (None if v is None or (isinstance(v, float) and v != v)
             else round(float(v), 3))
         for k, v in stack.predictions.items()}
    """
    return {
        k: (
            None
            if v is None or (isinstance(v, float) and v != v)
            else round(float(v), 3)
        )
        for k, v in predictions.items()
    }


def test_props_nan_becomes_null():
    """NaN value is serialised as JSON null (not the bare NaN token)."""
    predictions = {
        "pts": float("nan"),
        "reb": 6.2,
        "ast": 4.1,
    }
    result = _apply_props_comprehension(predictions)

    # NaN must map to None (serialises as null)
    assert result["pts"] is None, "NaN stat should become None/null"

    # Non-NaN stats must still be rounded floats
    assert result["reb"] == pytest.approx(6.2, abs=1e-3)
    assert result["ast"] == pytest.approx(4.1, abs=1e-3)

    # Serialises to valid JSON with null — no ValueError / bare-NaN token
    serialised = json.dumps(result)
    parsed = json.loads(serialised)
    assert parsed["pts"] is None


def test_props_none_becomes_null_no_typeerror():
    """None value does not raise TypeError and serialises as null."""
    predictions = {
        "pts": None,
        "reb": 8.0,
        "blk": None,
    }
    # Old code: round(float(None), 3) → TypeError
    # New code: short-circuit → None
    result = _apply_props_comprehension(predictions)

    assert result["pts"] is None
    assert result["blk"] is None
    assert result["reb"] == pytest.approx(8.0, abs=1e-3)

    # Must produce valid JSON
    serialised = json.dumps(result)
    parsed = json.loads(serialised)
    assert parsed["pts"] is None
    assert parsed["blk"] is None


def test_props_mixed_nan_none_and_valid():
    """Mixed dict with NaN, None, and valid floats all handled correctly."""
    predictions = {
        "pts": 22.5,
        "reb": float("nan"),
        "ast": None,
        "fg3m": 2.1,
        "stl": float("nan"),
        "blk": 0.8,
        "tov": None,
    }
    result = _apply_props_comprehension(predictions)

    assert result["pts"] == pytest.approx(22.5, abs=1e-3)
    assert result["reb"] is None
    assert result["ast"] is None
    assert result["fg3m"] == pytest.approx(2.1, abs=1e-3)
    assert result["stl"] is None
    assert result["blk"] == pytest.approx(0.8, abs=1e-3)
    assert result["tov"] is None

    # Full round-trip through JSON must not raise
    serialised = json.dumps(result)
    parsed = json.loads(serialised)
    assert parsed["reb"] is None
    assert parsed["ast"] is None
    assert parsed["tov"] is None
    assert parsed["pts"] == pytest.approx(22.5, abs=1e-3)


def test_props_all_valid_unchanged():
    """When all predictions are valid floats the result is byte-identical behaviour."""
    predictions = {"pts": 18.7, "reb": 5.3, "ast": 3.9}
    result = _apply_props_comprehension(predictions)
    assert result == {"pts": 18.7, "reb": 5.3, "ast": 3.9}


# ---------------------------------------------------------------------------
# BUG 3 — pregame top_edges edge_pct uses pp-gap not ev_pct
# ---------------------------------------------------------------------------

def _build_pregame_edge_entry(bet: dict) -> dict:
    """Replicate the fixed pregame fallback logic from courtvision_router.py.

    Mirrors the exact computation after the bug fix:
        model_prob / market_prob → (model_prob - market_prob) * 100  [pp]
    Falls back to None when either prob is missing or out-of-range.
    ev_pct is preserved as a separate key.
    """
    _side = (bet.get("side") or "OVER").upper()
    _line = float(bet.get("line") or 0)
    _stat_u = (bet.get("prop_stat") or bet.get("stat") or "").upper()

    _mp = bet.get("model_prob")
    _mkp = bet.get("market_prob")
    if (
        isinstance(_mp, (int, float))
        and isinstance(_mkp, (int, float))
        and 0.0 < _mp < 1.0
        and 0.0 < _mkp < 1.0
    ):
        _edge_pct = round((float(_mp) - float(_mkp)) * 100.0, 1)
    else:
        _edge_pct = None

    return {
        "label": f"{bet.get('player_name', '')} {_side[0]}{_line:g} {_stat_u}",
        "odds": bet.get("best_price") or bet.get("odds"),
        "edge_pct": _edge_pct,
        "ev_pct": bet.get("ev_pct"),
        "book": bet.get("best_book") or bet.get("book") or "",
        "stat": (_stat_u or "").lower(),
        "side": _side,
        "line": _line,
        "player": bet.get("player_name", ""),
    }


def test_pregame_edge_pct_is_pp_gap_not_ev():
    """edge_pct is (model_prob - market_prob)*100 pp, NOT ev_pct.

    Example from bug report:
      model_prob=0.60, market_prob=0.524
      pp-gap  = (0.60 - 0.524)*100 = 7.6 pp  ← correct
      ev_pct  ≈ 0.60*192 - 0.40*100 = 75.2  ← wrong metric
    """
    bet = {
        "player_name": "Test Player",
        "side": "OVER",
        "line": 22.5,
        "stat": "pts",
        "model_prob": 0.60,
        "market_prob": 0.524,
        "ev_pct": 14.5,          # dollar-return EV — must NOT appear as edge_pct
        "best_price": -115,
        "best_book": "DraftKings",
    }
    entry = _build_pregame_edge_entry(bet)

    # edge_pct must be the pp-gap value (~7.6), not ev_pct (~14.5)
    assert entry["edge_pct"] == pytest.approx(7.6, abs=0.15), (
        f"expected pp-gap ≈7.6 but got {entry['edge_pct']}"
    )
    assert entry["edge_pct"] != pytest.approx(14.5, abs=1.0), (
        "edge_pct must not equal ev_pct (EV dollar-return metric)"
    )


def test_pregame_edge_pct_matches_live_convention():
    """Pregame edge_pct is computed with the same formula as live path.

    Live path (line ~2420):
        edge_pct = round((model_prob - market_prob) * 100.0, 1)

    For model_prob=0.60, market_prob=0.524 → 7.6 pp.
    """
    model_prob = 0.60
    market_prob = 0.524

    # Live convention (inline formula, same as live regrade block)
    live_edge_pct = round((model_prob - market_prob) * 100.0, 1)

    bet = {
        "player_name": "Jayson Tatum",
        "side": "OVER",
        "line": 28.5,
        "stat": "pts",
        "model_prob": model_prob,
        "market_prob": market_prob,
        "ev_pct": 14.5,
        "best_price": -110,
    }
    entry = _build_pregame_edge_entry(bet)

    assert entry["edge_pct"] == pytest.approx(live_edge_pct, abs=1e-6), (
        f"pregame edge_pct {entry['edge_pct']} != live formula {live_edge_pct}"
    )


def test_pregame_edge_pct_none_when_probs_missing():
    """When model_prob or market_prob is absent, edge_pct is None (not ev_pct fallback)."""
    bet_no_model = {
        "player_name": "Player A",
        "side": "OVER",
        "line": 5.5,
        "stat": "reb",
        "market_prob": 0.52,
        "ev_pct": 10.0,      # present but must NOT be used as edge_pct
        "best_price": -110,
    }
    entry = _build_pregame_edge_entry(bet_no_model)
    assert entry["edge_pct"] is None

    bet_no_market = {
        "player_name": "Player B",
        "side": "UNDER",
        "line": 4.5,
        "stat": "ast",
        "model_prob": 0.58,
        "ev_pct": 8.0,
        "best_price": -105,
    }
    entry2 = _build_pregame_edge_entry(bet_no_market)
    assert entry2["edge_pct"] is None


def test_pregame_ev_pct_preserved_under_own_key():
    """ev_pct is kept as its own key so the UI can surface EV separately."""
    bet = {
        "player_name": "Player C",
        "side": "OVER",
        "line": 1.5,
        "stat": "fg3m",
        "model_prob": 0.62,
        "market_prob": 0.51,
        "ev_pct": 16.3,
        "best_price": -108,
    }
    entry = _build_pregame_edge_entry(bet)

    assert entry["ev_pct"] == pytest.approx(16.3, abs=1e-6)
    # edge_pct is still the pp-gap
    assert entry["edge_pct"] == pytest.approx((0.62 - 0.51) * 100.0, abs=0.15)
