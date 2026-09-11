"""Preparation controls for the G407 rendition-boundary census."""
from __future__ import annotations

import hashlib
import json
import re
import csv
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g407_accounting import bounded_rows, window_counts
from scripts.platformkit.tracking.g407_observer import Observer, parent_schema_preserved, q6_scan
from scripts.platformkit.tracking.g407_cards import _opaque, _typed, scan_files
from scripts.platformkit.tracking.g407_census import fetch_receipts
from scripts.platformkit.tracking.g407_population import (
    actual_rendition, centered_interval, even_draw, fps_bucket, join_format_receipts,
)
from scripts.platformkit.tracking.g407_probe import cap_receipt
from scripts.platformkit.tracking.g407_report import draw_table, section_counts
from scripts.platformkit.tracking.g407_tables import (
    bind_rendition, boundary_split, class_summaries, fps_bin, held_share,
    itag_consistency, measured_class, stratum_counts,
)

EVIDENCE = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
            "g407_live_rendition_boundary_census_2026-09-11")


def _attempt(index: int, rendition: str = "232") -> dict[str, object]:
    return {"section_identity": "s%02d" % index, "source_sha256": "%064x" % index,
            "competition": "nba", "canonical_game": "g%02d" % index,
            "attempt_kind": "ORIGINAL", "terminal": True,
            "terminal_utc": "2026-09-11T00:%02d:00Z" % index,
            "attempt_id": "a%02d" % index, "actual_rendition": rendition}


def test_prereg_seal_normalizes_file_crlf_to_lf() -> None:
    prereg = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
              "g407_live_rendition_boundary_census_2026-09-11" / "prereg.md")
    text = prereg.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"\nSEAL sha256 ([0-9a-f]{64})\n?$", text)
    assert match is not None
    assert hashlib.sha256(text[:match.start() + 1].encode("utf-8")).hexdigest() == match.group(1)


def test_actual_format_is_distinct_from_requested_format() -> None:
    attempt = _attempt(1)
    attempt["requested_format_id"] = "301"
    receipt = {"section_identity": "s01", "source_sha256": "%064x" % 1,
               "actual_format_id": "232", "measured_width": 1280,
               "measured_height": 720, "measured_fps": "25"}
    joined = join_format_receipts([attempt], [receipt])
    assert joined[0]["requested_format_id"] == "301"
    assert joined[0]["actual_format_id"] == "232"
    assert joined[0]["actual_rendition"] == "232"


def test_232_at_25_has_its_own_native_rate_bin() -> None:
    assert fps_bucket("232", 25) == "25"
    assert fps_bucket("232", "29.97") == "29_31"
    assert fps_bucket("232", "") == "UNKNOWN"
    assert fps_bucket("301", 25) == "NOT_232"


def test_duplicate_sections_cannot_fill_a_30_unit_stratum() -> None:
    rows = [_attempt(index) for index in range(29)]
    duplicate = _attempt(28)
    duplicate["attempt_id"] = "later"
    rows.append(duplicate)
    assert even_draw(rows)["232"] == []


def test_even_draw_requires_no_replacement_and_bounds_total() -> None:
    rows = [_attempt(index) for index in range(30)]
    selected = even_draw(rows)
    assert len(selected["232"]) == 30
    assert selected["232"][0]["section_identity"] == "s00"
    assert selected["232"][-1]["section_identity"] == "s29"


def test_center_interval_selects_earlier_tied_native_pts() -> None:
    assert centered_interval([0.0, 2.0, 4.0, 6.0]) == (1.0, 3.0)
    with pytest.raises(ValueError, match="native-pts-required"):
        centered_interval([])


def test_overruns_stay_raw_and_are_excluded_from_derived_counts() -> None:
    rows = [{"source_frame": 10, "track_id": "a", "x": "1", "y": "2"},
            {"source_frame": 15, "track_id": "a", "x": "1", "y": "2"},
            {"source_frame": 20, "track_id": "a", "x": "1", "y": "2"}]
    sealed, overrun = bounded_rows(rows, 10, 20)
    assert [row["source_frame"] for row in sealed] == [10, 15]
    assert [row["source_frame"] for row in overrun] == [20]
    counts = window_counts([0.0] * 10, [10, 15, 20], [10, 15, 20], [], rows, 10, 20)
    assert counts["raw_overrun_rows"] == 1
    assert counts["derived_out_of_window_rows"] == 0
    assert counts["evaluated_ticks"] == 2


