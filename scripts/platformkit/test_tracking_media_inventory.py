"""Focused tests for read-only resolution inventory and superseding refresh ids."""
from pathlib import Path

from scripts.platformkit.tracking_media_inventory import inventory, refresh_manifest


def test_inventory_and_manifest_preserve_the_old_game_id(monkeypatch, tmp_path):
    clip = tmp_path / "tennis__match_a.mp4"
    clip.write_bytes(b"placeholder")
    tracked = tmp_path / "tracking" / "match_a"
    tracked.mkdir(parents=True)
    (tracked / "tracking_data.csv").write_text("header\n" + "row\n" * 500,
                                                encoding="utf-8")
    monkeypatch.setattr("scripts.platformkit.tracking_media_inventory.probe_media",
                        lambda path: {"width": 640, "height": 360,
                                      "frame_rate": 25.0, "bit_rate": 321033,
                                      "path": str(path)})

    rows = inventory(tmp_path)
    manifest = refresh_manifest(rows, tmp_path / "tracking")

    assert rows[0]["legacy_low_resolution"] is True
    assert manifest[0]["supersedes_game_id"] == "match_a"
    assert manifest[0]["refresh_game_id"] == "match_a__refresh_720p"
    assert manifest[0]["existing_tracking_rows"] == 500
