"""Per-file test: scripts.platformkit.paper.prediction_close_attach.

Offline only -- writes a synthetic line_history tree under tmp_path, never
touches the real data/cache/line_history/ corpus or the network.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.paper import prediction_close_attach as pca

_HOME_TEAM = "Cincinnati Reds"
_AWAY_TEAM = "New York Mets"


def _write_history(base: Path, sport: str, date: str, rows) -> None:
    d = base / sport
    d.mkdir(parents=True, exist_ok=True)
    with (d / ("%s.jsonl" % date)).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(event_id="E1", selection=_HOME_TEAM, fair_odds=1.8):
    return {"sport": "mlb", "event_id": event_id, "selection": selection,
            "fair_odds": fair_odds}


def test_true_close_when_moneyline_captured_at_lock(tmp_path: Path):
    _write_history(tmp_path, "mlb", "2026-07-05", [
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "home",
         "odds": 1.75, "captured_at": "2026-07-05T23:50:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "away",
         "odds": 2.20, "captured_at": "2026-07-05T23:50:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
    ])
    out = pca.attach_true_close(_row(), _HOME_TEAM, _AWAY_TEAM,
                                line_history_base=tmp_path)
    assert out["clv_status"] == "true_close"
    assert out["clv_is_proxy"] is False
    assert out["clv_pct"] is not None
    assert out["beat_close"] is not None


def test_no_true_close_when_only_stale_quote(tmp_path: Path):
    """A quote captured HOURS before tip (outside the lock window) is not a
    true close -- honestly falls back to NO_TRUE_CLOSE, never fabricated."""
    _write_history(tmp_path, "mlb", "2026-07-05", [
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "home",
         "odds": 1.75, "captured_at": "2026-07-05T10:00:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "away",
         "odds": 2.20, "captured_at": "2026-07-05T10:00:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
    ])
    out = pca.attach_true_close(_row(), _HOME_TEAM, _AWAY_TEAM,
                                line_history_base=tmp_path)
    assert out == pca.NO_TRUE_CLOSE


def test_no_history_at_all_stays_no_true_close(tmp_path: Path):
    out = pca.attach_true_close(_row(event_id="E_NEVER_SEEN"), _HOME_TEAM,
                                _AWAY_TEAM, line_history_base=tmp_path)
    assert out == pca.NO_TRUE_CLOSE


def test_non_moneyline_selection_out_of_scope(tmp_path: Path):
    """A derived-market selection (not a literal team name) never qualifies --
    same scope boundary as grade_predictions._clv_from_proxy."""
    _write_history(tmp_path, "mlb", "2026-07-05", [
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "home",
         "odds": 1.75, "captured_at": "2026-07-05T23:50:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "away",
         "odds": 2.20, "captured_at": "2026-07-05T23:50:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
    ])
    row = _row(selection="Over 6.5")
    out = pca.attach_true_close(row, _HOME_TEAM, _AWAY_TEAM,
                                line_history_base=tmp_path)
    assert out == pca.NO_TRUE_CLOSE


def test_missing_event_id_stays_no_true_close(tmp_path: Path):
    out = pca.attach_true_close({"selection": _HOME_TEAM, "fair_odds": 1.8},
                                _HOME_TEAM, _AWAY_TEAM, line_history_base=tmp_path)
    assert out == pca.NO_TRUE_CLOSE


def test_degenerate_close_falls_back_honestly(tmp_path: Path):
    """A booksum<1 close (arb/degenerate) raises inside the Shin devig -- caught,
    never crashes, falls back to NO_TRUE_CLOSE (mirrors the proxy path's guard)."""
    _write_history(tmp_path, "mlb", "2026-07-05", [
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "home",
         "odds": 1.75, "captured_at": "2026-07-05T23:50:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
        {"sport": "mlb", "game_id": "E1", "market_type": "moneyline", "side": "away",
         "odds": 9.0, "captured_at": "2026-07-05T23:50:00+00:00",
         "commence_time": "2026-07-06T00:00Z"},
    ])
    out = pca.attach_true_close(_row(), _HOME_TEAM, _AWAY_TEAM,
                                line_history_base=tmp_path)
    assert out == pca.NO_TRUE_CLOSE
