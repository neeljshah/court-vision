"""Tests for the G411 exact integer-PTS extent audit and its measured tables."""
import csv
import json
from fractions import Fraction
from pathlib import Path

from scripts.platformkit.tracking import (g411_measure, g411_prepare, g411_q6,
                                          g411_rational, g411_rows, g411_run)

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "docs/evidence/tracking/g411_integer_pts_extent_audit_2026-09-12"
G408 = ROOT / "docs/evidence/tracking/g408_pts_duration_stop_proposal_2026-09-11"


def _rows(name):
    with (EV / name).open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _summary():
    return json.loads((EV / "summary.json").read_text())


def test_rational_boundary_and_first_excluded_are_distinct() -> None:
    receipt = g411_rational.replay_integer_pts([0, 5999, 6000], "1/60")
    assert receipt.admitted_indices == (0, 1)
    assert receipt.last_admitted_index == 1
    assert receipt.first_excluded_index == 2
    assert receipt.reason == "DEADLINE"
    assert g411_rational.within_inherited_bar(Fraction(6000, 60), "60/1")


def test_decimal_serialization_loss_is_visible_without_manufacturing_pts() -> None:
    exact = g411_rational.pts_to_seconds(3003, "1/30000")
    archived = g411_rational.decimal_text_to_fraction("0.100100")
    assert exact == Fraction(1001, 10000)
    assert archived == Fraction(1001, 10000)
    assert g411_rational.decimal_text_to_fraction("0.100") != exact


def test_gap_missing_backwards_and_stride_are_explicit() -> None:
    missing = g411_rational.replay_integer_pts([0, None, 100], "1/1", stride=2)
    backward = g411_rational.replay_integer_pts([0, 3, 2], "1/1")
    skipped_boundary = g411_rational.replay_integer_pts([0, 1, 100], "1/1", stride=2)
    assert missing.reason == "UNKNOWN" and missing.unknown_reason == "missing_pts"
    assert backward.reason == "UNKNOWN" and backward.unknown_reason == "backwards_pts"
    assert skipped_boundary.reason == "DEADLINE"
    assert skipped_boundary.first_excluded_index == 2


def test_prereg_seal_reads_file_and_normalizes_line_endings() -> None:
    prereg = ROOT / g411_prepare.PREREG
    assert g411_prepare.prereg_seal_is_valid(prereg)
    crlf_copy = Path(str(prereg) + ".test-copy")
    try:
        crlf_copy.write_bytes(prereg.read_bytes().replace(b"\n", b"\r\n"))
        assert g411_prepare.prereg_seal_is_valid(crlf_copy)
    finally:
        crlf_copy.unlink(missing_ok=True)


def test_prepare_inventory_and_code_built_q6_fixtures() -> None:
    inventory = g411_prepare.preparation_inventory(ROOT)
    assert inventory["mode"] == "PREPARE_ONLY"
    assert inventory["missing_paths"] == []
    fixtures = g411_q6.positive_fixtures()
    assert len(fixtures) == len(g411_q6.PATTERNS)
    assert all(row["fires_on_positive"] and row["silent_on_near_miss"]
               for row in fixtures)


def test_inherited_bar_is_the_unrounded_one_native_interval() -> None:
    assert g411_measure.bar("60.0") == Fraction(1, 60)
    exact = Fraction(5999, 60)
    # Exactly on the bar passes; the archived six-decimal render does not.
    assert g411_measure.within_bar(exact, "60.0") is True
    assert g411_measure.within_bar(Fraction("99.983333"), "60.0") is False
    assert abs(exact - Fraction("99.983333")) == Fraction(1, 3000000)


def test_first_excluded_and_last_admitted_differ_on_the_same_stream() -> None:
    receipt = g411_measure.rational_schedule_endpoints(
        [0, 1500, 3000, 9000000], Fraction(1, 90000), None, Fraction(1, 60))
    assert receipt["termination_reason"] == "DEADLINE"
    assert receipt["first_boundary_extent"] == Fraction(100, 1)
    assert receipt["last_admitted_extent"] == Fraction(3000, 90000)


