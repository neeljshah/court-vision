"""Preparation-only tests for the G409 coordinate-trace controls."""
from __future__ import annotations

import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g409_audit import field_scan, preserve_repeat_parent
from scripts.platformkit.tracking.g409_prepare import (
    cache_frame_identity,
    prereg_seal_valid,
    require_absolute_window,
    retain_silence,
    strict_event_join,
)
from scripts.platformkit.tracking.g409_transforms import (
    as_fraction_box,
    crop_xyxy,
    resize_and_pad_xyxy,
    uncrop_xyxy,
    xyxy_to_yxyx,
    yxyx_to_xyxy,
)


def _prereg() -> Path:
    return Path(__file__).resolve().parents[2] / "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12/prereg.md"


def test_prereg_seal_normalizes_file_crlf_to_lf() -> None:
    path = _prereg()
    assert prereg_seal_valid(path)
    body = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(body[:body.index("SEAL sha256")].encode("utf-8")).hexdigest() in body


def test_crop_resize_and_tuple_transforms_are_exact() -> None:
    native = as_fraction_box((110, 55, 210, 155))
    cropped = crop_xyxy(native, 100, 50)
    assert cropped == (Fraction(10), Fraction(5), Fraction(110), Fraction(105))
    assert uncrop_xyxy(cropped, 100, 50) == native
    assert yxyx_to_xyxy(xyxy_to_yxyx(cropped)) == cropped
    assert resize_and_pad_xyxy(cropped, Fraction(1, 2), Fraction(3), Fraction(7)) == (
        Fraction(8), Fraction(19, 2), Fraction(58), Fraction(119, 2)
    )


def test_absolute_window_indices_reject_relative_or_overrun_frames() -> None:
    assert require_absolute_window(105, 100, 120) == 105
    with pytest.raises(ValueError, match="absolute-frame-outside-window"):
        require_absolute_window(5, 100, 120)
    with pytest.raises(ValueError, match="absolute-frame-outside-window"):
        require_absolute_window(120, 100, 120)


def test_event_join_rejects_duplicate_and_absent_parent_keys() -> None:
    event = [{"event_key": "source/window/105"}]
    assert strict_event_join(event, [{"event_key": "source/window/105", "csv": "row"}])[0]["parent"]["csv"] == "row"
    with pytest.raises(ValueError, match="duplicate-event-join"):
        strict_event_join(event, [{"event_key": "source/window/105"}, {"event_key": "source/window/105"}])
    with pytest.raises(ValueError, match="duplicate-event-join"):
        strict_event_join(event * 2, [{"event_key": "source/window/105"}])
    with pytest.raises(ValueError, match="absent-event-join"):
        strict_event_join(event, [])


def test_stale_cache_frame_identity_is_retained() -> None:
    result = cache_frame_identity(native_frame=105, model_frame=104, cache_frame=104)
    assert result["identity_status"] == "STALE_CACHE_FRAME" and not result["matches"]


def test_silence_is_retained_for_every_selected_tick() -> None:
    selected = [{"source_sha256": "a", "window_id": "w", "frame": 105}]
    assert retain_silence(selected, []) == [dict(selected[0], producer_row_count=0, silence=1)]


def test_parent_repeat_shape_is_preserved_exactly() -> None:
    parent = {"identical": True, "runs": [{"stdout": "", "returncode": 0}], "schema": "parent"}
    result = preserve_repeat_parent(parent, {"g409": {"prepared": True}})
    assert result["identical"] is True and result["runs"] == parent["runs"]
    assert result["schema"] == "parent" and result["g409"] == {"prepared": True}


def test_character_code_scanner_positive_fixture_hides_matched_text(tmp_path: Path) -> None:
    path = tmp_path / "claims.csv"
    term = "".join(chr(code) for code in (114, 111, 105))
    path.write_text("claim\n%s\n" % term, encoding="utf-8", newline="\n")
    result = field_scan(path)
    assert result["count"] == 1 and result["hits"] == [{"field": "row:2:claim", "pattern_index": 0}]


# --- measured-stage tests (G409 finisher) -----------------------------------

from scripts.platformkit.tracking import g409_blind as BL
from scripts.platformkit.tracking import g409_build as B
from scripts.platformkit.tracking.g409_construct import (
    archived_crop,
    archived_serialize,
    construct_cases,
)
from scripts.platformkit.tracking import g409_fix1b as F


def _evidence() -> Path:
    return Path(__file__).resolve().parents[2] / (
        "docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12")


def test_archived_crop_and_serialization_reproduce_the_declared_transform() -> None:
    import numpy as np

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[300:460, 600:680] = 255
    cropped = archived_crop(frame)
    assert cropped.shape[0] == 1080 - 60 and cropped.shape[1] == 1920
    ys, xs = np.nonzero(cropped[:, :, 0])
    assert int(ys.min()) == 300 - 60 and int(xs.min()) == 600
    assert archived_serialize((240, 600, 400, 680)) == {
        "bbox_x1": 600, "bbox_y1": 240, "bbox_x2": 680, "bbox_y2": 400}


