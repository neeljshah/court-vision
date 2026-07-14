"""Per-file test for LIVE-EDGE slate_trader (tennis-wire + soccer/mlb verify).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_slate_trader.py -q
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.platformkit.live_edge.paper import slate_trader, tennis_model


def _write_line_history(tmp_path, sport, date, rows):
    d = tmp_path / sport
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


_TENNIS_ROWS = [
    {"sport": "tennis", "game_id": "T1", "home": "Player Home", "away": "Player Away",
     "market_type": "moneyline", "side": "home", "line": None, "odds": 1.8,
     "book": "pinnacle", "devigged_prob": 0.60,
     "captured_at": "2026-07-20T10:00:00+00:00", "commence_time": "2026-07-20T19:00Z"},
    {"sport": "tennis", "game_id": "T1", "home": "Player Home", "away": "Player Away",
     "market_type": "moneyline", "side": "away", "line": None, "odds": 2.0,
     "book": "pinnacle", "devigged_prob": 0.40,
     "captured_at": "2026-07-20T10:00:00+00:00", "commence_time": "2026-07-20T19:00Z"},
]


def test_build_tennis_shadow_rows_uses_real_model_hook(tmp_path, monkeypatch):
    """model_prob is called with (home, away) from the real capture row and
    its return value lands as conditioned_pred -- never the market price."""
    lh = _write_line_history(tmp_path, "tennis", "2026-07-20", _TENNIS_ROWS)
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: 0.75)
    rows = slate_trader.build_tennis_shadow_rows("2026-07-20", line_history_dir=lh)
    assert len(rows) == 1
    r = rows[0]
    assert r["sport"] == "tennis" and r["game"] == "T1"
    assert r["conditioned_pred"] == 0.75
    assert r["market_price"] == 0.60
    assert r["conditioned_pred"] != r["market_price"]  # the actual bug this fixes
    assert r["mechanism_applied"] == "tennis_elo_platt"


def test_build_tennis_shadow_rows_skips_when_model_returns_none(tmp_path, monkeypatch):
    lh = _write_line_history(tmp_path, "tennis", "2026-07-20", _TENNIS_ROWS)
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: None)
    rows = slate_trader.build_tennis_shadow_rows("2026-07-20", line_history_dir=lh)
    assert rows == []  # honest skip, never fabricated


def test_run_sport_slate_tennis_full_chain(tmp_path, monkeypatch):
    """End-to-end: real-shaped odds capture -> model -> resolve -> select ->
    record, all through the UNMODIFIED bridge chain. Divergence 0.75 vs 0.60
    clears the default 0.03 threshold -> a bet is recorded."""
    lh = _write_line_history(tmp_path, "tennis", "2026-07-20", _TENNIS_ROWS)
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: 0.75)
    monkeypatch.setattr(slate_trader, "_PAPER_DIR", tmp_path)
    out = slate_trader.run_sport_slate("tennis", "2026-07-20", line_history_dir=lh)
    assert out["n_total"] == 1
    assert out["resolution_rate"] == 1.0
    assert out["n_recorded"] == 1
    bet = out["sample_bet"]
    assert bet["side"] == "home" and bet["executed"] is False
    assert bet["channel"] == "paper_live_edge"


def test_run_sport_slate_market_echo_never_selects(tmp_path, monkeypatch):
    """Model prob == market price (the observed live bug for today's real
    shadow feed) -> divergence is exactly 0 -> not_selected, by construction."""
    lh = _write_line_history(tmp_path, "tennis", "2026-07-20", _TENNIS_ROWS)
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: 0.60)
    monkeypatch.setattr(slate_trader, "_PAPER_DIR", tmp_path)
    out = slate_trader.run_sport_slate("tennis", "2026-07-20", line_history_dir=lh)
    assert out["n_recorded"] == 0
    assert out["statuses"].get("not_selected") == 1


def test_load_existing_shadow_rows_filters_by_sport(tmp_path):
    shadow_dir = tmp_path
    rows = [{"sport": "mlb", "game": "M1"}, {"sport": "tennis", "game": "T1"}]
    (shadow_dir / "2026-07-20.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = slate_trader.load_existing_shadow_rows("mlb", "2026-07-20", shadow_dir=shadow_dir)
    assert out == [{"sport": "mlb", "game": "M1"}]


def test_render_report_mentions_edge_claimed_false():
    report = slate_trader.render_report([
        {"sport": "tennis", "date": "2026-07-20", "n_total": 1, "n_resolved": 1,
         "resolution_rate": 1.0, "n_selected": 1, "n_recorded": 1,
         "statuses": {"recorded": 1}, "sample_bet": None, "path": "x", "live": False},
    ])
    assert "edge_claimed=False" in report


def test_real_tennis_slice_resolution_rate_ge_95pct(monkeypatch):
    """ID-JOIN evidence: real on-disk tennis odds for 2026-07-14 resolve via
    the exact provenance join (never a fuzzy name match). Model is stubbed
    here so this test doesn't pay the ~9s corpus-replay cost -- resolution is
    about identity, not model accuracy. Skips honestly if data/ is absent
    (gitignored, not present in a fresh clone)."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    lh_dir = repo_root / "data" / "cache" / "line_history"
    if not (lh_dir / "tennis" / "2026-07-14.jsonl").is_file():
        pytest.skip("2026-07-14 tennis line_history not present in this clone")
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: 0.5)
    rows = slate_trader.build_tennis_shadow_rows("2026-07-14", line_history_dir=lh_dir)
    assert rows, "expected real tennis shadow rows built from 2026-07-14 odds"
    from scripts.platformkit.live_edge.paper.resolve_identity import resolve_identity
    n_resolved = sum(1 for r in rows if resolve_identity(r, line_history_dir=lh_dir) is not None)
    rate = n_resolved / len(rows)
    assert rate >= 0.95, f"tennis resolution rate {rate:.3f} on {len(rows)} matches is below 95%"
