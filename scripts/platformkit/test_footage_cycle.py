"""Focused tests for the footage download, tracking, score, and cleanup cycle."""
import logging
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit import footage_cycle


def test_download_retries_youtube_ladder_and_records_rung(monkeypatch, tmp_path, caplog):
    calls = []
    caplog.set_level(logging.INFO, logger=footage_cycle.__name__)

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, command, stderr="bot check")
        # real yt-dlp writes the file on success; the resolver checks for it
        (tmp_path / "game.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(footage_cycle.subprocess, "run", fake_run)
    destination = tmp_path / "game.mp4"

    result = footage_cycle.download_item(
        {"game_id": "game", "url": "https://youtube.example/watch?v=1", "format": "best"},
        destination,
    )

    assert result == destination
    assert len(calls) == 3
    assert "youtube:player_client=android,web_safari" in calls[1][0]
    assert "youtube:player_client=tv" in calls[2][0]
    assert all(call[1]["timeout"] == footage_cycle.MAX_ITEM_SECONDS for call in calls)
    assert "rung=tv" in caplog.text


def test_download_all_rungs_fail_includes_stderr_tail(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        raise subprocess.CalledProcessError(1, command, stderr="meaningful final yt-dlp error")

    monkeypatch.setattr(footage_cycle.subprocess, "run", fake_run)

    try:
        footage_cycle.download_item(
            {"game_id": "game", "url": "https://youtube.example/watch?v=1", "format": "best"},
            tmp_path / "game.mp4",
        )
    except RuntimeError as exc:
        assert "meaningful final yt-dlp error" in str(exc)
    else:
        raise AssertionError("Expected retry ladder to fail")
    assert len(calls) == 4
    assert calls[-1][0][-3:] == ["-f", "b[height<=720]", "https://youtube.example/watch?v=1"]


def test_queue_statuses_and_video_cleanup(monkeypatch, tmp_path):
    deleted = []

    def fake_download(item, destination):
        if item["game_id"] == "download_error":
            raise RuntimeError("network failed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")
        return destination

    def fake_track(item, video):
        if item["sport"] == "unknown":
            raise ValueError("Unsupported sport: unknown")
        output = tmp_path / item["game_id"] / "tracking_data.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("frame,track_id,cls,x,y\n0,1,player,1,1\n", encoding="utf-8")
        return output

    def fake_score(item, tracking_csv):
        return {"game_id": item["game_id"], "status": "ok", "passed": True}

    original_unlink = Path.unlink

    def note_unlink(self, *args, **kwargs):
        if self.suffix == ".mp4":
            deleted.append(self.name)
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(footage_cycle, "DOWNLOAD_DIR", tmp_path / "footage")
    monkeypatch.setattr(footage_cycle, "download_item", fake_download)
    monkeypatch.setattr(footage_cycle, "track_item", fake_track)
    monkeypatch.setattr(footage_cycle, "score_item", fake_score)
    monkeypatch.setattr(Path, "unlink", note_unlink)
    queue = [
        {"sport": "tennis", "game_id": "ok", "url": "x.mp4", "format": "direct"},
        {"sport": "unknown", "game_id": "unknown", "url": "x.mp4", "format": "direct"},
        {"sport": "tennis", "game_id": "download_error", "url": "x.mp4", "format": "direct"},
    ]

    results = footage_cycle.run_queue(queue, workers=3)

    assert {row["game_id"]: row["status"] for row in results} == {
        "ok": "ok", "unknown": "failed", "download_error": "download_failed",
    }
    assert set(deleted) == {"ok.mp4", "unknown.mp4", "download_error.mp4"}
    assert not list((tmp_path / "footage").glob("*.mp4"))


def test_nba_production_columns_are_not_laundered_into_court_coordinates():
    """ft_x/ft_y are an affine rescale of map_2d PIXELS, not court feet, and
    map_2d falls back to a hardcoded 940x500 when rectification fails. Aliasing
    them to x/y made the harness score image space against court-feet gates."""
    import pandas as pd

    frame = pd.DataFrame({"frame": [1, 2], "player_id": [10, 11],
                          "ft_x": [40.0, 50.0], "ft_y": [20.0, 25.0]})

    normalized = footage_cycle._normalize_tracking(frame)

    assert "track_id" in normalized, "player_id -> track_id is still correct"
    assert "x" not in normalized and "y" not in normalized


def test_player_only_sports_are_opted_in_here_too():
    """adapter_run opts baseball and soccer into player-only tracking. This
    caller duplicated nothing and so raised BallTrackingUnavailableError for
    soccer the moment soccer joined that set."""
    from scripts.platformkit.adapter_run import PLAYER_ONLY

    source = open("scripts/platformkit/footage_cycle.py", encoding="utf-8").read()

    assert "PLAYER_ONLY" in source, "must reuse adapter_run's set, not hardcode"
    assert {"baseball", "soccer"} <= PLAYER_ONLY


def test_track_item_writes_adapter_ball_telemetry_sidecar(monkeypatch, tmp_path):
    output_rows = "frame,track_id,cls,x,y\n0,1,player,1,1\n"
    module = SimpleNamespace(
        TennisAdapter=lambda: SimpleNamespace(process_video=lambda video, **options: []),
        write_csv=lambda rows, output: Path(output).write_text(output_rows, encoding="utf-8"),
    )

    monkeypatch.setattr(footage_cycle, "TRACKING_DIR", tmp_path)
    monkeypatch.setattr(footage_cycle, "SPORT_ADAPTERS", {"tennis": "TennisAdapter"})
    monkeypatch.setattr(footage_cycle.importlib, "import_module", lambda name: module)

    output = footage_cycle.track_item(
        {"sport": "tennis", "game_id": "tennis_sidecar"}, tmp_path / "clip.mp4")

    assert output.is_file()
    payload = json.loads((output.parent / "tracking_capability.json").read_text(encoding="utf-8"))
    assert payload == {"sport": "tennis", "ball_telemetry_available": True}
