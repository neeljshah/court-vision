"""Synthetic checks for the in-game replay scoreboard."""
import json

import pytest

from scripts.platformkit.ingame_replay_scoreboard import (discover_store, load_ticks,
                                                            score_ticks)


def _tick(game, index, model, market, outcome):
    return {"game_id": game, "ts": "2026-01-01T00:%02d:00Z" % index,
            "model_prob": model, "market_prob": market, "outcome": outcome}


def test_jsonl_quintile_briers_and_insufficient_flag(tmp_path):
    store = tmp_path / "ingame_grade_joined" / "mlb"
    store.mkdir(parents=True)
    records = []
    for bucket in range(5):
        records.extend(_tick("game-ok", bucket * 30 + index, 0.8, 0.6, 1.0)
                       for index in range(30))
    records.extend(_tick("game-small", index, 0.2, 0.3, 0.0) for index in range(10))
    path = store / "ticks.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")

    assert discover_store(tmp_path) == tmp_path / "ingame_grade_joined"
    rows = score_ticks(load_ticks(tmp_path / "ingame_grade_joined"))
    ok_rows = [row for row in rows if row["game"] == "game-ok"]
    assert len(ok_rows) == 5
    assert all(row["status"] == "OK" for row in ok_rows)
    assert [row["model_brier"] for row in ok_rows] == pytest.approx([0.04] * 5)
    assert [row["market_brier"] for row in ok_rows] == pytest.approx([0.16] * 5)
    small_rows = [row for row in rows if row["game"] == "game-small"]
    assert len(small_rows) == 5
    assert all(row["status"] == "INSUFFICIENT" for row in small_rows)
    assert all(row["model_brier"] is None for row in small_rows)
