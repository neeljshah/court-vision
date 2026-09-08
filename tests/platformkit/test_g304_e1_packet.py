import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g304_e1_extension import ROOT
from scripts.platformkit.tracking.seal_g304_inventory import canonical_seal, sha256_file
from scripts.platformkit.tracking.g304_e1_packet import (
    ADJUDICATION_PX,
    ELIGIBLE_ROWS,
    FRAME_GOOD_RULE,
    FRAME_INDEX_RULE,
    LANDMARKS_PER_ELIGIBLE,
    MIN_MARKING_STRUCTURES,
    MIN_SHOTS_PER_ARENA,
    NEGATIVE_ROWS,
    NEGATIVE_SPLIT,
    PER_ARENA_NEGATIVE_SPLIT,
    TOTAL_ROWS,
    frame_index_for_pts,
    validate_completed_packet,
)

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json"
)
LANDMARKS = [{"marking_structure": s} for s in ("sideline", "lane", "arc") * 2]
BALANCED = ["close_up"] * 4 + ["graphics_transition"] * 3 + ["replay_alternate"] * 3
SKEWED_A = ["close_up"] * 5 + ["graphics_transition"] * 3 + ["replay_alternate"] * 2
SKEWED_B = ["close_up"] * 3 + ["graphics_transition"] * 3 + ["replay_alternate"] * 4


def _packet(negatives_a: list[str], negatives_b: list[str]) -> dict:
    rows = []
    for arena, negatives in (("A", negatives_a), ("B", negatives_b)):
        for index in range(20):
            pts = float(index + 1)
            rows.append(
                {
                    "row_id": f"{arena}_e{index}",
                    "source_id": arena,
                    "pts_seconds": pts,
                    "frame_index": frame_index_for_pts(pts),
                    "selection_status": "selected",
                    "scope": "eligible",
                    "shot_identity": f"{arena}_shot_{index % MIN_SHOTS_PER_ARENA}",
                    "landmarks": LANDMARKS,
                }
            )
        for index, kind in enumerate(negatives):
            pts = float(index + 100)
            rows.append(
                {
                    "row_id": f"{arena}_n{index}",
                    "source_id": arena,
                    "pts_seconds": pts,
                    "frame_index": frame_index_for_pts(pts),
                    "selection_status": "selected",
                    "scope": "negative",
                    "negative_type": kind,
                }
            )
    return {
        "rows": rows,
        "source_rows": [{"id": "A"}, {"id": "B"}],
        "frame_good_rule": FRAME_GOOD_RULE,
    }


def test_g304_sealed_packet_contract_is_pinned() -> None:
    assert (TOTAL_ROWS, ELIGIBLE_ROWS, NEGATIVE_ROWS) == (60, 40, 20)
    assert PER_ARENA_NEGATIVE_SPLIT == {"close_up": 4, "graphics_transition": 3, "replay_alternate": 3}
    assert NEGATIVE_SPLIT == {"close_up": 8, "graphics_transition": 6, "replay_alternate": 6}
    assert MIN_SHOTS_PER_ARENA >= 4
    assert LANDMARKS_PER_ELIGIBLE == 6
    assert MIN_MARKING_STRUCTURES >= 3
    assert ADJUDICATION_PX == 4
    assert FRAME_GOOD_RULE == "p90 <= 12 px AND max <= 24 px"
    assert FRAME_INDEX_RULE == "frame_index = ceil(pts_seconds * 30)"


def test_balanced_two_arena_packet_has_no_violations() -> None:
    assert validate_completed_packet(_packet(BALANCED, BALANCED)) == []


def test_per_arena_negative_split_is_enforced_via_source_rows() -> None:
    errors = validate_completed_packet(_packet(SKEWED_A, SKEWED_B))
    assert errors == ["A needs the 4/3/3 negative split", "B needs the 4/3/3 negative split"]


def test_missing_fourth_shot_in_one_arena_is_reported() -> None:
    packet = _packet(BALANCED, BALANCED)
    for row in packet["rows"]:
        if row["source_id"] == "B" and row["scope"] == "eligible":
            row["shot_identity"] = "B_shot_0"
    assert validate_completed_packet(packet) == ["B needs at least four shots"]


def test_sealed_manifest_rows_obey_the_frame_index_rule() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    rows = manifest["rows"]
    assert len(rows) == TOTAL_ROWS
    assert [row["frame_index"] for row in rows] == [
        frame_index_for_pts(row["pts_seconds"]) for row in rows
    ]
    assert manifest["decode_recipe"]["frame_index_rule"].startswith(FRAME_INDEX_RULE)


EXTENSION = (
    Path(__file__).resolve().parents[2]
    / "docs/evidence/tracking/g304_e1_extension_manifest_2026-09-07.json"
)


def _manifests() -> tuple[dict, dict]:
    return (
        json.loads(MANIFEST.read_text(encoding="ascii")),
        json.loads(EXTENSION.read_text(encoding="ascii")),
    )


def test_extension_extends_the_sealed_packet_and_reseals_canonically() -> None:
    original, extension = _manifests()
    assert extension["extends"] == original["manifest_sha256_canonical_payload"]
    payload = {k: v for k, v in extension.items() if k != "manifest_sha256_canonical_payload"}
    assert canonical_seal(payload) == extension["manifest_sha256_canonical_payload"]
    for key in ("frame_good_rule", "primary_acceptance", "adjudication_threshold_px"):
        assert extension[key] == original[key]


def test_extension_rows_are_native_size_and_obey_the_frame_index_rule() -> None:
    _, extension = _manifests()
    rows = extension["rows"]
    assert extension["extension_rows_per_arena"] == {"wnba_01": 30, "wnba_04": 45}
    assert Counter(row["source_id"] for row in rows) == Counter(
        {"wnba_01": 30, "wnba_04": 45}
    )
    assert len(rows) == 75
    for row in rows:
        assert row["dimensions"] == [1920, 1080]
        assert row["frame_index"] == frame_index_for_pts(row["pts_seconds"])


def test_extension_positions_are_disjoint_from_the_sealed_sixty() -> None:
    original, extension = _manifests()
    def keyed(manifest: dict, field: str) -> set:
        return {(row["source_id"], row[field]) for row in manifest["rows"]}

    for field in ("pts_seconds", "frame_index", "row_id", "decode_sha256"):
        assert not keyed(original, field) & keyed(extension, field), field
    assert len(keyed(extension, "decode_sha256")) == 75


@pytest.mark.parametrize("index", (0, 18, 37, 56, 74))
def test_recorded_decode_recipe_reproduces_extension_renders_byte_for_byte(
    index: int, tmp_path: Path
) -> None:
    """The sealed recipe must re-derive decode_sha256 from pts_seconds alone."""
    _, extension = _manifests()
    row = extension["rows"][index]
    source = ROOT / next(
        s["path"] for s in extension["source_rows"] if s["id"] == row["source_id"]
    )
    if shutil.which("ffmpeg") is None or not source.exists():
        pytest.skip("local-only: needs ffmpeg and the gitignored bridge sources")
    output = tmp_path / "frame.jpg"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-ss", f"{row['pts_seconds']:.6f}", "-i", str(source),
            "-frames:v", "1", "-q:v", "2", str(output),
        ],
        check=True,
    )
    assert sha256_file(output) == row["decode_sha256"]
