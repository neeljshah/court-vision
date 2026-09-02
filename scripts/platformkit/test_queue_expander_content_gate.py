"""Focused routing contract for the generic queue content gate."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit import queue_content_gate, queue_expander


def test_queue_gate_routes_title_junk_probe_junk_and_usable(tmp_path, monkeypatch) -> None:
    """Every queue item is decided once before it can reach tracking."""
    quarantine = tmp_path / "quarantine"
    monkeypatch.setattr(queue_content_gate, "QUARANTINE_DIR", quarantine)
    monkeypatch.setattr(queue_content_gate, "REVIEW_DIR", tmp_path / "review")
    monkeypatch.setattr(queue_content_gate, "fetch_metadata", lambda _url: ("", ""))
    quarantined: list[Path] = []
    rendered: list[Path] = []

    def fake_download(_url: str, output: Path, _cookies: Path) -> bool:
        output.write_bytes(b"probe")
        return True

    def fake_census(video: Path, sample_count: int):
        assert sample_count == 12
        verdict = "JUNK" if "junk_frames" in video.name else "SUSPECT" if "suspect" in video.name else "USABLE"
        return SimpleNamespace(verdict=verdict), []

    def fake_quarantine(video: Path, _reason: str, destination: Path) -> Path:
        quarantined.append(video)
        assert destination == quarantine
        return video

    monkeypatch.setattr(queue_content_gate, "_probe_download", fake_download)
    monkeypatch.setattr(queue_content_gate.footage_census, "census_clip", fake_census)
    monkeypatch.setattr(queue_content_gate.footage_content_gate, "quarantine_manual",
                        fake_quarantine)
    monkeypatch.setattr(queue_content_gate.footage_census, "render_sample",
                        lambda _frames, _game_id, review: rendered.append(review))
    items = [
        {"sport": "football", "game_id": "football_title_junk",
         "url": "https://example.test/title", "title": "Football press conference"},
        {"sport": "football", "game_id": "football_no_metadata",
         "url": "https://example.test/no-metadata"},
        {"sport": "football", "game_id": "football_junk_frames",
         "url": "https://example.test/frames", "title": "Football full game replay"},
        {"sport": "football", "game_id": "football_suspect",
         "url": "https://example.test/suspect", "title": "Football full game replay"},
        {"sport": "football", "game_id": "football_ambiguous",
         "url": "https://example.test/ambiguous", "title": "Football vs Volleyball full game"},
        {"sport": "football", "game_id": "football_usable",
         "url": "https://example.test/usable", "title": "Football full game replay"},
    ]

    kept = queue_expander._gate_queue_items("football", items)

    assert [item["game_id"] for item in kept] == [
        "football_no_metadata", "football_suspect", "football_ambiguous", "football_usable",
    ]
    assert [item["content_gate"]["decision"] for item in kept] == ["USABLE", "SUSPECT", "USABLE", "USABLE"]
    assert kept[0]["content_gate"]["reason"] == "title_unknown:probe_census_usable"
    assert kept[2]["content_gate"]["reason"] == "title_ambiguous"
    assert quarantined and "junk_frames" in quarantined[0].name
    assert rendered == [tmp_path / "review" / "football_suspect"]
    assert (quarantine / "football_title_junk.queue.json").is_file()


def test_title_gate_rejects_only_known_junk_or_other_sports() -> None:
    assert queue_content_gate.title_rejection(
        "mlb", "Yankees vs Red Sox condensed game", "") is None
    assert queue_content_gate.title_rejection(
        "npb", "Full Archived games Buffaloes vs. Lions", "") is None
    assert queue_content_gate.title_rejection(
        "tennis", "Roland-Garros 2025 Full Match", "") is None
    assert queue_content_gate.title_rejection(
        "wnba", "Storm vs Aces | WNBA basketball full game", "") is None
    assert queue_content_gate.title_rejection(
        "wnba", "Storm vs Aces | women's basketball full game", "") is None
    assert queue_content_gate.title_rejection(
        "wnba", "Storm vs Aces | women-s basketball full game", "") is None
    assert queue_content_gate.title_rejection(
        "soccer", "Arsenal vs Chelsea FULL MATCH | Premier League football", "") is None
    assert queue_content_gate.title_rejection(
        "football", "Football vs Volleyball full game", "") == "title_ambiguous"
    assert queue_content_gate.title_rejection(
        "mlb", "Grapes vs Stripes exhibition", "") is None
    assert queue_content_gate.title_rejection(
        "mlb", "Yankees vs Red Sox full game",
        "Includes postgame interview with the manager",
    ) is None
    assert queue_content_gate.title_rejection("wnba", "PES gameplay", "")
    assert queue_content_gate.title_rejection("football", "Football press conference", "")
    assert queue_content_gate.title_rejection("mlb", "", "") is None
    assert queue_content_gate.title_rejection("mlb", "", "postgame press conference")


def test_probe_download_requests_exactly_ninety_seconds(tmp_path, monkeypatch) -> None:
    output = tmp_path / "football__probe.mp4"
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        output.write_bytes(b"probe")
        return SimpleNamespace()

    monkeypatch.setattr(queue_content_gate.subprocess, "run", fake_run)

    assert queue_content_gate._probe_download("https://example.test/video", output,
                                              tmp_path / "cookies.txt") is True
    command = commands[0]
    assert command[command.index("--download-sections") + 1] == "*00:10:00-00:11:30"
    assert "--no-part" in command
