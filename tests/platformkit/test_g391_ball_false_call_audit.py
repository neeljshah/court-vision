"""Prepare-only tests for G391's blind packet and causal-suppression rails."""
from __future__ import annotations

from pathlib import Path
import csv

import pytest

from scripts.platformkit.tracking.g391_prepare import (
    assert_all_states_survive,
    assert_packets_blind,
    assert_suppression_subset,
    freeze_packets,
    nearest_rank_p95,
    review_effect,
    shadow_decision,
    verify_preregistration,
)
from scripts.platformkit.tracking.g391_q6_scan import scan


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g391_ball_false_call_audit_2026-09-11/preregistration.md"


def _calls() -> list[dict[str, str]]:
    return [{"frame_key": "k%03d" % index, "game": "g%02d" % (index % 3),
             "section": "s%02d" % (index % 5), "frame_index": str(index),
             "native_path": "native/%03d.jpg" % index, "crop_path": "crop/%03d.jpg" % index}
            for index in range(60)]


def test_prereg_seal_reads_file_and_normalizes_crlf(tmp_path: Path):
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    crlf_copy = tmp_path / "preregistration.md"
    crlf_copy.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert verify_preregistration(PREREG) == verify_preregistration(crlf_copy)


def test_packets_are_opaque_deterministic_and_evenly_round_robin():
    first = freeze_packets(_calls())
    second = freeze_packets(list(reversed(_calls())))
    assert first == second
    assert len(first) == 60
    assert [packet["packet_id"] for packet in first[:30]] != [packet["packet_id"] for packet in first[30:]]
    assert_packets_blind(first)
    with pytest.raises(ValueError, match="packet-source-exposes-hidden-field"):
        freeze_packets([{**row, "label": "VISIBLE"} for row in _calls()])


def test_false_visible_call_includes_fn_and_unknown_fp_is_retained():
    assert review_effect("VISIBLE", True) == {"false_call": 1, "false_negative": 1, "unknown_retained": 0}
    assert review_effect("UNKNOWN", True) == {"false_call": 1, "false_negative": 0, "unknown_retained": 1}


def test_missing_history_passes_raw_and_confirmed_no_detection_suppresses():
    p95 = nearest_rank_p95(list(range(30)))
    assert p95 == 28
    assert shadow_decision([], p95) == "RETAINED_MISSING_HISTORY"
    no_detection = [{"seconds_before": 0.1, "availability": "PRESENT", "observation": "NO_DETECTION"},
                    {"seconds_before": 0.2, "availability": "PRESENT", "observation": "OBSERVED", "speed": 1}]
    assert shadow_decision(no_detection, p95) == "SUPPRESSED_CONFIRMED_NO_DETECTION"
    assert shadow_decision([], None) == "RETAINED_INSUFFICIENT_DEV"


def test_suppression_cannot_create_tp_and_every_state_survives():
    assert_suppression_subset(["a", "b"], ["a"])
    assert_all_states_survive(["a", "b", "c"], ["c", "b", "a"])
    with pytest.raises(ValueError, match="suppression-created-call"):
        assert_suppression_subset(["a"], ["a", "b"])
    with pytest.raises(ValueError, match="state-denominator-drop"):
        assert_all_states_survive(["a", "b"], ["a"])


def test_q6_scan_covers_text_artifacts_with_constructed_patterns(tmp_path: Path):
    clean = tmp_path / "clean.txt"
    clean.write_text("prepare-only calibration audit\n", encoding="ascii")
    assert scan([clean]) == {}
    flagged = tmp_path / "flagged.txt"
    flagged.write_text("a " + "".join(chr(code) for code in (101, 100, 103, 101)), encoding="ascii")
    assert str(flagged).replace("\\", "/") in scan([flagged])


from scripts.platformkit.tracking import g391_finish, g391_rate, g391_reproduce


def test_independent_scorer_reproduces_the_landed_g390_counts():
    rows, summary = g391_reproduce.score(ROOT)
    assert (summary["n_states"], summary["n_calls"]) == (549, 259)
    assert (summary["tp"], summary["fp"], summary["fn_visible_without_tp"]) == (90, 169, 212)
    assert len({row["frame_key"] for row in rows}) == 549


def test_suppression_cannot_lift_coverage_over_its_own_bar():
    limit = g391_reproduce.ceiling(ROOT)
    assert limit["suppression_cannot_add_tp"] and limit["all_549_states_survive"]
    oracle = [p for p in limit["probes"]
              if p["probe"] == "oracle_suppress_every_false_call"][0]
    assert (oracle["tp"], oracle["fp"]) == (90, 0)
    assert oracle["bars"]["coverage_c0_ge_0.25"] is False


def test_rater_parser_drops_an_invented_or_out_of_frame_ball(tmp_path: Path):
    raw = tmp_path / "batch.txt"
    ids = ["G391-001-" + "a" * 16, "G391-002-" + "b" * 16, "G391-003-" + "c" * 16]
    raw.write_text(
        ids[0] + ",CROWD,NO_BALL_VISIBLE,,,,LOW,stands behind the bench\n"
        + ids[1] + ",BALL,BALL_AT_MARKER,9000,300,30,LOW,off frame\n"
        + ids[2] + ",BALL,BALL_ELSEWHERE,,,,LOW,no centre given\n", encoding="ascii")
    rows = g391_rate.parse_batch(raw, "terra", ids)
    assert [row["packet_id"] for row in rows] == [ids[0]]


def test_audit_classes_separate_a_reference_dispute_from_a_near_miss():
    assert g391_finish.audit_class("BALL", "BALL_AT_MARKER", "VISIBLE") == "NEAR_MISS_LOCALISATION"
    assert g391_finish.audit_class("BALL", "BALL_AT_MARKER", "ABSENT") == "SUSPECTED_REFERENCE_ERROR"
    assert g391_finish.audit_class("BALL", "BALL_ELSEWHERE", "ABSENT") == "DUPLICATE_OR_SECOND_BALL"
    assert g391_finish.audit_class("UNKNOWN", "BALL_UNCERTAIN", "UNKNOWN") == "UNCERTAIN_REFERENCE_OR_PIXELS"
    assert g391_finish.audit_class("BALL", "BALL_UNCERTAIN", "ABSENT") == "UNCERTAIN_REFERENCE_OR_PIXELS"
    assert g391_finish.audit_class("CROWD", "BALL_UNCERTAIN", "ABSENT") == "BACKGROUND_CONFUSION_CROWD"
    assert g391_finish.audit_class("CROWD", "NO_BALL_VISIBLE", "ABSENT") == "BACKGROUND_CONFUSION_CROWD"


def test_timeline_index_has_sealed_even_ordinals_and_missing_prior_slots():
    index = ROOT / "docs/evidence/tracking/g391_ball_false_call_audit_2026-09-11/timeline_index.csv"
    rows = list(csv.DictReader(index.open(encoding="ascii", newline="")))
    assert (len(rows) == 30 and [int(row["ordinal"]) for row in rows] == [k * 549 // 30 for k in range(30)] and all(row["prior_minus_2"] == row["prior_minus_1"] == "MISSING" for row in rows))