def test_silent_ticks_remain_in_named_evaluated_denominator() -> None:
    rows = [{"source_frame": 10, "track_id": "a", "x": "1", "y": "2"}]
    counts = window_counts([0.0, 0.1], [10, 15], [10, 15], [15], rows, 10, 20)
    assert counts["evaluated_ticks"] == 2
    assert counts["suspension_ticks"] == 1
    assert counts["zero_output_evaluated_ticks"] == 1


def test_observer_return_parity_and_parent_schema_are_additive() -> None:
    observer = Observer()
    original = ["same", "object"]
    assert observer.call("route", lambda: original) is original
    assert observer.trace == [{"label": "route", "return_type": "list"}]
    assert parent_schema_preserved({"ticks": 2}, {"ticks": 2, "observer": "ok"})
    assert not parent_schema_preserved({"ticks": 2}, {"ticks": 3})


def test_q6_scan_is_field_aware_and_never_returns_matches() -> None:
    forbidden = "".join(chr(code) for code in (100, 111, 108, 108, 97, 114))
    result = q6_scan([{"claim": forbidden, "identifier": forbidden}], {"claim"})
    assert result["fields_scanned"] == 1
    assert result["pattern_indices"] == [0]
    assert result["counts"] == {"0": 1}


def _measured(rendition: str = "270", width: int = 1280, height: int = 720,
              fps: float = 25.0, index: int = 1) -> dict[str, object]:
    row = _attempt(index)
    row.update({"requested_format_id": rendition, "measured_width": width,
                "measured_height": height, "measured_fps": fps,
                "pc_sha256": "%064x" % index, "digest_match": 1, "retained": 1})
    return row


def test_measured_class_uses_decoded_height_and_rate_not_a_label() -> None:
    assert measured_class(720, 29.97002997002997) == "720p30"
    assert measured_class(1080, "60000/1001") == "UNKNOWN"
    assert measured_class(1080, 59.94) == "1080p60"
    assert measured_class("", 30) == "UNKNOWN"
    assert fps_bin(25.0) == "25" and fps_bin(48.0) == "OTHER" and fps_bin(None) == "UNKNOWN"


def test_requested_itag_alone_never_binds_an_actual_rendition() -> None:
    fallback = bind_rendition(_measured("270", 1280, 720, 25.0))
    assert fallback["itag_consistency"] == "MISMATCH_RESOLUTION"
    assert fallback["actual_format_id"] == ""
    assert fallback["actual_rendition"] == "UNRESOLVED"
    assert fallback["format_join_status"] == "UNRESOLVED"
    assert fallback["measured_class"] == "720p25"
    requested_only = bind_rendition(_measured("232", 1280, 720, 30.0, 2))
    assert requested_only["actual_rendition"] == "UNRESOLVED"
    receipt = _measured("232", 1280, 720, 30.0, 3)
    receipt.update({"delivered_format_id": "232", "delivered_format_receipt_sha256": "%064x" % 3,
                    "delivered_format_source_sha256": receipt["pc_sha256"]})
    bound = bind_rendition(receipt)
    assert bound["actual_rendition"] == "232" and bound["format_join_status"] == "BOUND"


def test_itag_consistency_separates_resolution_and_rate_failures() -> None:
    assert itag_consistency("312", 1920, 1080, 30.0) == "MISMATCH_RATE"
    assert itag_consistency("312", 1920, 1080, 60.0) == "CONSISTENT"
    assert itag_consistency("bv*", 1280, 720, 30.0) == "UNKNOWN_ITAG"
    assert itag_consistency("270", 1920, 1080, "") == "UNKNOWN_MEASUREMENT"


def test_unresolved_residual_is_counted_and_never_promoted_to_a_rendition() -> None:
    rows = [bind_rendition(_measured("270", 1280, 720, 25.0, index)) for index in range(31)]
    strata = {row["stratum"]: row for row in stratum_counts(rows, "actual_rendition")}
    assert strata["UNRESOLVED"]["unique_retained_sections"] == 31
    assert strata["232"]["sections_in_window"] == 0
    assert strata["232"]["status"] == "PARTIAL"
    assert strata["UNRESOLVED"]["sections_receipt_bound"] == 0
    assert strata["UNRESOLVED"]["status"] == "PARTIAL" and strata["UNRESOLVED"]["quota_met"] == 0


