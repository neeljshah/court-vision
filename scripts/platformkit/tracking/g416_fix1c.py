"""Fix 1c additive patch and compatibility receipts for G416."""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

SHADOW = ("shadow_court_x", "shadow_court_y", "shadow_status", "matrix_receipt",
          "source_receipt", "call_receipt", "would_violate_existing_guard")
OLD_READERS = (
    "g397_cards.py:1;g397_prepare.py:1;g397_report.py:1;g397_run.py:1;"
    "g399_prepare.py:1;g400_finish.py:1;g400_frames.py:1;g401_finish.py:2;"
    "g402_prepare.py:1;g402_retain.py:1;g404_finish.py:1;g406_measure.py:4;"
    "g406_seal.py:1;g407_report.py:2;g408_build.py:3;g410_measure.py:3;"
    "g410_render.py:2;g410_repeats.py:2;g410_sources.py:1;g411_extract.py:4;"
    "g411_run.py:1;g411_seal.py:2;g412_premise.py:4;g412_seal.py:1;"
    "g412_tables.py:1;g416_contract.py:22;g416_finish.py:26;g416_prepare.py:1"
)


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("proposal-anchor-not-unique")
    return text.replace(old, new)


def proposal_patch_text(root: Path) -> str:
    """Build an unapplied diff against the current archived writer path."""
    rel_tracker = "src/tracking/advanced_tracker.py"
    rel_pipe = "src/pipeline/unified_pipeline.py"
    tracker = (root / rel_tracker).read_text(encoding="utf-8")
    pipe = (root / rel_pipe).read_text(encoding="utf-8")
    tracker = _replace(tracker, '        p.previous_bb = det["bbox"]\n',
        '        p.previous_bb = det["bbox"]\n'
        '        for field in ("shadow_court_x", "shadow_court_y", "shadow_status",\n'
        '                      "matrix_receipt", "source_receipt", "call_receipt",\n'
        '                      "would_violate_existing_guard"):\n'
        '            setattr(p, field, det.get(field, "UNKNOWN"))\n'
        '        p._g416_shadow_timestamp = timestamp\n')
    tracker = _replace(tracker, '            head_x = (x1c + x2c) // 2\n            foot_y = y2c  # fallback: bbox bottom\n',
        '            head_x = (x1c + x2c) // 2\n            foot_y = y2c  # fallback: bbox bottom\n'
        '            shadow_route = "BOX"\n')
    tracker = _replace(tracker, '                if valid.any():\n                    foot_y = int(ankles_xy[valid, 1].mean())\n',
        '                if valid.any():\n                    shadow_route = "ANKLE"\n                    foot_y = int(ankles_xy[valid, 1].mean())\n')
    tracker = _replace(tracker, '            homo = np.int32(homo / homo[-1]).ravel()\n\n            if not (0 <= homo[0]',
        '            homo = np.int32(homo / homo[-1]).ravel()\n'
        '            shadow_homo = M1 @ (M @ kpt.reshape(3, 1))\n'
        '            shadow_homo = np.int32(shadow_homo / shadow_homo[-1]).ravel()\n'
        '            shadow_known = shadow_route == "BOX" and (0 <= shadow_homo[0] < map_2d.shape[1] and 0 <= shadow_homo[1] < map_2d.shape[0])\n'
        '            shadow_court_x = int(shadow_homo[0]) if shadow_known else "UNKNOWN"\n'
        '            shadow_court_y = int(shadow_homo[1]) if shadow_known else "UNKNOWN"\n'
        '            shadow_status = "PROPOSED" if shadow_known else "UNKNOWN"\n'
        '            matrix_receipt = "M1_AT_M_AT_KPT_ONE_NORMALIZATION_INT32" if shadow_known else "UNKNOWN"\n'
        '            source_receipt = "DETECTION_BOX" if shadow_known else "UNKNOWN"\n'
        '            call_receipt = "CURRENT_DETECTION_CALL" if shadow_known else "UNKNOWN"\n'
        '            would_violate_existing_guard = "UNKNOWN"\n\n            if not (0 <= homo[0]')
    tracker = _replace(tracker, '                "homo":      homo,\n                "color":     color_bgr,',
        '                "homo":      homo,\n'
        '                "shadow_court_x": shadow_court_x,\n'
        '                "shadow_court_y": shadow_court_y,\n'
        '                "shadow_status": shadow_status,\n'
        '                "matrix_receipt": matrix_receipt,\n'
        '                "source_receipt": source_receipt,\n'
        '                "call_receipt": call_receipt,\n'
        '                "would_violate_existing_guard": would_violate_existing_guard,\n'
        '                "color":     color_bgr,')
    pipe = _replace(pipe, '                slot     = self.players.index(p)\n                conf',
        '                slot     = self.players.index(p)\n'
        '                shadow_bound = getattr(p, "_g416_shadow_timestamp", None) == frame_idx\n'
        '                conf')
    pipe = _replace(pipe, '                    "bbox":             p.previous_bb,\n                    "x2d":',
        '                    "bbox":             p.previous_bb,\n'
        '                    "shadow_court_x": getattr(p, "shadow_court_x", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "shadow_court_y": getattr(p, "shadow_court_y", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "shadow_status": getattr(p, "shadow_status", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "matrix_receipt": getattr(p, "matrix_receipt", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "source_receipt": getattr(p, "source_receipt", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "call_receipt": getattr(p, "call_receipt", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "would_violate_existing_guard": getattr(p, "would_violate_existing_guard", "UNKNOWN") if shadow_bound else "UNKNOWN",\n'
        '                    "x2d":')
    pipe = _replace(pipe, '                    "bbox_y2":            bbox[2] if bbox else "",\n                    "ball_x2d":',
        '                    "bbox_y2":            bbox[2] if bbox else "",\n'
        '                    "shadow_court_x":   track.get("shadow_court_x", "UNKNOWN"),\n'
        '                    "shadow_court_y":   track.get("shadow_court_y", "UNKNOWN"),\n'
        '                    "shadow_status":     track.get("shadow_status", "UNKNOWN"),\n'
        '                    "matrix_receipt":    track.get("matrix_receipt", "UNKNOWN"),\n'
        '                    "source_receipt":    track.get("source_receipt", "UNKNOWN"),\n'
        '                    "call_receipt":      track.get("call_receipt", "UNKNOWN"),\n'
        '                    "would_violate_existing_guard": track.get("would_violate_existing_guard", "UNKNOWN"),\n'
        '                    "ball_x2d":')
    parts = []
    for before, after, rel in ((root / rel_tracker).read_text(encoding="utf-8"), tracker, rel_tracker), ((root / rel_pipe).read_text(encoding="utf-8"), pipe, rel_pipe):
        parts.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                          fromfile="a/" + rel, tofile="b/" + rel,
                                          lineterm=chr(10)))
    return "".join(parts).replace("+ " + chr(10), "+" + chr(10))


