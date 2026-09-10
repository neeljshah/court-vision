"""G376 -- the three sealed controls, the NOT_SCHEDULED rule and the preregistration seal."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shlex
from pathlib import Path

from scripts.platformkit.tracking.g376_classify import CLASSES, classify_section, section_row
from scripts.platformkit.tracking.g376_controls import (
    reproduction_control, synthetic_controls, write_synthetic_section)
from scripts.platformkit.tracking.g376_schedule import reconstructed_schedule, section_facts
from scripts.platformkit.tracking import g376_m1, g376_report, g376_rerun

REPO = Path(__file__).resolve().parents[2]
PREREG = (REPO / "docs/evidence/tracking/g376_declared_tick_observations_2026-09-10"
          / "g376_prereg_2026-09-10.md")


def _record(ticks: int, stride: int = 3, **extra) -> dict:
    record = {"stride": stride, "evaluated_frames": ticks, "decoded_frames": ticks * stride,
              "rows": ticks, "seconds": 1, "source_fps": 30.0}
    record.update(extra)
    return record


def _facts(directory: Path, record: dict) -> dict:
    return section_facts(directory.name, "TEST", directory, record)


def test_control_b_fully_observed_and_control_c_doubled_declaration(tmp_path: Path) -> None:
    rows = synthetic_controls(tmp_path)
    failed = [row for row in rows if not row["passed"]]
    assert not failed, failed
    doubled = {row["quantity"]: row["observed"] for row in rows
               if row["control"] == "c_doubled_declaration"}
    assert doubled["not_scheduled_share"] == "0.500000"
    assert doubled["observed_share"] == "0.500000"


def test_control_a_absent_rerun_is_not_a_pass() -> None:
    assert reproduction_control({})[0]["passed"] == 0
    passing = reproduction_control({"reproduction": "1.000000", "symmetric_difference": 0})
    assert all(row["passed"] for row in passing)
    missed = reproduction_control({"reproduction": "0.998000", "symmetric_difference": 4})
    assert not any(row["passed"] for row in missed)


def test_tick_outside_the_reconstructed_schedule_is_not_scheduled(tmp_path: Path) -> None:
    section = write_synthetic_section(tmp_path / "sec", ticks=10, stride=3)
    facts = _facts(section, _record(14))          # four declared ticks past the evaluated set
    classes = dict((frame, name) for frame, name, _ in classify_section(facts))
    assert classes[27] == "OBSERVED"
    for frame in (30, 33, 36, 39):
        assert classes[frame] == "NOT_SCHEDULED"
    subs = {frame: sub for frame, _, sub in classify_section(facts) if frame >= 30}
    assert set(subs.values()) == {"GATED_OR_UNREACHED"}


def test_evaluated_frame_without_a_track_row_is_scheduled_no_detection(tmp_path: Path) -> None:
    section = write_synthetic_section(tmp_path / "sec", ticks=10, stride=3)
    rows = list(csv.reader((section / "tracking_data.csv").open(newline="", encoding="utf-8")))
    with (section / "tracking_data.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([rows[0]] + [r for r in rows[1:] if r[0] != "12"])
    facts = _facts(section, _record(10))
    classes = dict((frame, name) for frame, name, _ in classify_section(facts))
    assert classes[12] == "SCHEDULED_NO_DETECTION"
    assert classes[9] == "OBSERVED"


def test_suspended_frame_is_not_scheduled_with_its_own_sub_reason(tmp_path: Path) -> None:
    section = write_synthetic_section(tmp_path / "sec", ticks=10, stride=3)
    with (section / "ball_tracking.csv").open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([30, 1.0, "", "", 0, 0, 0])
    facts = _facts(section, _record(11))
    subs = {frame: sub for frame, name, sub in classify_section(facts) if name == "NOT_SCHEDULED"}
    assert subs == {30: "SUSPENDED"}


def test_absent_ball_table_makes_every_declared_tick_unknown(tmp_path: Path) -> None:
    section = write_synthetic_section(tmp_path / "sec", ticks=10, stride=3)
    (section / "ball_tracking.csv").unlink()
    assert reconstructed_schedule(section / "ball_tracking.csv")["reason"] == "ball_table_absent"
    facts = _facts(section, _record(10))
    names = {name for _, name, _ in classify_section(facts)}
    assert names == {"UNKNOWN"}
    assert section_row(facts, list(classify_section(facts)))["producer_evaluated_ticks"] == ""


def test_the_four_classes_partition_every_declared_tick(tmp_path: Path) -> None:
    section = write_synthetic_section(tmp_path / "sec", ticks=10, stride=3)
    with (section / "ball_tracking.csv").open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([30, 1.0, "", "", 0, 0, 0])
    facts = _facts(section, _record(15))
    ticks = list(classify_section(facts))
    row = section_row(facts, ticks)
    assert len(ticks) == row["declared_ticks"] == 15
    assert sum(row[name.lower()] for name in CLASSES) == 15
    assert len({frame for frame, _, _ in ticks}) == 15


def test_preregistration_seal_normalizes_crlf_to_lf() -> None:
    payload = PREREG.read_bytes().replace(b"\r\n", b"\n")
    before, seal = payload.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(before).hexdigest() == seal.strip().decode("ascii")


# --- AMENDMENT A1 (M1-corrected producer-evaluated denominator) -------------------------------

AMENDMENT = (REPO / "docs/evidence/tracking/g376_declared_tick_observations_2026-09-10"
             / "g376_amendment_A1_2026-09-10.md")


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _report_inputs(out: Path) -> None:
    """One section where the RAW and the M1 zero share differ by construction."""
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / "classification.csv", [{
        "section_id": "sec", "set": "TESTSET", "declared_ticks": 100,
        "producer_evaluated_ticks": 80, "route_capped_ticks": 100,
        "ledger_evaluated_frames": 100, "observed_ticks": 78, "observed": 78}])
    _write_csv(out / "m1_denominators.csv", [{
        "section_id": "sec", "set": "TESTSET", "declared_ticks": 100,
        "producer_evaluated_ticks": 80, "schedule_reason": "",
        "m1_observed_ticks_in_declared": 30, "m1_zero_ticks_over_declared": 70,
        "m1_zero_share_over_declared": "0.700000",
        "m1_observed_ticks_in_producer_evaluated": 40,
        "m1_zero_ticks_over_producer_evaluated": 40,
        "m1_zero_share_over_producer_evaluated": "0.500000"}])
    _write_csv(out / "ticks.csv", [{"section_id": "sec", "set": "TESTSET", "frame": frame,
                                    "tick_class": "OBSERVED", "sub_reason": ""}
                                   for frame in range(20)])
    (out / "classification_summary.json").write_text(json.dumps(
        {"per_set": {"TESTSET": {"shares": {"unknown": "0.000000"}}}}), encoding="utf-8")


def test_consequence_emits_the_raw_and_the_m1_share_when_they_differ(tmp_path: Path) -> None:
    """A1.1 and A1.2: both denominators ship, the RAW column keeps its name and its value."""
    _report_inputs(tmp_path)
    summary = g376_report.run(argparse.Namespace(out=str(tmp_path)))
    row = next(csv.DictReader((tmp_path / "consequence.csv").open(newline="", encoding="utf-8")))
    assert row["zero_share_over_producer_evaluated"] == "0.025000"      # RAW, (80 - 78) / 80
    assert row["m1_zero_share_over_producer_evaluated"] == "0.500000"   # M1, (80 - 40) / 80
    assert row["observed_ticks"] == "78"
    corrected = summary["per_set"]["TESTSET"]["corrected_denominators"]
    assert corrected["zero_share_over_producer_evaluated"] == "0.025000"
    assert corrected["m1_zero_share_over_producer_evaluated"] == "0.500000"
    assert corrected["m1_zero_ticks_over_producer_evaluated"] == 40
    assert corrected["g370_m1_zero_share_over_declared"] == "0.700000"
    assert "RAW" in summary["raw_column_semantics"]


def test_consequence_marks_the_m1_columns_absent_without_the_m1_artifact(tmp_path: Path) -> None:
    _report_inputs(tmp_path)
    (tmp_path / "m1_denominators.csv").unlink()
    g376_report.run(argparse.Namespace(out=str(tmp_path)))
    row = next(csv.DictReader((tmp_path / "consequence.csv").open(newline="", encoding="utf-8")))
    assert row["zero_share_over_producer_evaluated"] == "0.025000"
    assert all(row[field] == g376_m1.ABSENT for field in g376_m1.M1_FIELDS)


def test_m1_totals_sum_then_divide_and_skip_a_section_without_a_schedule() -> None:
    """A1.1: a section with no reconstructed schedule contributes to neither sum."""
    scored = [{"set": "S", "declared_ticks": 100, "producer_evaluated_ticks": 80,
               "m1_zero_ticks_over_producer_evaluated": 40, "m1_zero_ticks_over_declared": 70},
              {"set": "S", "declared_ticks": 100, "producer_evaluated_ticks": 20,
               "m1_zero_ticks_over_producer_evaluated": 20, "m1_zero_ticks_over_declared": 100},
              {"set": "S", "declared_ticks": 999, "producer_evaluated_ticks": g376_m1.ABSENT,
               "m1_zero_ticks_over_producer_evaluated": g376_m1.ABSENT,
               "m1_zero_ticks_over_declared": g376_m1.ABSENT}]
    totals = g376_m1.totals(scored)["S"]
    assert totals["m1_producer_evaluated_ticks"] == 100
    assert totals["m1_zero_ticks_over_producer_evaluated"] == 60
    assert totals["m1_zero_share_over_producer_evaluated"] == "0.600000"   # 60/100, not mean(.5,1)
    assert totals["sections_scored"] == 2 and totals["sections_without_schedule"] == 1
    assert totals["g370_declared_ticks"] == 200


def test_amendment_a1_seal_normalizes_crlf_to_lf() -> None:
    payload = AMENDMENT.read_bytes().replace(b"\r\n", b"\n")
    before, seal = payload.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(before).hexdigest() == seal.strip().decode("ascii")


RERUN_LOG = (REPO / "docs/evidence/tracking/g376_declared_tick_observations_2026-09-10"
             / "rerun_log.txt")


def test_the_recorded_rerun_command_is_accepted_by_its_own_parser() -> None:
    """The recorded command must be re-issuable: --log is required (g376_rerun.build_parser)."""
    line = next(text for text in RERUN_LOG.read_text(encoding="utf-8").splitlines()
                if text.startswith("command:"))
    argv = shlex.split(line.split(" -m scripts.platformkit.tracking.g376_rerun ", 1)[1])
    args = g376_rerun.build_parser().parse_args(argv)
    assert args.log and args.summary and args.frames == 3000