def test_schedule_absent_is_unknown_and_residual_draw_uses_sealed_cap() -> None:
    trace = {"schedule_reason": "ball_table_absent", "evaluated_tick_ids": [],
             "suspended_tick_ids": [], "sealed_coordinate_rows": [],
             "sealed_window": {"sealed_start_frame": 0, "sealed_stop_frame": 0,
                               "sealed_source_frames": 0}}
    counts = section_counts({"_trace": trace})
    assert counts["schedule_status"] == "UNKNOWN"
    assert counts["schedule_reason"] == "ball_table_absent"
    assert all(counts[name] == "UNKNOWN" for name in (
        "attempted_reads", "evaluated_ticks", "suspension_ticks",
        "zero_output_evaluated_ticks", "held_pairs", "shared_pairs"))
    rows = [bind_rendition(_measured("232", 1280, 720, 30.0, index))
            for index in range(30)]
    drawn = draw_table(rows)
    assert all(row["status"] == "PARTIAL" for row in drawn if row["stratum"] == "UNRESOLVED")
    summaries = class_summaries(rows + [bind_rendition(_measured("270", 1280, 720, 25.0, 31))],
                                 [], [], [])
    assert all(row["quota_met"] == 0 for row in summaries
               if row["stratum"] in ("UNRESOLVED", "UNKNOWN"))
    assert all(row["status"] == "PARTIAL" for row in summaries
               if row["stratum"] in ("UNRESOLVED", "UNKNOWN"))
    assert "even_draw(eligible, QUOTA, 180)" in Path(
        "scripts/platformkit/tracking/g407_report.py").read_text(encoding="utf-8")


def test_empty_denominator_held_share_stays_unknown() -> None:
    assert held_share(0, 0) == "UNKNOWN"
    assert held_share(3, 4) == "0.750000"


def test_fixed_frame_cap_loses_half_the_target_at_sixty_native_frames() -> None:
    at_60 = cap_receipt([index / 60.0 for index in range(9000)], 60.0)
    at_30 = cap_receipt([index / 30.0 for index in range(3000)], 30.0)
    assert at_60["cap_status"] == "CAPPED" and at_60["cap_loss_over_5s"] == 1
    assert round(float(at_60["cap_loss_s"]), 3) == 50.0
    assert at_30["cap_loss_over_5s"] == 0 and float(at_30["cap_loss_s"]) == 0.0
    assert cap_receipt([], None)["cap_status"] == "UNKNOWN_NO_PTS"


def test_fetch_receipt_expands_one_video_line_into_section_identities(tmp_path) -> None:
    log = tmp_path / "feeder.log"
    log.write_text("2026-09-11T18:15:55Z FETCH start sport=basketball tag=cba Dys4JeucBBk "
                   "fmt=270 dur=7495s sections=2 offs=90,1533\n", encoding="utf-8")
    receipts = fetch_receipts(log)
    assert set(receipts) == {"cba-Dys4JeucBBk_s90", "cba-Dys4JeucBBk_s1533"}
    assert receipts["cba-Dys4JeucBBk_s90"]["requested_format_id"] == "270"


def test_boundary_split_names_every_activation_bucket() -> None:
    rows = [{"fetch_utc": "2026-09-11T19:00:00Z"}, {"fetch_utc": "2026-09-11T17:30:00Z"},
            {"fetch_utc": "2026-09-11T16:00:00Z"}, {"fetch_utc": ""}]
    counts = boundary_split(rows, "2026-09-11T17:01:52Z", "2026-09-11T18:56:17Z")
    assert counts == {"fetched_after_probe_aware_discovery": 1,
                      "fetched_after_232_first_selector": 1,
                      "fetched_before_both_boundaries": 1, "fetch_utc_UNKNOWN": 1}


