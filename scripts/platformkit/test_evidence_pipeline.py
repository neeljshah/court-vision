"""Tests for the evidence regeneration pipeline."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts.platformkit import evidence_pipeline


def _game(root: Path, game_id: str, sport: str) -> Path:
    directory = root / "data" / "tracking" / game_id
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "tracking_data.csv"
    csv_path.write_text("frame,track_id,cls,x,y\n1,1,player,10,10\n", encoding="ascii")
    (directory / "quality_report.json").write_text(
        json.dumps({"sport": sport, "passed": True}), encoding="ascii")
    return csv_path


def _fake_render(root: Path, calls: list[str], failing: set[str] | None = None):
    failing = failing or set()

    def render(csv_path, sport, out_path=None, gif_path=None, **kwargs):
        game_id = Path(csv_path).parent.name
        calls.append(game_id)
        if game_id in failing:
            raise RuntimeError("codec unavailable for %s" % game_id)
        for path in (out_path, gif_path):
            if path is not None:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_bytes(b"fake-render")
        return 5

    return render


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    _game(tmp_path, "game_a", "basketball")
    _game(tmp_path, "game_b", "tennis")
    demos = tmp_path / "docs" / "evidence" / "demos"
    demos.mkdir(parents=True)
    # game_a already has a current demo; game_b has none.
    (demos / "game_a_demo.gif").write_bytes(b"old-but-current")
    (demos / "game_a_demo.mp4").write_bytes(b"old-but-current")
    future = time.time() + 60
    for name in ("game_a_demo.gif", "game_a_demo.mp4"):
        os.utime(demos / name, (future, future))
    # a private broadcast-derived artifact sitting in the same tree
    (demos / "game_a_overlay.mp4").write_bytes(b"broadcast-pixels")
    return tmp_path


def test_only_new_skips_current_demos(tree: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(evidence_pipeline, "render_csv", _fake_render(tree, calls))
    result = evidence_pipeline.run_pipeline(tree, quiet=True)
    assert calls == ["game_b"]
    assert result["skipped"] == ["game_a"]
    assert result["rendered"] == ["game_b"]
    assert result["failures"] == []
    assert (tree / "docs" / "evidence" / "demos" / "game_b_demo.gif").is_file()


def test_rerender_all_ignores_existing(tree: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(evidence_pipeline, "render_csv", _fake_render(tree, calls))
    result = evidence_pipeline.run_pipeline(tree, only_new=False, quiet=True)
    assert calls == ["game_a", "game_b"]
    assert result["skipped"] == []


def test_manifest_marks_overlay_private(tree: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(evidence_pipeline, "render_csv", _fake_render(tree, calls))
    evidence_pipeline.run_pipeline(tree, quiet=True)
    manifest = json.loads(
        (tree / "docs" / "evidence" / "manifest.json").read_text(encoding="ascii"))
    entries = {entry["path"]: entry for entry in manifest["artifacts"]}

    overlay = entries["docs/evidence/demos/game_a_overlay.mp4"]
    assert overlay["kind"] == "broadcast_overlay"
    assert overlay["rights_safe"] is False
    assert overlay["visibility"] == "private"

    demo = entries["docs/evidence/demos/game_b_demo.gif"]
    assert demo["kind"] == "court_diagram_demo"
    assert demo["rights_safe"] is True
    assert demo["visibility"] == "public"
    assert demo["game"] == "game_b" and demo["sport"] == "tennis"
    assert demo["bytes"] == len(b"fake-render")
    assert demo["mtime_utc"].endswith("+00:00")

    # the hard rail: nothing broadcast-derived may ever be public
    assert not [entry for entry in manifest["artifacts"]
                if entry["rights_safe"]
                and any(token in entry["path"].lower()
                        for token in evidence_pipeline.PRIVATE_TOKENS)]
    assert manifest["n_games_with_tracking"] == 2
    assert manifest["n_public"] + manifest["n_private"] == manifest["n_artifacts"]


def test_unknown_media_defaults_to_private(tree: Path, monkeypatch) -> None:
    stray = tree / "docs" / "evidence" / "mystery_clip.mp4"
    stray.write_bytes(b"unknown-provenance")
    monkeypatch.setattr(evidence_pipeline, "render_csv", _fake_render(tree, []))
    evidence_pipeline.run_pipeline(tree, quiet=True)
    manifest = json.loads(
        (tree / "docs" / "evidence" / "manifest.json").read_text(encoding="ascii"))
    entry = next(item for item in manifest["artifacts"]
                 if item["path"].endswith("mystery_clip.mp4"))
    assert entry["kind"] == "unclassified" and entry["visibility"] == "private"


def test_failing_render_is_recorded_not_fatal(tree: Path, monkeypatch) -> None:
    _game(tree, "game_c", "basketball")
    calls: list[str] = []
    monkeypatch.setattr(evidence_pipeline, "render_csv",
                        _fake_render(tree, calls, failing={"game_b"}))
    result = evidence_pipeline.run_pipeline(tree, quiet=True)
    assert calls == ["game_b", "game_c"]
    assert result["rendered"] == ["game_c"]
    assert [item["game"] for item in result["failures"]] == ["game_b"]
    assert "codec unavailable" in result["failures"][0]["error"]
    # the surface is still rebuilt despite the failure
    assert (tree / "docs" / "evidence" / "manifest.json").is_file()
    assert (tree / "docs" / "evidence" / "multisport" / "README.md").is_file()


def test_sport_falls_back_to_report_tree(tmp_path: Path) -> None:
    directory = tmp_path / "data" / "tracking" / "game_d"
    directory.mkdir(parents=True)
    (directory / "tracking_data.csv").write_text("frame\n1\n", encoding="ascii")
    report = tmp_path / "data" / "tracking_reports" / "soccer"
    report.mkdir(parents=True)
    (report / "game_d.json").write_text("{}", encoding="ascii")
    assert evidence_pipeline.discover_games(tmp_path)[0]["sport"] == "soccer"
