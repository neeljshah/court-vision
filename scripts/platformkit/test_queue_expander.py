"""Focused tests for footage queue expansion."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit import queue_expander


def test_football_no_longer_accepts_highlight_reels() -> None:
    """The highlights exception was measured false and withdrawn on 2026-09-01.

    It rested on the claim that extended highlights "carry many clean
    broadcast-angle snaps". Five extended-highlight clips then tracked to 0 rows
    each: FootballAdapter emits ONLY low-motion pre-snap formation frames
    (>=14 detections, stable yard-line homography, no scene cut), and highlight
    reels cut away from exactly those. The adapter was refusing honestly.

    The floor must stay above highlight-reel length so the lane cannot spend
    capacity on footage that provably yields nothing.
    """
    assert queue_expander.MIN_DURATION_SECONDS["football"] >= 2400
    assert len(queue_expander.SOURCES["football"]) >= 3
    for sport in ("tennis", "wnba", "soccer", "kbo", "npb"):
        assert queue_expander.MIN_DURATION_SECONDS[sport] >= 3600


def test_every_source_sport_has_multiple_sources_and_a_duration_floor() -> None:
    assert set(queue_expander.SOURCES) == set(queue_expander.MIN_DURATION_SECONDS)
    assert {sport for sport in queue_expander.SOURCES if sport not in {
        "tennis", "wnba", "npb", "kbo", "soccer", "football", "mlb"
    }} >= {"nhl", "ncaa_basketball", "cricket"}
    for urls in queue_expander.SOURCES.values():
        assert len(urls) >= 2
        assert all(url.startswith("https://www.youtube.com/") for url in urls)

    assert queue_expander.MIN_DURATION_SECONDS["mlb"] >= 7200
    assert queue_expander.MIN_DURATION_SECONDS["cricket"] >= 6000
    assert queue_expander.MIN_DURATION_SECONDS["handball"] >= 3600
    assert queue_expander.MIN_DURATION_SECONDS["volleyball"] >= 3000


def test_football_expansion_removes_legacy_placeholder_entries(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    queue_path = data_dir / "footage_queue_football.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(json.dumps([
        {"sport": "football", "game_id": "fb_01", "url": "REPLACE_ME_1"},
    ]), encoding="utf-8")
    monkeypatch.setattr(queue_expander, "DATA_DIR", data_dir)
    monkeypatch.setattr(queue_expander, "TRACKING_DIR", data_dir / "tracking")
    monkeypatch.setattr(queue_expander, "COOKIES_FILE", data_dir / "cookies.txt")

    def fake_run(command, **_kwargs):
        field = command[command.index("--print") + 1]
        return SimpleNamespace(stdout=("newAAAAAA00\t6000\tFull Game Replay Football\n"
                                      if field.startswith("%(id)") else ""))

    monkeypatch.setattr(queue_expander.subprocess, "run", fake_run)
    monkeypatch.setattr(queue_expander, "_verify_football_candidate", lambda _: True)
    entries = queue_expander.expand_queue("football", ["https://example.test/list"], 1)

    assert [entry["game_id"] for entry in entries] == ["football_newAAAAAA00"]


def test_football_expansion_requires_metadata_and_visual_verification(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setattr(queue_expander, "DATA_DIR", data_dir)
    monkeypatch.setattr(queue_expander, "TRACKING_DIR", data_dir / "tracking")
    records = [
        ("studioAAAAA", 6000.0, "NFL Players Second Acts"),
        ("soccerAAAAA", 6000.0, "Full Game Replay Football"),
        ("validAAAAAA", 6000.0, "Full Game Replay Football"),
    ]
    monkeypatch.setattr(queue_expander, "_football_candidates", lambda _: records)
    checked = []
    monkeypatch.setattr(queue_expander, "_verify_football_candidate",
                        lambda video_id: checked.append(video_id) or video_id == "validAAAAAA")

    entries = queue_expander.expand_queue("football", ["https://example.test/list"], 3)

    assert [entry["game_id"] for entry in entries] == ["football_validAAAAAA"]
    assert checked == ["soccerAAAAA", "validAAAAAA"]


def test_football_probe_uses_a_small_section_and_web_client(monkeypatch):
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(queue_expander.subprocess, "run", fake_run)
    monkeypatch.setattr(queue_expander.football_content_gate, "screen",
                        lambda _path: SimpleNamespace(decision="accept"))

    assert queue_expander._verify_football_candidate("validAAAAAA") is True
    command = commands[0]
    assert "--download-sections" in command
    assert command[command.index("--download-sections") + 1] == "*00:10:00-00:10:12"
    assert "youtube:player_client=web" in command


def test_expand_queue_dedupes_filters_caps_and_writes_atomically(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    queue_path = data_dir / "footage_queue_tennis.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(
        json.dumps([
            {"sport": "tennis", "game_id": "tennis_oldAAAAAAAA", "url": "https://www.youtube.com/watch?v=oldAAAAAAAA", "format": "x"},
            {"sport": "tennis", "game_id": "tennis_trackedAAAA", "url": "https://www.youtube.com/watch?v=trackedAAAA", "format": "x"},
        ]),
        encoding="utf-8",
    )
    (data_dir / "tracking" / "tennis_trackedAAAA").mkdir(parents=True)
    monkeypatch.setattr(queue_expander, "DATA_DIR", data_dir)
    monkeypatch.setattr(queue_expander, "TRACKING_DIR", data_dir / "tracking")
    monkeypatch.setattr(queue_expander, "COOKIES_FILE", data_dir / "videos" / "cookies.txt")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        # real YouTube ids are exactly 11 chars; the expander now rejects
        # anything else (playlist/channel ids stalled every runner).
        output = "oldAAAAAAAA\ntrackedAAAA\nshortAAAAAA\nnewAAAAAAAA\nextraAAAAAA\nignoredAAAA\n"
        if command[command.index("--print") + 1] == "duration":
            output = "5000\n5000\n100\nNA\n7200\n7200\n"
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

    assert [item["game_id"] for item in entries] == ["tennis_oldAAAAAAAA", "tennis_trackedAAAA", "tennis_extraAAAAAA", "tennis_ignoredAAAA"]
    assert queue_path.read_text(encoding="utf-8") == json.dumps(entries, indent=2) + "\n"
    assert len(replaced) == 1
    assert replaced[0][1] == queue_path
    assert not replaced[0][0].exists()
    command = calls[0]
    assert command[command.index("--playlist-end") + 1] == str(queue_expander.SOURCE_SCAN_LIMIT)
    assert [command[command.index("--print") + 1] for command in calls] == ["id", "duration"]
