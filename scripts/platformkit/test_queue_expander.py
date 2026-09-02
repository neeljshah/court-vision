"""Focused tests for footage queue expansion around the generic content gate."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit import queue_expander


def test_every_source_sport_has_multiple_sources_and_a_duration_floor() -> None:
    assert set(queue_expander.SOURCES) == set(queue_expander.MIN_DURATION_SECONDS)
    for urls in queue_expander.SOURCES.values():
        assert len(urls) >= 2
        assert all(url.startswith("https://www.youtube.com/") for url in urls)
    assert queue_expander.MIN_DURATION_SECONDS["football"] >= 2400
    assert queue_expander.MIN_DURATION_SECONDS["mlb"] >= 7200


def test_expansion_regates_legacy_items_at_the_shared_gate(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    queue_path = data_dir / "footage_queue_football.json"
    queue_path.parent.mkdir(parents=True)
    legacy = [
        {"sport": "football", "game_id": "football_bad", "url": "https://bad"},
        {"sport": "football", "game_id": "football_good", "url": "https://good"},
    ]
    queue_path.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setattr(queue_expander, "DATA_DIR", data_dir)
    monkeypatch.setattr(queue_expander, "TRACKING_DIR", data_dir / "tracking")
    monkeypatch.setattr(queue_expander, "COOKIES_FILE", data_dir / "cookies.txt")
    seen: list[list[str]] = []

    def fake_gate(items, sport, cookies_file):
        assert sport == "football"
        assert cookies_file == data_dir / "cookies.txt"
        seen.append([item["game_id"] for item in items])
        return [item for item in items if item["game_id"] != "football_bad"]

    monkeypatch.setattr(queue_expander.queue_content_gate, "gate_items", fake_gate)
    entries = queue_expander.expand_queue("football", [], 0)

    assert seen == [["football_bad", "football_good"]]
    assert [entry["game_id"] for entry in entries] == ["football_good"]


def test_expand_queue_dedupes_filters_caps_and_writes_atomically(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    queue_path = data_dir / "footage_queue_tennis.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(json.dumps([
        {"sport": "tennis", "game_id": "tennis_oldAAAAAAAA", "url": "https://www.youtube.com/watch?v=oldAAAAAAAA", "format": "x"},
        {"sport": "tennis", "game_id": "tennis_trackedAAAA", "url": "https://www.youtube.com/watch?v=trackedAAAA", "format": "x"},
    ]), encoding="utf-8")
    (data_dir / "tracking" / "tennis_trackedAAAA").mkdir(parents=True)
    monkeypatch.setattr(queue_expander, "DATA_DIR", data_dir)
    monkeypatch.setattr(queue_expander, "TRACKING_DIR", data_dir / "tracking")
    monkeypatch.setattr(queue_expander, "COOKIES_FILE", data_dir / "videos" / "cookies.txt")
    monkeypatch.setattr(queue_expander.queue_content_gate, "gate_items",
                        lambda items, _sport, _cookies: items)
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        output = "oldAAAAAAAA\ntrackedAAAA\nshortAAAAAA\nnewAAAAAAAA\nextraAAAAAA\nignoredAAAA\n"
        if command[command.index("--print") + 1] == "duration":
            output = "5000\n5000\n100\nNA\n7200\n7200\n"
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(queue_expander.subprocess, "run", fake_run)
    entries = queue_expander.expand_queue("tennis", ["https://example.test/list"], 3)

    assert [item["game_id"] for item in entries] == [
        "tennis_oldAAAAAAAA", "tennis_trackedAAAA", "tennis_extraAAAAAA",
        "tennis_ignoredAAAA"]
    assert [command[command.index("--print") + 1] for command in calls] == ["id", "duration"]
    assert queue_path.read_text(encoding="utf-8") == json.dumps(entries, indent=2) + "\n"
