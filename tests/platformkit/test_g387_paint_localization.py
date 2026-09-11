"""G387 preparation controls: coordinates, retained uncertainty, even draw, and seal."""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.tracking import g387_controls, g387_receipts, g387_score, g387_tiles

PREREG = Path("docs/evidence/tracking/g387_paint_localization_controls_2026-09-11/prereg/g387_prereg_2026-09-11.md")


def _rating(rater: str, opaque_id: str, x1: float, y1: float, x2: float, y2: float, mx: float, my: float) -> dict[str, str]:
    return {"rater": rater, "opaque_id": opaque_id, "physical_id": "paint", "state": "VISIBLE", "x": str(x1), "y": str(y1), "x2": str(x2), "y2": str(y2), "mid_x": str(mx), "mid_y": str(my)}


def test_known_position_control_scores_exactly():
    point = g387_controls.known_points(["G387_%03d" % n for n in range(1, 31)])[0]
    values = (float(point["x1"]), float(point["y1"]), float(point["x2"]), float(point["y2"]), float(point["mid_x"]), float(point["mid_y"]))
    assert g387_score.control_success(point, [_rating("terra", point["opaque_id"], *values), _rating("sol", point["opaque_id"], *values)])


def test_native_tile_roundtrip_and_deliberate_offset_failure():
    native = g387_tiles.tile_to_native(5, 123.5, 456.25)
    assert g387_tiles.native_to_tile(*native) == (5, 123.5, 456.25)
    try:
        g387_tiles.tile_to_native(5, 640, 1)
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-tile coordinate was accepted")


def test_unknown_is_charged_and_controls_excluded_from_real_denominator():
    real = g387_score.real_frame("G387_001", [], [], {"terra": 0, "sol": 0}, "UNKNOWN")
    result = g387_score.summary([True] * 30, [real])
    assert result["controls_denominator"] == 30
    assert result["real_denominator"] == 1 and result["real_unknown"] == 1 and result["real_localized"] == 0


def test_even_selector_is_not_a_head_slice():
    rows = [{"retained": "RETAINED", "video_id": "v", "section_id": "s", "frame_order": str(n), "frame_key": str(n)} for n in range(49)]
    selected = g387_tiles.select_even_retained(rows)
    assert [row["frame_key"] for row in selected] != [str(n) for n in range(30)]
    assert selected[-1]["frame_key"] == "48"


def test_seal_change_detection_and_lf_normalization(tmp_path):
    path = tmp_path / "prereg.md"
    path.write_text(g387_receipts.seal_text("alpha\nbeta\n").replace("\n", "\r\n"), encoding="utf-8", newline="")
    assert g387_receipts.verify_seal(path)
    path.write_text(path.read_text(encoding="utf-8").replace("beta", "gamma"), encoding="utf-8", newline="\n")
    assert not g387_receipts.verify_seal(path)


def test_committed_prereg_seal_reads_the_file():
    assert PREREG.exists()
    assert g387_receipts.verify_seal(PREREG)


def test_canonical_receipt_is_process_independent():
    value = {"a": [1, 2], "b": {"state": "UNKNOWN"}}
    assert g387_score.canonical_sha256(value) == g387_score.canonical_sha256(dict(value))
