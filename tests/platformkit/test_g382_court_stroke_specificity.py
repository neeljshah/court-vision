"""G382 preparation controls: sealed transform, denominator, empties, identity, repeat receipt."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.platformkit.tracking import g334_seal
from scripts.platformkit.tracking import g382_export, g382_score
from scripts.platformkit.tracking.g382_masks import LABEL_CODES, UNKNOWN, label_name

PREREG = Path("docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md")


def test_prereg_seal_reads_file_and_normalises_lf():
    assert PREREG.exists()
    assert g334_seal.verify_seal(PREREG)


def test_exact_resize_transform_roundtrip_and_mask_shape():
    transform = g382_score.ResizeTransform.from_native(1920, 1080)
    assert (transform.work_width, transform.work_height) == (1280, 720)
    for x, y in ((0.0, 0.0), (101.25, 88.5), (1919.0, 1079.0)):
        assert np.allclose((x, y), transform.work_to_native(*transform.native_to_work(x, y)))
    mask = np.zeros((1080, 1920), dtype=np.uint8)
    assert transform.resize_mask(mask).shape == (720, 1280)


def test_unknown_is_kept_in_support_denominator(monkeypatch, tmp_path):
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    annotation = tmp_path / "f.json"
    annotation.write_text('{"frame_key":"f","image":{"width":10,"height":10},"painted_markings":[{"physical_marking_id":"m1","polygon":[[0,0],[1,0],[0,1]]}],"mask_regions":[]}', encoding="utf-8")
    class Stroke:
        stroke_id = "s"; family = 1; length = 12.0
        supports = np.asarray([(0.0, 0.0), (500.0, 500.0)], dtype=np.float32)
    monkeypatch.setattr(g382_score.g362_strokes, "extract_strokes", lambda _image: [Stroke()])
    _frame, strokes, supports = g382_score.score_frame("f", image, annotation)
    assert len(supports) == 2 and supports[1]["base_label"] == UNKNOWN
    assert strokes[0]["n_supports"] == "2" and strokes[0]["on_supports"] == "1"


def test_no_strokes_planned_frame_is_retained_in_marking_only_export():
    exported = g382_export.export([{"frame_key": "empty", "status": "SCORED"}], [])
    assert exported["frames"] == [{"frame_key": "empty", "status": "SCORED", "strokes": []}]


def test_complete_physical_marking_identity_and_independent_repeat_receipt():
    rows = [{"frame_key": "f", "stroke_id": "whole", "family": "3", "length_px": "40.0",
             "on_marking": "1", "physical_marking_ids": "paint_a,paint_b"}]
    exported = g382_export.export([{"frame_key": "f", "status": "SCORED"}], rows)
    stroke = exported["frames"][0]["strokes"][0]
    assert stroke["stroke_id"] == "whole" and stroke["physical_marking_ids"] == ["paint_a", "paint_b"]
    first = {"sha256": "a", "frames": 60, "strokes": 4, "supports": 12}
    assert g382_score.verify_repeat(first, dict(first))["identical"] is True
    assert g382_score.verify_repeat(first, {**first, "sha256": "b"})["identical"] is False


def test_frame_with_no_visible_painted_marking_is_scored_not_refused(tmp_path):
    from scripts.platformkit.tracking import g382_masks
    annotation = tmp_path / "n.json"
    annotation.write_text('{"frame_key":"n","image":{"width":8,"height":8},"painted_markings":[],'
                          '"mask_regions":[{"label":"STANDS","polygons":[[[0,0],[7,0],[7,7],[0,7]]]}]}',
                          encoding="utf-8")
    labels, physical = g382_masks.rasterize(g382_masks.read(annotation))
    assert physical == {} and label_name(int(labels[1, 1])) == "STANDS"
    assert not (labels == LABEL_CODES["PAINTED"]).any()


def test_adjudication_keeps_agreed_marking_drops_unresolved_and_stays_rasterizable(tmp_path):
    import json as _json
    from scripts.platformkit.tracking import g382_adjudicate, g382_masks
    box = lambda a, b, c, d: [[a, b], [c, b], [c, d], [a, d]]
    terra = {"painted_markings": [{"physical_marking_id": "CENTRE_LINE", "polygon": box(10, 10, 60, 20)},
                                  {"physical_marking_id": "BASELINE_LEFT", "polygon": box(70, 10, 90, 20)}],
             "mask_regions": [{"label": "STANDS", "polygons": [box(0, 60, 99, 99)]}]}
    sol = {"painted_markings": [{"physical_marking_id": "CENTRE_LINE", "polygon": box(15, 10, 65, 20)}],
           "mask_regions": [{"label": "STANDS", "polygons": [box(0, 70, 99, 99)]}]}
    doc, rows = g382_adjudicate.adjudicate("f", {"terra": terra, "sol": sol}, (100, 100), "both", set())
    decisions = {row["identifier"]: row["decision"] for row in rows}
    assert decisions["CENTRE_LINE"] == "AGREED" and decisions["BASELINE_LEFT"] == "UNRESOLVED"
    assert [item["physical_marking_id"] for item in doc["painted_markings"]] == ["CENTRE_LINE#0"]
    path = tmp_path / "f.json"
    path.write_text(_json.dumps(doc), encoding="utf-8")
    labels, physical = g382_masks.rasterize(g382_masks.read(path))
    assert len(physical) == 1 and 0 < int((labels == LABEL_CODES["PAINTED"]).sum()) < 1000


def test_final_masks_are_always_rasterizable_when_a_region_encloses_another(tmp_path):
    """A ring-shaped region refills solid, so the claimed footprint must be the FILLED polygon."""
    import json as _json
    from scripts.platformkit.tracking import g382_adjudicate, g382_masks
    box = lambda a, b, c, d: [[a, b], [c, b], [c, d], [a, d]]
    ring = [box(0, 0, 99, 99), box(30, 30, 70, 70)]
    doc = {"painted_markings": [], "mask_regions": [{"label": "STANDS", "polygons": ring},
                                                    {"label": "LED", "polygons": [box(40, 40, 60, 60)]}]}
    final, _rows = g382_adjudicate.adjudicate("f", {"terra": doc, "sol": doc}, (100, 100), "both", set())
    path = tmp_path / "f.json"
    path.write_text(_json.dumps(final), encoding="utf-8")
    g382_masks.rasterize(g382_masks.read(path))