def test_short_source_stays_eof_counted() -> None:
    receipt = g411_measure.rational_schedule_endpoints(
        [0, 1500, 3000], Fraction(1, 90000), None, Fraction(1, 60))
    assert receipt["termination_reason"] == "EOF_SHORT"
    assert receipt["first_excluded_index"] is None
    assert receipt["first_boundary_extent"] == Fraction(3000, 90000) + Fraction(1, 60)


def test_malformed_and_missing_units_stay_unknown_without_an_endpoint() -> None:
    for schedule in ([0, None, 3000], [0, 3000, 1500]):
        receipt = g411_measure.rational_schedule_endpoints(
            schedule, Fraction(1, 90000), None, Fraction(1, 60))
        assert receipt["termination_reason"] == "UNKNOWN"
        assert receipt["first_boundary_extent"] is None


def test_quantization_jitter_is_not_an_anomaly_but_a_drop_is() -> None:
    steady = [0, 1502, 3003, 4505, 6006, 7508]
    assert not [row for row in g411_measure.anomalies(steady)
                if row["kind"] == "off_grid_step"]
    dropped = steady + [7508 + 3004]
    assert [row for row in g411_measure.anomalies(dropped)
            if row["kind"] == "off_grid_step"]
    assert g411_measure.anomalies([0, 1502, 1502])[0]["kind"] == "duplicate_pts"


def test_construct_grid_matches_hand_declared_expectations() -> None:
    cases = g411_measure.construct_cases("1/90000", 1500)
    assert len(cases) == len(g411_measure.CONSTRUCT_KINDS)
    assert all(row["matches_declared"] for row in cases)
    delivered = _rows("construct_cases.csv")
    assert delivered and all(row["matches_declared"] == "True"
                             for row in delivered)


def test_measured_premise_reproduces_the_g408_counts() -> None:
    summary = _summary()
    assert summary["draw_n"] == 30 and summary["arm_c_n"] == 30
    assert summary["premise_float_contained_n"] == 30
    assert summary["premise_float_first_excluded_pass_n"] == 30
    assert summary["premise_float_last_admitted_pass_n"] == 26
    assert summary["premise_float_row_matches_g408_n"] == 30
    marginal = summary["premise_marginal_cases"]
    assert len(marginal) == 4
    assert all(row["excess_s"] == "0.000000333333" for row in marginal)


def test_measured_rational_extent_passes_without_moving_the_bar() -> None:
    summary = _summary()
    assert summary["rational_arm_c_contained_n"] == 30
    assert summary["rational_arm_c_first_excluded_pass_n"] == 30
    assert summary["rational_arm_c_last_admitted_pass_n"] == 30
    assert summary["rational_arm_c_unknown_n"] == 0
    assert summary["bar_moved"] is False and summary["epsilon_added"] is False
    assert summary["g408_historical_verdict_unchanged"] is True


def test_measured_bar_changes_are_all_serialization_and_named() -> None:
    summary = _summary()
    assert summary["bar_outcome_changes_n"] == 8
    assert summary["bar_outcome_changes_explained_by_serialization_n"] == 8
    rows = _rows("marginal_cases.csv")
    assert len(rows) == 8
    assert {row["endpoint_definition"] for row in rows} == {"last_admitted"}
    assert {row["rational_extent_exact"] for row in rows} == {"5999/60"}
    assert all(row["float_within_bar"] == "False"
               and row["rational_within_bar"] == "True" for row in rows)


def test_measured_readers_agree_on_every_retained_source() -> None:
    rows = _rows("source_receipts.csv")
    assert len(rows) == 30
    assert all(row["status"] == "OK" for row in rows)
    assert all(row["digest_matches_draw"] == "True" for row in rows)
    assert all(row["time_base_agree"] == "True" for row in rows)
    assert all(row["reader_multiset_agree"] == "True" for row in rows)
    assert all(int(row["missing_pts_count"]) == 0 for row in rows)


def test_measured_decimal_stream_reproduces_from_the_integers() -> None:
    assert _summary()["serialization_mismatch_sources_n"] == 0
    rows = [row for row in _rows("stream_join.csv") if row["frame_index"] == "-1"]
    assert len(rows) == 30
    assert all(row["serialization_matches"] == "True" for row in rows)


