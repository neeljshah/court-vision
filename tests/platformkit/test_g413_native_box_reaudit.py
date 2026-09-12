"""Preparation controls for the G413 finisher; no source store is opened here."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g413_contract import (associate, bounded, field_scan,
                                                          historical_pair_guard, per_tick,
                                                          residuals, transform_native)
from scripts.platformkit.tracking.g413_prepare import prereg_seal_valid


def test_prereg_seal_reads_file_and_normalizes_crlf() -> None:
    path = Path(__file__).resolve().parents[2] / "docs/evidence/tracking/g413_native_box_reaudit_2026-09-12/prereg.md"
    assert prereg_seal_valid(path)
    body = path.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(body[:body.index(b"SEAL sha256 ")]).hexdigest().encode() in body


def test_fixed_pairing_and_lexical_ties_are_one_to_one() -> None:
    box = {"bbox_x1": 0, "bbox_y1": 0, "bbox_x2": 10, "bbox_y2": 10}
    result = associate([{**box, "box_id": "b2"}, {**box, "box_id": "b1"}], [{**box, "det_id": "d1"}])
    assert result["matches"] == [{"box_id": "b1", "det_id": "d1", "iou": 1.0}]
    assert result["unmatched_producer"] == ["b2"]


def test_silent_ticks_and_unmatched_denominators_are_retained() -> None:
    draw = [{"card_id": "c1", "frame": 1}, {"card_id": "c2", "frame": 2}]
    ticks = per_tick(draw, [{"card_id": "c1", "frame": 1}], [{"card_id": "c1", "frame": 1}])
    assert [(row["producer_boxes"], row["producer_silence"]) for row in ticks] == [(1, 0), (0, 1)]


def test_historical_guard_requires_51_pairs_on_28_frames() -> None:
    rows = [{"card_id": "c%02d" % (index % 28)} for index in range(51)]
    assert historical_pair_guard(rows) == {"pairs": 51, "distinct_frames": 28}
    with pytest.raises(ValueError):
        historical_pair_guard(rows[:-1])


def test_frame_weighting_uses_one_median_per_frame() -> None:
    rows = [{"card_id": "c1", "dx": 0, "dy": 0}, {"card_id": "c1", "dx": 100, "dy": 100},
            {"card_id": "c2", "dx": 10, "dy": 10}]
    result = residuals(rows)
    assert result["matched_frames"] == 2 and result["equal_frame_median_dx"] == 30


def test_delivered_absolute_p50_is_the_ordinary_median() -> None:
    import csv
    from statistics import median

    root = Path(__file__).resolve().parents[2]
    out = root / "docs/evidence/tracking/g413_native_box_reaudit_2026-09-12"
    with (out / "associations.csv").open(encoding="utf-8", newline="") as handle:
        absolute = [abs(float(row[key])) for row in csv.DictReader(handle) for key in ("dx", "dy")]
    with (out / "residuals.csv").open(encoding="utf-8", newline="") as handle:
        pooled = next(row for row in csv.DictReader(handle) if row["row_type"] == "summary" and row["card_id"] == "POOLED")
    assert float(pooled["absolute_p50"]) == median(absolute)


def test_branch_transform_clip_flags_and_window_bounds() -> None:
    row = {"bbox_x1": -5, "bbox_y1": -70, "bbox_x2": 110, "bbox_y2": 10}
    result = transform_native(row, 100, 100, "padded")
    assert result["clip_left"] == 1 and result["clip_right"] == 1 and result["transform_status"] == "OK"
    assert bounded({"frame": 12, "sealed_start_frame": 10, "sealed_end_frame_exclusive": 13})
    assert not bounded({"frame": 13, "sealed_start_frame": 10, "sealed_end_frame_exclusive": 13})


def test_crop_clip_precedes_native_origin_restore() -> None:
    row = {"bbox_x1": 1, "bbox_y1": 35, "bbox_x2": 10, "bbox_y2": 80}
    result = transform_native(row, 100, 100, "padded")
    assert result["bbox_y1"] == 95 and result["bbox_y2"] == 100
    assert result["clip_bottom"] == 1


def test_scanner_patterns_and_positive_fixture_are_code_built(tmp_path: Path) -> None:
    term = "".join(chr(code) for code in (114, 111, 105))
    path = tmp_path / "claims.csv"
    path.write_bytes((chr(10).join(["claim,path", "%s,opaque_identifier" % term]) + chr(10)).encode("utf-8"))
    result = field_scan(path)
    assert result["count"] == 1 and result["indices"] == [0]


def test_before_condition_reports_missing_g412_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.platformkit.tracking.g413_prepare as prepare
    g406, g412 = tmp_path / "g406", tmp_path / "g412"
    g406.mkdir()
    for name in ("draw.csv", "source_receipts.csv", "all_masked_rows.csv", "comparator_detections.csv", "associations.csv"):
        (g406 / name).write_text("prepared\n", encoding="utf-8")
    monkeypatch.setattr(prepare, "G406", g406)
    monkeypatch.setattr(prepare, "G412", g412)
    result = prepare.prerequisite_status()
    assert result["status"] == "PARTIAL"
    assert result["missing_g412"]
