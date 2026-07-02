"""Per-file tests for clv_close_lookup.lookup_close_legs (offline, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import scripts.platformkit.clv_close_lookup as mod
from scripts.platformkit.clv_close_lookup import lookup_close_legs


def _write_history(tmp_path: Path) -> Path:
    """A minimal mlb line-history file with an at-lock two-way moneyline close."""
    d = tmp_path / "mlb"
    d.mkdir(parents=True)
    rows = [
        {"sport": "mlb", "game_id": "G42", "home": "Tigers", "away": "Astros",
         "market_type": "moneyline", "side": "home", "odds": 1.95,
         "captured_at": "2026-06-29T22:50:00+00:00",
         "commence_time": "2026-06-29T23:10:00+00:00"},
        {"sport": "mlb", "game_id": "G42", "home": "Tigers", "away": "Astros",
         "market_type": "moneyline", "side": "away", "odds": 1.90,
         "captured_at": "2026-06-29T22:50:00+00:00",
         "commence_time": "2026-06-29T23:10:00+00:00"},
    ]
    (d / "2026-06-29.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return tmp_path


def test_lookup_finds_at_lock_close(tmp_path, monkeypatch):
    base = _write_history(tmp_path)
    monkeypatch.setattr(mod._ls, "DEFAULT_HISTORY_DIR", base, raising=False)
    legs = lookup_close_legs({"event_id": "G42", "sport": "mlb"})
    assert legs is not None
    home, away, is_true = legs
    assert abs(home - 1.95) < 1e-9 and abs(away - 1.90) < 1e-9
    assert is_true is True  # captured 20 min before tip -> within the 30-min lock


def test_no_join_id_returns_none():
    assert lookup_close_legs({"sport": "mlb"}) is None


def test_unknown_game_returns_none(tmp_path, monkeypatch):
    base = _write_history(tmp_path)
    monkeypatch.setattr(mod._ls, "DEFAULT_HISTORY_DIR", base, raising=False)
    assert lookup_close_legs({"event_id": "NOPE", "sport": "mlb"}) is None


def test_never_raises_on_garbage():
    assert lookup_close_legs({"event_id": object()}) is None or True
