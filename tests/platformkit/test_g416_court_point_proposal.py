"""Correction tests for the sealed G416 additive court-point proposal."""
from __future__ import annotations

import csv
import hashlib
import inspect
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g416_contract import (
    DETECTOR_GUARD, PIPELINE_GUARD, additive_row, native_then_cropped_foot,
    project_m_then_m1, shadow_point,
)
from scripts.platformkit.tracking.g416_finish import control_rows
from scripts.platformkit.tracking.g416_fix1c import SHADOW, serializer_fixture
from scripts.platformkit.tracking.g416_oracle import independent_corner_oracle
from scripts.platformkit.tracking.g416_prepare import binding_census, premise_holds
from scripts.platformkit.tracking.g416_q6_scan import scan_text

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/tracking/g416_court_point_proposal_2026-09-12"


def rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_prereg_seal_is_unchanged() -> None:
    text = (OUT / "prereg.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"(^|\n)SEAL sha256 ([0-9a-f]{64})\n?$", text)
    assert match is not None
    assert hashlib.sha256(text[:match.start() + len(match.group(1))].encode()).hexdigest() == match.group(2)


def test_archived_chain_is_one_normalization_and_one_int32_cast() -> None:
    stored = (10, 20, 110, 220)
    foot = native_then_cropped_foot(stored, 1920, 1020)
    assert foot == (60, 205)
    m = (2, 0, 3, 0, 3, 4, 0, 0, 1)
    m1 = (1, 0, 10, 0, 1, 20, 0, 0, 1)
    # By hand: foot=(60,205), M@kpt=(123,619,1), M1@that=(133,639,1).
    assert project_m_then_m1(m, m1, foot) == (133, 639)
    kpt = np.array([60, 205, 1])
    archived = np.int32((np.array(m1).reshape(3, 3) @ (np.array(m).reshape(3, 3) @ kpt.reshape(3, 1))) /
                        (np.array(m1).reshape(3, 3) @ (np.array(m).reshape(3, 3) @ kpt.reshape(3, 1)))[-1]).ravel()
    assert tuple(archived[:2]) == (133, 639)


def test_oracle_is_separate_and_uses_no_proposal_helpers() -> None:
    source = inspect.getsource(__import__("scripts.platformkit.tracking.g416_oracle", fromlist=["*"]))
    assert "g416_contract" not in source
    assert "native_then_cropped_foot" not in source
    assert "project_m_then_m1" not in source
    identity = (1, 0, 0, 0, 1, 0, 0, 0, 1)
    assert independent_corner_oracle(identity, identity, (-16, -16, 110, 220), 1920, 1020) == (47, 205)


def test_all_32_controls_include_genuine_clip_for_each_size() -> None:
    controls = control_rows()
    assert len(controls) == 32
    assert len({tuple(row[key] for key in ("width", "height", "clipped", "matrix_valid", "receipt_bound", "box_present")) for row in controls}) == 32
    assert all(row["agree_or_unknown"] == "1" for row in controls)
    for width in (1920, 1280):
        clipped = [row for row in controls if row["width"] == width and row["clipped"] == 1 and row["box_present"] == 1]
        assert clipped and all(row["stored_x1"] == -16 for row in clipped)
        assert any(row["proposal_status"] == "PROPOSED" for row in clipped)


def test_binding_premise_and_full_279_row_deficit_census() -> None:
    census = binding_census(ROOT)
    assert premise_holds(census)
    deficit = rows("binding_deficits.csv")
    assert len(deficit) == 279
    assert {row["call_identity_present"] for row in deficit} == {"NO"}
    assert sum(row["sampled_row"] == "YES" for row in deficit) == 30
    assert len({(row["section_id"], row["frame"]) for row in deficit if row["sampled_row"] == "YES"}) == 30


def test_bound_detection_reproduction_is_explicit_and_honest() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    assert summary["bound_detection_rows_reproduced"] == "0/0"
    assert summary["archived_projection_lines"] == "advanced_tracker.py:1426-1428"
    assert summary["archived_tracker_sha256"] == "fa3b6db7dd180f1da5d12f962e95a9f052f3abdee3373c7c2dcade10cc7a1477"


def test_evidence_has_32_controls_30_cards_and_court_map_labels() -> None:
    assert len(rows("construct_cases.csv")) == 32
    eye = rows("eye_index.csv")
    assert len(eye) == 30
    assert {row["review_judgment"] for row in eye} == {"COURT_MAP_OLD_SHADOW_LABELLED"}
    assert all((OUT / row["render"]).exists() for row in eye)


def test_patch_is_valid_unapplied_and_byte_identical() -> None:
    proposal = ROOT / "docs/research/organization-sprint/PROPOSED_g416_court_point.diff"
    copy = OUT / proposal.name
    assert proposal.read_bytes() == copy.read_bytes()
    checked = subprocess.run(["git", "apply", "--check", str(proposal)], cwd=ROOT, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert "shadow_court_x" in proposal.read_text(encoding="utf-8")


def test_additive_unknown_preserves_parent_and_guards() -> None:
    parent = {"x_position": 7, "y_position": 9}
    point = shadow_point((7, 9), (10, 20, 110, 220), 1920, 1020, None, None, True, "ANKLE")
    result = additive_row(parent, point, "m", "s", "c")
    assert result["x_position"] == 7 and result["y_position"] == 9
    assert point.status == "UNKNOWN_NON_BOX_ROUTE"
    assert DETECTOR_GUARD == 250 and PIPELINE_GUARD == 350


def test_repeats_q6_and_ledger_cover_fix_1c_inputs() -> None:
    repeats = json.loads((OUT / "repeats.json").read_text(encoding="utf-8"))
    assert repeats["identical"] is True
    assert len(repeats["runs"]) == 2
    q6 = json.loads((OUT / "q6_scan.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in q6["paths"]}
    assert "docs/evidence/tracking/G416_VERIFY_fix1b_REJECT_2026-09-11.md" in paths
    assert "docs/evidence/tracking/RESULTS_LEDGER.md" in paths
    assert "scripts/platformkit/tracking/g416_finish.py" in paths
    assert "tests/platformkit/test_g416_court_point_proposal.py" in paths
    assert q6["shared_log_scan"]["classification"]["3"]["classification"] == "rows older than G416 = inherited context"
    assert bytes([13, 10]) not in (ROOT / "docs/evidence/tracking/RESULTS_LEDGER.md").read_bytes()
    fixture = "".join(chr(value) for value in (114, 111, 105))
    assert scan_text(fixture)[1] == 1


def test_serializer_fixture_carries_all_fields_and_unknown_routes() -> None:
    rows_fixture = serializer_fixture()
    assert tuple(rows_fixture[0][key] for key in SHADOW[:3]) == (133, 639, "PROPOSED")
    assert rows_fixture[0]["would_violate_existing_guard"] == "UNKNOWN"
    for row in rows_fixture[1:]:
        assert row["route"] in {"ANKLE", "FLOW", "PREDICTION", "RETAINED_POINT"}
        assert all(row[field] == "UNKNOWN" for field in SHADOW)
    patch = (OUT / "PROPOSED_g416_court_point.diff").read_text(encoding="utf-8")
    assert "p._g416_shadow_timestamp = timestamp" in patch
    assert "track.get(\"shadow_court_x\", \"UNKNOWN\")" in patch


def test_fix_1c_restores_all_parent_and_reader_compatibility_entries() -> None:
    schema = json.loads((OUT / "parent_schema.json").read_text(encoding="utf-8"))
    assert "g410_per_row" in schema and "draw_kind" in schema["g410_per_row"]
    assert set(SHADOW) <= set(schema["additive_fields"])
    manifest = rows("reader_manifest.csv")
    assert len(manifest) == 30
    assert all(row["field_alias"] == "" for row in manifest[:28])
    restored = rows("field_restoration.csv")
    assert sum(row["kind"] == "reader_row" for row in restored) == 28
    assert {row["item"] for row in restored if row["kind"] == "status"} == {
        "bound_call_identity:UNKNOWN", "original_clamp_rows:DESCRIPTIVE"}
