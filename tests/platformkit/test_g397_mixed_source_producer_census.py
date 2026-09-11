"""Focused controls for the G397 preparation helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g397_census import cap_duration_seconds, classify_format
from scripts.platformkit.tracking.g397_tables import enrich_ledger, evaluated_tick_rows, held_pair_summary


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")


def test_cap_duration_preserves_native_30_and_60_fps() -> None:
    assert cap_duration_seconds(3000, 30.0) == 100.0
    assert cap_duration_seconds(3000, 60.0) == 50.0
    assert classify_format({"width": 1920, "height": 1080, "fps": 30}) == "1080p30"
    assert classify_format({"width": 1280, "height": 720, "fps": 60}) == "720p60"


def test_prereg_seal_uses_lf_normalized_file_bytes() -> None:
    prereg = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
              "g397_mixed_source_producer_census_2026-09-11" / "prereg.md")
    text = prereg.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"\nSEAL sha256 ([0-9a-f]{64})\n?$", text)
    assert match is not None
    above = re.sub(r"\nSEAL sha256 [0-9a-f]{64}\n?$", "\n", text)
    assert hashlib.sha256(above.encode("utf-8")).hexdigest() == match.group(1)


def test_non_emitting_evaluated_tick_remains_in_named_denominator(tmp_path: Path) -> None:
    ball, tracking = tmp_path / "ball.csv", tmp_path / "tracking.csv"
    _write(ball, "frame,live\n0,1\n3,1\n6,1\n")
    _write(tracking, "frame,player_id,x,y\n0,p1,1,2\n6,p1,1,2\n")
    rows, reason = evaluated_tick_rows(ball, tracking)
    assert reason == ""
    evaluated = [row for row in rows if row["state"] == "EVALUATED"]
    assert [row["frame"] for row in evaluated] == [0, 3, 6]
    assert evaluated[1]["emitting"] == 0


def test_missing_schedule_is_unknown(tmp_path: Path) -> None:
    tracking = tmp_path / "tracking.csv"
    _write(tracking, "frame,player_id,x,y\n0,p1,1,2\n")
    assert held_pair_summary(tmp_path / "absent_ball.csv", tracking) == {
        "status": "UNKNOWN", "reason": "ball_table_absent"}


def test_held_pairs_do_not_bridge_an_empty_evaluated_tick(tmp_path: Path) -> None:
    ball, tracking = tmp_path / "ball.csv", tmp_path / "tracking.csv"
    _write(ball, "frame,live\n0,1\n3,1\n6,1\n")
    _write(tracking, "frame,player_id,x,y\n0,p1,1.0,2.0\n6,p1,1.0,2.0\n")
    result = held_pair_summary(ball, tracking)
    assert result["held_pairs"] == 0
    assert result["shared_pairs"] == 0
    assert result["no_output_ticks"] == 1


def test_failure_rows_keep_fields_and_enrichment_is_immutable() -> None:
    original = {"attempt_id": "failed-1", "status": "FAILED", "source_height": ""}
    enriched = enrich_ledger([original], {})
    assert original == {"attempt_id": "failed-1", "status": "FAILED", "source_height": ""}
    assert enriched == [{"attempt_id": "failed-1", "status": "FAILED", "source_height": "",
                         "g397_join_status": "UNKNOWN", "g397_probe_width": None,
                         "g397_probe_height": None, "g397_probe_fps": None}]


def test_duplicate_attempts_are_not_silently_collapsed() -> None:
    with pytest.raises(ValueError, match="duplicate-attempt-id"):
        enrich_ledger([{"attempt_id": "same"}, {"attempt_id": "same"}], {})


def test_measured_classes_reject_the_off_rate_and_off_size_cases() -> None:
    from scripts.platformkit.tracking.g397_census import classify_format as classify
    assert classify({"width": 1280, "height": 720, "fps": 30}) == "OTHER"
    assert classify({"width": 1920, "height": 1080, "fps": 60}) == "OTHER"
    assert classify({"width": 1280, "height": 720, "fps": 59.940065028018545}) == "720p60"
    assert classify({"width": 1920, "height": 1080, "fps": None}) == "UNKNOWN"


def test_cap_duration_uses_the_measured_rate_not_a_nominal_one() -> None:
    assert round(cap_duration_seconds(3000, 59.940065028018545), 4) == 50.0500
    assert round(cap_duration_seconds(3000, 29.97), 4) == 100.1001


def test_frame_rate_rationals_are_parsed_and_zero_rate_is_unknown() -> None:
    from scripts.platformkit.tracking.g397_probe import rational
    assert rational("60000/1001") == pytest.approx(59.94005994005994)
    assert rational("30/1") == 30.0
    assert rational("0/0") is None
    assert rational("") is None


def test_held_pairs_use_the_producer_coordinate_columns(tmp_path: Path) -> None:
    ball, tracking = tmp_path / "ball.csv", tmp_path / "tracking.csv"
    _write(ball, "frame,live\n0,1\n3,1\n6,0\n")
    _write(tracking, "frame,player_id,x_position,y_position\n0,p1,22,1403\n3,p1,22,1403\n")
    result = held_pair_summary(ball, tracking)
    assert result["coordinate_columns"] == "x_position/y_position"
    assert result["held_pairs"] == 1 and result["shared_pairs"] == 1
    assert result["held_share"] == 1.0
    assert result["evaluated_ticks"] == 2


def test_suspended_frames_never_enter_the_evaluated_denominator(tmp_path: Path) -> None:
    ball, tracking = tmp_path / "ball.csv", tmp_path / "tracking.csv"
    _write(ball, "frame,live\n0,1\n3,0\n6,1\n")
    _write(tracking, "frame,player_id,x_position,y_position\n0,p1,1,2\n3,p1,1,2\n6,p1,1,2\n")
    rows, reason = evaluated_tick_rows(ball, tracking)
    assert reason == ""
    assert [r["frame"] for r in rows if r["state"] == "EVALUATED"] == [0, 6]
    assert [r["frame"] for r in rows if r["state"] == "SUSPENDED"] == [3]
    assert held_pair_summary(ball, tracking)["evaluated_ticks"] == 2


def test_enriched_copy_keeps_every_repeat_attempt_of_one_section() -> None:
    attempts = [{"attempt_id": "L1:s90", "game_id": "s90", "source_height": 1080},
                {"attempt_id": "L2:s90", "game_id": "s90", "source_height": 1080}]
    enriched = enrich_ledger(attempts, {"L2:s90": {"width": 1920, "height": 1080, "fps": 30}})
    assert [row["g397_join_status"] for row in enriched] == ["UNKNOWN", "MATCH"]
    assert [row["source_height"] for row in enriched] == [1080, 1080]
