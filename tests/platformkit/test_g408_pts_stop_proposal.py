"""Construct and measured checks for the G408 presentation-time stop proposal."""
import csv
import hashlib
import json
from pathlib import Path

from scripts.platformkit.tracking import g408_q6
from scripts.platformkit.tracking.g408_argv import fixtures, legacy_argv
from scripts.platformkit.tracking.g408_proposal import (
    caller_frame_cap,
    file_hashes,
    validate_proposed_diff,
)
from scripts.platformkit.tracking.g408_stop import (construct_cases,
                                                    replay_frame_cap,
                                                    replay_pts_prefetch,
                                                    replay_pts_stop)
from scripts.platformkit.tracking.g408_tables import arm_c_bar

ROOT = Path(".")
EVIDENCE = ROOT / "docs/evidence/tracking/g408_pts_duration_stop_proposal_2026-09-11"


def _rows(name):
    with (EVIDENCE / name).open(encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def test_prereg_seal_reads_file_and_normalizes_line_endings() -> None:
    prereg = (EVIDENCE / "prereg.md").read_bytes().decode("utf-8")
    normalized = prereg.replace("\r\n", "\n").replace("\r", "\n")
    prefix, seal = normalized.rsplit("SEAL sha256 ", 1)
    assert "\n" not in seal.strip()
    assert hashlib.sha256(prefix.encode("utf-8")).hexdigest() == seal.strip()


def test_duplicate_boundary_and_stride_refusal() -> None:
    receipt = replay_pts_stop([0.0, 1.0, 1.0, 99.999, 100.0, 101.0])
    assert receipt.admitted_indices == (0, 1, 2, 3)
    assert receipt.first_boundary_index == 4
    assert receipt.first_boundary_pts == 100.0
    assert receipt.reason == "DEADLINE"
    # No frame is counted as stride work unless it was admitted first.
    assert receipt.stride_work_count == len(receipt.admitted_indices)


def test_missing_backwards_and_eof_short_are_explicit() -> None:
    missing = replay_pts_stop([0.0, 1.0, None, 101.0])
    backward = replay_pts_stop([0.0, 2.0, 1.0, 101.0])
    infinite = replay_pts_stop([0.0, float("inf"), 101.0])
    short = replay_pts_stop([0.0, 1.0, 2.0])
    assert (missing.reason, missing.unknown_reason) == (
        "UNKNOWN", "missing_or_nonfinite_pts")
    assert (backward.reason, backward.unknown_reason) == (
        "UNKNOWN", "backwards_pts")
    assert (infinite.reason, infinite.unknown_reason) == (
        "UNKNOWN", "missing_or_nonfinite_pts")
    assert short.reason == "EOF_SHORT"


def test_skipped_anomalies_terminate_before_prefetch_stride_continue() -> None:
    missing = replay_pts_prefetch([0.0, None, 1.0], stride=2)
    backward = replay_pts_prefetch([0.0, 2.0, 1.0], stride=2)
    assert (missing.reason, missing.unknown_reason) == (
        "UNKNOWN", "missing_or_nonfinite_pts")
    assert (backward.reason, backward.unknown_reason) == (
        "UNKNOWN", "backwards_pts")
    assert missing.admitted_indices == (0,)


def test_explicit_cap_is_independent_earlier_limit() -> None:
    capped = replay_pts_stop([float(i) for i in range(200)],
                             explicit_frame_cap=3)
    default = replay_pts_stop([float(i) for i in range(200)])
    assert capped.reason == "FRAME_CAP"
    assert capped.admitted_indices == (0, 1, 2)
    assert default.reason == "DEADLINE"
    assert default.first_boundary_index == 100
    assert caller_frame_cap(None, None) == 3000
    assert caller_frame_cap(100.0, None) is None
    assert caller_frame_cap(100.0, 17) == 17


def test_explicit_cap_wins_a_deadline_tie_before_the_next_read() -> None:
    tied = replay_pts_stop([0.0, 100.0], explicit_frame_cap=1)
    assert tied.reason == "FRAME_CAP"
    assert tied.admitted_indices == (0,)
    assert tied.first_boundary_pts is None


def test_frame_cap_arm_records_its_own_boundary() -> None:
    receipt = replay_frame_cap([float(i) for i in range(10)], frame_cap=4)
    assert receipt.reason == "FRAME_CAP"
    assert receipt.admitted_indices == (0, 1, 2, 3)
    assert receipt.first_boundary_pts == 4.0
    assert replay_frame_cap([0.0, 1.0], frame_cap=9).reason == "EOF_SHORT"


def test_thirty_construct_cases_match_hand_declared_expectations() -> None:
    cases = construct_cases()
    assert len(cases) == 30
    assert len({row["case"] for row in cases}) == 30
    assert {row["kind"] for row in cases} == {
        "regular", "duplicate", "missing", "backward", "boundary_gap"}
    assert all(row["matches_declared"] for row in cases)
    # The exact-deadline frame is excluded in every kind that reaches it.
    exact = {row["kind"]: row for row in cases
             if row["endpoint"] == "exact_deadline"}
    assert exact["regular"]["expected_reason"] == "DEADLINE"
    assert 2 not in exact["regular"]["expected_admitted_indices"]


def test_delivered_controls_table_matches_the_module() -> None:
    delivered = _rows("construct_cases.csv")
    assert len(delivered) == 30
    assert all(row["matches_declared"] == "True" for row in delivered)


def test_argv_fixtures_keep_legacy_bytes_and_precedence() -> None:
    rows = {row["case"]: row for row in fixtures()}
    assert len(rows) == 11
    assert rows["legacy_no_duration"]["argv"] == legacy_argv(
        "python", "V", "G", "D")
    assert rows["legacy_no_duration"]["legacy_identical"] is True
    for case in ("fps_30", "fps_29_97", "fps_59_94", "fps_60", "fps_25",
                 "fps_unknown", "fps_variable", "short_source"):
        argv = rows[case]["argv"]
        assert "--duration-seconds" in argv
        assert "--frames" not in argv          # implicit 3000 is omitted
        assert rows[case]["deadline_depends_on_fps"] is False
    explicit = rows["explicit_frames_with_duration"]["argv"]
    assert explicit[explicit.index("--frames") + 1] == "900"
    assert "--duration-seconds" in explicit


def test_delivered_argv_fixtures_match_the_module() -> None:
    delivered = json.loads((EVIDENCE / "argv_fixtures.json").read_text())
    assert delivered["legacy_frame_cap"] == 3000
    assert delivered["cases"] == fixtures()


def test_thirty_source_denominator_is_immutable_and_matches_g401() -> None:
    draw = _rows("draw.csv")
    receipts = _rows("source_receipts.csv")
    assert len(draw) == len(receipts) == 30
    assert [row["source_name"] for row in draw] == [
        row["source_name"] for row in receipts]
    assert all(row["g401_digest_match"] == "True" for row in receipts)
    stops = _rows("paired_stops.csv")
    assert len(stops) == 90
    assert len({row["source_name"] for row in stops}) == 30


def test_restored_alias_columns_preserve_the_prior_schema() -> None:
    receipt_fields = set(_rows("source_receipts.csv")[0])
    prior_receipt_fields = set(_rows("pre_fix1b/source_receipts.csv")[0])
    index_fields = set(_rows("admitted_indices.csv")[0])
    prior_index_fields = set(_rows("pre_fix1b/admitted_indices.csv")[0])
    stop_fields = set(_rows("paired_stops.csv")[0])
    assert prior_receipt_fields <= receipt_fields
    assert prior_index_fields <= index_fields
    assert "endpoint_gap_s" in stop_fields


def test_premise_reproduces_the_landed_g401_paired_caps() -> None:
    landed = {row["source_name"]: row for row in csv.DictReader(
        (ROOT / "docs/evidence/tracking/g401_fps_cap_duration_shadow_2026-09-11"
              / "paired_caps.csv").open(encoding="ascii"))}
    arms = {}
    for row in _rows("paired_stops.csv"):
        arms.setdefault(row["source_name"], {})[row["arm"]] = row
    assert len(arms) == 30
    for name, by_arm in arms.items():
        a = by_arm["A_legacy_frame_cap_3000"]
        b = by_arm["B_g401_fps_frame_cap"]
        assert a["frame_cap"] == "3000"
        assert b["frame_cap"] == landed[name]["arm_b_frame_cap"]
        assert float(a["last_admitted_pts"]) == float(
            landed[name]["arm_a_last_admitted_pts"])
        assert float(b["first_excluded_pts"]) == float(
            landed[name]["arm_b_first_excluded_pts"])
    overshoot = arms["nba__1rZZ_7buX_Y_s5474.mp4"]["B_g401_fps_frame_cap"]
    assert float(overshoot["first_excluded_pts"]) == 100.088489


def test_measured_arm_c_contains_every_timeline_within_one_interval() -> None:
    stops = _rows("paired_stops.csv")
    bar = arm_c_bar(stops)
    assert bar["arm_c_n"] == 30
    assert bar["arm_c_containment_pass"] is True
    assert bar["arm_c_endpoint_pass"] is True
    assert bar["arm_c_inherited_unrounded_extent_n"] == 30
    assert bar["arm_c_unknown_n"] == 0
    arm_c = [row for row in stops if row["arm"] == "C_proposed_pts_stop"]
    # Never past the deadline: the gap is an undershoot on every timeline.
    assert all(float(row["last_admitted_gap_s"]) > 0 for row in arm_c)


def test_summary_records_the_inherited_and_measured_counts() -> None:
    summary = json.loads((EVIDENCE / "summary.json").read_text())
    assert summary["arm_a_reaching_target_n"] == 0
    assert summary["arm_b_reaching_target_n"] == 29
    assert summary["arm_c_inherited_unrounded_extent_n"] == 30
    assert summary["proposal_applied_anywhere"] is False
    assert summary["proposal_validation_errors"] == []
    assert summary["reproduced_by_two_fresh_processes"] is True
    assert summary["q6_non_opaque_hits"] == 0


def test_proposed_diff_and_current_base_hashes_are_staticly_ready() -> None:
    bases = file_hashes(ROOT)
    diff = (EVIDENCE / "PROPOSED_g408_pts_duration.diff").read_text(
        encoding="utf-8")
    assert validate_proposed_diff(diff, bases, ROOT) == []


def test_proposed_diff_checks_pts_before_any_detector_work() -> None:
    diff = (EVIDENCE / "PROPOSED_g408_pts_duration.diff").read_text(
        encoding="utf-8")
    # Timestamp validation is in the prefetcher before its stride continue.
    start = diff.index("target=self._decode_loop")
    prefetch = diff[start:diff.index("except Exception:", start)]
    added = "\n".join(line[1:] for line in prefetch.splitlines()
                      if line.startswith("+"))
    stride_continue = prefetch.rindex("continue")
    assert added.index("missing_or_nonfinite_pts") < stride_continue
    assert "not np.isfinite(_pts)" in added
    assert added.index("_pts >= self._pts_deadline") < stride_continue
    # The explicit cap is checked before a next PTS read, so a cap/deadline
    # tie is classified FRAME_CAP and cannot update the admitted endpoint.
    cap = diff.index("if self.max_frames and gameplay_frames >= self.max_frames")
    read = diff.index("ok, frame, _fi = _prefetcher.read()")
    assert cap < read
    # The proposal never derives the deadline from a frame rate.
    assert "self.duration_seconds" in diff
    assert "fps *" not in diff and "* fps" not in diff


def test_q6_patterns_fire_on_positives_and_ignore_typed_numbers() -> None:
    fixture_rows = g408_q6.positive_fixtures()
    assert len(fixture_rows) == 12
    assert all(row["fires_on_positive"] and row["silent_on_near_miss"]
               for row in fixture_rows)
    scan = json.loads((EVIDENCE / "q6_scan.json").read_text())
    assert scan["non_opaque_hit_count"] == 0
    assert scan["all_fixtures_pass"] is True
