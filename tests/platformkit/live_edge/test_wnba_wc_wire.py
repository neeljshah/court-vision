"""Per-file test for WNBA + World-Cup/soccer wiring into slate_trader.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_wnba_wc_wire.py -q
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.platformkit.live_edge.paper import slate_trader, soccer_model, wnba_model


def _write_line_history(tmp_path, sport, date, rows):
    d = tmp_path / sport
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


_WNBA_ROWS = [
    {"sport": "wnba", "game_id": "W1", "home": "Atlanta Dream", "away": "Las Vegas Aces",
     "market_type": "moneyline", "side": "home", "line": None, "odds": 2.0,
     "book": "espn:DraftKings", "devigged_prob": 0.50,
     "captured_at": "2026-07-20T10:00:00+00:00", "commence_time": "2026-07-20T23:00Z"},
    {"sport": "wnba", "game_id": "W1", "home": "Atlanta Dream", "away": "Las Vegas Aces",
     "market_type": "moneyline", "side": "away", "line": None, "odds": 2.0,
     "book": "espn:DraftKings", "devigged_prob": 0.50,
     "captured_at": "2026-07-20T10:00:00+00:00", "commence_time": "2026-07-20T23:00Z"},
]

_SOCCER_INTL_ROWS = [
    {"sport": "soccer_intl", "game_id": "S1", "home": "France", "away": "Spain",
     "market_type": "moneyline", "side": "home", "line": None, "odds": 2.4,
     "book": "espn:DraftKings", "devigged_prob": 0.55,
     "captured_at": "2026-07-20T10:00:00+00:00", "commence_time": "2026-07-20T19:00Z"},
    {"sport": "soccer_intl", "game_id": "S1", "home": "France", "away": "Spain",
     "market_type": "moneyline", "side": "away", "line": None, "odds": 3.5,
     "book": "espn:DraftKings", "devigged_prob": 0.45,
     "captured_at": "2026-07-20T10:00:00+00:00", "commence_time": "2026-07-20T19:00Z"},
]


def test_build_wnba_shadow_rows_uses_real_model_hook(tmp_path, monkeypatch):
    lh = _write_line_history(tmp_path, "wnba", "2026-07-20", _WNBA_ROWS)
    monkeypatch.setattr(wnba_model, "model_prob", lambda home, away: 0.70)
    rows = slate_trader.build_wnba_shadow_rows("2026-07-20", line_history_dir=lh)
    assert len(rows) == 1
    r = rows[0]
    assert r["sport"] == "wnba" and r["game"] == "W1"
    assert r["conditioned_pred"] == 0.70
    assert r["market_price"] == 0.50
    assert r["conditioned_pred"] != r["market_price"]
    assert r["mechanism_applied"] == "wnba_elo"


def test_build_wnba_shadow_rows_skips_when_model_returns_none(tmp_path, monkeypatch):
    lh = _write_line_history(tmp_path, "wnba", "2026-07-20", _WNBA_ROWS)
    monkeypatch.setattr(wnba_model, "model_prob", lambda home, away: None)
    rows = slate_trader.build_wnba_shadow_rows("2026-07-20", line_history_dir=lh)
    assert rows == []


def test_run_sport_slate_wnba_full_chain(tmp_path, monkeypatch):
    lh = _write_line_history(tmp_path, "wnba", "2026-07-20", _WNBA_ROWS)
    monkeypatch.setattr(wnba_model, "model_prob", lambda home, away: 0.70)
    monkeypatch.setattr(slate_trader, "_PAPER_DIR", tmp_path)
    out = slate_trader.run_sport_slate("wnba", "2026-07-20", line_history_dir=lh)
    assert out["n_total"] == 1
    assert out["resolution_rate"] == 1.0
    assert out["n_recorded"] == 1
    bet = out["sample_bet"]
    assert bet["side"] == "home" and bet["executed"] is False
    assert bet["channel"] == "paper_live_edge"


def test_build_soccer_intl_shadow_rows_uses_real_model_hook(tmp_path, monkeypatch):
    lh = _write_line_history(tmp_path, "soccer_intl", "2026-07-20", _SOCCER_INTL_ROWS)
    monkeypatch.setattr(soccer_model, "model_prob", lambda home, away, **kw: 0.65)
    rows = slate_trader.build_soccer_shadow_rows("soccer_intl", "2026-07-20", line_history_dir=lh)
    assert len(rows) == 1
    r = rows[0]
    assert r["sport"] == "soccer_intl" and r["game"] == "S1"
    assert r["conditioned_pred"] == 0.65
    assert r["market_price"] == 0.55
    assert r["mechanism_applied"] == "soccer_intl_dixon_coles_platt"


def test_run_sport_slate_soccer_intl_full_chain(tmp_path, monkeypatch):
    lh = _write_line_history(tmp_path, "soccer_intl", "2026-07-20", _SOCCER_INTL_ROWS)
    monkeypatch.setattr(soccer_model, "model_prob", lambda home, away, **kw: 0.65)
    monkeypatch.setattr(slate_trader, "_PAPER_DIR", tmp_path)
    out = slate_trader.run_sport_slate("soccer_intl", "2026-07-20", line_history_dir=lh)
    assert out["n_total"] == 1
    assert out["resolution_rate"] == 1.0
    assert out["n_recorded"] == 1
    bet = out["sample_bet"]
    assert bet["side"] == "home" and bet["executed"] is False


def test_real_wnba_slice_resolution_rate_ge_95pct(monkeypatch):
    """Real on-disk wnba odds for 2026-07-14 resolve via the exact provenance
    join. Model stubbed -- resolution is about identity, not model accuracy.
    Skips honestly if data/ is absent (gitignored, not present in a fresh
    clone)."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    lh_dir = repo_root / "data" / "cache" / "line_history"
    if not (lh_dir / "wnba" / "2026-07-14.jsonl").is_file():
        pytest.skip("2026-07-14 wnba line_history not present in this clone")
    monkeypatch.setattr(wnba_model, "model_prob", lambda home, away: 0.5)
    rows = slate_trader.build_wnba_shadow_rows("2026-07-14", line_history_dir=lh_dir)
    assert rows, "expected real wnba shadow rows built from 2026-07-14 odds"
    from scripts.platformkit.live_edge.paper.resolve_identity import resolve_identity
    n_resolved = sum(1 for r in rows if resolve_identity(r, line_history_dir=lh_dir) is not None)
    rate = n_resolved / len(rows)
    assert rate >= 0.95, f"wnba resolution rate {rate:.3f} on {len(rows)} matches is below 95%"


def test_real_soccer_intl_slice_resolution_rate_ge_95pct(monkeypatch):
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    lh_dir = repo_root / "data" / "cache" / "line_history"
    if not (lh_dir / "soccer_intl" / "2026-07-14.jsonl").is_file():
        pytest.skip("2026-07-14 soccer_intl line_history not present in this clone")
    monkeypatch.setattr(soccer_model, "model_prob", lambda home, away, **kw: 0.5)
    rows = slate_trader.build_soccer_shadow_rows("soccer_intl", "2026-07-14", line_history_dir=lh_dir)
    assert rows, "expected real soccer_intl shadow rows built from 2026-07-14 odds"
    from scripts.platformkit.live_edge.paper.resolve_identity import resolve_identity
    n_resolved = sum(1 for r in rows if resolve_identity(r, line_history_dir=lh_dir) is not None)
    rate = n_resolved / len(rows)
    assert rate >= 0.95, f"soccer_intl resolution rate {rate:.3f} on {len(rows)} matches is below 95%"
