"""Per-file test for go_live: eligibility gating (no double-count of
pm_trading), dedup idempotency, and a fixture live-record.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_go_live.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.live_edge.paper import bridge, go_live, tennis_model


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


def test_tennis_records_live_when_uncovered(tmp_path, monkeypatch):
    """Empty ledger -> tennis is eligible -> one bet lands in the real target
    path, executed=False, edge_claimed never set True."""
    lh = _write_line_history(tmp_path, "tennis", "2026-07-20", _TENNIS_ROWS)
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: 0.75)
    ledger_path = tmp_path / "clv_ledger.jsonl"
    manifest_path = tmp_path / "go_live_minted.jsonl"
    summary = go_live.run_go_live("2026-07-20", path=ledger_path, line_history_dir=lh,
                                   manifest_path=manifest_path)
    r = summary["results"]["tennis"]
    assert r["eligible"] is True
    assert r["n_recorded"] == 1
    rows = [json.loads(ln) for ln in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["executed"] is False
    assert "edge_claimed" not in rows[0] or rows[0].get("edge_claimed") is not True
    manifest_rows = [json.loads(ln) for ln in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert len(manifest_rows) == 1 and manifest_rows[0]["sport"] == "tennis"


def test_rerun_is_idempotent_no_duplicate(tmp_path, monkeypatch):
    """Second run on the same day, same odds -> the bet already recorded is
    skipped as a dup, not written twice."""
    lh = _write_line_history(tmp_path, "tennis", "2026-07-20", _TENNIS_ROWS)
    monkeypatch.setattr(tennis_model, "model_prob", lambda home, away, **kw: 0.75)
    ledger_path = tmp_path / "clv_ledger.jsonl"
    manifest_path = tmp_path / "go_live_minted.jsonl"
    go_live.run_go_live("2026-07-20", path=ledger_path, line_history_dir=lh,
                         manifest_path=manifest_path)
    summary2 = go_live.run_go_live("2026-07-20", path=ledger_path, line_history_dir=lh,
                                    manifest_path=manifest_path)
    r2 = summary2["results"]["tennis"]
    assert r2["n_recorded"] == 0
    assert r2["n_skipped_dup"] == 1
    rows = [json.loads(ln) for ln in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1  # still just the one bet, not two


def test_sport_already_covered_by_pm_trading_is_skipped(tmp_path, monkeypatch):
    """A ledger with a pre-existing non-us row for wnba today -> wnba is
    marked ineligible and nothing is built/recorded for it (avoids
    double-counting pm_trading's own mint)."""
    ledger_path = tmp_path / "clv_ledger.jsonl"
    existing = {"sport": "wnba", "game_date": "2026-07-20", "channel": "pm_trading",
                "status": "open", "bet_id": "existing-1"}
    ledger_path.write_text(json.dumps(existing) + "\n", encoding="utf-8")
    lh = tmp_path / "lh_empty"
    manifest_path = tmp_path / "go_live_minted.jsonl"
    summary = go_live.run_go_live("2026-07-20", path=ledger_path, line_history_dir=lh,
                                   manifest_path=manifest_path)
    r = summary["results"]["wnba"]
    assert r["eligible"] is False
    assert r["reason"] == "covered_by_pm_trading_today"
    assert r["n_recorded"] == 0


def test_empty_slate_is_honest_noop(tmp_path):
    """No line_history captured for the day -> zero rows built, zero
    recorded -- not a fabricated bet."""
    ledger_path = tmp_path / "clv_ledger.jsonl"
    lh = tmp_path / "lh_empty"
    manifest_path = tmp_path / "go_live_minted.jsonl"
    summary = go_live.run_go_live("2026-07-20", path=ledger_path, line_history_dir=lh,
                                   manifest_path=manifest_path)
    r = summary["results"]["tennis"]
    assert r["eligible"] is True
    assert r["n_total"] == 0
    assert r["n_recorded"] == 0
