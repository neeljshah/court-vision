from pathlib import Path

import pytest

from scripts.platformkit.tracking.g403_contract import (
    RoundStatus,
    answer_status,
    binding_issues,
    overall_round_status,
    retain_centre_gaps,
)
from scripts.platformkit.tracking.g403_controls import (
    VISIBLE_SCENES,
    build_control_catalogue,
    validate_native_bindings,
)
from scripts.platformkit.tracking.g403_prereg import asserted_prereg_seal, verify_prereg_seal
from scripts.platformkit.tracking import g403_build, g403_package


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11/prereg.md"


def test_g403_prereg_seal_uses_file_bytes_with_crlf_normalization(tmp_path: Path):
    assert verify_prereg_seal(PREREG)
    crlf_copy = tmp_path / "prereg-crlf.md"
    crlf_copy.write_bytes(PREREG.read_bytes().replace(b"\n", b"\r\n"))
    assert verify_prereg_seal(crlf_copy)
    assert asserted_prereg_seal(crlf_copy) == asserted_prereg_seal(PREREG)


def test_g403_audit_legacy_statuses_and_final_states_are_additive():
    audit = g403_build.EVIDENCE / "shot_claim_audit.csv"
    states = g403_package.final_states(g403_build.g400_dir())
    statuses = g403_package.settled_labels(g403_build.g400_dir())
    with audit.open(encoding="utf-8", newline="") as handle:
        rows = list(__import__("csv").DictReader(handle))
    with (audit.parent / "pre_fix1b/shot_claim_audit.csv").open(encoding="utf-8", newline="") as handle:
        original = {row["frame_key"]: row["settled_label"] for row in __import__("csv").DictReader(handle)}
    assert len(rows) == 30
    assert all(row["settled_label"] == statuses[row["frame_key"]] for row in rows)
    assert all(row["settled_label"] == original[row["frame_key"]] for row in rows)
    assert all(row["final_state"] == states[row["frame_key"]] for row in rows)


def test_g403_preserves_label_and_geometry_and_reports_binding_failures():
    status = answer_status("VISIBLE", (20, 20, 20, 40))
    assert status.label_status == "VALID_LABEL"
    assert status.box_status == "INVALID_GEOMETRY"
    missing = answer_status("", None)
    assert missing.label_status == "MISSING_LABEL"
    assert missing.box_status == "INVALID_GEOMETRY"
    assert binding_issues(("k1", "k2", "k3"), ("k1", "k1", "k4")) == {
        "duplicate_ids": ["k1"], "missing_ids": ["k2", "k3"], "unexpected_ids": ["k4"],
    }


def test_g403_pooled_pass_cannot_erase_failed_or_incomplete_round():
    rounds = [RoundStatus("r1", 29, 29, True), RoundStatus("r8", 30, 30, False)]
    assert overall_round_status(rounds) == "FAILED"
    assert overall_round_status([RoundStatus("r1", 28, 29, True)]) == "INCOMPLETE"
    assert overall_round_status([RoundStatus("r1", 29, 29, True)]) == "DONE"


def test_g403_retains_every_raw_gap_and_binds_native_control_catalogue():
    pairs = [{"frame_key": "k%03d" % index, "left_cx": index, "left_cy": 0,
              "right_cx": index + 3, "right_cy": 4} for index in range(125)]
    retained = retain_centre_gaps(pairs)
    assert len(retained) == 125
    assert all(row["gap_px"] == pytest.approx(5.0) for row in retained)

    cases = build_control_catalogue()
    validate_native_bindings(cases)
    assert len(cases) == 30
    assert len([case for case in cases if case.expected_state == "VISIBLE"]) == 20
    assert {case.scene for case in cases if case.expected_state == "VISIBLE"} == VISIBLE_SCENES
    assert all(case.sheet_scale == 1.0 for case in cases)


