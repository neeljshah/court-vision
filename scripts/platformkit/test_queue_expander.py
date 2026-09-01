"""Focused tests for footage queue expansion."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit import queue_expander


def test_expand_queue_dedupes_filters_caps_and_writes_atomically(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    queue_path = data_dir / "footage_queue_tennis.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(
        json.dumps([
            {"sport": "tennis", "game_id": "tennis_old", "url": "https://www.youtube.com/watch?v=old", "format": "x"},
            {"sport": "tennis", "game_id": "tennis_tracked", "url": "https://www.youtube.com/watch?v=tracked", "format": "x"},
        ]),
        encoding="utf-8",
    )
    (data_dir / "tracking" / "tennis_tracked").mkdir(parents=True)
    monkeypatch.setattr(queue_expander, "DATA_DIR", data_dir)
    monkeypatch.setattr(queue_expander, "TRACKING_DIR", data_dir / "tracking")
    monkeypatch.setattr(queue_expander, "COOKIES_FILE", data_dir / "videos" / "cookies.txt")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        output = "old\ntracked\nshort\nnew\nextra\nignored\n"
        if command[command.index("--print") + 1] == "duration":
            output = "5000\n5000\n100\n3600\n7200\n7200\n"
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr(queue_expander.subprocess, "run", fake_run)
    replaced: list[tuple[Path, Path]] = []
    original_replace = queue_expander.os.replace

    def checking_replace(source, destination):
        source_path, destination_path = Path(source), Path(destination)
        assert source_path.exists()
        replaced.append((source_path, destination_path))
        original_replace(source, destination)

    monkeypatch.setattr(queue_expander.os, "replace", checking_replace)

    entries = queue_expander.expand_queue("tennis", ["https://example.test/list"], 3)

    assert [item["game_id"] for item in entries] == ["tennis_old", "tennis_tracked", "tennis_new", "tennis_extra"]
    assert queue_path.read_text(encoding="utf-8") == json.dumps(entries, indent=2) + "\n"
    assert len(replaced) == 1
    assert replaced[0][1] == queue_path
    assert not replaced[0][0].exists()
    assert [command[command.index("--print") + 1] for command in calls] == ["id", "duration"]
