"""Focused checks for the settled-tick baseline lock command."""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.ingame import ingame_baseline_lock as lock


def _row(game: str, index: int, model: float, market: float, outcome: int) -> dict[str, object]:
    return {"game_id": game, "ts": "2026-08-%02dT00:00:00Z" % (index + 1),
            "model_prob": model, "market_prob": market, "outcome": outcome}


def test_summarize_fingerprints_and_scores_settled_ticks(tmp_path) -> None:
    store = tmp_path / "ingame_grade_joined"
    store.mkdir()
    rows = [_row("game-a", 0, .8, .6, 1), _row("game-b", 1, .2, .4, 0)]
    (store / "ticks.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n",
                                        encoding="utf-8")

    report = lock.summarize(store)

    assert report["corpus"]["source_row_count"] == 2
    assert report["corpus"]["settled_tick_count"] == 2
    assert report["corpus"]["eligible_tick_count"] == 2
    assert report["corpus"]["game_count"] == 2
    assert report["corpus"]["date_range"] == {"min": "2026-08-01", "max": "2026-08-02"}
    assert len(report["corpus"]["file_hash"]) == 64
    assert report["delta_brier"] == pytest.approx(.12)
    assert report["gap_effective_n"] == 2
    assert report["verdict"] == "INSUFFICIENT"


def test_main_prints_one_json_object_for_missing_store(tmp_path, capsys) -> None:
    assert lock.main(["--cache-root", str(tmp_path)]) == 0
    output = capsys.readouterr().out.splitlines()

    assert len(output) == 1
    assert json.loads(output[0])["verdict"] == "INSUFFICIENT"


def test_verdict_is_match_only_within_locked_tolerance() -> None:
    assert lock._verdict(-.047, 30) == "MATCH"
    assert lock._verdict(-.034, 30) == "BEHIND"
