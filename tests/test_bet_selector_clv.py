"""
test_bet_selector_clv.py -- Tests for the dual edge+CLV filter (16.5-03).

Acceptance criterion: bet_selector applies a dual filter
(edge > 4% AND predicted CLV > 1.5%); bets below the CLV threshold are dropped.
"""

from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction import bet_selector  # noqa: E402

_CFG = {
    "edge_min": 0.04,
    "bankroll": 1000.0,
    "clv_min": 1.5,
    "clv_filter_enabled": True,
    "max_bets_per_game": 10,
    "max_combined_pct": 0.5,
    "default_odds": -110,
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirect bet_selector output + config to a temp sandbox."""
    monkeypatch.setattr(bet_selector, "_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(bet_selector, "_BET_LOG_PATH", str(tmp_path / "bet_log.json"))
    monkeypatch.setattr(bet_selector, "_load_config", lambda: dict(_CFG))


def _edge_row(player: str, edge: float, game_id: str = "G1") -> dict:
    return {
        "player": player, "stat": "pts", "edge": edge,
        "book_line": 25.0, "projection": 27.0, "odds": -110,
        "game_id": game_id, "confidence": "high",
        "team": "BOS", "opp_team": "NYK",
    }


def _clv_fn_by_edge(feats: dict) -> dict:
    """Deterministic stub: strong edges get high predicted CLV, weak ones low."""
    high = feats["our_edge"] >= 0.07
    prob = 0.62 if high else 0.505
    return {
        "clv_prob": prob,
        "clv_label": int(prob >= 0.5),
        "expected_clv": (prob - 0.5) * 100.0,   # 12.0% high / 0.5% low
    }


# ── tests ─────────────────────────────────────────────────────────────────────

def test_dual_filter_drops_low_clv_bets():
    """A bet that clears the 4% edge bar but not the 1.5% CLV bar is dropped."""
    rows = [
        _edge_row("Star A", 0.08),   # edge ok, CLV 12.0% -> keep
        _edge_row("Star B", 0.06),   # edge ok, CLV 0.5%  -> drop
    ]
    bets = bet_selector.select(
        rows, "2026-05-21", dry_run=True, clv_predict_fn=_clv_fn_by_edge,
    )
    assert len(bets) == 1
    assert bets[0]["player"] == "Star A"


def test_edge_filter_still_applies():
    """A sub-4% edge is dropped before the CLV gate is ever consulted."""
    calls: list = []

    def tracking_fn(feats):
        calls.append(feats)
        return {"clv_prob": 0.9, "clv_label": 1, "expected_clv": 40.0}

    rows = [_edge_row("Weak Edge", 0.02)]   # below edge_min
    bets = bet_selector.select(
        rows, "2026-05-21", dry_run=True, clv_predict_fn=tracking_fn,
    )
    assert bets == []
    assert calls == []   # CLV predictor not even called for a sub-edge bet


def test_high_clv_and_high_edge_kept():
    """A bet clearing both bars is selected and carries CLV fields."""
    rows = [_edge_row("Star A", 0.09)]
    bets = bet_selector.select(
        rows, "2026-05-21", dry_run=True, clv_predict_fn=_clv_fn_by_edge,
    )
    assert len(bets) == 1
    bet = bets[0]
    assert bet["predicted_clv"] == pytest.approx(12.0)
    assert bet["clv_prob"] == pytest.approx(0.62)


def test_clv_gate_skipped_when_no_model(tmp_path):
    """With no trained model, bet_selector falls back to edge-only filtering."""
    rows = [_edge_row("Star A", 0.08), _edge_row("Star B", 0.06)]
    bets = bet_selector.select(
        rows, "2026-05-21", dry_run=True,
        clv_model_path=str(tmp_path / "does_not_exist.pkl"),
    )
    # Both clear the edge bar; no CLV model -> both kept.
    assert len(bets) == 2


def test_clv_prediction_error_keeps_bet():
    """A predictor that raises must not abort the slate — the bet is kept."""
    def boom(feats):
        raise RuntimeError("model exploded")

    rows = [_edge_row("Star A", 0.08)]
    bets = bet_selector.select(
        rows, "2026-05-21", dry_run=True, clv_predict_fn=boom,
    )
    assert len(bets) == 1
    assert bets[0]["player"] == "Star A"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
