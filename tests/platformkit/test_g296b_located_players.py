"""Pin G296B's immutable frame selection and merge schema."""
import csv
import json
from pathlib import Path

from scripts.platformkit.tracking.g296b_located_players import (
    FRAME_HEADER, FRAME_INDICES, PLAYER_HEADER,
)


def test_exact_frame_indices_and_formula():
    expected = (0, 7584, 15168, 22752, 30335, 37919, 45503, 53087,
                60671, 68255, 75839, 83423, 91006, 98590, 106174, 113758,
                121342, 128926, 136510, 144094, 151677, 159261, 166845, 174429)
    assert FRAME_INDICES == expected
    assert FRAME_INDICES == tuple(round(i * 174429 / 23) for i in range(24))
    assert len(set(FRAME_INDICES)) == 24


def test_exact_csv_headers():
    assert PLAYER_HEADER == (
        "source_frame,person_index,role,feet_visible,foot_x_px,foot_y_px,confidence,note"
    )
    assert FRAME_HEADER == "source_frame,court_visible,shot_description,players_located"


def test_microsecond_seek_never_passes_target_pts():
    for frame in FRAME_INDICES:
        micros = frame * 1_000_000 // 30
        assert micros * 30 <= frame * 1_000_000 < (micros + 1) * 30


def test_manifest_source_pts_and_native_dimensions_when_present():
    root = Path(__file__).resolve().parents[2]
    path = root / "docs/evidence/tracking/g296b_located_players_artifact/manifest.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text())
    assert tuple(manifest["frame_indices"]) == FRAME_INDICES
    assert len(manifest["frames"]) == 24
    for row, index in zip(manifest["frames"], FRAME_INDICES):
        assert row["source_frame"] == index
        assert row["source_pts"] == index * 512
        assert (row["width"], row["height"]) == (1920, 1080)


def test_local_launcher_has_no_network_size_stop_or_other_worktree_fallback():
    root = Path(__file__).resolve().parents[2]
    wrapper = (root / "scripts/platformkit/tracking/g296b_pod_run.sh").read_text()
    assert "conv=fsync" in wrapper
    assert "du -sm" not in wrapper
    assert "USED_MB" not in wrapper
    assert '[ "$H" = a12 ]' in wrapper
    assert '|| WT=' not in wrapper


def test_committed_annotations_when_present():
    root = Path(__file__).resolve().parents[2]
    artifact = root / "docs/evidence/tracking/g296b_located_players_artifact"
    if not (artifact / "located_players.csv").exists():
        return  # Extraction harness can be tested before independent annotation.
    with (artifact / "located_players.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == PLAYER_HEADER.split(",")
        people = list(reader)
    with (artifact / "frames.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == FRAME_HEADER.split(",")
        frames = list(reader)
    assert tuple(int(row["source_frame"]) for row in frames) == FRAME_INDICES
    keys = [(row["source_frame"], row["person_index"]) for row in people]
    assert len(keys) == len(set(keys))
    for row in people:
        assert None not in row and all(value is not None for value in row.values())
        assert int(row["source_frame"]) in FRAME_INDICES
        assert row["role"] in {"player_on_court", "official", "bench_or_coach",
                                "spectator_or_media", "other"}
        assert row["confidence"] in {"confident", "approximate", "guess"}
        assert row["feet_visible"] in {"true", "false"}
        if row["feet_visible"] == "false":
            assert row["foot_x_px"] == row["foot_y_px"] == ""
        else:
            assert 0 <= float(row["foot_x_px"]) < 1920
            assert 0 <= float(row["foot_y_px"]) < 1080
    for row in frames:
        assert row["court_visible"] in {"true", "false"}
        assert row["shot_description"]
        assert int(row["players_located"]) == sum(
            p["source_frame"] == row["source_frame"] and
            p["role"] == "player_on_court" and p["feet_visible"] == "true"
            for p in people
        )
