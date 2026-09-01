"""Focused checks for the paired settled-tick baseline lock command."""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.ingame import ingame_baseline_lock as lock


def _row(game: str, index: int, model: float | None, market: float, outcome: int) -> dict[str, object]:
    row: dict[str, object] = {"game_id": game, "ts": "2026-08-%02dT00:00:00Z" % (index + 1),
                              "market_prob": market, "outcome": outcome}
    if model is not None:
        row["model_prob"] = model
    return row


def test_summarize_uses_paired_ticks_and_reports_model_drops(tmp_path) -> None:
    store = tmp_path / "ingame_grade_joined"
    store.mkdir()
    rows = [_row("game-a", 0, .8, .6, 1), _row("game-b", 1, .2, .4, 0),
            _row("game-c", 2, None, .7, 1)]
    (store / "ticks.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n",
                                        encoding="utf-8")

    report = lock.summarize(store)

    assert report["corpus"]["source_row_count"] == 3
    assert report["corpus"]["settled_tick_count"] == 3
    assert report["corpus"]["eligible_tick_count"] == 3
    assert report["corpus"]["paired_tick_count"] == 2
    assert report["corpus"]["dropped_missing_model_prob_count"] == 1
    assert report["corpus"]["n_games"] == 2
    assert report["n_games"] == 2
    assert report["ess"] > 0.0
    assert report["corpus"]["date_range"] == {"min": "2026-08-01", "max": "2026-08-02"}
    assert len(report["corpus"]["file_hash"]) == 64
    assert report["delta_brier"] == pytest.approx(.12)
    assert report["verdict"] == "INSUFFICIENT"


def test_main_prints_one_json_object_for_missing_store(tmp_path, capsys) -> None:
    assert lock.main(["--cache-root", str(tmp_path)]) == 0
    output = capsys.readouterr().out.splitlines()

    assert len(output) == 1
    assert json.loads(output[0])["verdict"] == "INSUFFICIENT"


def test_verdict_uses_clustered_interval_not_centered_prior_antitest() -> None:
    # Old anti-test pinned a narrow band centered on the stale prior as MATCH.
    assert lock._verdict(30.0, (-.048, -.046)) == "BEHIND"
    assert lock._verdict(30.0, (-.050, .010)) == "INSUFFICIENT"
    assert lock._verdict(30.0, (.001, .020)) == "MATCH"