def test_class_summary_keeps_unknown_out_of_every_numerator() -> None:
    receipt = _measured("232", 1280, 720, 30.0, 1)
    receipt.update({"delivered_format_id": "232", "delivered_format_receipt_sha256": "%064x" % 1,
                    "delivered_format_source_sha256": receipt["pc_sha256"]})
    rows = [bind_rendition(receipt)]
    held = [{"section_identity": "s01", "scope": "FULL_ADMITTED", "held_pairs": 2,
             "shared_pairs": 0, "zero_output_evaluated_ticks": 1, "schedule_status": "KNOWN"},
             {"section_identity": "s01", "scope": "SEALED_2S", "held_pairs": 1,
             "shared_pairs": "UNKNOWN", "zero_output_evaluated_ticks": 0,
             "schedule_status": "KNOWN"}]
    cover = [{"section_identity": "s01", "ledger_decoded_frames": 10,
              "producer_read_frames": 4, "evaluated_ticks": 3, "suspended_ticks": 1,
              "schedule_status": "KNOWN", "cap_loss_s": "UNKNOWN"}]
    entry = [row for row in class_summaries(rows, held, cover, [])
             if row["stratum"] == "232" and row["stratum_system"] == "actual_rendition"][0]
    assert entry["held_share_FULL_ADMITTED"] == "UNKNOWN"
    assert entry["shared_pairs_SEALED_2S"] == 0
    assert entry["cap_sections_measured"] == 0 and entry["cap_loss_s_min"] == "UNKNOWN"
    assert entry["quota_met"] == 0


def test_file_scan_exempts_typed_numbers_and_opaque_digests(tmp_path) -> None:
    assert _opaque("%064x" % 7) and not _opaque("abc")
    assert _typed("0.119") and _typed("%064x" % 7) and not _typed("tracked")
    (tmp_path / "t.csv").write_text("a,b\n0.119,tracked\n", encoding="utf-8")
    records = scan_files(tmp_path)
    assert records[0]["text"].split() == ["a", "b", "tracked"]


def test_delivered_evidence_reports_a_partial_supply_without_scoring_unknown_as_zero() -> None:
    summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    assert summary["derived_out_of_window_rows"] == 0
    assert summary["scratch_replay_launches"] == 0
    assert summary["sections_retained_off_pod"] == summary["sections_digest_match"]
    assert summary["sections_retained_off_pod"] == summary["sections_probe_agree"]
    assert summary["sections_reads_reconcile"] == 111
    assert summary["sections_reads_reconcile_unknown"] == 10
    with (EVIDENCE / "coverage.csv").open(newline="", encoding="utf-8") as handle:
        absent = [row for row in csv.DictReader(handle) if row["schedule_status"] == "UNKNOWN"]
    assert len(absent) == 10 and all(row["reads_reconcile"] == "UNKNOWN" for row in absent)
    assert all(row["schedule_reason"] == "ball_table_absent" for row in absent)
    assert all(row[name] == "UNKNOWN" for row in absent for name in (
        "producer_read_frames", "evaluated_ticks", "suspended_ticks",
        "ledger_evaluated_frames", "verdict_evaluated_frames", "verdict_attempted_frames_capped"))
    with (EVIDENCE / "window_counts.csv").open(newline="", encoding="utf-8") as handle:
        windows = [row for row in csv.DictReader(handle) if row["schedule_status"] == "UNKNOWN"]
    assert all(row["schedule_reason"] == "ball_table_absent" for row in windows)
    assert all(row[name] == "UNKNOWN" for row in windows for name in (
        "attempted_reads", "evaluated_ticks", "suspension_ticks",
        "zero_output_evaluated_ticks", "held_pairs", "shared_pairs"))
    assert summary["admitted_strata_partial"], "a short stratum must be named, never pooled"
    measured = [row for row in summary["strata"]
                if row["stratum_system"] == "measured_class" and row["stratum"] != "UNKNOWN"]
    assert measured and all(row["quota_met"] == 0 for row in measured)
    repeats = json.loads((EVIDENCE / "repeats.json").read_text(encoding="utf-8"))
    assert repeats["identical"] == 1 and len(repeats["runs"]) == 2
    assert all(run["returncode"] == 0 for run in repeats["runs"])
    scan = json.loads((EVIDENCE / "q6_scan.json").read_text(encoding="utf-8"))
    assert scan["non_opaque_hits"] == 0