def restored_schema(original_fields: list[str], trace: list[str], matrix: list[str]) -> dict[str, object]:
    """Return the old parent namespaces followed by additive G416 fields."""
    return {"additive_fields": list(SHADOW), "g410_matrix": matrix,
            "g410_per_row": original_fields, "g410_trace": trace}


def restored_readers() -> list[dict[str, object]]:
    """Restore all prior reader rows, then append explicit output aliases."""
    rows = []
    for item in OLD_READERS.split(";"):
        name, hits = item.split(":")
        rows.append({"path": "scripts/platformkit/tracking/" + name, "field_hits": hits,
                     "reader_status": "PROPOSED_OR_TEST", "field_alias": ""})
    for path, alias in (("src/tracking/advanced_tracker.py", "detection_to_slot"),
                        ("src/pipeline/unified_pipeline.py", "slot_to_csv")):
        rows.append({"path": path, "field_hits": len(SHADOW), "reader_status": "PROPOSED_UNAPPLIED",
                     "field_alias": alias})
    return rows


def restoration_rows(original_fields: list[str]) -> list[dict[str, str]]:
    """List every compatibility item restored from the fix-1a baseline."""
    rows = [{"kind": "field", "item": "parent_schema.g410_per_row." + field,
             "restoration": "RESTORED"} for field in original_fields]
    rows += [{"kind": "field", "item": "replay_shadow_points.route", "restoration": "RESTORED"},
             {"kind": "field", "item": "summary.citations", "restoration": "RESTORED"},
             {"kind": "field", "item": "summary.original_retention", "restoration": "RESTORED"},
             {"kind": "status", "item": "bound_call_identity:UNKNOWN", "restoration": "RESTORED"},
             {"kind": "status", "item": "original_clamp_rows:DESCRIPTIVE", "restoration": "RESTORED"}]
    for row in restored_readers()[:28]:
        rows.append({"kind": "reader_row", "item": str(row["path"]), "restoration": "RESTORED"})
    return rows


def serializer_fixture() -> list[dict[str, object]]:
    """Isolated detection to slot to CSV fixture matching the proposal fields."""
    good = dict(zip(SHADOW, (133, 639, "PROPOSED", "M1_AT_M_AT_KPT_ONE_NORMALIZATION_INT32",
                             "DETECTION_BOX", "CURRENT_DETECTION_CALL", "UNKNOWN")))
    unknown = dict.fromkeys(SHADOW, "UNKNOWN")
    def row(route: str, detection: dict[str, object]) -> dict[str, object]:
        slot = {field: detection.get(field, "UNKNOWN") for field in SHADOW}
        emitted = {field: slot.get(field, "UNKNOWN") for field in SHADOW}
        return {"route": route, **emitted}
    return [row("BOX", good), row("ANKLE", unknown), row("FLOW", unknown),
            row("PREDICTION", unknown), row("RETAINED_POINT", unknown)]