def test_every_construct_case_is_consistent_with_the_executed_code() -> None:
    cases = construct_cases()
    assert len(cases) >= 7
    assert all(c["crop_y_matches_code"] == "1" for c in cases)
    assert all(c["crop_x_unchanged"] == "1" for c in cases)
    assert all(c["uncrop_recovers_native_y1"] == "1" for c in cases)
    straddling = [c for c in cases if c["straddles_crop_line"] == "1"]
    assert straddling and all(c["uncrop_exact"] == "0" for c in straddling)


def test_lf_normalized_digests_match_the_sealed_upstream_values() -> None:
    rows = B.build_input_hashes()
    named = [r for r in rows if r["expected_sha256"]]
    assert len(named) == 3
    assert all(r["expected_match_lf"] == "1" for r in named)


def test_premise_reproduces_the_sealed_counts_and_offset() -> None:
    residuals, geometry = B.build_residuals()
    assert len(residuals) == 51
    assert geometry["dy"]["before"]["median"] == -58.2
    assert geometry["dy"]["before"]["p10"] == -67.75
    assert geometry["dy"]["before"]["p90"] == -45.75
    assert geometry["dx"]["before"]["median"] == 0.0
    assert geometry["dy"]["after"]["median"] == 1.8
    assert geometry["dx"]["after"] == geometry["dx"]["before"]


def test_export_join_is_exact_with_no_duplicate_or_absent_keys() -> None:
    joins = B.build_export_join()
    assert len(joins) == 206
    assert {r["join_status"] for r in joins} == {"MATCH"}
    assert all(r["coordinates_equal"] == "1" for r in joins)


def test_blind_marks_precede_every_overlay_and_the_transform_raises_agreement() -> None:
    rows, receipts, summary = BL.build_per_tick()
    assert len(rows) == 206 and len(receipts) == 60
    assert summary["blind_marks_precede_every_overlay"]
    assert summary["hits_ge_0_50_after"] > summary["hits_ge_0_50_before"]
    assert summary["median_best_iou_after"] > summary["median_best_iou_before"]


def test_stage_trace_records_only_topcut_60_and_a_cropped_export_frame() -> None:
    import json as _json

    path = _evidence() / "stage_trace.jsonl"
    records = [_json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    crops = [r for r in records if r["stage"] == "crop"]
    exports = [r for r in records if r["stage"] == "export"]
    assert crops and exports
    assert {r["topcut"] for r in crops} == {60}
    for rec in crops:
        assert rec["post_crop"]["shape"][0] == rec["native"]["shape"][0] - 60
        assert rec["post_crop"]["shape"][1] == rec["native"]["shape"][1]
    for rec in exports:
        assert rec["export_frame_shape"][0] in {1020, 660}
        if rec["bbox"]:
            assert rec["serialized"]["bbox_y1"] == rec["bbox"][0]
            assert rec["serialized"]["bbox_x1"] == rec["bbox"][1]


def test_fix1b_crop_rebind_binds_all_sixty_native_detector_inputs() -> None:
    rows = B.read_csv(_evidence() / "crop_rebind.csv")
    assert len(rows) == 60
    assert {row["match"] for row in rows} == {"yes"}
    assert all(row["native_shape"] and row["crop_shape"] for row in rows)


def test_fix1b_card_manifest_has_an_actual_detector_input_panel_per_tick() -> None:
    rows = B.read_csv(_evidence() / "card_panel_manifest.csv")
    assert len(rows) == 60
    assert all(row["actual_detector_input_panel"] == "frame[60:]" for row in rows)
    assert all((_evidence() / row["render_path"]).is_file() for row in rows)


def test_fix1b_controls_keep_all_cases_and_declare_the_route_status() -> None:
    rows = B.read_csv(_evidence() / "controls.csv")
    assert len(rows) == 7
    assert all(row["control_route"] in {"copied_statement", "archived_function"} for row in rows)
    assert all(row["control_route_v2"] for row in rows)
    assert all(row["route_sha256_before_import"] for row in rows)
    assert all("control_route_error" in row for row in rows)
    assert all("copied_statement" in row for row in rows)
    assert B.read_csv(_evidence() / "construct_cases.csv") == rows


def test_real_repeats_preserves_the_parent_receipt_and_adds_fix1b() -> None:
    root = Path(__file__).resolve().parents[2]
    parent_bytes = subprocess.run(
        ["git", "show", "75050b6a5:docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12/repeats.json"],
        cwd=root, capture_output=True, check=True,
    ).stdout
    parent = json.loads(parent_bytes)
    actual = json.loads((_evidence() / "repeats.json").read_bytes())
    assert actual["baseline_digests"] == parent["baseline_digests"]
    assert actual["scope"] == parent["scope"]
    assert actual["frozen_inputs_not_regenerated"] == parent["frozen_inputs_not_regenerated"]
    assert all(key in actual for key in parent)
    assert {key: actual[key] for key in parent} == parent
    assert actual["fix1b_repeats"]["identical"] is True
