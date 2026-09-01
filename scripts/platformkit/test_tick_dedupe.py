import json

import pytest

from scripts.platformkit.tick_dedupe import assert_no_duplicate_stores, load_ticks_deduped


def _tick(game="KXMLBGAME-1"):
    return {"game_id": game, "ts": "2026-08-01T00:00:00Z", "model_prob": .6,
            "market_prob": .55, "outcome": 1, "state_summary": {"home_score": 1, "away_score": 0}}


def test_loader_drops_natural_key_duplicates_and_reports_counts(tmp_path):
    (tmp_path / "one.jsonl").write_text(json.dumps(_tick()) + "\n", encoding="utf-8")
    (tmp_path / "two.jsonl").write_text(json.dumps(_tick()) + "\n", encoding="utf-8")
    records, report = load_ticks_deduped(tmp_path)
    assert len(records) == 1
    assert report == {"raw_count": 2, "deduped_count": 1, "duplicate_pct": 50.0,
                      "stores_seen": ["."]}


def test_duplicate_store_guard_rejects_matching_file_sets(tmp_path):
    for name in ("mlb", "mlb_clean"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "ticks.jsonl").write_text(json.dumps(_tick()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate tick stores"):
        assert_no_duplicate_stores(tmp_path)
