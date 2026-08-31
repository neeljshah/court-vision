"""Focused tests for the video provenance manifest."""
import hashlib
import json
from scripts.platformkit import provenance


def test_record_and_verify_provenance(tmp_path, monkeypatch):
    video = tmp_path / "game.mp4"
    payload = b"fixture video bytes"
    video.write_bytes(payload)
    manifest = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(provenance, "PROVENANCE_PATH", manifest)

    row = provenance.record_provenance(
        "game-1", "tennis", "https://example.test/game", video,
        "domains.tennis.tracking.adapter",
    )

    assert row["sha256"] == hashlib.sha256(payload).hexdigest()
    assert row["size_bytes"] == len(payload)
    assert row["sport"] == "tennis"
    assert row["source_url"] == "https://example.test/game"
    assert row["adapter_module"] == "domains.tennis.tracking.adapter"
    assert row["thresholds_snapshot"] == provenance.SPORTS["tennis"]
    required_fields = {"capture_ts", "adapter_version", "harness_version",
                       "resolution", "fps"}
    assert required_fields <= row.keys()
    stored = json.loads(manifest.read_text(encoding="utf-8"))
    assert stored["game_id"] == "game-1"
    assert provenance.verify_provenance("game-1")["sha256"] == stored["sha256"]
    assert provenance.verify_provenance("absent") is None


def test_missing_video_records_missing_hash(tmp_path, monkeypatch):
    manifest = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(provenance, "PROVENANCE_PATH", manifest)

    row = provenance.record_provenance(
        "gone", "basketball", "source", tmp_path / "gone.mp4", "scripts.run_clip"
    )

    assert row["sha256"] == "missing"
    assert row["resolution"] is None
    assert row["fps"] is None