def _rows(name: str):
    import csv
    path = ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11" / name
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _summary():
    import json
    path = ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11/summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_g403_premise_reproduces_every_landed_g400_count():
    summary = _summary()
    assert summary["premise_measured"] == summary["premise_expected"]
    assert summary["premise_all_match"] == 1
    assert len(_rows("answer_binding.csv")) == 600
    assert len(_rows("gaps.csv")) == 125
    assert sum(1 for row in _rows("diameter_population.csv") if row["usable"] == "1") == 288


def test_g403_invalid_coordinate_is_one_answer_kept_and_excluded_from_diameters():
    invalid = [row for row in _rows("diameter_population.csv") if row["usable"] == "0"]
    assert len(invalid) == 1
    assert invalid[0]["exclusion"] == "CENTRE_OUTSIDE_NATIVE_FRAME"
    assert float(invalid[0]["cx"]) > float(invalid[0]["width"])
    assert invalid[0]["rater"] and invalid[0]["archive"].endswith(".txt")
    binding = [row for row in _rows("answer_binding.csv") if row["frame_key"] == invalid[0]["frame_key"]]
    kept = [row for row in binding if row["in_native_frame"] == "0" and row["label"] == "VISIBLE"]
    assert len(kept) == 1 and kept[0]["label_status"] == "VALID_LABEL" and kept[0]["box_status"] == "VALID_BOX"


def test_g403_round8_is_the_only_round_with_a_binding_slip_signature():
    rounds = {int(row["round"]): row for row in _rows("binding_offset.csv")}
    assert int(rounds[8]["slipped"]) > int(rounds[8]["aligned"])
    assert [key for key, row in rounds.items() if row["lead_exceeds_same"] == "1"] == [8]
    others = [row for key, row in rounds.items() if key != 8]
    assert sum(int(row["slipped"]) for row in others) < sum(int(row["aligned"]) for row in others)
    assert int(rounds[8]["strict_lead_match"]) > sum(int(row["strict_lead_match"]) for row in others)


def test_g403_taxonomy_and_shot_audit_keep_their_denominators():
    reasons = _rows("reason_categories.csv")
    assert len(reasons) == 115
    from scripts.platformkit.tracking.g403_diagnose import CATEGORIES
    assert all(row["object_category"] in CATEGORIES for row in reasons)
    audit = _rows("shot_claim_audit.csv")
    assert len(audit) == 30
    assert {row["play_state"] for row in audit} <= {"PLAY", "NON_PLAY", "UNCLASSIFIED"}
    assert sum(1 for row in audit if row["play_state"] == "UNCLASSIFIED") >= 1
    summary = _summary()
    assert summary["shot_audit_non_play_share"] < summary["g400_state_label_non_play_share"]


def test_g403_control_package_is_answer_bound_and_slip_detectable():
    catalogue, answers = _rows("control_catalogue.csv"), _rows("control_answers.csv")
    assert len(catalogue) == 30 and len(answers) == 30
    assert [row["case_id"] for row in catalogue] == [row["case_id"] for row in answers]
    assert all(row["sheet_scale"] == "1.0" for row in catalogue)
    assert sum(1 for row in answers if row["expected_state"] == "VISIBLE") == 20
    keys = [(row["expected_state"], row["expected_cx"], row["expected_cy"]) for row in answers]
    assert all(keys[i] != keys[i + 1] for i in range(len(keys) - 1))
    assert _summary()["consecutive_controls_distinguishable"] == 1


def test_g403_instruction_and_amendment_seals_verify_from_file_bytes():
    base = ROOT / "docs/evidence/tracking/g403_ball_rater_failure_controls_2026-09-11"
    for name in ("instructions.md", "amendment_A1.md"):
        assert verify_prereg_seal(base / name)
    text = (base / "instructions.md").read_text(encoding="utf-8")
    assert "max(3 px, diameter_720p / 2)" in text and "sheet_scale` 1.0" in text
    assert "BINDING_FAULT" in text