def test_delivered_tables_reproduce_and_the_scan_is_clean() -> None:
    repeats = json.loads((EV / "repeats.json").read_text())
    assert repeats["identical"] is True
    assert len(repeats["runs"]) == 2
    assert all(run["returncode"] == 0 and run["identical"]
               for run in repeats["runs"])
    scan = json.loads((EV / "q6_scan.json").read_text())
    assert scan["non_opaque_hit_count"] == 0
    assert scan["all_fixtures_pass"] is True
    assert scan["scanned_count"] >= 60


def test_g408_parent_header_is_a_subset_of_the_g411_header() -> None:
    from scripts.platformkit.tracking import g408_tables, g411_run
    missing = [name for name in g408_tables.STOP_FIELDS
               if name not in g411_run.STOP_FIELDS]
    assert missing == []
    rows = _rows("paired_stops.csv")
    assert rows and all(name in rows[0] for name in g408_tables.STOP_FIELDS)
    for row in rows:
        if row["termination_reason"] != "UNKNOWN":
            assert row["span_s"] == row["last_admitted_extent_s"]
            assert row["endpoint_gap_s"] == row["last_admitted_gap_s"]


def test_all_90_parent_fields_keep_their_g408_meanings() -> None:
    from scripts.platformkit.tracking import g408_tables
    parent = {(row["source_name"], row["arm"]): row for row in
              _csv_rows(G408 / "paired_stops.csv")}
    candidate = _rows("paired_stops.csv")
    assert len(parent) == len(candidate) == 90
    for row in candidate:
        prior = parent[(row["source_name"], row["arm"])]
        for field in g408_tables.STOP_FIELDS:
            assert g411_run._parent_same(field, prior[field], row[field])
    audit = _rows("parent_field_audit.csv")
    assert len(audit) == len(g408_tables.STOP_FIELDS)
    assert all(row["identical_meaning"] == "yes" and
               row["rows_differing_of_90"] == "0" for row in audit)


def test_parent_stop_fields_handle_nonzero_origin_and_unknown() -> None:
    from scripts.platformkit.tracking import g408_tables
    native = {"time_base": "1/1"}
    parent_nonzero = g408_tables.arm_rows("nonzero", 0, [50, 149, 150], 1)[2]
    rat = g411_measure.rational_schedule_endpoints(
        [50, 149, 150], Fraction(1, 1), None, Fraction(1, 1))
    row = g411_rows.stop_row("nonzero", parent_nonzero["arm"], parent_nonzero,
                             rat, "1", native, 3, "0")
    assert (row["read_frames"], row["deadline_s"], row["contained"],
            row["deadline_from_origin_s"], row["boundary_reached"]) == (
                3, "150.000000000000", True, "100", True)
    for field in g408_tables.STOP_FIELDS:
        assert g411_run._parent_same(field, str(parent_nonzero[field]), row[field])
    cases = (([50, None], "missing_pts"),
             ([50, 51, 50], "backwards_pts"),
             ([50, 51, 52], None))
    for index, (schedule, alias) in enumerate(cases):
        parent = g408_tables.arm_rows("malformed", index, schedule, 1)[2]
        rat = g411_measure.rational_schedule_endpoints(
            schedule, Fraction(1, 1), None, Fraction(1, 1))
        candidate = g411_rows.stop_row("malformed", parent["arm"], parent,
                                       rat, "1", native, len(schedule), str(index))
        for field in g408_tables.STOP_FIELDS:
            assert g411_run._parent_same(field, str(parent[field]), candidate[field])
        assert candidate["unknown_reason_g411"] == alias


def test_empty_schedule_keeps_every_parent_stop_field() -> None:
    from scripts.platformkit.tracking import g408_stop, g408_tables
    parent_receipt = g408_stop.replay_pts_stop([])
    parent = g408_tables.arm_rows("empty", 0, [], 1)[2]
    rat = g411_measure.rational_schedule_endpoints(
        [], Fraction(1, 1), None, Fraction(1, 1))
    candidate = g411_rows.stop_row("empty", parent["arm"], parent, rat, "1",
                                   {"time_base": "1/1"}, 0, "0")
    assert (parent_receipt.reason, parent_receipt.unknown_reason) == (
        "EOF_SHORT", "start_outside_schedule")
    for field in g408_tables.STOP_FIELDS:
        assert g411_run._parent_same(field, str(parent[field]), candidate[field])
    assert candidate["unknown_reason_g411"] is None


def _csv_rows(path: Path) -> list:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))
