"""Focused tests for the footage download, tracking, score, and cleanup cycle."""
from pathlib import Path

from scripts.platformkit import footage_cycle


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
