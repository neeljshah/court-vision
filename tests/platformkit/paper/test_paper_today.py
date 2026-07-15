"""Per-file test: scripts.platformkit.paper.paper_today -- execution block +
prop-field regression on the digest's placed rows.

Run: python -m pytest tests/platformkit/paper/test_paper_today.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.paper import paper_today as pt


def _write_ledger(path: Path, rows: list) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _prop_row(**over) -> dict:
    row = {
        "sport": "mlb", "matchup": "CIN @ COL", "taken_decimal": 1.91,
        "market_type": "prop", "market": "prop", "prop_player": "Ildemaro Vargas",
        "prop_stat": "hits", "prop_side": "under", "line": 0.5,
        "market_prob": 0.55, "model_prob": 0.60, "tier": "B", "stake_units": 1.0,
        "event_id": "G1", "ts": "2026-07-10T00:00:00Z", "status": "open",
    }
    row.update(over)
    return row


def test_build_today_includes_execution_block(tmp_path):
    """build_today's digest carries an 'execution' block, even with no ledger."""
    ledger = tmp_path / "clv_ledger.jsonl"
    _write_ledger(ledger, [])
    bankroll = tmp_path / "bankroll.json"

    doc = pt.build_today(clv_path=ledger, start_units=0.0, bankroll_path=bankroll)

    assert "execution" in doc
    ex = doc["execution"]
    assert "by_market_type" in ex and "quality" in ex
    assert ex["quality"]["n_gated"] == 0
    assert ex["quality"]["avg_expected_clv_pct"] is None  # never fabricated


def test_build_today_execution_groups_by_market_type(tmp_path):
    """Placed rows of different market_type each get their own breaker entry."""
    ledger = tmp_path / "clv_ledger.jsonl"
    _write_ledger(ledger, [
        _prop_row(),
        {"sport": "nba", "matchup": "BOS @ MIA", "taken_decimal": 1.87,
         "market_type": "moneyline", "market": "moneyline", "ts": "2026-07-11T00:00:00Z",
         "status": "open", "event_id": "G2"},
    ])
    bankroll = tmp_path / "bankroll.json"

    doc = pt.build_today(clv_path=ledger, start_units=0.0, bankroll_path=bankroll)
    by_mt = doc["execution"]["by_market_type"]
    assert "prop" in by_mt and "moneyline" in by_mt
    for entry in by_mt.values():
        assert entry["state"] in ("LIVE", "CAPPED", "UNKNOWN")


def test_build_today_execution_carries_realized_ingame_and_thresholds(tmp_path):
    """New blocks present (possibly null if the modules aren't importable), never
    fabricated -- just checking the keys exist so the frontend has a stable shape."""
    ledger = tmp_path / "clv_ledger.jsonl"
    _write_ledger(ledger, [])
    bankroll = tmp_path / "bankroll.json"

    doc = pt.build_today(clv_path=ledger, start_units=0.0, bankroll_path=bankroll)

    ex = doc["execution"]
    assert "realized_ingame" in ex
    assert "thresholds" in ex
    # thresholds module is a same-lane dependency that already exists on disk --
    # assert its real pre-registered values surface, not just presence.
    if ex["thresholds"] is not None:
        assert ex["thresholds"]["prop_expected_clv_min_pct"] == 1.0
        assert ex["thresholds"]["ingame_max_spread_bp"] == 800.0


def test_placed_rows_keep_prop_identity_fields(tmp_path):
    """Regression: a placed prop row must not lose prop_player/prop_stat/prop_side/
    line -- the game-detail 'AWAY'-only bug root cause. paper_today's own
    _PLACED_FIELDS already carries these; assert they survive to the served row.
    """
    ledger = tmp_path / "clv_ledger.jsonl"
    today = "2026-07-10"
    _write_ledger(ledger, [_prop_row(game_date="2026-07-10T18:00:00Z")])
    bankroll = tmp_path / "bankroll.json"

    doc = pt.build_today(
        clv_path=ledger, start_units=0.0, today=today, bankroll_path=bankroll,
    )
    all_placed = doc["placed"] + doc["pending"]
    assert len(all_placed) >= 1
    row = all_placed[0]
    assert row["prop_player"] == "Ildemaro Vargas"
    assert row["prop_stat"] == "hits"
    assert row["prop_side"] == "under"
    assert row["line"] == 0.5
