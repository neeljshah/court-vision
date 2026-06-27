"""Per-file test for pm_close_capture -- the PM/Kalshi close sweep.

Fully offline (temp ledger + injected capture_fn). Pins: only CONFIRMED (non-proxy)
closes are stamped (true_close, clv_is_proxy=False); a proxy/open market is counted but
NEVER written; a row with no event_id or an already-resolved row is skipped (idempotent);
outcome/unit_result are preserved. No network.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/pm_trading/test_pm_close_capture.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.pm_trading import pm_close_capture as P
from scripts.platformkit.pm_trading.close_capture import CloseResult


def _row(bet_id, *, event_id="KXMLBGAME-X", clv_pct=None, is_proxy=True, outcome="win"):
    return {"channel": "paper_pm", "status": "settled", "is_pm": True,
            "sport": "mlb", "side": "home", "taken_decimal": 2.0, "bet_id": bet_id,
            "event_id": event_id, "outcome": outcome, "unit_result": 1.0,
            "clv_pct": clv_pct, "clv_is_proxy": is_proxy}


def _write(tmp_path, rows):
    p = tmp_path / "clv.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _confirmed_close(row, *, kalshi_fetch=None):
    return CloseResult(close_home_dec=1.80, close_away_dec=2.10,
                       is_proxy=False, close_source="kalshi")


def _proxy_close(row, *, kalshi_fetch=None):
    return CloseResult(close_home_dec=1.80, close_away_dec=2.10,
                       is_proxy=True, close_source="proxy")


def test_stamps_confirmed_close(tmp_path):
    p = _write(tmp_path, [_row("pm|kalshi|g1|home")])
    out = P.sweep_closes(p, capture_fn=_confirmed_close)
    assert out["n_targets"] == 1 and out["n_captured"] == 1
    assert out["executed"] is False
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    settled = [r for r in rows if r.get("clv_pct") is not None]
    assert settled, "a settled twin with clv_pct should be appended"
    s = settled[-1]
    assert s["clv_is_proxy"] is False and s["clv_status"] == "true_close"
    assert s["outcome"] == "win" and s["unit_result"] == 1.0   # preserved


def test_proxy_close_is_counted_not_written(tmp_path):
    p = _write(tmp_path, [_row("pm|kalshi|g2|home")])
    out = P.sweep_closes(p, capture_fn=_proxy_close)
    assert out["n_proxy"] == 1 and out["n_captured"] == 0
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert all(r.get("clv_pct") is None for r in rows)   # nothing fabricated


def test_skips_no_event_id_and_already_resolved(tmp_path):
    rows = [_row("pm|a", event_id=""),                       # no event_id -> skip
            _row("pm|b", clv_pct=4.2, is_proxy=False)]        # already resolved -> skip
    p = _write(tmp_path, rows)
    out = P.sweep_closes(p, capture_fn=_confirmed_close)
    assert out["n_targets"] == 0 and out["n_captured"] == 0


def test_no_close_available_is_honest(tmp_path):
    p = _write(tmp_path, [_row("pm|g3|home")])
    out = P.sweep_closes(p, capture_fn=lambda r, **k: None)
    assert out["n_no_close"] == 1 and out["n_captured"] == 0
